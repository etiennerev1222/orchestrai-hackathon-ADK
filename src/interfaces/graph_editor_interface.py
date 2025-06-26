import logging
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.shared.execution_task_graph_management import (
    ExecutionTaskGraph,
    ExecutionTaskNode,
    ExecutionTaskType,
)

logger = logging.getLogger(__name__)
router = APIRouter()

class TaskCreate(BaseModel):
    id: str
    objective: str
    task_type: ExecutionTaskType
    parent_id: Optional[str] = None
    dependencies: List[str] = []
    assigned_agent_type: Optional[str] = None
    meta: Optional[Dict[str, Any]] = None

class TaskUpdate(BaseModel):
    objective: Optional[str] = None
    task_type: Optional[ExecutionTaskType] = None
    assigned_agent_type: Optional[str] = None
    meta: Optional[Dict[str, Any]] = None

class LinkRequest(BaseModel):
    from_id: str
    to_id: str

class ToggleEditMode(BaseModel):
    enabled: bool
    user_id: Optional[str] = None

@router.get("/execution_graph/{execution_plan_id}")
async def get_execution_graph(execution_plan_id: str):
    graph = ExecutionTaskGraph(execution_plan_id)
    return graph.as_dict()

@router.post("/execution_graph/{execution_plan_id}/add_task")
async def add_task(execution_plan_id: str, task: TaskCreate):
    graph = ExecutionTaskGraph(execution_plan_id)
    node = ExecutionTaskNode(
        task_id=task.id,
        objective=task.objective,
        task_type=task.task_type,
        parent_id=task.parent_id,
        dependencies=task.dependencies,
        assigned_agent_type=task.assigned_agent_type,
        meta=task.meta,
    )
    graph.add_task(node, is_root=task.parent_id is None)
    logger.info(f"[GraphEditor] Added task {task.id} to {execution_plan_id}")
    return {"added": task.id}

@router.patch("/execution_graph/{execution_plan_id}/edit_task/{task_id}")
async def edit_task(execution_plan_id: str, task_id: str, updates: TaskUpdate):
    graph = ExecutionTaskGraph(execution_plan_id)
    try:
        node = graph.edit_task(task_id, updates.dict(exclude_none=True))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    logger.info(f"[GraphEditor] Edited task {task_id} in {execution_plan_id}")
    return node.to_dict()

@router.post("/execution_graph/{execution_plan_id}/delete_task/{task_id}")
async def delete_task(execution_plan_id: str, task_id: str):
    graph = ExecutionTaskGraph(execution_plan_id)
    try:
        graph.delete_task(task_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    logger.info(f"[GraphEditor] Deleted task {task_id} from {execution_plan_id}")
    return {"deleted": task_id}

@router.post("/execution_graph/{execution_plan_id}/link_tasks")
async def link_tasks(execution_plan_id: str, data: LinkRequest):
    graph = ExecutionTaskGraph(execution_plan_id)
    try:
        graph.link_tasks(data.from_id, data.to_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    logger.info(
        f"[GraphEditor] Linked {data.from_id} -> {data.to_id} in {execution_plan_id}"
    )
    return {"linked": True}

@router.post("/execution_graph/{execution_plan_id}/unlink_tasks")
async def unlink_tasks(execution_plan_id: str, data: LinkRequest):
    graph = ExecutionTaskGraph(execution_plan_id)
    graph.unlink_tasks(data.from_id, data.to_id)
    logger.info(
        f"[GraphEditor] Unlinked {data.from_id} -/-> {data.to_id} in {execution_plan_id}"
    )
    return {"unlinked": True}

@router.get("/execution_graph/{execution_plan_id}/validate")
async def validate_graph(execution_plan_id: str):
    graph = ExecutionTaskGraph(execution_plan_id)
    try:
        valid = graph.validate_graph()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"valid": valid}

@router.post("/execution_graph/{execution_plan_id}/toggle_edit_mode")
async def toggle_edit_mode(execution_plan_id: str, data: ToggleEditMode):
    graph = ExecutionTaskGraph(execution_plan_id)
    graph.set_edit_mode(data.enabled, data.user_id)
    logger.info(
        f"[GraphEditor] Edit mode set to {data.enabled} for {execution_plan_id} by {data.user_id}"
    )
    return {"edit_mode": graph.get_edit_mode()}

@router.get("/execution_graph/{execution_plan_id}/edit_mode")
async def get_edit_mode(execution_plan_id: str):
    graph = ExecutionTaskGraph(execution_plan_id)
    return {"edit_mode": graph.get_edit_mode()}
