
import logging
import uvicorn
import os
import contextlib

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCard, AgentCapabilities, AgentSkill
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.responses import JSONResponse

from src.shared.service_discovery import register_self_with_gra
from .executor import ReformulatorAgentExecutor

AGENT_NAME = "ReformulatorAgentServer"
logger = logging.getLogger(__name__)
if not logger.hasHandlers():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

def get_reformulator_agent_card() -> AgentCard:
    """
    Crée et retourne la "carte d'agent" pour notre ReformulatorAgent.
    """
    capabilities = AgentCapabilities(streaming=False)
    
    reformulation_skill = AgentSkill(
        id="reformulation",
        name="Reformulate Objective",
        description="Reformulates a given objective text according to predefined rules.",
        tags=["text processing", "reformulation", "planning"],
        examples=["Reformulate: plan a meeting for tomorrow"]
    )
    
    agent_url = os.environ.get("PUBLIC_URL", f"http://localhost_placeholder_for_{AGENT_NAME}:8080")
     
    agent_card = AgentCard(
        name="Simple Reformulator Agent",
        description="An A2A agent that reformulates objectives.",
        url=agent_url,
        version="0.1.0",
        capabilities=capabilities,
        defaultInputModes=["application/json"],
        defaultOutputModes=["application/json"],
        skills=[reformulation_skill]
    )
    logger.info(f"Agent Card créée: {agent_card.name}")
    return agent_card

@contextlib.asynccontextmanager
async def lifespan(app_param: Starlette):
    logger.info(f"[{AGENT_NAME}] Démarrage du cycle de vie (lifespan)...")
    
    agent_public_url = os.environ.get("PUBLIC_URL")
    agent_internal_url = os.environ.get("INTERNAL_URL")
    
    if agent_public_url and agent_internal_url:
        try:
            agent_card = get_reformulator_agent_card()
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
    agent_executor = ReformulatorAgentExecutor()
    task_store = InMemoryTaskStore()
    request_handler = DefaultRequestHandler(agent_executor=agent_executor, task_store=task_store)
    
    agent_card = get_reformulator_agent_card()
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