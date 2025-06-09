# src/agents/validator/server.py

import asyncio
import logging
import uvicorn
import httpx
import contextlib
import os # Pour lire une éventuelle URL publique via variable d'env

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore # Ou FirestoreTaskStore
from a2a.types import (
    AgentCard,
    AgentCapabilities,
    AgentSkill,
)
from starlette.applications import Starlette # Pour le type hint de asgi_app

# Importation pour la découverte du GRA
from src.shared.service_discovery import get_gra_base_url, register_self_with_gra

# Importer l'AgentExecutor spécifique
from .executor import ValidatorAgentExecutor

logger = logging.getLogger(__name__)
if not logger.hasHandlers():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# --- Configuration spécifique à cet agent pour le GRA ---
AGENT_NAME = "ValidatorAgentServer"
AGENT_SKILLS = ["validation", "decision_making"] # Adaptez si besoin
# -------------------------------------------------------------

def get_validator_agent_card(host: str, port: int) -> AgentCard:
    capabilities = AgentCapabilities(streaming=False, push_notifications=False)
    validation_skill_obj = AgentSkill(
        id="plan_validation",
        name="Validate Plan",
        description="Validates a plan based on evaluation results and specific criteria.",
        tags=AGENT_SKILLS,
        examples=["Validate this evaluated plan: [JSON output from Evaluator Agent]"]
    )
    agent_card = AgentCard(
        name="Plan Validator Agent",
        description="An A2A agent that validates evaluated plans.",
        url=f"http://{host}:{port}/",
        version="0.1.0",
        defaultInputModes=["application/json"],
        defaultOutputModes=["application/json"],
        capabilities=capabilities,
        skills=[validation_skill_obj]
    )
    logger.info(f"Agent Card créée: {agent_card.name} accessible à {agent_card.url}")
    return agent_card


agent_executor = ValidatorAgentExecutor()
task_store = InMemoryTaskStore()
request_handler = DefaultRequestHandler(agent_executor=agent_executor, task_store=task_store)

def create_app_instance(host: str, port: int) -> Starlette:
    agent_card = get_validator_agent_card(host, port)
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
    agent_card = get_validator_agent_card("placeholder", 0) # l'host/port n'importe pas ici
 # === LA CORRECTION EST ICI ===
    # On accède directement à l'attribut .skills de la carte, pas via .capabilities
    skill_ids = [skill.id for skill in agent_card.skills] if agent_card.skills else []

    logger.info(f"[{AGENT_NAME}] Enregistrement avec URLs et compétences : {skill_ids}")
    
    # On passe maintenant les compétences à la fonction d'enregistrement
    await register_self_with_gra(AGENT_NAME, agent_public_url, agent_internal_url, skill_ids)
    yield
    logger.info(f"[{AGENT_NAME}] Serveur en cours d'arrêt.")

app.router.lifespan_context = lifespan

# N'oubliez pas de l'attacher à l'application globale
app.router.lifespan_context = lifespan

if __name__ == "__main__":
    SERVER_HOST = "localhost"
    SERVER_PORT = 8003
    os.environ[f"{AGENT_NAME.upper()}_PUBLIC_URL"] = f"http://{SERVER_HOST}:{SERVER_PORT}"
    logger.info(f"Lancement du serveur {AGENT_NAME} sur http://{SERVER_HOST}:{SERVER_PORT}")
    try:
        uvicorn.run(app, host=SERVER_HOST, port=SERVER_PORT, lifespan="on")
    except Exception as e:
        logger.error(f"Erreur lors du lancement du serveur {AGENT_NAME}: {e}", exc_info=True)