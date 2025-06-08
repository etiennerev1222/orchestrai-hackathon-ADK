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

from src.shared.service_discovery import get_gra_base_url
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

async def register_self_with_gra(agent_public_url: str):
    # ... (Logique d'enregistrement identique aux autres agents, en utilisant AGENT_NAME et AGENT_SKILLS_LIST)
    gra_base_url = await get_gra_base_url()
    if not gra_base_url:
        logger.error(f"[{AGENT_NAME}] Impossible de découvrir l'URL du GRA. Enregistrement annulé.")
        return
    registration_payload = {"name": AGENT_NAME, "url": agent_public_url, "skills": AGENT_SKILLS_LIST}
    register_endpoint = f"{gra_base_url}/register"
    max_retries = 3
    retry_delay = 5
    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient() as client:
                logger.info(f"[{AGENT_NAME}] Tentative d'enregistrement ({agent_public_url}) auprès du GRA à {register_endpoint} (essai {attempt + 1}/{max_retries})")
                response = await client.post(register_endpoint, json=registration_payload, timeout=10.0)
                response.raise_for_status()
                logger.info(f"[{AGENT_NAME}] Enregistré avec succès auprès du GRA. Réponse: {response.json()}")
                return
        except httpx.RequestError as e:
            logger.warning(f"[{AGENT_NAME}] Échec de l'enregistrement (essai {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1: await asyncio.sleep(retry_delay)
            else: logger.error(f"[{AGENT_NAME}] Échec final de l'enregistrement.")
        except Exception as e:
            logger.error(f"[{AGENT_NAME}] Erreur inattendue lors de l'enregistrement: {e}")
            break

agent_executor = DecompositionAgentExecutor()
task_store = InMemoryTaskStore()
request_handler = DefaultRequestHandler(agent_executor=agent_executor, task_store=task_store)

def create_app_instance(host: str, port: int) -> Starlette:
    agent_card = get_decomposition_agent_card(host, port)
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