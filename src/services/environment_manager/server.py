import os
import logging
import contextlib
from datetime import datetime
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn
import httpx
import asyncio

from src.shared.agent_state import AgentOperationalState
from src.shared.service_discovery import get_gra_base_url, register_self_with_gra
from .logic import EnvironmentManager

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

manager = EnvironmentManager()
state = {
    "state": AgentOperationalState.IDLE.value,
    "detail": "idle",
    "last_update": datetime.utcnow().isoformat(),
}

async def notify_state():
    gra_url = await get_gra_base_url()
    if not gra_url:
        return
    payload = state.copy()
    payload["name"] = "EnvironmentManager"
    async with httpx.AsyncClient() as client:
        try:
            await client.post(f"{gra_url}/agent_status_update", json=payload, timeout=5.0)
        except Exception as e:
            logger.error(f"Failed to notify GRA: {e}")

class CreateEnv(BaseModel):
    environment_id: str
    base_image: str | None = None

class ExecCommand(BaseModel):
    environment_id: str
    command: str

class FilePayload(BaseModel):
    environment_id: str
    path: str
    content: str | None = None

class CloudUpload(BaseModel):
    environment_id: str
    path: str
    bucket: str
    destination: str
    execution_plan_id: str | None = None
    task_id: str | None = None

app = FastAPI()

@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    public_url = os.environ.get("PUBLIC_URL")
    internal_url = os.environ.get("INTERNAL_URL")
    if public_url and internal_url:
        await register_self_with_gra("EnvironmentManager", public_url, internal_url, ["environment_manager"])
        await notify_state()
    yield

app.router.lifespan_context = lifespan

@app.post("/create_environment")
async def create_environment(data: CreateEnv):
    env_id = await manager.create_isolated_environment(data.environment_id, data.base_image or "python:3.11")
    if not env_id:
        raise HTTPException(status_code=500, detail="creation failed")
    state.update({"state": AgentOperationalState.WORKING.value, "detail": f"created {env_id}", "last_update": datetime.utcnow().isoformat()})
    await notify_state()
    return {"environment_id": env_id}

@app.post("/delete_environment")
async def delete_environment(data: CreateEnv):
    await manager.destroy_environment(data.environment_id)
    state.update({"state": AgentOperationalState.WORKING.value, "detail": f"deleted {data.environment_id}", "last_update": datetime.utcnow().isoformat()})
    await notify_state()
    return {"deleted": data.environment_id}

@app.post("/exec_in_environment")
async def exec_in_environment(data: ExecCommand):
    result = await manager.safe_execute_command_in_environment(data.environment_id, data.command)
    return result

@app.post("/upload_to_environment")
async def upload_to_environment(data: FilePayload):
    await manager.write_file_to_environment(data.environment_id, data.path, data.content or "")
    return {"uploaded": data.path}

@app.post("/download_from_environment")
async def download_from_environment(data: FilePayload):
    content = await manager.read_file_from_environment(data.environment_id, data.path)
    return {"content": content}

@app.post("/upload_to_cloud_and_index")
async def upload_to_cloud_and_index(data: CloudUpload):
    result = await manager.upload_to_cloud_and_index(data.environment_id, data.path, data.bucket, data.destination, data.execution_plan_id, data.task_id)
    return result

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/status")
async def status():
    return state

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
