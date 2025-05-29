# my_simple_a2a_service/reformulator_server/main_server.py

import asyncio
import logging
import uvicorn # Pour exécuter notre application ASGI

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

# Importation de notre AgentExecutor
from .executor import ReformulatorAgentExecutor

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


async def run_server(host: str = "localhost", port: int = 8000, log_level: str = "info"):
    """
    Configure et démarre le serveur A2A pour le ReformulatorAgent.
    """
    logger.info(f"Démarrage du ReformulatorAgentServer à l'adresse http://{host}:{port}")

    # 1. Créer l'instance de notre AgentExecutor
    reformulator_executor = ReformulatorAgentExecutor()

    # 2. Créer un gestionnaire de tâches (simple, en mémoire pour ce démo)
    task_store = InMemoryTaskStore()

    # 3. Créer le gestionnaire de requêtes par défaut, en lui passant notre exécuteur et le task_store
    request_handler = DefaultRequestHandler(
        agent_executor=reformulator_executor,
        task_store=task_store
    )

    # 4. Obtenir la carte d'agent
    agent_card = get_reformulator_agent_card(host, port)

    # 5. Créer l'application serveur A2A (basée sur Starlette)
    # Cette application gère les routes HTTP, la communication A2A, etc.
    a2a_server_app = A2AStarletteApplication(
        agent_card=agent_card,
        http_handler=request_handler
        # D'autres options de configuration peuvent être passées ici si nécessaire
    )

    # 6. Construire l'application ASGI à partir de notre serveur A2A
    # L'application ASGI est ce que uvicorn va exécuter.
    asgi_app = a2a_server_app.build()

    # 7. Configuration d'Uvicorn
    # Uvicorn est un serveur ASGI (Asynchronous Server Gateway Interface) ultra-rapide.
    config = uvicorn.Config(
        app=asgi_app,
        host=host,
        port=port,
        log_level=log_level.lower(),
        lifespan="auto" # Gère le cycle de vie de l'application (démarrage/arrêt)
    )

    # 8. Créer et démarrer le serveur Uvicorn
    uvicorn_instance = uvicorn.Server(config)
    
    try:
        await uvicorn_instance.serve()
    except KeyboardInterrupt:
        logger.info("Arrêt du serveur demandé par l'utilisateur (KeyboardInterrupt).")
    finally:
        logger.info("Serveur Uvicorn arrêté.")


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


