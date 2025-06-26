import os
import httpx

class EnvironmentHelper:
    def __init__(self, base_url: str | None = None):
        self.base_url = base_url or os.environ.get("ENV_MANAGER_URL", "http://environment-manager.default.svc.cluster.local:8080")
        self.client = httpx.AsyncClient()

    async def create_environment(self, environment_id: str, base_image: str | None = None):
        payload = {"environment_id": environment_id}
        if base_image:
            payload["base_image"] = base_image
        resp = await self.client.post(f"{self.base_url}/create_environment", json=payload, timeout=30)
        resp.raise_for_status()
        return resp.json()

    async def exec_in_environment(self, environment_id: str, command: str):
        payload = {"environment_id": environment_id, "command": command}
        resp = await self.client.post(f"{self.base_url}/exec_in_environment", json=payload, timeout=60)
        resp.raise_for_status()
        return resp.json()

    async def upload_to_environment(self, environment_id: str, path: str, content: str):
        payload = {"environment_id": environment_id, "path": path, "content": content}
        resp = await self.client.post(f"{self.base_url}/upload_to_environment", json=payload, timeout=60)
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
        resp = await self.client.post(f"{self.base_url}/upload_to_cloud_and_index", json=payload, timeout=60)
        resp.raise_for_status()
        return resp.json()

    async def close(self):
        await self.client.aclose()
