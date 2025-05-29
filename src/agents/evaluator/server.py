# src/agents/evaluator/server.py

import asyncio
import logging
import uvicorn

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import (
AgentCard,
AgentCapabilities,
AgentSkill,
)

# Importer l'AgentExecutor spécifique à l'évaluateur
print("Importation de EvaluatorAgentExecutor...")
from .executor import EvaluatorAgentExecutor # Assurez-vous que le chemin est correct
print("Importation réussie.")
logger = logging.getLogger(__name__)
if not logger.hasHandlers():
    logging.basicConfig(level=logging.INFO)

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


async def run_server(host: str = "localhost", port: int = 8000, log_level: str = "info"):
    """
    Configure et démarre le serveur A2A pour le EvaluatorAgent.
    """
    logger.info(f"Démarrage de l'EvaluatorAgentServer à l'adresse http://{host}:{port}")

    evaluator_executor = EvaluatorAgentExecutor()
    task_store = InMemoryTaskStore()
    request_handler = DefaultRequestHandler(
    agent_executor=evaluator_executor,
    task_store=task_store
    )
    agent_card = get_evaluator_agent_card(host, port)
    a2a_server_app = A2AStarletteApplication(
    agent_card=agent_card,
    http_handler=request_handler
    )
    asgi_app = a2a_server_app.build()
    config = uvicorn.Config(
    app=asgi_app,
    host=host,
    port=port,
    log_level=log_level.lower(),
    lifespan="auto"
    )
    uvicorn_instance = uvicorn.Server(config)

    try:
        await uvicorn_instance.serve()
    except KeyboardInterrupt:
        logger.info("Arrêt du serveur demandé par l'utilisateur (KeyboardInterrupt).")
    finally:
        logger.info("Serveur Uvicorn arrêté.")


if __name__ == "__main__":
    print("Lancement du serveur EvaluatorAgent...")
    # Choisir un port différent du ReformulatorAgentServer
    SERVER_HOST = "localhost"
    SERVER_PORT = 8002 # Par exemple, 8002 pour l'évaluateur

    logger.info("Pour lancer le serveur, assurez-vous d'avoir 'uvicorn' et les dépendances serveur A2A installés.")
    logger.info(f"Exemple: pip install uvicorn a2a-sdk[server]")

    try:
        asyncio.run(run_server(host=SERVER_HOST, port=SERVER_PORT))
    except Exception as e:
        logger.error(f"Erreur lors du lancement du serveur: {e}", exc_info=True)