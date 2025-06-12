# src/agents/testing_agent/server.py
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

from src.shared.service_discovery import get_gra_base_url, register_self_with_gra
from .executor import TestingAgentExecutor
from .logic import AGENT_SKILL_SOFTWARE_TESTING, AGENT_SKILL_TEST_CASE_GENERATION

logger = logging.getLogger(__name__)
if not logger.hasHandlers():
    logging.basicConfig(level=logging.INFO)

AGENT_NAME = "TestingAgentServer"
AGENT_SKILLS_LIST = [AGENT_SKILL_SOFTWARE_TESTING, AGENT_SKILL_TEST_CASE_GENERATION]

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
    agent_url = os.environ.get("PUBLIC_URL")
    if not agent_url:
        logger.error(f"[{AGENT_NAME}] PUBLIC_URL environment variable is not set. Agent cannot be registered.")
        #on définit la varibeble d'environnement pour l'URL publique
        agent_url = "http://localhost:8080"
    logger.info(f"[{AGENT_NAME}] Agent URL temporaire set to {agent_url}")
     
    return AgentCard(
        name="Software Testing Agent",
        description="Agent specialized in testing software and generating test reports.",
        url=agent_url,
        version="0.1.0",
        defaultInputModes=["application/json"], # Prend les specs de test et le livrable en JSON string
        defaultOutputModes=["application/json"],# Retourne un rapport de test JSON string
        capabilities=capabilities,
        skills=skills_objects
    )

agent_executor = TestingAgentExecutor()
task_store = InMemoryTaskStore()
request_handler = DefaultRequestHandler(agent_executor=agent_executor, task_store=task_store)

def create_app_instance(host: str, port: int) -> Starlette:
    agent_card = get_testing_agent_card()
    a2a_server_app_instance = A2AStarletteApplication(agent_card=agent_card, http_handler=request_handler)
    return a2a_server_app_instance.build()

app = create_app_instance(host="localhost", port=8080)

# --- IMPORTS À AJOUTER ---
from starlette.routing import Route
from starlette.responses import JSONResponse
# === DÉBUT DE LA CORRECTION : AJOUT DE LA ROUTE /health ===

# 2. Définir la fonction de la route de santé
async def health_check_endpoint(request):
    """Endpoint simple pour la vérification de santé."""
    return JSONResponse({"status": "ok"})

# 3. Ajouter la nouvelle route à la liste des routes existantes de l'application
app.router.routes.append(
    Route("/health", endpoint=health_check_endpoint, methods=["GET"])
)
@contextlib.asynccontextmanager
async def lifespan(app_param: Starlette):
    agent_public_url = os.environ.get("PUBLIC_URL")
    agent_internal_url = os.environ.get("INTERNAL_URL")
    
    if not agent_public_url or not agent_internal_url:
        logger.error(f"[{AGENT_NAME}] PUBLIC_URL ou INTERNAL_URL manquant ! Impossible de s'enregistrer.")
        yield
        return

    # === AJOUT : Récupérer les compétences ===
    # La fonction get_..._card est déjà définie dans chaque fichier server.py
    # On l'appelle pour obtenir la carte et extraire les compétences.
    agent_card = get_testing_agent_card() # l'host/port n'importe pas ici
     # === LA CORRECTION EST ICI ===
    # On accède directement à l'attribut .skills de la carte, pas via .capabilities
    skill_ids = [skill.id for skill in agent_card.skills] if agent_card.skills else []


    logger.info(f"[{AGENT_NAME}] Enregistrement avec URLs et compétences : {skill_ids}")
    
    # On passe maintenant les compétences à la fonction d'enregistrement
    await register_self_with_gra(AGENT_NAME, agent_public_url, agent_internal_url, skill_ids)
    yield
    logger.info(f"[{AGENT_NAME}] Serveur en cours d'arrêt.")

app.router.lifespan_context = lifespan

if __name__ == "__main__":
    SERVER_HOST = "localhost"
    SERVER_PORT = 8008
    os.environ[f"{AGENT_NAME.upper()}_PUBLIC_URL"] = f"http://{SERVER_HOST}:{SERVER_PORT}"
    logger.info(f"Lancement du serveur {AGENT_NAME} sur http://{SERVER_HOST}:{SERVER_PORT}")
    try:
        uvicorn.run(app, host=SERVER_HOST, port=SERVER_PORT, lifespan="on")
    except Exception as e:
        logger.error(f"Erreur lors du lancement du serveur {AGENT_NAME}: {e}", exc_info=True)