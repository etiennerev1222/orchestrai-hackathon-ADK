# src/agents/decomposition_agent/server.py
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
from .executor import DecompositionAgentExecutor
from .logic import AGENT_SKILL_DECOMPOSE_EXECUTION_PLAN # Importer la compétence

logger = logging.getLogger(__name__)
if not logger.hasHandlers():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

AGENT_NAME = "DecompositionAgentServer"
AGENT_SKILLS_LIST = [AGENT_SKILL_DECOMPOSE_EXECUTION_PLAN]

def get_decomposition_agent_card(host: str, port: int) -> AgentCard:
    capabilities = AgentCapabilities(streaming=False)
    skill_obj = AgentSkill(
        id=AGENT_SKILL_DECOMPOSE_EXECUTION_PLAN,
        name="Decompose Execution Plan",
        description="Decomposes a high-level textual plan into a structured list of execution tasks for the execution Team1 (JSON).",
        tags=["planning", "decomposition", "execution_setup"],
        examples=["Decompose this plan: [Text of TEAM 1's validated plan]"]
    )
    return AgentCard(
        name="Execution Plan Decomposition Agent",
        description="Agent that takes a validated plan text and breaks it down into structured execution tasks.",
        url=f"http://{host}:{port}/",
        version="0.1.0",
        defaultInputModes=["text/plain"], # Prend le plan texte en entrée
        defaultOutputModes=["application/json"], # Retourne une liste de tâches en JSON via un artefact textuel
        capabilities=capabilities,
        skills=[skill_obj]
    )


agent_executor = DecompositionAgentExecutor()
task_store = InMemoryTaskStore()
request_handler = DefaultRequestHandler(agent_executor=agent_executor, task_store=task_store)

def create_app_instance(host: str, port: int) -> Starlette:
    agent_card = get_decomposition_agent_card(host, port)
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
    agent_card = get_decomposition_agent_card("placeholder", 0) # l'host/port n'importe pas ici
     # === LA CORRECTION EST ICI ===
    # On accède directement à l'attribut .skills de la carte, pas via .capabilities
    skill_ids = [skill.id for skill in agent_card.skills] if agent_card.skills else []

    logger.info(f"[{AGENT_NAME}] Enregistrement avec URLs et compétences : {skill_ids}")
    
    # On passe maintenant les compétences à la fonction d'enregistrement
    await register_self_with_gra(AGENT_NAME, agent_public_url, agent_internal_url, skill_ids)
    yield
    logger.info(f"[{AGENT_NAME}] Serveur en cours d'arrêt.")

app.router.lifespan_context = lifespan