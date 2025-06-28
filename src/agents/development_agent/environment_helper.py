import os
import httpx
import logging # Ajout de logging pour les messages de debug

logger = logging.getLogger(__name__)

class EnvironmentHelper:
    def __init__(self, base_url: str | None = None, auth_token: str | None = None):
        self.base_url = base_url or os.environ.get("ENV_MANAGER_URL", "http://environment-manager.default.svc.cluster.local:8080")
        self.auth_token = auth_token # Stocke le jeton d'authentification
        self.client = httpx.AsyncClient()

    # Méthode utilitaire pour construire les en-têtes
    def _get_headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
            logger.debug("Authorization header added to request.")
        else:
            logger.warning("No auth_token provided for EnvironmentHelper. Requests might fail if authentication is required.")
        return headers

    async def create_environment(self, environment_id: str, base_image: str | None = None):
        payload = {"environment_id": environment_id}
        if base_image:
            payload["base_image"] = base_image
        resp = await self.client.post(f"{self.base_url}/create_environment", json=payload, headers=self._get_headers(), timeout=30)
        resp.raise_for_status()
        return resp.json()

    async def exec_in_environment(self, environment_id: str, command: str):
        payload = {"environment_id": environment_id, "command": command}
        resp = await self.client.post(f"{self.base_url}/exec_in_environment", json=payload, headers=self._get_headers(), timeout=60)
        resp.raise_for_status()
        return resp.json()

    async def upload_to_environment(self, environment_id: str, path: str, content: str):
        payload = {"environment_id": environment_id, "path": path, "content": content}
        resp = await self.client.post(f"{self.base_url}/upload_to_environment", json=payload, headers=self._get_headers(), timeout=60)
        resp.raise_for_status()
        return resp.json()

    async def upload_to_cloud_and_index(self, environment_id: str, path: str, bucket: str, destination: str, execution_plan_id: str | None = None, task_id: str | None = None):
        payload = {
            "environment_id": environment_id,
            "path": path,
            "bucket": bucket,
            "destination": destination,
            "execution_plan_id": execution_plan_id,
            "task_id": task_id,
        }
        resp = await self.client.post(f"{self.base_url}/upload_to_cloud_and_index", json=payload, headers=self._get_headers(), timeout=60)
        resp.raise_for_status()
        return resp.json()

    async def close(self):
        await self.client.aclose()
