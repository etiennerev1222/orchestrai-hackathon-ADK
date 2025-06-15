import asyncio
import logging
import uvicorn
import httpx
import contextlib
import os

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCard, AgentCapabilities, AgentSkill
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.responses import JSONResponse

from src.shared.service_discovery import get_gra_base_url, register_self_with_gra
from .executor import DecompositionAgentExecutor
from .logic import AGENT_SKILL_DECOMPOSE_EXECUTION_PLAN

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

AGENT_NAME = "DecompositionAgentServer"
AGENT_SKILLS_LIST = [AGENT_SKILL_DECOMPOSE_EXECUTION_PLAN]

def get_decomposition_agent_card() -> AgentCard:
    capabilities = AgentCapabilities(streaming=False)
    skill_obj = AgentSkill(
        id=AGENT_SKILL_DECOMPOSE_EXECUTION_PLAN,
        name="Decompose Execution Plan",
        description="Decomposes a high-level textual plan into a structured list of execution tasks for the execution Team1 (JSON).",
        tags=["planning", "decomposition", "execution_setup"],
        examples=["Decompose this plan: [Text of TEAM 1's validated plan]"]
    )
    agent_url = os.environ.get("PUBLIC_URL", f"http://localhost_placeholder_for_{AGENT_NAME}:8080")
    
    return AgentCard(
        name="Execution Plan Decomposition Agent",
        description="Agent that takes a validated plan text and breaks it down into structured execution tasks.",
        url=agent_url,
        version="0.1.0",
        defaultInputModes=["text/plain"],
        defaultOutputModes=["application/json"],
        capabilities=capabilities,
        skills=[skill_obj]
    )


agent_executor = DecompositionAgentExecutor()
task_store = InMemoryTaskStore()
request_handler = DefaultRequestHandler(agent_executor=agent_executor, task_store=task_store)

@contextlib.asynccontextmanager
async def lifespan(app_param: Starlette):
    """
    Logique de démarrage et d'arrêt du serveur.
    Tente d'enregistrer l'agent si les URLs sont disponibles, sinon attend passivement.
    """
    logger.info(f"[{AGENT_NAME}] Démarrage du cycle de vie (lifespan)...")
    
    agent_public_url = os.environ.get("PUBLIC_URL")
    agent_internal_url = os.environ.get("INTERNAL_URL")
    
    if agent_public_url and agent_internal_url:
        try:
            agent_card = get_decomposition_agent_card()
            skill_ids = [skill.id for skill in agent_card.skills] if agent_card.skills else []
            logger.info(f"[{AGENT_NAME}] URLs détectées. Tentative d'enregistrement avec les compétences : {skill_ids}")
            await register_self_with_gra(AGENT_NAME, agent_public_url, agent_internal_url, skill_ids)
        except Exception as e:
            logger.error(f"[{AGENT_NAME}] L'enregistrement auprès du GRA a échoué durant le démarrage : {e}", exc_info=True)
    else:
        logger.warning(f"[{AGENT_NAME}] PUBLIC_URL ou INTERNAL_URL manquant. Le serveur démarre en mode passif sans s'enregistrer.")

    yield
    
    logger.info(f"[{AGENT_NAME}] Serveur en cours d'arrêt.")


def create_app_instance() -> Starlette:
    agent_card = get_decomposition_agent_card()
    a2a_app = A2AStarletteApplication(agent_card=agent_card, http_handler=request_handler)
    app = a2a_app.build()

    async def health_check_endpoint(request):
        return JSONResponse({"status": "ok"})
    
    app.router.routes.append(
        Route("/health", endpoint=health_check_endpoint, methods=["GET"])
    )
    
    app.router.lifespan_context = lifespan
    
    return app

app = create_app_instance()

if __name__ == "__main__":
    is_production = 'K_SERVICE' in os.environ
    port = int(os.environ.get("PORT", 8080))
    host = "0.0.0.0" if is_production else "localhost"
    
    logger.info(f"Démarrage du serveur Uvicorn pour {AGENT_NAME} sur {host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="info")