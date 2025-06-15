# src/agents/development_agent/server.py
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
from .executor import DevelopmentAgentExecutor
from .logic import AGENT_SKILL_CODING_PYTHON

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

AGENT_NAME = "DevelopmentAgentServer"

def get_development_agent_card() -> AgentCard:
    agent_url = os.environ.get("PUBLIC_URL", f"http://localhost_placeholder_for_{AGENT_NAME}:8080")
    
    capabilities = AgentCapabilities(streaming=False)
    skills_objects = [
        AgentSkill(
            id=AGENT_SKILL_CODING_PYTHON,
            name="Python Code Generation",
            description="Generates Python code based on specifications.",
            tags=["coding", "python", "development", "software_engineering"],
            examples=[
                '{"objective": "Create a function to sum two numbers", "local_instructions": ["Must handle integers and floats"], "acceptance_criteria": ["Returns 5 for inputs 2 and 3"]}'
            ]
        ),
    ]
    
    return AgentCard(
        name="Software Development Agent",
        description="Agent specialized in writing and modifying source code.",
        url=agent_url,
        version="0.1.0",
        defaultInputModes=["application/json"],
        defaultOutputModes=["text/plain"],
        capabilities=capabilities,
        skills=skills_objects
    )

agent_executor = DevelopmentAgentExecutor()
task_store = InMemoryTaskStore()
request_handler = DefaultRequestHandler(agent_executor=agent_executor, task_store=task_store)

# MODIFIÉ : La fonction lifespan est maintenant résiliente
@contextlib.asynccontextmanager
async def lifespan(app_param: Starlette):
    logger.info(f"[{AGENT_NAME}] Démarrage du cycle de vie (lifespan)...")
    
    agent_public_url = os.environ.get("PUBLIC_URL")
    agent_internal_url = os.environ.get("INTERNAL_URL")
    
    if agent_public_url and agent_internal_url:
        try:
            agent_card = get_development_agent_card()
            skill_ids = [skill.id for skill in agent_card.skills] if agent_card.skills else []
            logger.info(f"[{AGENT_NAME}] URLs détectées. Tentative d'enregistrement avec les compétences : {skill_ids}")
            await register_self_with_gra(AGENT_NAME, agent_public_url, agent_internal_url, skill_ids)
        except Exception as e:
            logger.error(f"[{AGENT_NAME}] L'enregistrement auprès du GRA a échoué durant le démarrage : {e}", exc_info=True)
    else:
        logger.warning(f"[{AGENT_NAME}] PUBLIC_URL ou INTERNAL_URL manquant. Le serveur démarre en mode passif sans s'enregistrer.")

    yield
    
    logger.info(f"[{AGENT_NAME}] Serveur en cours d'arrêt.")

# --- Création de l'application ---
def create_app_instance() -> Starlette:
    agent_card = get_development_agent_card()
    a2a_app = A2AStarletteApplication(agent_card=agent_card, http_handler=request_handler)
    app = a2a_app.build()

    logger.info(f"Routes enregistrées après a2a_app.build(): {[str(r.path) + ' (' + str(r.methods) + ')' for r in app.router.routes]}")

    async def health_check_endpoint(request):
        return JSONResponse({"status": "ok"})
    
    app.router.routes.append(
        Route("/health", endpoint=health_check_endpoint, methods=["GET"])
    )
    
    # Attacher le gestionnaire de cycle de vie
    app.router.lifespan_context = lifespan
    
    return app

app = create_app_instance()

# --- MODIFIÉ : Démarrage Uvicorn compatible Cloud Run ---
if __name__ == "__main__":
    is_production = 'K_SERVICE' in os.environ
    port = int(os.environ.get("PORT", 8080)) # Port par défaut 8080 pour les agents
    host = "0.0.0.0" if is_production else "localhost"
    
    logger.info(f"Démarrage du serveur Uvicorn pour {AGENT_NAME} sur {host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="info")