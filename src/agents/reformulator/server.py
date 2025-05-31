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
import httpx # AJOUTÉ
import contextlib # AJOUTÉ
# Importation de notre AgentExecutor
from .executor import ReformulatorAgentExecutor
from src.shared.service_discovery import get_gra_base_url # Assurez-vous que ce chemin est correct

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
# ------------------------------------------------------------------------------------

# Variable globale pour stocker la config uvicorn pour le lifespan
uvicorn_config_reformulator = None # Nom unique pour éviter conflit si importé ailleurs

@contextlib.asynccontextmanager
async def lifespan(app): # FastAPI ou Starlette app
    global uvicorn_config_reformulator
    # Actions au démarrage
    host = uvicorn_config_reformulator.host if uvicorn_config_reformulator  else "localhost"
    port = uvicorn_config_reformulator.port if uvicorn_config_reformulator else 8002 # Port par défaut pour l'évaluateur
    
    if host == "0.0.0.0":
        logger.warning(f"[{AGENT_NAME}] L'agent écoute sur 0.0.0.0. L'URL d'enregistrement utilise 'localhost'. Assurez-vous que c'est accessible par le GRA.")
        agent_public_url = f"http://localhost:{port}"
    else:
        agent_public_url = f"http://{host}:{port}"
        
    await register_self_with_gra(agent_public_url)
    yield
    # Actions à l'arrêt
    logger.info(f"[{AGENT_NAME}] Serveur en cours d'arrêt.")

async def run_server(host: str = "localhost", port: int = 8001, log_level: str = "info"): # Adapter le port
    logger.info(f"Démarrage de {AGENT_NAME} à l'adresse http://{host}:{port}")

    # 1. Définir le lifespan DANS la portée de run_server pour capturer host et port
    @contextlib.asynccontextmanager
    async def lifespan_for_this_agent_instance(app): # 'app' est l'instance Starlette
        current_host = host
        current_port = port
        # Logique pour déterminer agent_public_url (comme dans ma réponse précédente)
        # ...
        agent_public_url = os.environ.get(f"{AGENT_NAME}_PUBLIC_URL", f"http://{'localhost' if current_host == '0.0.0.0' else current_host}:{current_port}")
        logger.info(f"[{AGENT_NAME}] Lifespan: Démarrage. URL publique pour enregistrement : {agent_public_url}")
        await register_self_with_gra(agent_public_url)
        yield
        logger.info(f"[{AGENT_NAME}] Serveur en cours d'arrêt (lifespan).")

    # 2. Créer l'instance de l'Executor spécifique à l'agent
    agent_executor = ReformulatorAgentExecutor() # Ou EvaluatorAgentExecutor, ValidatorAgentExecutor

    # 3. Créer les composants A2A standard
    task_store = InMemoryTaskStore()
    request_handler = DefaultRequestHandler(
        agent_executor=agent_executor,
        task_store=task_store
    )
    agent_card = get_reformulator_agent_card(host, port) # Ou get_evaluator_agent_card, etc.

    # 4. Créer l'application A2AStarletteApplication SANS l'argument lifespan
    a2a_server_app_instance = A2AStarletteApplication(
        agent_card=agent_card,
        http_handler=request_handler
    )
    
    # 5. Construire l'application ASGI (Starlette)
    asgi_app = a2a_server_app_instance.build()

    # 6. Attacher notre lifespan à l'application Starlette construite
    # Ceci est la manière standard pour Starlette/FastAPI
    if hasattr(asgi_app, 'router') and hasattr(asgi_app.router, 'lifespan_context'):
        asgi_app.router.lifespan_context = lifespan_for_this_agent_instance
        logger.info(f"[{AGENT_NAME}] Lifespan attaché à asgi_app.router.lifespan_context.")
    else:
        logger.error(f"[{AGENT_NAME}] Impossible d'attacher le lifespan. L'enregistrement au GRA ne se fera pas.")


    # 7. Configurer Uvicorn pour qu'il utilise le lifespan de l'application
    config = uvicorn.Config(
        app=asgi_app,
        host=host,
        port=port,
        log_level=log_level.lower(),
        lifespan="on" # <--- Important: "on" ici
    )
    
    server = uvicorn.Server(config)
    
    try:
        await server.serve()
    except KeyboardInterrupt:
        logger.info(f"[{AGENT_NAME}] Arrêt du serveur demandé (KeyboardInterrupt).")
    finally:
        logger.info(f"Serveur {AGENT_NAME} arrêté.")

if __name__ == "__main__":
    # Paramètres pour le serveur
    SERVER_HOST = "localhost"
    SERVER_PORT = 8001 # Choisir un port, par exemple 8001 pour cet agent

    # Ajouter uvicorn à votre requirements.txt et l'installer: pip install uvicorn
    logger.info("Pour lancer le serveur, assurez-vous d'avoir 'uvicorn' installé.")
    logger.info(f"Exemple: pip install uvicorn httpx sse-starlette starlette") # httpx, sse-starlette, starlette sont des dépendances de a2a.server

    # Exécute la fonction principale du serveur
    # asyncio.run() est utilisé pour exécuter une fonction asynchrone depuis un contexte synchrone.
    try:
        asyncio.run(run_server(host=SERVER_HOST, port=SERVER_PORT))
    except Exception as e:
        logger.error(f"Erreur lors du lancement du serveur: {e}", exc_info=True)


