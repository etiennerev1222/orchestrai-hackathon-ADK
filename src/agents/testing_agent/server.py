# src/agents/testing_agent/server.py
import logging
import uvicorn
import contextlib
import os

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCard, AgentCapabilities, AgentSkill
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.responses import JSONResponse

from src.shared.service_discovery import register_self_with_gra
from .executor import TestingAgentExecutor
from .logic import AGENT_SKILL_SOFTWARE_TESTING, AGENT_SKILL_TEST_CASE_GENERATION

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

AGENT_NAME = "TestingAgentServer"

def get_testing_agent_card() -> AgentCard:
    capabilities = AgentCapabilities(streaming=False)
    skills_objects = [
        AgentSkill(
            id=AGENT_SKILL_SOFTWARE_TESTING,
            name="Software Testing and Validation",
            description="Tests software deliverables against specifications and acceptance criteria.",
            tags=["testing", "qa", "validation", "software_engineering"],
            examples=[
                '{"objective": "Test login function", "deliverable": "<code>...", "acceptance_criteria": ["User can login with valid credentials"]}'
            ]
        ),
        AgentSkill(
            id=AGENT_SKILL_TEST_CASE_GENERATION,
            name="Test Case Generation",
            description="Generates test cases based on software specifications.",
            tags=["testing", "qa", "planning"],
            examples=[
                '{"objective": "Generate test cases for user registration"}'
            ]
        )
    ]
    # On utilise l'URL si elle existe, sinon on met une valeur temporaire.
    agent_url = os.environ.get("PUBLIC_URL", f"http://localhost_placeholder_for_{AGENT_NAME}:8080")
     
    return AgentCard(
        name="Software Testing Agent",
        description="Agent specialized in testing software and generating test reports.",
        url=agent_url,
        version="0.1.0",
        defaultInputModes=["application/json"],
        defaultOutputModes=["application/json"],
        capabilities=capabilities,
        skills=skills_objects
    )

agent_executor = TestingAgentExecutor()
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
            agent_card = get_testing_agent_card()
            skill_ids = [skill.id for skill in agent_card.skills] if agent_card.skills else []
            logger.info(f"[{AGENT_NAME}] URLs détectées. Tentative d'enregistrement avec les compétences : {skill_ids}")
            await register_self_with_gra(AGENT_NAME, agent_public_url, agent_internal_url, skill_ids)
        except Exception as e:
            logger.error(f"[{AGENT_NAME}] L'enregistrement auprès du GRA a échoué durant le démarrage : {e}", exc_info=True)
    else:
        logger.warning(f"[{AGENT_NAME}] PUBLIC_URL ou INTERNAL_URL manquant. Le serveur démarre en mode passif sans s'enregistrer.")

    yield
    
    logger.info(f"[{AGENT_NAME}] Serveur en cours d'arrêt.")


# --- Création de l'application Starlette ---
def create_app_instance() -> Starlette:
    agent_card = get_testing_agent_card()
    a2a_app = A2AStarletteApplication(agent_card=agent_card, http_handler=request_handler)
    app = a2a_app.build()

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