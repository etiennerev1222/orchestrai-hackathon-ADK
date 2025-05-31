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
# ----------------------------------------------------

async def run_server(host: str = "localhost", port: int = 8003, log_level: str = "info"): # Port 8003
    logger.info(f"Démarrage de {AGENT_NAME} à l'adresse http://{host}:{port}")

    @contextlib.asynccontextmanager
    async def lifespan_for_this_agent_instance(app): # 'app' est l'instance Starlette
        current_host = host
        current_port = port
        
        actual_host_for_url = "localhost" if current_host == "0.0.0.0" else current_host
        if current_host == "0.0.0.0":
             logger.warning(f"[{AGENT_NAME}] L'agent écoute sur 0.0.0.0. Utilisation de 'http://localhost:{current_port}' pour l'enregistrement au GRA.")

        agent_public_url = os.environ.get(f"{AGENT_NAME}_PUBLIC_URL", f"http://{actual_host_for_url}:{current_port}")
        logger.info(f"[{AGENT_NAME}] Lifespan: Démarrage. URL publique pour enregistrement : {agent_public_url}")
        
        await register_self_with_gra(agent_public_url)
        yield
        logger.info(f"[{AGENT_NAME}] Serveur en cours d'arrêt (lifespan).")

    validator_executor = ValidatorAgentExecutor()
    task_store = InMemoryTaskStore()
    request_handler = DefaultRequestHandler(
        agent_executor=validator_executor,
        task_store=task_store
    )
    agent_card = get_validator_agent_card(host, port)

    a2a_server_app_instance = A2AStarletteApplication(
        agent_card=agent_card,
        http_handler=request_handler
        # Ne pas passer le lifespan ici
    )
    
    asgi_app: Starlette = a2a_server_app_instance.build()

    # Attacher le lifespan à l'application Starlette construite
    if hasattr(asgi_app, 'router') and hasattr(asgi_app.router, 'lifespan_context'):
        asgi_app.router.lifespan_context = lifespan_for_this_agent_instance
        logger.info(f"[{AGENT_NAME}] Lifespan attaché à asgi_app.router.lifespan_context.")
    else:
        logger.error(f"[{AGENT_NAME}] Impossible d'attacher le lifespan. L'enregistrement au GRA ne se fera pas.")

    config = uvicorn.Config(
        app=asgi_app,
        host=host,
        port=port,
        log_level=log_level.lower(),
        lifespan="on" # Dire à Uvicorn de respecter le lifespan de l'application
    )
    
    server = uvicorn.Server(config)
    
    try:
        await server.serve()
    except KeyboardInterrupt:
        logger.info(f"[{AGENT_NAME}] Arrêt du serveur demandé (KeyboardInterrupt).")
    finally:
        logger.info(f"Serveur {AGENT_NAME} arrêté.")

if __name__ == "__main__":
    SERVER_HOST = "localhost"
    SERVER_PORT = 8003  # Port spécifique pour le ValidatorAgent

    print(f"Lancement du serveur {AGENT_NAME}...")
    logger.info(f"Pour lancer le serveur {AGENT_NAME}, assurez-vous d'avoir 'uvicorn' et les dépendances A2A installés.")
    try:
        asyncio.run(run_server(host=SERVER_HOST, port=SERVER_PORT))
    except Exception as e:
        logger.error(f"Erreur lors du lancement du serveur {AGENT_NAME}: {e}", exc_info=True)