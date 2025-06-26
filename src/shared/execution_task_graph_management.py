from typing import Optional, Dict, List, Any, Union
from enum import Enum
from datetime import datetime
import uuid
import firebase_admin
from firebase_admin import firestore
import logging

logger = logging.getLogger(__name__)

from src.shared.firebase_init import db

class ExecutionTaskType(str, Enum):
    EXECUTABLE = "executable"
    EXPLORATORY = "exploratory"
    CONTAINER = "container"
    DECOMPOSITION = "decomposition"

class ExecutionTaskState(str, Enum):
    PENDING = "pending"
    READY = "ready"
    ASSIGNED = "assigned"
    WORKING = "working"
    AWAITING_VALIDATION = "awaiting_validation"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"

class ExecutionTaskNode:
    def __init__(
        self,
        task_id: str,
        objective: str,
        task_type: ExecutionTaskType,
        parent_id: Optional[str] = None,
        dependencies: Optional[List[str]] = None,
        assigned_agent_type: Optional[str] = None,
        meta: Optional[Dict[str, Any]] = None,
        input_data_refs: Optional[Dict[str, str]] = None,
    ):
        self.id: str = task_id
        self.objective: str = objective
        self.task_type: ExecutionTaskType = task_type
        self.parent_id: Optional[str] = parent_id
        self.sub_task_ids: List[str] = []

        self.state: ExecutionTaskState = ExecutionTaskState.PENDING
        self.dependencies: List[str] = dependencies if dependencies is not None else []
        
        self.assigned_agent_type: Optional[str] = assigned_agent_type
        self.assigned_agent_id: Optional[str] = None
        
        self.input_data_refs: Dict[str, str] = input_data_refs if input_data_refs is not None else {}
        self.output_artifact_ref: Optional[str] = None
        self.result_summary: Optional[str] = None

        self.history: List[Dict[str, Any]] = []
        self.meta: Dict[str, Any] = meta if meta is not None else {}
        self.created_at: str = datetime.utcnow().isoformat()
        self.updated_at: str = self.created_at

    def update_state(self, new_state: ExecutionTaskState, details: Optional[str] = None):
        now = datetime.utcnow().isoformat()
        old_state = self.state
        self.history.append({
            "from_state": str(old_state.value),
            "to_state": str(new_state.value),
            "timestamp": now,
            "details": details
        })
        self.state = new_state
        self.updated_at = now

    def to_dict(self) -> Dict[str, Any]:
        data = self.__dict__.copy()
        data['task_type'] = self.task_type.value
        data['state'] = self.state.value
        data['output_artifact_ref'] = self.output_artifact_ref 

        return data

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'ExecutionTaskNode':
        node = ExecutionTaskNode(
            task_id=data['id'],
            objective=data['objective'],
            task_type=ExecutionTaskType(data['task_type'])
        )
        
        for key, value in data.items():
            if key in ['id', 'objective', 'task_type']:
                continue
            
            if key == 'state':
                if value is not None:
                    try:
                        node.state = ExecutionTaskState(value)
                    except ValueError:
                        logger.error(f"Valeur d'état invalide '{value}' pour la tâche {data.get('id')}. Conservation de PENDING.")
                        node.state = ExecutionTaskState.PENDING
                continue
            
            if hasattr(node, key):
                setattr(node, key, value)

        node.dependencies = data.get('dependencies', [])
        node.sub_task_ids = data.get('sub_task_ids', [])
        node.history = data.get('history', [])
        node.input_data_refs = data.get('input_data_refs', {})
        node.meta = data.get('meta', {})

        return node

class ExecutionTaskGraph:
    def __init__(self, execution_plan_id: str):
        if not execution_plan_id:
            raise ValueError("Un execution_plan_id est requis.")
        self.execution_plan_id = execution_plan_id
        self.collection_ref = db.collection("execution_task_graphs") 
        self.doc_ref = self.collection_ref.document(self.execution_plan_id)
        self.logger = logging.getLogger(f"{__name__}.ExecutionTaskGraph.{self.execution_plan_id}")

    def _get_graph_data(self) -> Dict[str, Any]:
        doc = self.doc_ref.get()
        if not doc.exists:
            initial_data = {
                "execution_plan_id": self.execution_plan_id,
                "root_task_ids": [],
                "nodes": {},
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat(),
                "overall_status": "PENDING",
                "edit_mode": False,
                "last_edit_by": None,
                "edit_started_at": None,
            }
            self.doc_ref.set(initial_data)
            return initial_data
        return doc.to_dict()

    def _save_graph_data(self, graph_data: Dict[str, Any]):
        graph_data['updated_at'] = datetime.utcnow().isoformat()
        self.doc_ref.set(graph_data)

    def add_task(self, task_node: ExecutionTaskNode, is_root: bool = False):
        self.logger.debug(f"[{self.execution_plan_id}] ExecutionTaskGraph.add_task pour {task_node.id}, état: {task_node.state.value}, output_artifact_ref initial: {task_node.output_artifact_ref}")
        
        graph_data = self._get_graph_data()
        nodes = graph_data.get("nodes", {})
        
        nodes[task_node.id] = task_node.to_dict()
        graph_data["nodes"] = nodes

        if is_root and task_node.id not in graph_data.get("root_task_ids", []):
            graph_data.setdefault("root_task_ids", []).append(task_node.id)
        
        if task_node.parent_id and task_node.parent_id in nodes:
            if task_node.id not in nodes[task_node.parent_id]['sub_task_ids']:
                 nodes[task_node.parent_id]['sub_task_ids'].append(task_node.id)

        self._save_graph_data(graph_data)
        return task_node

    def get_task(self, task_id: str) -> Optional[ExecutionTaskNode]:
        graph_data = self._get_graph_data()
        node_data = graph_data.get("nodes", {}).get(task_id)
        if node_data:
            return ExecutionTaskNode.from_dict(node_data)
        return None

    def update_task_output(self, task_id: str, artifact_ref: Optional[str] = None, summary: Optional[str] = None):
        task_node_obj = self.get_task(task_id) 
        if not task_node_obj:
            self.logger.error(f"[{self.execution_plan_id}] Tâche {task_id} non trouvée dans update_task_output.")
            raise ValueError(f"Tâche d'exécution {task_id} introuvable pour update_task_output.")
        
        self.logger.debug(f"[{self.execution_plan_id}] update_task_output pour {task_id}: artifact_ref='{artifact_ref}', summary='{summary}'. Current task output_artifact_ref='{task_node_obj.output_artifact_ref}'")

        if artifact_ref is not None:
            task_node_obj.output_artifact_ref = artifact_ref
        if summary is not None:
            task_node_obj.result_summary = summary
        task_node_obj.updated_at = datetime.utcnow().isoformat()
        
        self.add_task(task_node_obj)


    def get_ready_tasks(self) -> List[ExecutionTaskNode]:
        graph_data = self._get_graph_data()
        nodes_dict = graph_data.get("nodes", {})
        ready_tasks = []
        self.logger.debug(f"get_ready_tasks: Examen de {len(nodes_dict)} noeuds pour le plan {self.execution_plan_id}.")

        for node_id, node_data in nodes_dict.items():
            current_node_state_from_db = node_data.get('state')
            self.logger.debug(f"get_ready_tasks: Examen noeud '{node_id}', État brut DB: '{current_node_state_from_db}'")
            
            if current_node_state_from_db == ExecutionTaskState.PENDING.value:
                node = ExecutionTaskNode.from_dict(node_data)

                self.logger.debug(f"get_ready_tasks: Noeud '{node_id}' est PENDING. Vérification dépendances...")
                all_deps_completed = True
                if not node.dependencies: 
                    self.logger.debug(f"get_ready_tasks: Noeud '{node_id}' (PENDING) n'a pas de dépendances. Passage à READY.")
                    node.update_state(ExecutionTaskState.READY, "Aucune dépendance, prête pour assignation.")
                    self.add_task(node)
                    reloaded_node = self.get_task(node.id)
                    if reloaded_node: ready_tasks.append(reloaded_node)
                    continue

                for dep_id in node.dependencies:
                    dep_node_data = nodes_dict.get(dep_id)
                    dep_state_str = dep_node_data.get("state") if dep_node_data else "NON_EXISTENT"
                    if not dep_node_data or ExecutionTaskState(dep_state_str) != ExecutionTaskState.COMPLETED:
                        all_deps_completed = False
                        self.logger.debug(f"get_ready_tasks: Noeud '{node_id}': Dépendance '{dep_id}' non complétée (état: {dep_state_str}).")
                        break
                
                if all_deps_completed:
                    self.logger.debug(f"get_ready_tasks: Noeud '{node_id}' (PENDING): Toutes les dépendances complétées. Passage à READY.")
                    node.update_state(ExecutionTaskState.READY, "Toutes les dépendances sont complétées.")
                    self.add_task(node)
                    reloaded_node = self.get_task(node.id)
                    if reloaded_node: ready_tasks.append(reloaded_node)
            elif current_node_state_from_db == ExecutionTaskState.READY.value:
                 self.logger.debug(f"get_ready_tasks: Noeud '{node_id}' est déjà READY. Ajout à la liste.")
                 ready_tasks.append(ExecutionTaskNode.from_dict(node_data))
            else:
                self.logger.debug(f"get_ready_tasks: Noeud '{node_id}' (état: {current_node_state_from_db}) n'est ni PENDING ni déjà READY. Ignoré pour cette passe.")
        
        self.logger.debug(f"get_ready_tasks: Tâches prêtes trouvées pour {self.execution_plan_id}: {[t.id for t in ready_tasks]}")
        return ready_tasks

    def update_task_state(self, task_id: str, new_state: ExecutionTaskState, details: Optional[str] = None):
        task_node = self.get_task(task_id)
        if not task_node:
            self.logger.error(f"[{self.execution_plan_id}] Tâche {task_id} non trouvée dans update_task_state.")
            raise ValueError(f"Tâche d'exécution {task_id} introuvable pour update_task_state.")

        task_node.update_state(new_state, details)
        task_node.updated_at = datetime.utcnow().isoformat()
        self.add_task(task_node)

    def set_overall_status(self, status: str):
        graph_data = self._get_graph_data()
        graph_data["overall_status"] = status
        self._save_graph_data(graph_data)

    def as_dict(self) -> Dict[str, Any]:
        return self._get_graph_data()

    # --- New methods for interactive edition ---

    def set_edit_mode(self, enabled: bool, user_id: Optional[str] = None):
        graph_data = self._get_graph_data()
        graph_data["edit_mode"] = enabled
        if enabled:
            graph_data["last_edit_by"] = user_id
            graph_data["edit_started_at"] = datetime.utcnow().isoformat()
        else:
            graph_data["edit_started_at"] = None
        self._save_graph_data(graph_data)

    def get_edit_mode(self) -> bool:
        graph_data = self._get_graph_data()
        return bool(graph_data.get("edit_mode", False))

    def edit_task(self, task_id: str, updates: Dict[str, Any]):
        graph_data = self._get_graph_data()
        nodes = graph_data.get("nodes", {})
        node_data = nodes.get(task_id)
        if not node_data:
            raise ValueError(f"Tâche {task_id} introuvable pour édition")
        if node_data.get("state") == ExecutionTaskState.COMPLETED.value:
            raise ValueError("Impossible de modifier une tâche complétée")

        allowed_fields = {
            "objective",
            "task_type",
            "assigned_agent_type",
            "meta",
        }
        for key, val in updates.items():
            if key in allowed_fields:
                if key == "task_type":
                    val = ExecutionTaskType(val).value
                node_data[key] = val
        nodes[task_id] = node_data
        graph_data["nodes"] = nodes
        self._save_graph_data(graph_data)
        return ExecutionTaskNode.from_dict(node_data)

    def _recursive_delete(self, task_id: str, nodes: Dict[str, Any], graph_data: Dict[str, Any]):
        node_data = nodes.get(task_id)
        if not node_data:
            return
        for sub_id in list(node_data.get("sub_task_ids", [])):
            self._recursive_delete(sub_id, nodes, graph_data)
        for other_id, other_data in nodes.items():
            deps = other_data.get("dependencies", [])
            if task_id in deps:
                deps.remove(task_id)
                other_data["dependencies"] = deps
        parent_id = node_data.get("parent_id")
        if parent_id and parent_id in nodes:
            parent_subs = nodes[parent_id].get("sub_task_ids", [])
            if task_id in parent_subs:
                parent_subs.remove(task_id)
                nodes[parent_id]["sub_task_ids"] = parent_subs
        if task_id in graph_data.get("root_task_ids", []):
            graph_data["root_task_ids"].remove(task_id)
        nodes.pop(task_id, None)

    def delete_task(self, task_id: str):
        graph_data = self._get_graph_data()
        nodes = graph_data.get("nodes", {})
        node_data = nodes.get(task_id)
        if not node_data:
            raise ValueError(f"Tâche {task_id} introuvable")
        if node_data.get("state") == ExecutionTaskState.COMPLETED.value:
            raise ValueError("Impossible de supprimer une tâche complétée")

        self._recursive_delete(task_id, nodes, graph_data)
        graph_data["nodes"] = nodes
        self._save_graph_data(graph_data)

    def link_tasks(self, from_id: str, to_id: str):
        graph_data = self._get_graph_data()
        nodes = graph_data.get("nodes", {})
        if from_id not in nodes or to_id not in nodes:
            raise ValueError("Tâches introuvables pour liaison")
        deps = nodes[to_id].get("dependencies", [])
        if from_id not in deps:
            deps.append(from_id)
            nodes[to_id]["dependencies"] = deps
        self._ensure_acyclic(nodes)
        graph_data["nodes"] = nodes
        self._save_graph_data(graph_data)

    def unlink_tasks(self, from_id: str, to_id: str):
        graph_data = self._get_graph_data()
        nodes = graph_data.get("nodes", {})
        if to_id not in nodes:
            return
        deps = nodes[to_id].get("dependencies", [])
        if from_id in deps:
            deps.remove(from_id)
            nodes[to_id]["dependencies"] = deps
        graph_data["nodes"] = nodes
        self._save_graph_data(graph_data)

    def _ensure_acyclic(self, nodes: Dict[str, Any]):
        visited: Dict[str, int] = {}

        def dfs(nid: str, stack: List[str]):
            state = visited.get(nid, 0)
            if state == 1:
                raise ValueError("Cycle détecté dans le graphe")
            if state == 2:
                return
            visited[nid] = 1
            for dep in nodes.get(nid, {}).get("dependencies", []):
                if dep in nodes:
                    dfs(dep, stack + [nid])
            visited[nid] = 2

        for nid in nodes.keys():
            if visited.get(nid, 0) == 0:
                dfs(nid, [])

    def validate_graph(self):
        graph_data = self._get_graph_data()
        nodes = graph_data.get("nodes", {})
        self._ensure_acyclic(nodes)
        return True
    
