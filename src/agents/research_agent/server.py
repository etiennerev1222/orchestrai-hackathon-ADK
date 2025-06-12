# src/agents/research_agent/server.py
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
from .executor import ResearchAgentExecutor
from .logic import AGENT_SKILL_GENERAL_ANALYSIS, AGENT_SKILL_WEB_RESEARCH, AGENT_SKILL_DOCUMENT_SYNTHESIS

logger = logging.getLogger(__name__)
if not logger.hasHandlers():
    logging.basicConfig(level=logging.INFO)

AGENT_NAME = "ResearchAgentServer"
# Définir les compétences que cet agent déclarera
AGENT_SKILLS_LIST = [AGENT_SKILL_GENERAL_ANALYSIS, AGENT_SKILL_WEB_RESEARCH, AGENT_SKILL_DOCUMENT_SYNTHESIS]


def get_research_agent_card() -> AgentCard:
    capabilities = AgentCapabilities(streaming=False)
    skills_objects = [
        AgentSkill(
            id=AGENT_SKILL_GENERAL_ANALYSIS,
            name="General Analysis",
            description="Performs general analysis on a given topic or input.",
            tags=["research", "analysis"],
            examples=["Analyze the feasibility of X.", "Provide insights on Y based on Z."]
        ),
        AgentSkill(
            id=AGENT_SKILL_WEB_RESEARCH,
            name="Web Research",
            description="Conducts research on the internet for a specific query.",
            tags=["research", "web", "information_retrieval"],
            examples=["Find information about technology X.", "What are the latest trends in Y?"]
        ),
        AgentSkill(
            id=AGENT_SKILL_DOCUMENT_SYNTHESIS,
            name="Document Synthesis",
            description="Synthesizes information into a document or report.",
            tags=["research", "writing", "reporting"],
            examples=["Write a summary report on X.", "Draft a section about Y for a document."]
        )
    ]
    agent_url = os.environ.get("PUBLIC_URL")
    if not agent_url:
        logger.error(f"[{AGENT_NAME}] PUBLIC_URL environment variable is not set. Agent cannot be registered.")
        #on définit la varibeble d'environnement pour l'URL publique
        agent_url = "http://localhost:8080"
    logger.info(f"[{AGENT_NAME}] Agent URL temporaire set to {agent_url}")
     
    return AgentCard(
        name="Research and Analysis Agent",
        description="Agent specialized in research, analysis, and information synthesis.",
        url=agent_url,
        version="0.1.0",
        defaultInputModes=["application/json"], # Prend un JSON string comme input (objectif, instructions, etc.)
        defaultOutputModes=["application/json"],# Retourne un JSON string (résumé, et potentiellement new_sub_tasks)
        capabilities=capabilities,
        skills=skills_objects
    )

agent_executor = ResearchAgentExecutor()
task_store = InMemoryTaskStore()
request_handler = DefaultRequestHandler(agent_executor=agent_executor, task_store=task_store)

def create_app_instance(host: str, port: int) -> Starlette:
    agent_card = get_research_agent_card()
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
    agent_card = get_research_agent_card() # l'host/port n'importe pas ici
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
    SERVER_PORT = 8006
    os.environ[f"{AGENT_NAME.upper()}_PUBLIC_URL"] = f"http://{SERVER_HOST}:{SERVER_PORT}"
    logger.info(f"Lancement du serveur {AGENT_NAME} sur http://{SERVER_HOST}:{SERVER_PORT}")
    try:
        uvicorn.run(app, host=SERVER_HOST, port=SERVER_PORT, lifespan="on")
    except Exception as e:
        logger.error(f"Erreur lors du lancement du serveur {AGENT_NAME}: {e}", exc_info=True)