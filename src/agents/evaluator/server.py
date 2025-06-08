# src/agents/evaluator/server.py

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
from starlette.applications import Starlette # <-- AJOUT POTENTIEL
from fastapi import FastAPI # < -- AJOUT POTENTIEL (si asgi_app est FastAPI)


from src.shared.service_discovery import get_gra_base_url
from .executor import EvaluatorAgentExecutor

logger = logging.getLogger(__name__)
if not logger.hasHandlers():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

AGENT_NAME = "EvaluatorAgentServer"
AGENT_SKILLS = ["evaluation", "plan_analysis"]
def get_evaluator_agent_card(host: str, port: int) -> AgentCard:
    """
    Crée et retourne la "carte d'agent" pour notre EvaluatorAgent.
    """
    capabilities = AgentCapabilities(
    streaming=False,
    push_notifications=False
    )
 
    evaluation_skill = AgentSkill(
    id="plan_evaluation",
    name="Evaluate Plan",
    description="Evaluates a given plan based on predefined criteria.",
    tags=["text analysis", "evaluation", "planning"],
    examples=[
    "Evaluate: [Reformulated Plan Text Here]",
    "Assess the quality of this plan: [Plan Text]"
    ]
    )

    agent_card = AgentCard(
    name="Plan Evaluator Agent",
    description="An A2A agent that evaluates plans or objectives.",
    url=f"http://{host}:{port}/",
    version="0.1.0",
    defaultInputModes=["text/plain"],
    defaultOutputModes=["application/json"], # L'évaluateur retourne un JSON (via TextArtifact)
    capabilities=capabilities,
    skills=[evaluation_skill]
    )
    logger.info(f"Agent Card créée: {agent_card.name} accessible à {agent_card.url}")
    return agent_card



# --- AJOUT : Fonction pour s'enregistrer auprès du GRA ---
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


# La fonction app_lifespan reste la même, mais son attachement change.
@contextlib.asynccontextmanager
async def app_lifespan_for_evaluator(app_passed_by_starlette): # Le nom du paramètre n'importe pas vraiment
    actual_host_for_run_server = "localhost" # Valeur par défaut
    actual_port_for_run_server = 8002       # Valeur par défaut pour l'évaluateur
    
    # Essayer de récupérer host et port depuis une source plus fiable si possible
    # Pour l'instant, on utilise des valeurs codées en dur pour l'exemple,
    # mais il faudrait idéalement les passer à la fonction run_server
    # et les rendre accessibles ici (par exemple, via closure si lifespan est définie dans run_server).
    # Pour cet exemple, nous allons les coder en dur pour la simplicité de la correction immédiate.
    # Dans une version finale, il faudrait que `host` et `port` de `run_server` soient accessibles ici.

    # NOTE: Pour une solution plus propre, définissez app_lifespan DANS run_server
    # pour qu'elle ait accès à `host` et `port` de run_server par closure.
    # Sinon, vous devrez déterminer host et port autrement ici.
    # Pour l'instant, je vais utiliser les valeurs par défaut de run_server
    # en supposant que ce sont celles utilisées.

    # Ceci est un placeholder, car host et port de run_server ne sont pas directement dans ce scope
    # On va utiliser les ports par défaut des agents pour l'instant pour l'URL publique
    port_for_this_agent = 8002 # Port de l'évaluateur
    # host_for_this_agent = "localhost" # Supposer localhost pour l'enregistrement

    # Pour que cela fonctionne, nous allons rendre host et port accessibles via la config
    # de l'application si A2AStarletteApplication les stocke, ou les passer.
    # Solution la plus simple pour l'instant : utiliser les valeurs par défaut.
    agent_public_url = os.environ.get(f"{AGENT_NAME}_PUBLIC_URL", f"http://localhost:{port_for_this_agent}")
    if "0.0.0.0" in agent_public_url: # Si l'URL publique configurée contient 0.0.0.0
         logger.warning(f"[{AGENT_NAME}] L'URL publique semble être 0.0.0.0. Utilisation de 'http://localhost:{port_for_this_agent}' pour l'enregistrement au GRA.")
         agent_public_url = f"http://localhost:{port_for_this_agent}"

    logger.info(f"[{AGENT_NAME}] Lifespan: Démarrage. URL publique pour enregistrement: {agent_public_url}")
    await register_self_with_gra(agent_public_url)
    yield
    logger.info(f"[{AGENT_NAME}] Serveur en cours d'arrêt (lifespan).")

agent_executor = EvaluatorAgentExecutor()
task_store = InMemoryTaskStore()
request_handler = DefaultRequestHandler(agent_executor=agent_executor, task_store=task_store)

def create_app_instance(host: str, port: int) -> Starlette:
    agent_card = get_evaluator_agent_card(host, port)
    a2a_server_app_instance = A2AStarletteApplication(agent_card=agent_card, http_handler=request_handler)
    return a2a_server_app_instance.build()

app = create_app_instance(host="localhost", port=8080)

@contextlib.asynccontextmanager
async def lifespan(app_param: Starlette):
    host = os.environ.get("HOST", "localhost")
    port = int(os.environ.get("PORT", 8080))
    agent_public_url = os.environ.get(f"{AGENT_NAME.upper()}_PUBLIC_URL", f"http://{host}:{port}")
    logger.info(f"[{AGENT_NAME}] Lifespan: Démarrage. URL publique pour enregistrement : {agent_public_url}")
    await register_self_with_gra(agent_public_url)
    yield
    logger.info(f"[{AGENT_NAME}] Serveur en cours d'arrêt.")

app.router.lifespan_context = lifespan

if __name__ == "__main__":
    SERVER_HOST = "localhost"
    SERVER_PORT = 8002
    os.environ[f"{AGENT_NAME.upper()}_PUBLIC_URL"] = f"http://{SERVER_HOST}:{SERVER_PORT}"
    logger.info(f"Lancement du serveur {AGENT_NAME} sur http://{SERVER_HOST}:{SERVER_PORT}")
    try:
        uvicorn.run(app, host=SERVER_HOST, port=SERVER_PORT, lifespan="on")
    except Exception as e:
        logger.error(f"Erreur lors du lancement du serveur {AGENT_NAME}: {e}", exc_info=True)