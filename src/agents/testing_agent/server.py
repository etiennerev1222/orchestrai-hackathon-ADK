# src/agents/testing_agent/server.py
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
from .executor import TestingAgentExecutor
from .logic import AGENT_SKILL_SOFTWARE_TESTING, AGENT_SKILL_TEST_CASE_GENERATION

logger = logging.getLogger(__name__)
if not logger.hasHandlers():
    logging.basicConfig(level=logging.INFO)

AGENT_NAME = "TestingAgentServer"
AGENT_SKILLS_LIST = [AGENT_SKILL_SOFTWARE_TESTING, AGENT_SKILL_TEST_CASE_GENERATION]

def get_testing_agent_card(host: str, port: int) -> AgentCard:
    capabilities = AgentCapabilities(streaming=False)
    skills_objects = [
        AgentSkill(
            id=AGENT_SKILL_SOFTWARE_TESTING,
            name="Software Testing and Validation",
            description="Tests software deliverables against specifications and acceptance criteria.",
            tags=["testing", "qa", "validation", "software_engineering"],
            examples=[
                '{"objective": "Test login function", "deliverable": "<code>...", "acceptance_criteria": ["User can login with valid credentials"]}'
            ]
        ),
        AgentSkill(
            id=AGENT_SKILL_TEST_CASE_GENERATION,
            name="Test Case Generation",
            description="Generates test cases based on software specifications.",
            tags=["testing", "qa", "planning"],
            examples=[
                '{"objective": "Generate test cases for user registration"}'
            ]
        )
    ]
    return AgentCard(
        name="Software Testing Agent",
        description="Agent specialized in testing software and generating test reports.",
        url=f"http://{host}:{port}/",
        version="0.1.0",
        defaultInputModes=["application/json"], # Prend les specs de test et le livrable en JSON string
        defaultOutputModes=["application/json"],# Retourne un rapport de test JSON string
        capabilities=capabilities,
        skills=skills_objects
    )

async def register_self_with_gra(agent_public_url: str):
    # ... (Logique d'enregistrement identique à ResearchAgent/DevelopmentAgent) ...
    gra_base_url = await get_gra_base_url()
    if not gra_base_url:
        logger.error(f"[{AGENT_NAME}] Impossible de découvrir l'URL du GRA. Enregistrement annulé.")
        return
    registration_payload = {"name": AGENT_NAME, "url": agent_public_url, "skills": AGENT_SKILLS_LIST}
    register_endpoint = f"{gra_base_url}/register"
    max_retries = 3; retry_delay = 5
    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient() as client:
                logger.info(f"[{AGENT_NAME}] Tentative enregistrement ({agent_public_url}) GRA {register_endpoint} (essai {attempt+1})")
                response = await client.post(register_endpoint, json=registration_payload, timeout=10.0)
                response.raise_for_status()
                logger.info(f"[{AGENT_NAME}] Enregistré GRA. Réponse: {response.json()}")
                return
        except Exception as e:
            logger.warning(f"[{AGENT_NAME}] Échec enregistrement GRA (essai {attempt+1}): {e}")
            if attempt < max_retries -1: await asyncio.sleep(retry_delay)
            else: logger.error(f"[{AGENT_NAME}] Échec final enregistrement GRA.")


async def run_server(host: str = "localhost", port: int = 8008, log_level: str = "info"): # Port 8008
    logger.info(f"Démarrage de {AGENT_NAME} à http://{host}:{port}")

    @contextlib.asynccontextmanager
    async def lifespan(app_starlette: Starlette):
        actual_host = "localhost" if host == "0.0.0.0" else host
        agent_public_url = os.environ.get(f"{AGENT_NAME.upper()}_PUBLIC_URL", f"http://{actual_host}:{port}")
        logger.info(f"[{AGENT_NAME}] Lifespan: Démarrage. URL publique: {agent_public_url}")
        await register_self_with_gra(agent_public_url)
        yield
        logger.info(f"[{AGENT_NAME}] Serveur en cours d'arrêt.")

    agent_executor = TestingAgentExecutor()
    task_store = InMemoryTaskStore()
    request_handler = DefaultRequestHandler(agent_executor=agent_executor, task_store=task_store)
    agent_card = get_testing_agent_card(host, port)
    
    a2a_app_instance = A2AStarletteApplication(agent_card=agent_card, http_handler=request_handler)
    asgi_app = a2a_app_instance.build()
    asgi_app.router.lifespan_context = lifespan

    config = uvicorn.Config(app=asgi_app, host=host, port=port, log_level=log_level.lower(), lifespan="on")
    server = uvicorn.Server(config)
    
    try:
        await server.serve()
    finally:
        logger.info(f"Serveur {AGENT_NAME} arrêté.")

if __name__ == "__main__":
    SERVER_PORT_TEST_AGENT = 8008 # Port unique
    SERVER_HOST_TEST_AGENT = "localhost"
    logger.info(f"Lancement du serveur {AGENT_NAME} sur http://{SERVER_HOST_TEST_AGENT}:{SERVER_PORT_TEST_AGENT}")
    try:
        asyncio.run(run_server(host=SERVER_HOST_TEST_AGENT, port=SERVER_PORT_TEST_AGENT))
    except Exception as e:
        logger.error(f"Erreur lancement serveur {AGENT_NAME}: {e}", exc_info=True)