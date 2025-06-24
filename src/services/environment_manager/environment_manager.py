import os
import logging
import httpx
import asyncio
import json
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

FALLBACK_ENV_ID = "exec_default"

class EnvironmentManager:
    """HTTP client wrapper for the Environment Manager service."""

    def __init__(self, base_url: Optional[str] = None):
        self.base_url = base_url or os.environ.get(
            "ENV_MANAGER_URL",
            "http://environment-manager.default.svc.cluster.local:8080",
        )
        self.client = httpx.AsyncClient()

    @staticmethod
    def extract_global_plan_id(plan_id: str) -> str:
        if plan_id == "N/A":
            return "default"
        import re
        match = re.search(r"gplan_[a-f0-9]+", plan_id)
        return match.group(0) if match else "default"

    @staticmethod
    def normalize_environment_id(plan_id: str) -> str:
        return f"exec-{EnvironmentManager.extract_global_plan_id(plan_id)}"

    async def _post(self, endpoint: str, payload: Dict[str, Any], timeout: int = 30) -> Dict[str, Any]:
        url = f"{self.base_url.rstrip('/')}/{endpoint.lstrip('/')}"
        try:
            resp = await self.client.post(url, json=payload, timeout=timeout)
            resp.raise_for_status()
            if resp.content:
                return resp.json()
            return {}
        except Exception as e:
            logger.error(f"Request to {url} failed: {e}")
            raise

    async def create_isolated_environment(self, environment_id: str, base_image: str = "python:3.11") -> Optional[str]:
        payload = {"environment_id": self.normalize_environment_id(environment_id), "base_image": base_image}
        try:
            data = await self._post("create_environment", payload)
            return data.get("environment_id")
        except Exception:
            return None

    async def destroy_environment(self, environment_id: str) -> None:
        payload = {"environment_id": self.normalize_environment_id(environment_id)}
        try:
            await self._post("delete_environment", payload)
        except Exception:
            pass

    async def execute_command_in_environment(self, environment_id: str, command: str, workdir: str = "/app") -> Dict[str, Any]:
        cmd = f"cd {workdir} && {command}" if workdir else command
        payload = {"environment_id": self.normalize_environment_id(environment_id), "command": cmd}
        return await self._post("exec_in_environment", payload, timeout=60)

    async def write_file_to_environment(self, environment_id: str, file_path: str, content: str) -> None:
        payload = {"environment_id": self.normalize_environment_id(environment_id), "path": file_path, "content": content}
        await self._post("upload_to_environment", payload, timeout=60)

    async def read_file_from_environment(self, environment_id: str, file_path: str) -> str:
        payload = {"environment_id": self.normalize_environment_id(environment_id), "path": file_path}
        data = await self._post("download_from_environment", payload)
        return data.get("content", "")

    async def list_files_in_environment(self, environment_id: str, path: str = ".") -> List[Dict[str, Any]]:
        cmd_str = (
            "find . -maxdepth 1 -mindepth 1 "
            "-exec stat -c '{\"name\":\"%n\", \"type\":\"%F\", \"size\":%s, \"mtime\":%Y}' {} \\; | jq -s ."
        )
        result = await self.execute_command_in_environment(environment_id, cmd_str, workdir=path)
        if result.get("exit_code") != 0:
            stderr = result.get("stderr", "")
            if "No such file" in stderr:
                raise FileNotFoundError(f"Path '{path}' not found in environment '{environment_id}'")
            raise RuntimeError(f"Failed to list files: {stderr}")
        stdout = result.get("stdout", "")
        if not stdout:
            return []
        file_list_raw = json.loads(stdout)
        formatted_list = []
        for item in file_list_raw:
            raw_type = str(item.get("type", ""))
            if raw_type == "directory":
                mapped_type = "directory"
            elif "file" in raw_type:
                mapped_type = "file"
            elif "link" in raw_type:
                mapped_type = "link"
            else:
                mapped_type = "unknown"
            formatted_list.append({
                "name": item.get("name"),
                "type": mapped_type,
                "size": int(item.get("size", 0)),
                "last_modified": int(float(item.get("mtime", 0)))
            })
        return formatted_list

    async def get_environment_or_fallback(self, plan_id: str, fallback_id: str = FALLBACK_ENV_ID) -> str:
        target_env = self.normalize_environment_id(plan_id)
        created = await self.create_isolated_environment(target_env)
        if not created:
            logger.warning(f"Environment '{target_env}' unavailable, falling back to '{fallback_id}'.")
            await self.create_isolated_environment(fallback_id)
            return fallback_id
        return target_env

    async def safe_tool_call(self, tool_coro, description: str, timeout_sec: int = 60) -> Dict[str, Any]:
        try:
            result = await asyncio.wait_for(tool_coro, timeout=timeout_sec)
            return result
        except asyncio.TimeoutError:
            msg = f"Tool timeout for: {description}"
            logger.error(msg)
            return {"error": msg}
        except Exception as e:
            msg = f"Error calling tool ({description}): {str(e)}"
            logger.error(msg)
            return {"error": msg}

    async def safe_execute_command_in_environment(self, environment_id: str, command: str, workdir: str = "/app") -> Dict[str, Any]:
        return await self.safe_tool_call(
            self.execute_command_in_environment(environment_id, command, workdir),
            f"execute_command_in_environment: {command}"
        )

    async def close(self):
        await self.client.aclose()
