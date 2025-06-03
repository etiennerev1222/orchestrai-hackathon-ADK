# src/agents/research_agent/server.py
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
from .executor import ResearchAgentExecutor
from .logic import AGENT_SKILL_GENERAL_ANALYSIS, AGENT_SKILL_WEB_RESEARCH, AGENT_SKILL_DOCUMENT_SYNTHESIS

logger = logging.getLogger(__name__)
if not logger.hasHandlers():
    logging.basicConfig(level=logging.INFO)

AGENT_NAME = "ResearchAgentServer"
# Définir les compétences que cet agent déclarera
AGENT_SKILLS_LIST = [AGENT_SKILL_GENERAL_ANALYSIS, AGENT_SKILL_WEB_RESEARCH, AGENT_SKILL_DOCUMENT_SYNTHESIS]


def get_research_agent_card(host: str, port: int) -> AgentCard:
    capabilities = AgentCapabilities(streaming=False)
    skills_objects = [
        AgentSkill(
            id=AGENT_SKILL_GENERAL_ANALYSIS,
            name="General Analysis",
            description="Performs general analysis on a given topic or input.",
            tags=["research", "analysis"],
            examples=["Analyze the feasibility of X.", "Provide insights on Y based on Z."]
        ),
        AgentSkill(
            id=AGENT_SKILL_WEB_RESEARCH,
            name="Web Research",
            description="Conducts research on the internet for a specific query.",
            tags=["research", "web", "information_retrieval"],
            examples=["Find information about technology X.", "What are the latest trends in Y?"]
        ),
        AgentSkill(
            id=AGENT_SKILL_DOCUMENT_SYNTHESIS,
            name="Document Synthesis",
            description="Synthesizes information into a document or report.",
            tags=["research", "writing", "reporting"],
            examples=["Write a summary report on X.", "Draft a section about Y for a document."]
        )
    ]
    return AgentCard(
        name="Research and Analysis Agent",
        description="Agent specialized in research, analysis, and information synthesis.",
        url=f"http://{host}:{port}/",
        version="0.1.0",
        defaultInputModes=["application/json"], # Prend un JSON string comme input (objectif, instructions, etc.)
        defaultOutputModes=["application/json"],# Retourne un JSON string (résumé, et potentiellement new_sub_tasks)
        capabilities=capabilities,
        skills=skills_objects
    )

async def register_self_with_gra(agent_public_url: str):
    gra_base_url = await get_gra_base_url()
    if not gra_base_url:
        logger.error(f"[{AGENT_NAME}] Impossible de découvrir l'URL du GRA. Enregistrement annulé.")
        return
    registration_payload = {"name": AGENT_NAME, "url": agent_public_url, "skills": AGENT_SKILLS_LIST}
    register_endpoint = f"{gra_base_url}/register"
    # ... (logique d'enregistrement avec retries, identique aux autres agents) ...
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

async def run_server(host: str = "localhost", port: int = 8006, log_level: str = "info"): # Port 8006
    logger.info(f"Démarrage de {AGENT_NAME} à http://{host}:{port}")

    @contextlib.asynccontextmanager
    async def lifespan(app_starlette: Starlette): # Renommé 'app' pour éviter conflit avec variable globale 'app' si présente
        actual_host = "localhost" if host == "0.0.0.0" else host
        agent_public_url = os.environ.get(f"{AGENT_NAME.upper()}_PUBLIC_URL", f"http://{actual_host}:{port}")
        logger.info(f"[{AGENT_NAME}] Lifespan: Démarrage. URL publique: {agent_public_url}")
        await register_self_with_gra(agent_public_url)
        yield
        logger.info(f"[{AGENT_NAME}] Serveur en cours d'arrêt.")

    agent_executor = ResearchAgentExecutor()
    task_store = InMemoryTaskStore()
    request_handler = DefaultRequestHandler(agent_executor=agent_executor, task_store=task_store)
    agent_card = get_research_agent_card(host, port)
    
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
    SERVER_PORT_RESEARCH_AGENT = 8006 # Port unique
    SERVER_HOST_RESEARCH_AGENT = "localhost"
    logger.info(f"Lancement du serveur {AGENT_NAME} sur http://{SERVER_HOST_RESEARCH_AGENT}:{SERVER_PORT_RESEARCH_AGENT}")
    try:
        asyncio.run(run_server(host=SERVER_HOST_RESEARCH_AGENT, port=SERVER_PORT_RESEARCH_AGENT))
    except Exception as e:
        logger.error(f"Erreur lancement serveur {AGENT_NAME}: {e}", exc_info=True)