import asyncio
import logging
from src.services.environment_manager import KubernetesEnvironmentManager, FALLBACK_ENV_ID

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

async def main():
    manager = KubernetesEnvironmentManager()
    env_id = FALLBACK_ENV_ID
    logging.info(f"Creating fallback environment '{env_id}' if needed...")
    created = await manager.create_isolated_environment(env_id)
    if created:
        logging.info(f"Fallback environment '{created}' ready. Verify with kubectl or /health endpoint.")
    else:
        logging.error("Failed to create fallback environment.")

if __name__ == '__main__':
    asyncio.run(main())
