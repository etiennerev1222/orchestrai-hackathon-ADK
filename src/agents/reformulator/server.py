# my_simple_a2a_service/reformulator_server/main_server.py

import asyncio
import logging
import uvicorn # Pour exécuter notre application ASGI
import os # Pour lire une éventuelle URL publique via variable d'env
# Importations depuis le SDK A2A
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore # Un gestionnaire de tâches simple en mémoire
from a2a.types import (
    AgentCard,
    AgentCapabilities,
    AgentSkill,
    # D'autres types pourraient être nécessaires pour une AgentCard plus complexe
)
import starlette # Pour le type hint de asgi_app
import httpx # AJOUTÉ
import contextlib # AJOUTÉ
# Importation de notre AgentExecutor
from .executor import ReformulatorAgentExecutor
from src.shared.service_discovery import get_gra_base_url, register_self_with_gra
from starlette.applications import Starlette

# --- AJOUT : Configuration spécifique à cet agent pour le GRA ---
AGENT_NAME = "ReformulatorAgentServer"
AGENT_SKILLS = ["reformulation", "text_processing"] # Compétences de cet agent
# 


# Configuration du logging
logger = logging.getLogger(__name__)
if not logger.hasHandlers():
    logging.basicConfig(level=logging.INFO)

def get_reformulator_agent_card(host: str, port: int) -> AgentCard:
    """
    Crée et retourne la "carte d'agent" pour notre ReformulatorAgent.
    Cette carte décrit l'agent au monde extérieur.
    """
    capabilities = AgentCapabilities(
        streaming=False, # Notre agent simple ne streame pas de réponses pour l'instant
        push_notifications=False # Pas de notifications push pour l'instant
    )

    # Définir une compétence simple pour cet agent
    reformulation_skill = AgentSkill(
        id="objective_reformulation", # Un ID unique pour la compétence
        name="Reformulate Objective",
        description="Reformulates a given objective text according to predefined rules.",
        tags=["text processing", "reformulation", "planning"],
        examples=[
            "Reformulate: plan a meeting for tomorrow",
            "Reformulate urgent: review this document"
        ]
    )

    agent_card = AgentCard(
        name="Simple Reformulator Agent",
        description="An A2A agent that reformulates objectives.",
        url=f"http://{host}:{port}/", # L'URL où cet agent sera accessible
        version="0.1.0",
        capabilities=capabilities,
        defaultInputModes=["text/plain"],
        defaultOutputModes=["text/plain"],
        skills=[reformulation_skill]
    )
    logger.info(f"Agent Card créée: {agent_card.name} accessible à {agent_card.url}")
    return agent_card
# ------------------------------------------------------------------------------------

# Variable globale pour stocker la config uvicorn pour le lifespan
uvicorn_config_reformulator = None # Nom unique pour éviter conflit si importé ailleurs

from starlette.applications import Starlette

agent_executor = ReformulatorAgentExecutor()
task_store = InMemoryTaskStore()
request_handler = DefaultRequestHandler(agent_executor=agent_executor, task_store=task_store)

def create_app_instance(host: str, port: int) -> Starlette:
    agent_card = get_reformulator_agent_card(host, port)
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
    agent_card = get_reformulator_agent_card("placeholder", 0) # l'host/port n'importe pas ici
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
    SERVER_PORT = 8001
    os.environ[f"{AGENT_NAME.upper()}_PUBLIC_URL"] = f"http://{SERVER_HOST}:{SERVER_PORT}"
    logger.info(f"Lancement du serveur {AGENT_NAME} sur http://{SERVER_HOST}:{SERVER_PORT}")
    try:
        uvicorn.run(app, host=SERVER_HOST, port=SERVER_PORT, lifespan="on")
    except Exception as e:
        logger.error(f"Erreur lors du lancement du serveur {AGENT_NAME}: {e}", exc_info=True)

        