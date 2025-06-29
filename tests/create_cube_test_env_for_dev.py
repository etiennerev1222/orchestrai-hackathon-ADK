
import asyncio
from src.services.environment_manager import KubernetesEnvironmentManager
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def create_test_env():
    env_manager = KubernetesEnvironmentManager()
    test_env_id = "my-test-env-001"
    test_env_id = "exec-gplan_d68b67c75b22"
    logger.info(f"Attempting to create environment '{test_env_id}'...")
    created_env_id = await env_manager.create_isolated_environment(test_env_id)
    
    if created_env_id:
        logger.info(f"Environment '{created_env_id}' created successfully on GKE. You can now try calling the agent.")
    else:
        logger.error(f"Failed to create environment '{test_env_id}'. Check GKE permissions.")

if __name__ == "__main__":
    asyncio.run(create_test_env())