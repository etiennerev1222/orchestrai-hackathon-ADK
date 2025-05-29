# src/agents/validator/server.py

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

from .executor import ValidatorAgentExecutor

logger = logging.getLogger(__name__)
if not logger.hasHandlers():
    logging.basicConfig(level=logging.INFO)


def get_validator_agent_card(host: str, port: int) -> AgentCard:
    """
    Crée et retourne la "carte d'agent" pour notre ValidatorAgent.
    """
    capabilities = AgentCapabilities(
        streaming=False,
        push_notifications=False
    )

    validation_skill = AgentSkill(
        id="plan_validation",
        name="Validate Plan",
        description="Validates a plan based on evaluation results and specific criteria.",
        tags=["decision", "validation", "planning_gate"],
        examples=[
            "Validate this evaluated plan: [JSON output from Evaluator Agent]"
        ]
    )

    agent_card = AgentCard(
        name="Plan Validator Agent",
        description="An A2A agent that validates evaluated plans.",
        url=f"http://{host}:{port}/",
        version="0.1.0",
        defaultInputModes=["application/json"],  # Attend du JSON (l'artefact de l'évaluateur)
        defaultOutputModes=["application/json"],  # Retourne un JSON (le résultat de la validation)
        capabilities=capabilities,
        skills=[validation_skill]
    )
    logger.info(f"Agent Card créée: {agent_card.name} accessible à {agent_card.url}")
    return agent_card


async def run_server(host: str = "localhost", port: int = 8003, log_level: str = "info"):  # Port 8003
    """
    Configure et démarre le serveur A2A pour le ValidatorAgent.
    """
    logger.info(f"Démarrage du ValidatorAgentServer à l'adresse http://{host}:{port}")

    validator_executor = ValidatorAgentExecutor()
    task_store = InMemoryTaskStore()
    request_handler = DefaultRequestHandler(
        agent_executor=validator_executor,
        task_store=task_store
    )
    agent_card = get_validator_agent_card(host, port)
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
    SERVER_HOST = "localhost"
    SERVER_PORT = 8003  # Port différent pour cet agent

    logger.info("Pour lancer le serveur, assurez-vous d'avoir 'uvicorn' et les dépendances serveur A2A installés.")

    try:
        asyncio.run(run_server(host=SERVER_HOST, port=SERVER_PORT))
    except Exception as e:
        logger.error(f"Erreur lors du lancement du serveur: {e}", exc_info=True)
