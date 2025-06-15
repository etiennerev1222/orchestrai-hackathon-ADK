# Ce code est juste pour démonstration et ne fait pas partie du script shell.
# C'est un exemple de script Python que vous pourriez exécuter une fois
# pour créer l'environnement avant de lancer le curl.

import asyncio
from src.services.environment_manager.environment_manager import EnvironmentManager
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def create_test_env():
    env_manager = EnvironmentManager()
    test_env_id = "my-test-env-001" # Doit correspondre à celui dans votre payload JSON
    
    logger.info(f"Attempting to create environment '{test_env_id}'...")
    created_env_id = await env_manager.create_isolated_environment(test_env_id)
    
    if created_env_id:
        logger.info(f"Environment '{created_env_id}' created successfully on GKE. You can now try calling the agent.")
        # Optional: You could list pods to verify
        # await env_manager.execute_command_in_environment(test_env_id, "ls -l /")
    else:
        logger.error(f"Failed to create environment '{test_env_id}'. Check GKE permissions.")

if __name__ == "__main__":
    asyncio.run(create_test_env())