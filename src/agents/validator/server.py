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
from src.shared.service_discovery import get_gra_base_url

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

# --- Fonction pour s'enregistrer auprès du GRA ---
async def register_self_with_gra(agent_public_url: str):
    gra_base_url = await get_gra_base_url()
    if not gra_base_url:
        logger.error(f"[{AGENT_NAME}] Impossible de découvrir l'URL du GRA. Enregistrement annulé.")
        return

    registration_payload = {
        "name": AGENT_NAME,
        "url": agent_public_url,
        "skills": AGENT_SKILLS
    }
    register_endpoint = f"{gra_base_url}/register"
    
    max_retries = 3
    retry_delay = 5 # secondes
    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient() as client:
                logger.info(f"[{AGENT_NAME}] Tentative d'enregistrement ({agent_public_url}) auprès du GRA à {register_endpoint} (essai {attempt + 1}/{max_retries})")
                response = await client.post(register_endpoint, json=registration_payload, timeout=10.0)
                response.raise_for_status()
                logger.info(f"[{AGENT_NAME}] Enregistré avec succès auprès du GRA. Réponse: {response.json()}")
                return
        except httpx.RequestError as e:
            logger.warning(f"[{AGENT_NAME}] Échec de l'enregistrement auprès du GRA (essai {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay)
            else:
                logger.error(f"[{AGENT_NAME}] Échec final de l'enregistrement après {max_retries} essais. L'agent ne sera pas découvrable via le GRA.")
        except Exception as e:
            logger.error(f"[{AGENT_NAME}] Erreur inattendue lors de l'enregistrement: {e}")
            break 

agent_executor = ValidatorAgentExecutor()
task_store = InMemoryTaskStore()
request_handler = DefaultRequestHandler(agent_executor=agent_executor, task_store=task_store)

def create_app_instance(host: str, port: int) -> Starlette:
    agent_card = get_validator_agent_card(host, port)
    a2a_server_app_instance = A2AStarletteApplication(agent_card=agent_card, http_handler=request_handler)
    return a2a_server_app_instance.build()

app = create_app_instance(host="localhost", port=8080)

@contextlib.asynccontextmanager
async def lifespan(app_param: Starlette):
    # L'URL publique est directement fournie par l'environnement Docker.
    # Fini les devinettes.
    agent_public_url = os.environ.get("PUBLIC_URL")
    
    if not agent_public_url:
        logger.error(f"[{AGENT_NAME}] La variable d'environnement PUBLIC_URL est manquante ! Impossible de s'enregistrer.")
        yield # Permet au serveur de démarrer même si l'enregistrement échoue
        return

    logger.info(f"[{AGENT_NAME}] Lifespan: Démarrage. URL publique pour enregistrement : {agent_public_url}")
    await register_self_with_gra( agent_public_url)
    yield
    logger.info(f"[{AGENT_NAME}] Serveur en cours d'arrêt.")

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