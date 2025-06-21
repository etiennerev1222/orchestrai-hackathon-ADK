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

# --- 1. Import du nouveau handler ---
from src.shared.log_handler import InMemoryLogHandler

from src.shared.service_discovery import get_gra_base_url, register_self_with_gra
from .executor import UserInteractionAgentExecutor
from .logic import ACTION_CLARIFY_OBJECTIVE

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- 2. Initialisation et configuration du logging ---
in_memory_log_handler = InMemoryLogHandler(maxlen=200)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
in_memory_log_handler.setFormatter(formatter)
logging.getLogger().addHandler(in_memory_log_handler)
logging.getLogger().setLevel(logging.INFO)

AGENT_NAME = "UserInteractionAgentServer"

def get_user_interaction_agent_card() -> AgentCard:
    """
    Crée et retourne la "carte d'agent".
    """
    agent_url = os.environ.get("PUBLIC_URL", f"http://localhost_placeholder_for_{AGENT_NAME}:8080")

    capabilities = AgentCapabilities(streaming=False, push_notifications=False)
    
    skills_objects = [
        AgentSkill(
            id=ACTION_CLARIFY_OBJECTIVE,
            name="Clarify User Objective",
            description="Interacts with the user to clarify an initial objective...",
            tags=["user_interaction", "clarification", "dialogue"],
            examples=[
                '{"action": "clarify_objective", "raw_objective": "Plan a holiday."}'
            ]
        )
    ]

    agent_card = AgentCard(
        name="User Interaction Agent",
        description="An A2A agent that handles direct interactions with the user...",
        url=agent_url,
        version="0.1.0",
        defaultInputModes=["application/json"],
        defaultOutputModes=["application/json"],
        capabilities=capabilities,
        skills=skills_objects
    )
    logger.info(f"Agent Card créée: {agent_card.name} accessible à l'URL : {agent_card.url}")
    return agent_card

agent_executor = UserInteractionAgentExecutor()
task_store = InMemoryTaskStore()
request_handler = DefaultRequestHandler(agent_executor=agent_executor, task_store=task_store)

# --- 3. Création de l'endpoint /logs ---
async def logs_endpoint(request):
    """Retourne les dernières lignes de log de l'agent."""
    return JSONResponse(content=in_memory_log_handler.get_logs())

async def restart_endpoint(request):
    """Arrête le processus pour forcer un redémarrage de l'agent."""
    logger.warning(f"[{AGENT_NAME}] Restart requested via /restart")
    asyncio.get_event_loop().call_later(0.1, os._exit, 0)
    return JSONResponse({"status": "restarting"})

@contextlib.asynccontextmanager
async def lifespan(app_param: Starlette):
    logger.info(f"[{AGENT_NAME}] Démarrage du cycle de vie (lifespan)...")
    
    agent_public_url = os.environ.get("PUBLIC_URL")
    agent_internal_url = os.environ.get("INTERNAL_URL")
    
    if agent_public_url and agent_internal_url:
        try:
            agent_card = get_user_interaction_agent_card()
            skill_ids = [skill.id for skill in agent_card.skills] if agent_card.skills else []
            logger.info(f"[{AGENT_NAME}] URLs détectées. Tentative d'enregistrement avec les compétences : {skill_ids}")
            await register_self_with_gra(AGENT_NAME, agent_public_url, agent_internal_url, skill_ids)
            await agent_executor._notify_gra_of_status_change()
        except Exception as e:
            logger.error(f"[{AGENT_NAME}] L'enregistrement auprès du GRA a échoué durant le démarrage : {e}", exc_info=True)
    else:
        logger.warning(f"[{AGENT_NAME}] PUBLIC_URL ou INTERNAL_URL manquant. Le serveur démarre en mode passif sans s'enregistrer.")

    yield
    
    logger.info(f"[{AGENT_NAME}] Serveur en cours d'arrêt.")

def create_app_instance() -> Starlette:
    agent_card = get_user_interaction_agent_card()
    a2a_app = A2AStarletteApplication(agent_card=agent_card, http_handler=request_handler)
    app = a2a_app.build()

    async def health_check_endpoint(request):
        return JSONResponse({"status": "ok"})
    async def status_endpoint(request):
        """Retourne le statut opérationnel détaillé de l'agent."""
        if not agent_executor:
            return JSONResponse({"state": "Error", "message": "Executor not initialized"}, status_code=500)
        return JSONResponse(agent_executor.get_status())
    
    app.router.routes.append(
        Route("/health", endpoint=health_check_endpoint, methods=["GET"])
    )
    app.router.routes.append(
        Route("/status", endpoint=status_endpoint, methods=["GET"])
    )

    # --- 4. Ajout de la nouvelle route ---
    app.router.routes.append(
        Route("/logs", endpoint=logs_endpoint, methods=["GET"])
    )
    app.router.routes.append(
        Route("/restart", endpoint=restart_endpoint, methods=["POST"])
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