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
from src.shared.service_discovery import get_gra_base_url
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

def get_user_interaction_agent_card(host: str, port: int) -> AgentCard:
    capabilities = AgentCapabilities(streaming=False, push_notifications=False)
    
    skills_objects = [
        AgentSkill(
            id=SKILL_CLARIFY_OBJECTIVE,
            name="Clarify User Objective",
            description="Interacts with the user to clarify an initial objective, potentially asking questions if details are missing.",
            tags=["user_interaction", "clarification", "dialogue"],
            examples=[
                '{"action": "clarify_objective", "raw_objective": "Plan a holiday.", "conversation_history": []}'
            ]
        ),
        # Ajoutez d'autres objets AgentSkill ici pour les compétences futures
    ]

    agent_card = AgentCard(
        name="User Interaction Agent",
        description="An A2A agent that handles direct interactions with the user, such as clarifying objectives or presenting results for review.",
        url=f"http://{host}:{port}/",
        version="0.1.0",
        # Cet agent recevra un JSON et retournera un JSON (via un artefact textuel)
        defaultInputModes=["application/json"], # Le GlobalSupervisor enverra un JSON
        defaultOutputModes=["application/json"],# L'artefact sera un JSON
        capabilities=capabilities,
        skills=skills_objects # Utilise la liste d'objets AgentSkill
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
        "skills": AGENT_SKILLS_LIST # Utilise la liste de chaînes de compétences
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
                logger.error(f"[{AGENT_NAME}] Échec final de l'enregistrement après {max_retries} essais.")
        except Exception as e:
            logger.error(f"[{AGENT_NAME}] Erreur inattendue lors de l'enregistrement: {e}")
            break

async def run_server(host: str = "localhost", port: int = 8004, log_level: str = "info"): # Port suggéré : 8004
    logger.info(f"Démarrage de {AGENT_NAME} à l'adresse http://{host}:{port}")

    @contextlib.asynccontextmanager
    async def lifespan_for_this_agent_instance(app: Starlette):
        current_host = host
        current_port = port
        
        actual_host_for_url = "localhost" if current_host == "0.0.0.0" else current_host
        if current_host == "0.0.0.0":
             logger.warning(f"[{AGENT_NAME}] L'agent écoute sur 0.0.0.0. Utilisation de 'http://localhost:{current_port}' pour l'enregistrement au GRA.")

        agent_public_url = os.environ.get(f"{AGENT_NAME.upper()}_PUBLIC_URL", f"http://{actual_host_for_url}:{current_port}")
        logger.info(f"[{AGENT_NAME}] Lifespan: Démarrage. URL publique pour enregistrement : {agent_public_url}")
        
        await register_self_with_gra(agent_public_url)
        yield
        logger.info(f"[{AGENT_NAME}] Serveur en cours d'arrêt (lifespan).")

    agent_executor = UserInteractionAgentExecutor()
    task_store = InMemoryTaskStore()
    request_handler = DefaultRequestHandler(
        agent_executor=agent_executor,
        task_store=task_store
    )
    agent_card = get_user_interaction_agent_card(host, port)

    a2a_server_app_instance = A2AStarletteApplication(
        agent_card=agent_card,
        http_handler=request_handler
    )
    
    asgi_app: Starlette = a2a_server_app_instance.build()

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
        lifespan="on"
    )
    
    server = uvicorn.Server(config)
    
    try:
        await server.serve()
    except KeyboardInterrupt:
        logger.info(f"[{AGENT_NAME}] Arrêt du serveur demandé (KeyboardInterrupt).")
    finally:
        logger.info(f"Serveur {AGENT_NAME} arrêté.")

if __name__ == "__main__":
    # Port suggéré pour cet agent, différent des autres
    # Reformulator: 8001, Evaluator: 8002, Validator: 8003
    # UserInteractionAgent: 8004
    SERVER_PORT_UI_AGENT = 8004 
    SERVER_HOST_UI_AGENT = "localhost"

    logger.info(f"Lancement du serveur {AGENT_NAME} sur http://{SERVER_HOST_UI_AGENT}:{SERVER_PORT_UI_AGENT}")
    try:
        asyncio.run(run_server(host=SERVER_HOST_UI_AGENT, port=SERVER_PORT_UI_AGENT))
    except Exception as e:
        logger.error(f"Erreur lors du lancement du serveur {AGENT_NAME}: {e}", exc_info=True)