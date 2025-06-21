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
from starlette.routing import Route
from starlette.responses import JSONResponse

# --- 1. Import du nouveau handler ---
from src.shared.log_handler import InMemoryLogHandler

from src.shared.service_discovery import get_gra_base_url, register_self_with_gra
from .executor import DevelopmentAgentExecutor
from .logic import AGENT_SKILL_CODING_PYTHON

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- 2. Initialisation et configuration du logging ---
in_memory_log_handler = InMemoryLogHandler(maxlen=200)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
in_memory_log_handler.setFormatter(formatter)
logging.getLogger().addHandler(in_memory_log_handler)
logging.getLogger().setLevel(logging.INFO)

AGENT_NAME = "DevelopmentAgentServer"

def get_development_agent_card() -> AgentCard:
    agent_url = os.environ.get("PUBLIC_URL", f"http://localhost_placeholder_for_{AGENT_NAME}:8080")
    
    capabilities = AgentCapabilities(streaming=False)
    skills_objects = [
        AgentSkill(
            id=AGENT_SKILL_CODING_PYTHON,
            name="Python Code Generation",
            description="Generates Python code based on specifications.",
            tags=["coding", "python", "development", "software_engineering"],
            examples=[
                '{"objective": "Create a function to sum two numbers", "local_instructions": ["Must handle integers and floats"], "acceptance_criteria": ["Returns 5 for inputs 2 and 3"]}'
            ]
        ),
    ]
    
    return AgentCard(
        name="Software Development Agent",
        description="Agent specialized in writing and modifying source code.",
        url=agent_url,
        version="0.1.0",
        defaultInputModes=["application/json"],
        defaultOutputModes=["text/plain"],
        capabilities=capabilities,
        skills=skills_objects
    )

agent_executor = DevelopmentAgentExecutor()
task_store = InMemoryTaskStore()
request_handler = DefaultRequestHandler(agent_executor=agent_executor, task_store=task_store)

# --- 3. Création de l'endpoint /logs ---
async def logs_endpoint(request):
    """Retourne les dernières lignes de log de l'agent."""
    return JSONResponse(content=in_memory_log_handler.get_logs())

@contextlib.asynccontextmanager
async def lifespan(app_param: Starlette):
    logger.info(f"[{AGENT_NAME}] Démarrage du cycle de vie (lifespan)...")
    
    agent_public_url = os.environ.get("PUBLIC_URL")
    agent_internal_url = os.environ.get("INTERNAL_URL")
    
    if agent_public_url and agent_internal_url:
        try:
            agent_card = get_development_agent_card()
            skill_ids = [skill.id for skill in agent_card.skills] if agent_card.skills else []
            logger.info(f"[{AGENT_NAME}] URLs détectées. Tentative d'enregistrement avec les compétences : {skill_ids}")
            await register_self_with_gra(AGENT_NAME, agent_public_url, agent_internal_url, skill_ids)
            await agent_executor._notify_gra_of_status_change()
        except Exception as e:
            logger.error(f"[{AGENT_NAME}] L'enregistrement auprès du GRA a échoué durant le démarrage : {e}", exc_info=True)
    else:
        logger.warning(f"[{AGENT_NAME}] PUBLIC_URL ou INTERNAL_URL manquant. Le serveur démarre en mode passif sans s'enregistrer.")

    yield
    
    logger.info(f"[{AGENT_NAME}] Serveur en cours d'arrêt.")

def create_app_instance() -> Starlette:
    agent_card = get_development_agent_card()
    a2a_app = A2AStarletteApplication(agent_card=agent_card, http_handler=request_handler)
    app = a2a_app.build()

    logger.info(f"Routes enregistrées après a2a_app.build(): {[str(r.path) + ' (' + str(r.methods) + ')' for r in app.router.routes]}")

    async def health_check_endpoint(request):
        return JSONResponse({"status": "ok"})
    async def status_endpoint(request):
        """Retourne le statut opérationnel détaillé de l'agent."""
        if not agent_executor:
            return JSONResponse({"state": "Error", "message": "Executor not initialized"}, status_code=500)
        return JSONResponse(agent_executor.get_status())
        
    app.router.routes.append(
        Route("/health", endpoint=health_check_endpoint, methods=["GET"])
    )
    app.router.routes.append(
        Route("/status", endpoint=status_endpoint, methods=["GET"])
    )

    # --- 4. Ajout de la nouvelle route ---
    app.router.routes.append(
        Route("/logs", endpoint=logs_endpoint, methods=["GET"])
    )

    app.router.lifespan_context = lifespan

    return app

app = create_app_instance()

from starlette.responses import PlainTextResponse

async def debug_env_endpoint(request):
    # Vérifie la variable d'environnement
    ca_cert_env = os.environ.get("GKE_SSL_CA_CERT", "Non défini")
    
    # Vérifie la présence du fichier
    ca_pem_path = ca_cert_env if os.path.isfile(ca_cert_env) else "Fichier introuvable"

    # Affiche quelques variables utiles
    env_vars = {
        "GKE_CLUSTER_ENDPOINT": os.environ.get("GKE_CLUSTER_ENDPOINT", "Non défini"),
        "GKE_SSL_CA_CERT": ca_cert_env,
        "Fichier ca.pem trouvé à": ca_pem_path
    }
    
    output = "\n".join([f"{key}: {value}" for key, value in env_vars.items()])
    return PlainTextResponse(output)

# Ajoute la route dans app
app.router.routes.append(
    Route("/debug/env", endpoint=debug_env_endpoint, methods=["GET"])
)

if __name__ == "__main__":
    is_production = 'K_SERVICE' in os.environ
    port = int(os.environ.get("PORT", 8080))
    host = "0.0.0.0" if is_production else "localhost"
    
    logger.info(f"Démarrage du serveur Uvicorn pour {AGENT_NAME} sur {host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="info")