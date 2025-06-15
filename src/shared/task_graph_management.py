from typing import Optional, Dict, List, Any
from enum import Enum
from datetime import datetime
import uuid
import firebase_admin
from firebase_admin import firestore, credentials

if not firebase_admin._apps:
    try:
        cred = credentials.ApplicationDefault()
        firebase_admin.initialize_app(cred)
    except Exception as e:
        print(f"CRITICAL: Firestore initialization failed. Ensure GOOGLE_APPLICATION_CREDENTIALS is set. Error: {e}")
db = firestore.client()

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
        meta: Optional[Dict[str, Any]] = None,
        artifact_ref: Optional[Any] = None,
    ):
        self.id: str = task_id
        self.parent: Optional[str] = parent
        self.children: List[str] = []
        self.state: TaskState = TaskState.SUBMITTED
        self.assigned_agent: Optional[str] = assigned_agent
        self.objective: Optional[str] = objective
        self.artifact_ref: Optional[Any] = artifact_ref
        self.history: List[Dict[str, Any]] = []
        self.meta: Dict[str, Any] = meta if meta is not None else {}

    def to_dict(self) -> Dict[str, Any]:
        """Convertit l'objet TaskNode en dictionnaire pour Firestore."""
        data = self.__dict__.copy()
        data['state'] = self.state.value
        return data

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'TaskNode':
        """Crée un objet TaskNode à partir d'un dictionnaire Firestore."""
        node = TaskNode(task_id=data['id'])
        for key, value in data.items():
            if key == 'state':
                setattr(node, key, TaskState(value))
            else:
                setattr(node, key, value)
        return node
    
    def update_state(self, new_state: TaskState, details: Optional[str] = None):
        """Met à jour l'état et l'historique de la tâche."""
        now = datetime.utcnow().isoformat()
        old_state = self.state
        self.history.append({
            "from_state": str(old_state.value),
            "to_state": str(new_state.value),
            "timestamp": now,
            "details": details
        })
        self.state = new_state

    def __repr__(self):
        return (
            f"TaskNode(id='{self.id}', objective='{self.objective}', state='{self.state.value}', "
            f"parent='{self.parent}', children={len(self.children)})"
        )


class TaskGraph:
    def __init__(self, plan_id: str):
        if not plan_id:
            raise ValueError("Un plan_id est requis pour initialiser un TaskGraph avec Firestore.")
        self.plan_id = plan_id
        self.collection_ref = db.collection("task_graphs")
        self.doc_ref = self.collection_ref.document(self.plan_id)

    def _get_graph_data(self) -> Dict[str, Any]:
        """Récupère les données complètes du graphe depuis Firestore."""
        doc = self.doc_ref.get()
        if not doc.exists:
            initial_data = {"plan_id": self.plan_id, "roots": [], "nodes": {}}
            self.doc_ref.set(initial_data)
            return initial_data
        return doc.to_dict()

    def _save_graph_data(self, graph_data: Dict[str, Any]):
        """Sauvegarde l'intégralité du graphe dans Firestore."""
        self.doc_ref.set(graph_data)

    def add_task(self, task_node: TaskNode):
        """Ajoute ou met à jour une tâche dans Firestore."""
        graph_data = self._get_graph_data()
        nodes = graph_data.get("nodes", {})
        
        nodes[task_node.id] = task_node.to_dict()

        if task_node.parent:
            if task_node.parent in nodes and task_node.id not in nodes[task_node.parent]['children']:
                nodes[task_node.parent]['children'].append(task_node.id)
        else:
            if task_node.id not in graph_data.get("roots", []):
                graph_data["roots"].append(task_node.id)

        self._save_graph_data(graph_data)
        return task_node

    def get_task(self, task_id: str) -> Optional[TaskNode]:
        """Récupère une tâche spécifique depuis Firestore."""
        graph_data = self._get_graph_data()
        node_data = graph_data.get("nodes", {}).get(task_id)
        if node_data:
            return TaskNode.from_dict(node_data)
        return None

    def update_state(self, task_id: str, state: TaskState, details: Optional[str] = None, artifact_ref: Optional[Any] = None):
        node = self.get_task(task_id)
        if not node:
            raise ValueError(f"Tâche {task_id} introuvable.")
        
        node.update_state(state, details)
        if artifact_ref is not None:
            node.artifact_ref = artifact_ref
            
        self.add_task(node)

    def get_ready_tasks(self) -> List[TaskNode]:
        """CORRIGÉ : Lit depuis Firestore et applique la logique."""
        graph_data = self._get_graph_data()
        nodes_dict = graph_data.get("nodes", {})
        
        ready_tasks = []
        for node_id, node_data in nodes_dict.items():
            node = TaskNode.from_dict(node_data)
            if node.state == TaskState.SUBMITTED:
                parent_id = node.parent
                if not parent_id:
                    ready_tasks.append(node)
                else:
                    parent_data = nodes_dict.get(parent_id, {})
                    if parent_data.get("state") == TaskState.COMPLETED.value:
                        ready_tasks.append(node)
        return ready_tasks

    def replan_branch(self, task_id: str, new_subtasks: List[TaskNode]):
        """CORRIGÉ : Remplace les enfants d'une tâche par de nouvelles tâches."""
        graph_data = self._get_graph_data()
        nodes = graph_data.get("nodes", {})

        if task_id not in nodes:
            raise ValueError(f"Tâche {task_id} introuvable pour la replanification.")
        
        old_children_ids = nodes[task_id].get("children", [])
        for child_id in old_children_ids:
            if child_id in nodes:
                del nodes[child_id]
        
        nodes[task_id]["children"] = [t.id for t in new_subtasks]
        for sub_task in new_subtasks:
            nodes[sub_task.id] = sub_task.to_dict()

        self._save_graph_data(graph_data)

    def as_dict(self) -> Dict[str, Any]:
        """CORRIGÉ : Retourne simplement les données brutes de Firestore."""
        return self._get_graph_data()
    