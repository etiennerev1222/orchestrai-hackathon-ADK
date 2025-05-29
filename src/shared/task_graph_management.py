from typing import Optional, Dict, List, Any
from enum import Enum
import json
from datetime import datetime
import uuid


class TaskState(str, Enum):
    SUBMITTED = "submitted"
    WORKING = "working"
    COMPLETED = "completed"
    FAILED = "failed"
    UNABLE = "unable_to_complete"
    CANCELLED = "cancelled"


class TaskNode:
    def __init__(
        self,
        task_id: str,
        parent: Optional[str] = None,
        assigned_agent: Optional[str] = None,
        objective: Optional[str] = None,
        expected_result: Optional[Any] = None,
        meta: Optional[Dict[str, Any]] = None,
        artifact_ref: Optional[Any] = None,
    ):
        self.id: str = task_id
        self.parent: Optional[str] = parent
        self.children: List[str] = []
        self.state: TaskState = TaskState.SUBMITTED
        self.assigned_agent: Optional[str] = assigned_agent
        self.objective: Optional[str] = objective
        self.expected_result: Optional[Any] = expected_result
        self.artifact_ref: Optional[Any] = artifact_ref
        self.history: List[Dict[str, Any]] = []
        self.meta: Dict[str, Any] = meta if meta is not None else {}

    def update_state(self, new_state: TaskState, details: Optional[str] = None) -> bool:
        now = datetime.utcnow().isoformat()
        old_state = self.state
        self.history.append({
            "from_state": str(old_state.value),
            "to_state": str(new_state.value),
            "timestamp": now,
            "details": details
        })
        self.state = new_state
        return old_state != new_state and new_state in [
            TaskState.FAILED, TaskState.UNABLE, TaskState.CANCELLED
        ]

    def __repr__(self):
        return (
            f"TaskNode(id='{self.id}', objective='{self.objective}', state='{self.state.value}', "
            f"parent='{self.parent}', children={self.children}, assigned_agent='{self.assigned_agent}')"
        )


class TaskGraph:
    def __init__(self):
        self.nodes: Dict[str, TaskNode] = {}
        self.roots: List[str] = []

    def add_task(self, task_id: str, parent_id: Optional[str] = None, objective: Optional[str] = None, **kwargs):
        if task_id in self.nodes:
            node = self.nodes[task_id]
            if parent_id and parent_id not in self.nodes:
                raise ValueError(f"Parent task with id {parent_id} does not exist.")
            if objective:
                node.objective = objective
            for key, value in kwargs.items():
                if hasattr(node, key):
                    setattr(node, key, value)
        else:
            node = TaskNode(task_id, parent=parent_id, objective=objective, **kwargs)
            self.nodes[task_id] = node
            if parent_id:
                if parent_id not in self.nodes:
                    raise ValueError(f"Parent task with id {parent_id} does not exist for new task {task_id}.")
                parent_node = self.nodes[parent_id]
                if task_id not in parent_node.children:
                    parent_node.children.append(task_id)
            else:
                if task_id not in self.roots:
                    self.roots.append(task_id)
        return node

    def remove_task(self, task_id: str):
        if task_id not in self.nodes:
            return

        node_to_remove = self.nodes[task_id]

        for child_id in list(node_to_remove.children):
            self.remove_task(child_id)

        if node_to_remove.parent and node_to_remove.parent in self.nodes:
            parent_node = self.nodes[node_to_remove.parent]
            if task_id in parent_node.children:
                parent_node.children.remove(task_id)

        del self.nodes[task_id]

        if task_id in self.roots:
            self.roots.remove(task_id)

    def update_state(self, task_id: str, state: TaskState, details: Optional[str] = None):
        if task_id not in self.nodes:
            raise ValueError(f"Task with id {task_id} not found.")
        node = self.nodes[task_id]

        state_changed_and_requires_propagation = node.update_state(state, details)

        if state_changed_and_requires_propagation:
            for child_id in node.children:
                if self.nodes[child_id].state not in [
                    TaskState.COMPLETED, TaskState.FAILED, TaskState.UNABLE, TaskState.CANCELLED
                ]:
                    self.update_state(child_id, TaskState.CANCELLED, "Parent task failed, was unable to complete, or was cancelled.")

    def assign_agent(self, task_id: str, agent_name: str):
        if task_id not in self.nodes:
            raise ValueError(f"Task with id {task_id} not found.")
        self.nodes[task_id].assigned_agent = agent_name

    def get_task(self, task_id: str) -> Optional[TaskNode]:
        return self.nodes.get(task_id)

    def get_parents(self, task_id: str) -> List[TaskNode]:
        if task_id not in self.nodes:
            raise ValueError(f"Task with id {task_id} not found.")
        node = self.nodes[task_id]
        return [self.nodes[p_id] for p_id in [node.parent] if node.parent and p_id in self.nodes]

    def get_children(self, task_id: str) -> List[TaskNode]:
        if task_id not in self.nodes:
            raise ValueError(f"Task with id {task_id} not found.")
        return [self.nodes[c_id] for c_id in self.nodes[task_id].children if c_id in self.nodes]

    def get_ready_tasks(self) -> List[TaskNode]:
        ready_tasks = []
        for node in self.nodes.values():
            if node.state == TaskState.SUBMITTED:
                if not node.parent:
                    ready_tasks.append(node)
                elif node.parent and self.nodes[node.parent].state == TaskState.COMPLETED:
                    ready_tasks.append(node)
        return ready_tasks

    def get_failed_tasks(self) -> List[TaskNode]:
        return [n for n in self.nodes.values() if n.state == TaskState.FAILED]

    def get_completed_tasks(self) -> List[TaskNode]:
        return [n for n in self.nodes.values() if n.state == TaskState.COMPLETED]

    def replan_branch(self, task_id: str, new_subtasks_data: List[Dict[str, Any]]):
        if task_id not in self.nodes:
            raise ValueError(f"Task with id {task_id} not found for replanning.")

        node_to_replan = self.nodes[task_id]

        for child_id in list(node_to_replan.children):
            self.remove_task(child_id)
        node_to_replan.children = []

        for sub_task_data in new_subtasks_data:
            sub_id = sub_task_data["id"]
            kwargs_for_node = {k: v for k, v in sub_task_data.items() if k != "id"}
            self.add_task(task_id=sub_id, parent_id=task_id, **kwargs_for_node)

    def _serialize_node_data(self, node: TaskNode) -> Dict[str, Any]:
        return {
            "parent": node.parent,
            "children": node.children,
            "state": node.state.value,
            "assigned_agent": node.assigned_agent,
            "objective": node.objective,
            "expected_result": node.expected_result,
            "artifact_ref": node.artifact_ref,
            "history": node.history,
            "meta": node.meta,
        }

    def export_graph(self, filepath: str):
        serializable_nodes = {
            task_id: self._serialize_node_data(node) for task_id, node in self.nodes.items()
        }
        graph_data = {
            "roots": self.roots,
            "nodes": serializable_nodes
        }
        with open(filepath, "w") as f:
            json.dump(graph_data, f, indent=2)

    def load_graph(self, filepath: str):
        with open(filepath, "r") as f:
            data = json.load(f)

        self.nodes = {}
        self.roots = data.get("roots", [])

        for task_id, node_data in data.get("nodes", {}).items():
            node_kwargs = {
                "parent": node_data.get("parent"),
                "assigned_agent": node_data.get("assigned_agent"),
                "objective": node_data.get("objective"),
                "expected_result": node_data.get("expected_result"),
                "meta": node_data.get("meta"),
                "artifact_ref": node_data.get("artifact_ref")
            }
            node = TaskNode(task_id=task_id, **node_kwargs)
            node.state = TaskState(node_data["state"])
            node.children = node_data.get("children", [])
            node.history = node_data.get("history", [])
            self.nodes[task_id] = node

    def as_dict(self) -> Dict[str, Any]:
        return {
            "roots": self.roots,
            "nodes": {tid: self._serialize_node_data(node) for tid, node in self.nodes.items()}
        }

    def to_networkx(self):
        import networkx as nx
        G = nx.DiGraph()
        for task_id, node in self.nodes.items():
            G.add_node(task_id, objective=node.objective, state=node.state.value, agent=node.assigned_agent)
            if node.parent:
                G.add_edge(node.parent, task_id)
        return G
