import docker
import asyncio
import os
import io
import tarfile
import logging
import json
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

FALLBACK_ENV_ID = "exec_default"

class DockerEnvironmentManager:
    """Simpler environment manager using local Docker containers."""
    def __init__(self, base_image: str | None = None):
        self.client = docker.from_env()
        self.base_image = base_image or os.environ.get("DEV_ENV_BASE_IMAGE", "python:3.11-slim-buster")
        self.environments: Dict[str, Dict[str, Any]] = {}

    @staticmethod
    def normalize_environment_id(env_id: str) -> str:
        return env_id.replace("/", "_")

    async def create_isolated_environment(self, environment_id: str, base_image: str | None = None) -> str:
        env_id = self.normalize_environment_id(environment_id)
        return await asyncio.to_thread(self._create_env_sync, env_id, base_image or self.base_image)

    def _create_env_sync(self, env_id: str, image: str) -> str:
        volume_name = f"env_{env_id}_vol"
        try:
            volume = self.client.volumes.get(volume_name)
        except docker.errors.NotFound:
            volume = self.client.volumes.create(volume_name)
        try:
            container = self.client.containers.get(env_id)
            container.stop()
            container.remove()
        except docker.errors.NotFound:
            pass
        container = self.client.containers.run(
            image,
            detach=True,
            name=env_id,
            volumes={volume_name: {"bind": "/app", "mode": "rw"}},
            tty=True,
            command="/bin/bash",
        )
        self.environments[env_id] = {"container": container, "volume": volume}
        logger.info(f"Docker environment '{env_id}' created using {image}")
        return env_id

    async def destroy_environment(self, environment_id: str) -> None:
        env_id = self.normalize_environment_id(environment_id)
        await asyncio.to_thread(self._destroy_env_sync, env_id)

    def _destroy_env_sync(self, env_id: str) -> None:
        info = self.environments.get(env_id)
        if not info:
            return
        container = info["container"]
        volume = info["volume"]
        try:
            container.stop()
            container.remove()
        except docker.errors.NotFound:
            pass
        try:
            volume.remove()
        except docker.errors.NotFound:
            pass
        self.environments.pop(env_id, None)
        logger.info(f"Docker environment '{env_id}' destroyed")

    async def execute_command_in_environment(self, environment_id: str, command: str, workdir: str = "/app") -> Dict[str, Any]:
        env_id = self.normalize_environment_id(environment_id)
        return await asyncio.to_thread(self._exec_sync, env_id, command, workdir)

    def _exec_sync(self, env_id: str, command: str, workdir: str) -> Dict[str, Any]:
        container = self.environments[env_id]["container"]
        exit_code, output = container.exec_run(command, workdir=workdir)
        stdout = output.decode("utf-8", errors="ignore")
        return {"stdout": stdout, "stderr": "", "exit_code": exit_code}

    async def write_file_to_environment(self, environment_id: str, file_path: str, content: str) -> Dict[str, Any]:
        env_id = self.normalize_environment_id(environment_id)
        await asyncio.to_thread(self._write_file_sync, env_id, file_path, content)
        return {"status": "success", "file_path": file_path}

    def _write_file_sync(self, env_id: str, file_path: str, content: str) -> None:
        container = self.environments[env_id]["container"]
        dir_name = os.path.dirname(file_path) or "/"
        container.exec_run(f"mkdir -p {dir_name}")
        tar_stream = io.BytesIO()
        with tarfile.open(fileobj=tar_stream, mode="w") as tar:
            data = content.encode("utf-8")
            tarinfo = tarfile.TarInfo(name=os.path.basename(file_path))
            tarinfo.size = len(data)
            tar.addfile(tarinfo, io.BytesIO(data))
        tar_stream.seek(0)
        container.put_archive(path=dir_name, data=tar_stream.read())

    async def read_file_from_environment(self, environment_id: str, file_path: str) -> str:
        env_id = self.normalize_environment_id(environment_id)
        return await asyncio.to_thread(self._read_file_sync, env_id, file_path)

    def _read_file_sync(self, env_id: str, file_path: str) -> str:
        container = self.environments[env_id]["container"]
        exit_code, output = container.exec_run(f"cat {file_path}")
        if exit_code != 0:
            raise FileNotFoundError(f"File '{file_path}' not found in environment '{env_id}'")
        return output.decode("utf-8", errors="ignore")

    async def list_files_in_environment(self, environment_id: str, path: str = ".") -> List[Dict[str, Any]]:
        cmd = (
            "find . -maxdepth 1 -mindepth 1 "
            "-exec stat -c '{\"name\":\"%n\", \"type\":\"%F\", \"size\":%s, \"mtime\":%Y}' {} \\; | jq -s ."
        )
        result = await self.execute_command_in_environment(environment_id, cmd, workdir=path)
        if result.get("exit_code") != 0:
            stderr = result.get("stderr", "")
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
        try:
            await self.create_isolated_environment(target_env)
            return target_env
        except Exception:
            logger.warning(f"Environment '{target_env}' unavailable, falling back to '{fallback_id}'.")
            await self.create_isolated_environment(fallback_id)
            return fallback_id

    async def start_background_tasks(self):
        pass

