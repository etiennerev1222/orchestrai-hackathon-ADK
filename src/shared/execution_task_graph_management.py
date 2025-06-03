# src/shared/execution_task_graph_management.py
from typing import Optional, Dict, List, Any, Union
from enum import Enum
from datetime import datetime
import uuid
import firebase_admin
from firebase_admin import firestore
import logging # AJOUT: Pour le logging

logger = logging.getLogger(__name__) # AJOUT: Initialiser le logger pour ce module

# S'assurer que firebase_init est appelé quelque part (ex: au démarrage du superviseur)
# ou réutiliser le 'db' de firebase_init.py
from src.shared.firebase_init import db # Réutiliser le client db initialisé

class ExecutionTaskType(str, Enum):
    EXECUTABLE = "executable"       # Produit un livrable concret
    EXPLORATORY = "exploratory"     # Recherche, analyse, peut générer des sous-tâches
    CONTAINER = "container"         # Pour structurer le plan, regrouper des tâches
    DECOMPOSITION = "decomposition" # Tâche initiale pour décomposer le plan de TEAM 1

class ExecutionTaskState(str, Enum):
    PENDING = "pending"                     # En attente de ses dépendances
    READY = "ready"                         # Dépendances satisfaites, prête à être assignée
    ASSIGNED = "assigned"                   # Assignée à un agent, en attente de démarrage
    WORKING = "working"                     # En cours d'exécution par un agent
    AWAITING_VALIDATION = "awaiting_validation" # Livrable produit, en attente de test/validation
    COMPLETED = "completed"                 # Terminée avec succès
    FAILED = "failed"                       # Échec de l'exécution
    BLOCKED = "blocked"                     # Ne peut pas continuer (ex: dépendance échouée)
    CANCELLED = "cancelled"                 # Annulée

class ExecutionTaskNode:
    def __init__(
        self,
        task_id: str,
        objective: str,
        task_type: ExecutionTaskType,
        parent_id: Optional[str] = None, # Pour les sous-tâches générées dynamiquement
        dependencies: Optional[List[str]] = None,
        assigned_agent_type: Optional[str] = None, # Ex: "coding_python", "web_research"
        meta: Optional[Dict[str, Any]] = None,
        input_data_refs: Optional[Dict[str, str]] = None, # Ex: {"code_to_test": "artifact_id_123"}
    ):
        self.id: str = task_id
        self.objective: str = objective
        self.task_type: ExecutionTaskType = task_type
        self.parent_id: Optional[str] = parent_id
        self.sub_task_ids: List[str] = [] # Pour les tâches générées par celle-ci

        self.state: ExecutionTaskState = ExecutionTaskState.PENDING
        self.dependencies: List[str] = dependencies if dependencies is not None else []
        
        self.assigned_agent_type: Optional[str] = assigned_agent_type
        self.assigned_agent_id: Optional[str] = None # ID de l'instance d'agent spécifique
        
        self.input_data_refs: Dict[str, str] = input_data_refs if input_data_refs is not None else {}
        self.output_artifact_ref: Optional[str] = None # ID ou URI de l'artefact produit
        self.result_summary: Optional[str] = None # Ex: rapport de test, résumé de recherche

        self.history: List[Dict[str, Any]] = []
        self.meta: Dict[str, Any] = meta if meta is not None else {} # Pour infos additionnelles, retry_count etc.
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
        return data

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'ExecutionTaskNode':
        # Créer l'instance. Son état sera PENDING par défaut.
        node = ExecutionTaskNode(
            task_id=data['id'],
            objective=data['objective'],
            task_type=ExecutionTaskType(data['task_type'])
        )
        
        # Parcourir toutes les données du dictionnaire Firestore
        for key, value in data.items():
            # Les champs passés au constructeur sont déjà pris en compte
            if key in ['id', 'objective', 'task_type']:
                continue
            
            # Traiter spécifiquement l'état
            if key == 'state':
                if value is not None: # S'assurer qu'il y a une valeur pour l'état
                    try:
                        node.state = ExecutionTaskState(value) # ÉCRASER L'ÉTAT PENDING INITIAL
                    except ValueError:
                        logger.error(f"Valeur d'état invalide '{value}' pour la tâche {data.get('id')}. Conservation de PENDING.")
                        node.state = ExecutionTaskState.PENDING # Fallback sécurisé
                continue # Passer à la clé suivante
            
            # Pour les autres attributs, les assigner directement s'ils existent sur l'objet
            if hasattr(node, key):
                setattr(node, key, value)
            # else:
            #     logger.warning(f"Clé '{key}' de Firestore non trouvée comme attribut de ExecutionTaskNode pour {data.get('id')}")

        # S'assurer que les listes/dictionnaires sont bien initialisés si absents de Firestore
        node.dependencies = data.get('dependencies', [])
        node.sub_task_ids = data.get('sub_task_ids', [])
        node.history = data.get('history', [])
        node.input_data_refs = data.get('input_data_refs', {})
        node.meta = data.get('meta', {}) # Assurer que meta est aussi initialisé

        return node

class ExecutionTaskGraph:
    def __init__(self, execution_plan_id: str):
        if not execution_plan_id:
            raise ValueError("Un execution_plan_id est requis.")
        self.execution_plan_id = execution_plan_id
        # Nom de collection suggéré, à créer dans Firestore
        self.collection_ref = db.collection("execution_task_graphs") 
        self.doc_ref = self.collection_ref.document(self.execution_plan_id)
        # AJOUT: Logger spécifique pour cette instance de graphe
        self.logger = logging.getLogger(f"{__name__}.ExecutionTaskGraph.{self.execution_plan_id}")

    def _get_graph_data(self) -> Dict[str, Any]:
        doc = self.doc_ref.get()
        if not doc.exists:
            initial_data = {
                "execution_plan_id": self.execution_plan_id,
                "root_task_ids": [], # Peut y avoir plusieurs points d'entrée initiaux
                "nodes": {},
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat(),
                "overall_status": "PENDING" # Statut global du plan d'exécution
            }
            self.doc_ref.set(initial_data)
            return initial_data
        return doc.to_dict()

    def _save_graph_data(self, graph_data: Dict[str, Any]):
        graph_data['updated_at'] = datetime.utcnow().isoformat()
        self.doc_ref.set(graph_data)

    def add_task(self, task_node: ExecutionTaskNode, is_root: bool = False):
        self.logger.debug(f"Ajout/Mise à jour tâche: {task_node.id}, état: {task_node.state.value}")
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

    def update_task_state(self, task_id: str, new_state: ExecutionTaskState, details: Optional[str] = None):
        task_node = self.get_task(task_id)
        if not task_node:
            raise ValueError(f"Tâche d'exécution {task_id} introuvable.")
        
        task_node.update_state(new_state, details)
        # Pour sauvegarder, on ré-ajoute la tâche (ce qui met à jour son dict)
        self.add_task(task_node) 

    def update_task_output(self, task_id: str, artifact_ref: Optional[str] = None, summary: Optional[str] = None):
        task_node = self.get_task(task_id)
        if not task_node:
            raise ValueError(f"Tâche d'exécution {task_id} introuvable.")
        if artifact_ref is not None:
            task_node.output_artifact_ref = artifact_ref
        if summary is not None:
            task_node.result_summary = summary
        task_node.updated_at = datetime.utcnow().isoformat()
        self.add_task(task_node)


    def get_ready_tasks(self) -> List[ExecutionTaskNode]:
        graph_data = self._get_graph_data()
        nodes_dict = graph_data.get("nodes", {})
        ready_tasks = []
        self.logger.debug(f"get_ready_tasks: Examen de {len(nodes_dict)} noeuds pour le plan {self.execution_plan_id}.")

        for node_id, node_data in nodes_dict.items():
            current_node_state_from_db = node_data.get('state')
            # MODIFICATION: Log plus détaillé et condition plus stricte pour considérer une tâche
            self.logger.debug(f"get_ready_tasks: Examen noeud '{node_id}', État brut DB: '{current_node_state_from_db}'")
            
            # Ne considérer que les tâches qui sont PENDING pour potentiellement devenir READY
            # Les tâches déjà READY d'un cycle précédent seront re-évaluées par la logique appelante si nécessaire
            # ou si elles n'ont pas été traitées.
            if current_node_state_from_db == ExecutionTaskState.PENDING.value:
                node = ExecutionTaskNode.from_dict(node_data) # Crée une instance à partir des données DB
                # node.state sera ExecutionTaskState.PENDING ici

                self.logger.debug(f"get_ready_tasks: Noeud '{node_id}' est PENDING. Vérification dépendances...")
                all_deps_completed = True
                if not node.dependencies: 
                    self.logger.debug(f"get_ready_tasks: Noeud '{node_id}' (PENDING) n'a pas de dépendances. Passage à READY.")
                    node.update_state(ExecutionTaskState.READY, "Aucune dépendance, prête pour assignation.")
                    self.add_task(node) # Sauvegarder le changement d'état
                    # Charger la tâche à nouveau pour s'assurer qu'on a bien l'objet avec son historique mis à jour
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
                    reloaded_node = self.get_task(node.id) # Renvoyer l'instance fraîchement sauvegardée
                    if reloaded_node: ready_tasks.append(reloaded_node)
            # FIN DE LA MODIFICATION : Les autres états ne sont plus activement recherchés pour passer à READY ici.
            # La logique du superviseur prendra les tâches déjà READY.
            elif current_node_state_from_db == ExecutionTaskState.READY.value:
                 # Si une tâche est déjà READY (par ex. d'un cycle précédent non traitée), la retourner.
                 self.logger.debug(f"get_ready_tasks: Noeud '{node_id}' est déjà READY. Ajout à la liste.")
                 ready_tasks.append(ExecutionTaskNode.from_dict(node_data))
            else:
                self.logger.debug(f"get_ready_tasks: Noeud '{node_id}' (état: {current_node_state_from_db}) n'est ni PENDING ni déjà READY. Ignoré pour cette passe.")
        
        self.logger.debug(f"get_ready_tasks: Tâches prêtes trouvées pour {self.execution_plan_id}: {[t.id for t in ready_tasks]}")
        return ready_tasks
    

    def set_overall_status(self, status: str):
        graph_data = self._get_graph_data()
        graph_data["overall_status"] = status
        self._save_graph_data(graph_data)

    def as_dict(self) -> Dict[str, Any]:
        return self._get_graph_data()
    