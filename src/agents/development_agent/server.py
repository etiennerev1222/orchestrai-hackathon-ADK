import asyncio
import contextlib
import logging
import os
import uvicorn

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from starlette.routing import Route
from starlette.applications import Starlette

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCard, AgentCapabilities, AgentSkill

from src.shared.log_handler import InMemoryLogHandler
from src.shared.service_discovery import register_self_with_gra
from src.shared.stats_utils import increment_agent_restart

from .executor import DevelopmentAgentExecutor

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

AGENT_NAME = os.environ.get("AGENT_NAME", "DevelopmentAgentGKEv2")

in_memory_log_handler = InMemoryLogHandler(maxlen=200)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
in_memory_log_handler.setFormatter(formatter)
logging.getLogger().addHandler(in_memory_log_handler)
logging.getLogger().setLevel(logging.INFO)


def get_agent_card() -> AgentCard:
    agent_url = os.environ.get("PUBLIC_URL") or os.environ.get("INTERNAL_URL") or f"http://{AGENT_NAME}.default.svc.cluster.local:8080"
    capabilities = AgentCapabilities(streaming=False)
    skill = AgentSkill(
    id="coding_python",
    name="Python Code Generation",
    description="Generates Python code and writes it to a shared volume",
    tags=["python", "code", "generation"]  # 👈 obligatoire avec Pydantic v2
)
    return AgentCard(
        name="Development Agent GKEv2",
        description="A Kubernetes-native version of the Development Agent specialized in code generation and execution.",
        url=agent_url,
        version="2.0.0",
        defaultInputModes=["application/json"],
        defaultOutputModes=["text/plain"],
        capabilities=capabilities,
        skills=[skill],
    )


agent_executor = DevelopmentAgentExecutor()
task_store = InMemoryTaskStore()
request_handler = DefaultRequestHandler(agent_executor=agent_executor, task_store=task_store)


async def logs_endpoint(request):
    return JSONResponse(in_memory_log_handler.get_logs())

async def restart_endpoint(request):
    logger.warning(f"[{AGENT_NAME}] Restart requested via /restart")
    increment_agent_restart(AGENT_NAME)
    asyncio.get_event_loop().call_later(0.1, os._exit, 0)
    return JSONResponse({"status": "restarting"})

@contextlib.asynccontextmanager
async def lifespan(app: Starlette):
    # --- DÉBUT BLOC DE DÉBOGAGE ---
    logger.info("--- [DEBUG] DÉBUT DU LIFESPAN ---")
    public_url = os.environ.get("PUBLIC_URL")
    internal_url = os.environ.get("INTERNAL_URL")
    logger.info(f"--- [DEBUG] PUBLIC_URL lue depuis l'environnement : '{public_url}'")
    logger.info(f"--- [DEBUG] INTERNAL_URL lue depuis l'environnement : '{internal_url}'")
    # --- FIN BLOC DE DÉBOGAGE ---

    if public_url and internal_url:
        logger.info("--- [DEBUG] Condition 'if public_url and internal_url' est VRAIE. Tentative d'enregistrement...")
        try:
            card = get_agent_card()
            skills = [s.id for s in card.skills]
            await register_self_with_gra(AGENT_NAME, public_url, internal_url, skills)
            await agent_executor._notify_gra_of_status_change()
        except Exception as e:
            logger.error(f"--- [DEBUG] L'enregistrement avec le GRA a échoué : {e}", exc_info=True)
    else:
        logger.warning("--- [DEBUG] Condition 'if public_url and internal_url' est FAUSSE. Enregistrement ignoré.")
    
    yield
    
    logger.info(f"--- [DEBUG] FIN DU LIFESPAN ---")


def create_app() -> FastAPI:
    card = get_agent_card()
    a2a_app = A2AStarletteApplication(agent_card=card, http_handler=request_handler)
    starlette_app = a2a_app.build()

    async def status_endpoint(request):
        return JSONResponse(agent_executor.get_status())
    async def health_check_endpoint(request):
        return JSONResponse({"status": "ok"})

    starlette_app.router.routes.append(Route("/health", endpoint=health_check_endpoint, methods=["GET"]))
    starlette_app.router.routes.append(Route("/status", endpoint=status_endpoint, methods=["GET"]))
    starlette_app.router.routes.append(Route("/logs", endpoint=logs_endpoint, methods=["GET"]))
    starlette_app.router.routes.append(Route("/restart", endpoint=restart_endpoint, methods=["POST"]))
    starlette_app.router.lifespan_context = lifespan

    app = FastAPI()
    app.mount("/", starlette_app)
    return app


app = create_app()
app.router.lifespan_context = lifespan  

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    logger.info(f"Starting {AGENT_NAME} on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
