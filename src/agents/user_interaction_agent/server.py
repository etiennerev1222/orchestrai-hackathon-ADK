# src/agents/user_interaction_agent/server.py
import asyncio
import logging
import uvicorn
import httpx
import contextlib
import os

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import (
    AgentCard,
    AgentCapabilities,
    AgentSkill,
)
from starlette.applications import Starlette

# Assurez-vous que ce chemin est correct par rapport à votre structure
from src.shared.service_discovery import get_gra_base_url, register_self_with_gra
from .executor import UserInteractionAgentExecutor
# Importer la constante d'action depuis logic.py pour la cohérence
from .logic import ACTION_CLARIFY_OBJECTIVE


logger = logging.getLogger(__name__)
if not logger.hasHandlers():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

AGENT_NAME = "UserInteractionAgentServer"
# Définir les compétences ici pour les utiliser dans l'AgentCard et l'enregistrement GRA
SKILL_CLARIFY_OBJECTIVE = ACTION_CLARIFY_OBJECTIVE # Utilise la constante de logic.py
# Plus tard :
# SKILL_PRESENT_PLAN_FOR_REVIEW = "present_plan_for_review"
# SKILL_GET_USER_DECISION = "get_user_decision"

AGENT_SKILLS_LIST = [SKILL_CLARIFY_OBJECTIVE] # Ajoutez d'autres compétences ici au fur et à mesure
# REMPLACEZ votre fonction par celle-ci
def get_user_interaction_agent_card() -> AgentCard:
    """
    Crée et retourne la "carte d'agent".
    L'URL est maintenant lue depuis la variable d'environnement PUBLIC_URL
    pour garantir qu'elle est toujours correcte.
    """
    # On lit l'URL publique depuis l'environnement, qui est la source de vérité
    agent_url = os.environ.get("PUBLIC_URL")
    if not agent_url:
        logger.warning("PUBLIC_URL n'est pas définie. L'URL de l'agent pourrait être incorrecte.")
        # On met une valeur par défaut pour éviter un crash, même si elle est probablement fausse
        agent_url = "http://localhost:8080/"

    capabilities = AgentCapabilities(streaming=False, push_notifications=False)
    
    skills_objects = [
        AgentSkill(
            id=SKILL_CLARIFY_OBJECTIVE,
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
        url=agent_url,  # On utilise l'URL lue depuis l'environnement
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

def create_app_instance(host: str, port: int) -> Starlette:
    agent_card = get_user_interaction_agent_card()
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
    agent_card = get_user_interaction_agent_card() # l'host/port n'importe pas ici
     # === LA CORRECTION EST ICI ===
    # On accède directement à l'attribut .skills de la carte, pas via .capabilities
    skill_ids = [skill.id for skill in agent_card.skills] if agent_card.skills else []


    logger.info(f"[{AGENT_NAME}] Enregistrement avec URLs et compétences : {skill_ids}")
    
    # On passe maintenant les compétences à la fonction d'enregistrement
    await register_self_with_gra(AGENT_NAME, agent_public_url, agent_internal_url, skill_ids)
    yield
    logger.info(f"[{AGENT_NAME}] Serveur en cours d'arrêt.")

# N'oubliez pas de l'attacher à l'application globale
app.router.lifespan_context = lifespan
if __name__ == "__main__":
    SERVER_HOST = "localhost"
    SERVER_PORT = 8004
    os.environ[f"{AGENT_NAME.upper()}_PUBLIC_URL"] = f"http://{SERVER_HOST}:{SERVER_PORT}"
    logger.info(f"Lancement du serveur {AGENT_NAME} sur http://{SERVER_HOST}:{SERVER_PORT}")
    try:
        uvicorn.run(app, host=SERVER_HOST, port=SERVER_PORT, lifespan="on")
    except Exception as e:
        logger.error(f"Erreur lors du lancement du serveur {AGENT_NAME}: {e}", exc_info=True)