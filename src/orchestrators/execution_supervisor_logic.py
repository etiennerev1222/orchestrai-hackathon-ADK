# src/orchestrators/execution_supervisor_logic.py
import logging
import uuid
import asyncio
from typing import Optional, Dict, Any, List
import httpx
from src.shared.execution_task_graph_management import (
    ExecutionTaskGraph,
    ExecutionTaskNode,
    ExecutionTaskState,
    ExecutionTaskType
)
from src.shared.service_discovery import get_gra_base_url
from src.clients.a2a_api_client import call_a2a_agent # À adapter si les agents TEAM 2 ont des besoins différents
# Importer les futurs agents de TEAM 2 quand ils seront définis
from src.shared.execution_task_graph_management import ExecutionTaskNode, ExecutionTaskType # Assurez-vous que ExecutionTaskType est importé
import json

# --- AJOUT DES IMPORTS NÉCESSAIRES ---
from src.agents.testing_agent.logic import AGENT_SKILL_SOFTWARE_TESTING
from src.agents.development_agent.logic import AGENT_SKILL_CODING_PYTHON
# --- FIN DE L'AJOUT ---

# Ce logger de module est bien, mais les méthodes utiliseront self.logger
logger = logging.getLogger(__name__) # Peut rester pour des logs au niveau du module si besoin
if not logger.hasHandlers(): # S'assurer que le logger de module a un handler
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
# Compétence pour l'agent de décomposition de plan
DECOMPOSITION_AGENT_SKILL = "execution_plan_decomposition" 

class ExecutionSupervisorLogic:
    def __init__(self, global_plan_id: str, team1_plan_final_text: str):
        self.global_plan_id = global_plan_id # ID du plan global parent
        self.team1_plan_final_text = team1_plan_final_text # Le plan texte de TEAM 1
        self._local_to_global_id_map_for_plan: Dict[str, str] = {}
        
        # L'ID du plan d'exécution sera dérivé du plan global pour traçabilité
        self.execution_plan_id = f"exec_{self.global_plan_id}_{uuid.uuid4().hex[:8]}"
        self.task_graph = ExecutionTaskGraph(execution_plan_id=self.execution_plan_id)
        
        self._gra_base_url: Optional[str] = None
         # --- AJOUT DE L'INITIALISATION DU LOGGER D'INSTANCE ---
        self.logger = logging.getLogger(f"{__name__}.ExecutionSupervisorLogic.{self.execution_plan_id}")
        # S'assurer que ce logger hérite de la configuration de base ou configurer spécifiquement si besoin
        if not self.logger.hasHandlers() and not self.logger.propagate:
             # Si vous voulez que ce logger ait son propre niveau/handler, configurez-le ici.
             # Sinon, s'il propage (par défaut à True), il utilisera les handlers du logger root.
             # Pour être sûr qu'il logue au moins au niveau INFO si le root logger est plus restrictif:
             if not self.logger.handlers: # Vérifier s'il a déjà des handlers (par exemple hérités)
                 if not logging.getLogger().hasHandlers(): # Si le root logger n'a pas de handlers
                     logging.basicConfig(level=logging.INFO) # Configurer le root logger
                 # Si vous voulez un niveau spécifique pour CE logger d'instance :
                 # self.logger.setLevel(logging.DEBUG) # ou INFO
                 # if not self.logger.handlers: # Re-vérifier après setLevel si des handlers ont été ajoutés
                 #     handler = logging.StreamHandler()
                 #     formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
                 #     handler.setFormatter(formatter)
                 #     self.logger.addHandler(handler)
                 # self.logger.propagate = False # Empêcher la double journalisation si vous ajoutez un handler ici

        self.logger.info(f"ExecutionSupervisorLogic initialisé pour global_plan '{global_plan_id}'. Execution plan ID: '{self.execution_plan_id}'")
        # --- FIN DE L'AJOUT ---

    async def _ensure_gra_url(self): # Similaire aux autres superviseurs
        if not self._gra_base_url:
            self._gra_base_url = await get_gra_base_url()
            if not self._gra_base_url:
                msg = "[ExecutionSupervisor] Impossible de découvrir l'URL du GRA."
                logger.error(msg)
                raise ConnectionError(msg)
        return self._gra_base_url

    async def _get_agent_url_from_gra(self, skill: str) -> Optional[str]: # Compléter cette méthode
        gra_url = await self._ensure_gra_url()
        agent_target_url = None
        try:
            async with httpx.AsyncClient() as client: # Assurez-vous que httpx est importé
                self.logger.info(f"[ExecutionSupervisor] Demande au GRA ({gra_url}) un agent avec la compétence: '{skill}'")
                response = await client.get(f"{gra_url}/agents", params={"skill": skill}, timeout=10.0)
                response.raise_for_status()
                data = response.json()
                agent_target_url = data.get("url")
                if agent_target_url:
                    self.logger.info(f"[ExecutionSupervisor] URL pour '{skill}' obtenue du GRA: {agent_target_url} (Agent: {data.get('name')})")
                else:
                    self.logger.error(f"[ExecutionSupervisor] Aucune URL retournée par le GRA pour la compétence '{skill}'. Réponse: {data}")
        except httpx.HTTPStatusError as e:
            self.logger.error(f"[ExecutionSupervisor] Erreur HTTP ({e.response.status_code}) en contactant le GRA pour '{skill}' à {e.request.url}: {e.response.text}")
        except httpx.RequestError as e:
            self.logger.error(f"[ExecutionSupervisor] Erreur de requête en contactant le GRA pour '{skill}': {e}")
        except Exception as e:
            self.logger.error(f"[ExecutionSupervisor] Erreur inattendue en contactant le GRA pour '{skill}': {e}", exc_info=True)
        return agent_target_url

    async def initialize_and_decompose_plan(self):
        """
        Tâche initiale : faire décomposer le plan textuel de TEAM 1 en ExecutionTaskGraph.
        """
        self.logger.info(f"[{self.execution_plan_id}] Initialisation et décomposition du plan de TEAM 1.")
        self.task_graph.set_overall_status("INITIALIZING")

        # 1. Créer une tâche racine de type "DECOMPOSITION"
        decomposition_task_id = f"decompose_{self.execution_plan_id}"
        decomposition_task = ExecutionTaskNode(
            task_id=decomposition_task_id,
            objective="Décomposer le plan textuel de TEAM 1 en tâches d'exécution structurées.",
            task_type=ExecutionTaskType.DECOMPOSITION,
            assigned_agent_type=DECOMPOSITION_AGENT_SKILL 
        )
        self.task_graph.add_task(decomposition_task, is_root=True)
        self.task_graph.update_task_state(decomposition_task_id, ExecutionTaskState.READY) # Prête immédiatement
        
        self.logger.info(f"[{self.execution_plan_id}] Tâche de décomposition '{decomposition_task_id}' créée et prête.")
        
        # Dans un cycle de process_plan, cette tâche "READY" sera prise.
        # L'agent de décomposition devra parser self.team1_plan_final_text
        # et ensuite appeler des méthodes sur self.task_graph pour ajouter les vraies tâches d'exécution.
        # Par exemple, l'artefact de l'agent de décomposition pourrait être un JSON
        # décrivant les nouvelles tâches et leurs dépendances, que ce superviseur interpréterait.
        
        # Pour l'instant, laissons le cycle `process_plan_execution` la prendre.
        self.task_graph.set_overall_status("PENDING_DECOMPOSITION")

# Dans src/orchestrators/execution_supervisor_logic.py

# ... (autres imports, s'assurer que httpx, json, et call_a2a_agent sont bien importés)
# from src.clients.a2a_api_client import call_a2a_agent
# import json
# import httpx # Si _get_agent_url_from_gra l'utilise, comme dans l'exemple précédent
    async def _fetch_artifact_content(self, artifact_id: str) -> Optional[str]:
        """
        Récupère le contenu textuel d'un artefact depuis le GRA.
        """
        if not artifact_id:
            return None
        try:
            gra_url = await self._ensure_gra_url()
            async with httpx.AsyncClient() as client:
                self.logger.info(f"[{self.execution_plan_id}] Récupération de l'artefact '{artifact_id}' depuis le GRA.")
                response = await client.get(f"{gra_url}/artifacts/{artifact_id}", timeout=10.0)
                response.raise_for_status()
                artifact_data = response.json() # L'artefact A2A complet
                
                # Extraire le contenu textuel de la première partie de l'artefact
                if artifact_data and artifact_data.get("parts"):
                    first_part = artifact_data["parts"][0]
                    if first_part.get("type") == "text" and "text" in first_part:
                        return first_part["text"]
                    # Gérer d'autres types de parties si nécessaire
                self.logger.warning(f"[{self.execution_plan_id}] Artefact '{artifact_id}' n'a pas de contenu textuel extractible dans sa première partie.")
                return None
        except Exception as e:
            self.logger.error(f"[{self.execution_plan_id}] Erreur lors de la récupération du contenu de l'artefact '{artifact_id}': {e}", exc_info=True)
            return None
    async def _prepare_input_for_execution_agent(self, task_node: ExecutionTaskNode) -> str:
        input_payload = {
            "objective": task_node.objective,
            "local_instructions": task_node.meta.get("local_instructions", []),
            "acceptance_criteria": task_node.meta.get("acceptance_criteria", []),
            "task_id": task_node.id,
            "execution_plan_id": self.execution_plan_id,
            "task_type": task_node.task_type.value
        }

        if task_node.task_type == ExecutionTaskType.EXPLORATORY:
            available_skills = await self._get_all_available_execution_skills_from_gra()
            input_payload["available_execution_skills"] = available_skills

        # NOUVELLE LOGIQUE pour injecter le contenu des artefacts des dépendances
        # Ceci est une convention : si une tâche de test dépend d'une tâche de dev,
        # on injecte le livrable.
        # Une approche plus robuste utiliserait les `input_data_refs` si le `DecompositionAgent`
        # était instruit de les remplir. Pour l'instant, inférons par convention.
        
        if task_node.assigned_agent_type == AGENT_SKILL_SOFTWARE_TESTING and task_node.dependencies:
            self.logger.debug(f"[{self.execution_plan_id}] Tâche de test {task_node.id}. Recherche du livrable parmi les dépendances: {task_node.dependencies}")
            for dep_id in task_node.dependencies:
                dep_task_node = self.task_graph.get_task(dep_id)
                if dep_task_node and dep_task_node.assigned_agent_type == AGENT_SKILL_CODING_PYTHON: # Convention
                    if dep_task_node.output_artifact_ref:
                        self.logger.info(f"[{self.execution_plan_id}] Tâche de test {task_node.id} dépend de la tâche de code {dep_id}. Tentative de récupération de l'artefact {dep_task_node.output_artifact_ref}.")
                        deliverable_content = await self._fetch_artifact_content(dep_task_node.output_artifact_ref)
                        if deliverable_content:
                            input_payload["deliverable"] = deliverable_content
                            self.logger.info(f"[{self.execution_plan_id}] Livrable (code) de {dep_id} injecté pour la tâche de test {task_node.id}.")
                        else:
                            self.logger.warning(f"[{self.execution_plan_id}] Impossible de récupérer le contenu du livrable de {dep_id} pour la tâche de test {task_node.id}.")
                            input_payload["deliverable"] = f"// ERREUR: Contenu du livrable de la tâche {dep_id} (artefact {dep_task_node.output_artifact_ref}) non récupérable."
                        break # On prend le premier livrable de code trouvé
            if "deliverable" not in input_payload:
                 self.logger.warning(f"[{self.execution_plan_id}] Aucun livrable de code trouvé dans les dépendances pour la tâche de test {task_node.id}.")
                 input_payload["deliverable"] = "// ATTENTION: Aucun livrable de code trouvé dans les dépendances directes."


        # L'ancienne logique input_data_refs peut coexister ou être remplacée/affinée
        # Pour l'instant, laissons-la pour d'autres usages potentiels
        if task_node.input_data_refs:
            input_payload["input_artifacts_references"] = {} # Renommé pour clarté
            for ref_name, artifact_id_or_ref in task_node.input_data_refs.items():
                self.logger.info(f"[{self.execution_plan_id}] Tâche {task_node.id} a une référence d'input_data_refs '{ref_name}': {artifact_id_or_ref}.")
                input_payload["input_artifacts_references"][ref_name] = {"artifact_id_or_ref": artifact_id_or_ref}
        
        return json.dumps(input_payload, ensure_ascii=False, indent=2)

    async def _process_completed_exploratory_task(self, completed_task_node: ExecutionTaskNode, artifact_content_text: Optional[str]):
        self.logger.info(f"[{self.execution_plan_id}] Traitement du résultat de la tâche exploratoire: {completed_task_node.id}")
        if not artifact_content_text:
            self.logger.warning(f"[{self.execution_plan_id}] Tâche exploratoire {completed_task_node.id} complétée sans artefact textuel pour de nouvelles tâches.")
            self.task_graph.update_task_state(completed_task_node.id, ExecutionTaskState.COMPLETED, "Exploration terminée, pas de nouvelles tâches spécifiées dans l'artefact.")
            return

        try:
            exploration_result = json.loads(artifact_content_text)
            # Supposons que l'agent exploratoire retourne une clé "new_sub_tasks" avec une liste
            # de tâches structurées comme celles du DecompositionAgent
            new_sub_tasks_dicts = exploration_result.get("new_sub_tasks", [])
            
            if not isinstance(new_sub_tasks_dicts, list):
                self.logger.error(f"[{self.execution_plan_id}] La clé 'new_sub_tasks' de l'artefact de {completed_task_node.id} n'est pas une liste.")
                self.task_graph.update_task_state(completed_task_node.id, ExecutionTaskState.FAILED, "Format incorrect de l'artefact pour les nouvelles sous-tâches.")
                return

            if not new_sub_tasks_dicts:
                self.logger.info(f"[{self.execution_plan_id}] Tâche exploratoire {completed_task_node.id} n'a pas défini de nouvelles sous-tâches.")
                summary = exploration_result.get("summary", "Exploration terminée.")
                self.task_graph.update_task_output(completed_task_node.id, summary=summary) # Mettre à jour le résumé de la tâche exploratoire
                self.task_graph.update_task_state(completed_task_node.id, ExecutionTaskState.COMPLETED, summary)
                return

            self.logger.info(f"[{self.execution_plan_id}] Tâche exploratoire {completed_task_node.id} a défini {len(new_sub_tasks_dicts)} nouvelle(s) sous-tâche(s).")

            # Utiliser une version adaptée de la logique de mapping/normalisation et d'ajout
            # Le 'parent_exec_node_id' sera l'ID de la tâche exploratoire qui vient de se terminer.
            # Les dépendances initiales des nouvelles sous-tâches seront la tâche exploratoire parente.
            
            local_id_to_global_id_map_expl = {}
            nodes_to_add_to_graph_expl = {}

            # (Réutiliser ou adapter la fonction create_node_from_json_task que nous avons définie précédemment)
            # def create_node_from_json_task(task_data_dict, assigned_parent_id: Optional[str]): ...

            def first_pass_create_sub_nodes(task_list_json: List[Dict], current_parent_global_id: str): # parent_id est requis ici
                for task_json in task_list_json:
                    # node_obj est une instance de ExecutionTaskNode
                    node_obj, _ = self._create_node_from_json_data( # Externaliser la création du nœud
                        task_json, 
                        current_parent_global_id, 
                        local_id_to_global_id_map_expl # Passer la map pour la peupler
                    ) 
                    nodes_to_add_to_graph_expl[node_obj.id] = (node_obj, task_json)
                    
                    json_sub_tasks = task_json.get("sous_taches", [])
                    if json_sub_tasks:
                        first_pass_create_sub_nodes(json_sub_tasks, node_obj.id)
            
            # Lancer la création des nœuds pour les nouvelles sous-tâches
            first_pass_create_sub_nodes(new_sub_tasks_dicts, completed_task_node.id)

            # Deuxième passe : Résoudre les dépendances et ajouter au graphe
            for global_id, (node_obj, task_json_original) in nodes_to_add_to_graph_expl.items():
                node_obj.dependencies.append(completed_task_node.id) # Dépend de la tâche exploratoire parente
                
                local_deps = task_json_original.get("dependances", [])
                for local_dep_id in local_deps:
                    if local_dep_id in local_id_to_global_id_map_expl:
                        global_dep_id = local_id_to_global_id_map_expl[local_dep_id]
                        if global_dep_id != node_obj.id:
                            node_obj.dependencies.append(global_dep_id)
                        else:
                            self.logger.warning(f"[{self.execution_plan_id}] Tentative d'auto-dépendance (exploratoire) pour {global_id}. Ignorée.")
                    else:
                        # Ici, une dépendance locale pourrait se référer à une tâche existante HORS de ce lot de new_sub_tasks.
                        # Il faudrait une map globale des ID ou une méthode pour résoudre cela.
                        # Pour l'instant, on logue et on ignore si ce n'est pas dans les nouvelles sous-tâches.
                        self.logger.warning(f"[{self.execution_plan_id}] Dépendance locale (exploratoire) '{local_dep_id}' pour '{task_json_original.get('id')}' non trouvée parmi les nouvelles sous-tâches mappées. Elle sera ignorée (ou doit pointer vers une tâche existante).")
                
                node_obj.dependencies = list(set(node_obj.dependencies))
                self.task_graph.add_task(node_obj)
                self.logger.info(f"[{self.execution_plan_id}] Nouvelle sous-tâche (issue d'exploration) '{node_obj.objective}' (ID: {node_obj.id}) ajoutée.")

            summary = exploration_result.get("summary", f"{len(new_sub_tasks_dicts)} nouvelles sous-tâches ajoutées.")
            self.task_graph.update_task_output(completed_task_node.id, summary=summary)
            self.task_graph.update_task_state(completed_task_node.id, ExecutionTaskState.COMPLETED, summary)

        except json.JSONDecodeError:
            self.logger.error(f"[{self.execution_plan_id}] Artefact de la tâche exploratoire {completed_task_node.id} est un JSON invalide.")
            self.task_graph.update_task_state(completed_task_node.id, ExecutionTaskState.FAILED, "Artefact d'exploration JSON invalide.")
        except Exception as e:
            self.logger.error(f"[{self.execution_plan_id}] Erreur lors du traitement du résultat de la tâche exploratoire {completed_task_node.id}: {e}", exc_info=True)
            self.task_graph.update_task_state(completed_task_node.id, ExecutionTaskState.FAILED, f"Erreur traitement résultat exploration: {str(e)}")


    def _create_node_from_json_data(self, task_data_dict: Dict[str, Any], assigned_parent_id: Optional[str], local_id_map: Dict[str,str]) -> tuple[ExecutionTaskNode, Dict[str,Any]]:
        """
        Helper pour créer un ExecutionTaskNode à partir d'un dictionnaire JSON de tâche
        et met à jour la map d'ID locaux vers globaux.
        Retourne le nœud créé et le dictionnaire original (pour les dépendances).
        """
        local_id = task_data_dict.get("id")
        if not local_id:
            self.logger.warning(f"[{self.execution_plan_id}] Tâche JSON sans 'id' local, génération d'un ID temporaire.")
            local_id = f"temp_id_{uuid.uuid4().hex[:6]}"
        
        # ID global unique
        global_task_id = f"exec_{local_id.replace(' ', '_')}_{self.execution_plan_id[:6]}_{uuid.uuid4().hex[:4]}"
        
        if local_id in local_id_map:
            self.logger.warning(f"[{self.execution_plan_id}] ID local '{local_id}' déjà mappé lors de la création de nœud. Ancien: {local_id_map[local_id]}, Nouveau: {global_task_id}")
        local_id_map[local_id] = global_task_id

        node_meta = {
            "local_id_from_agent": local_id,
            "local_instructions": task_data_dict.get("instructions_locales", []),
            "acceptance_criteria": task_data_dict.get("acceptance_criteria", [])
        }
        if task_data_dict.get("nom"):
            node_meta["local_nom_from_agent"] = task_data_dict.get("nom")
        
        new_node = ExecutionTaskNode(
            task_id=global_task_id,
            objective=task_data_dict.get("description", task_data_dict.get("nom", "Objectif non défini")),
            task_type=ExecutionTaskType(task_data_dict.get("type", "exploratory").lower()),
            assigned_agent_type=task_data_dict.get("assigned_agent_type"),
            dependencies=[], # Sera rempli dans la 2ème passe
            parent_id=assigned_parent_id,
            meta=node_meta
        )
        return new_node, task_data_dict

    async def _get_all_available_execution_skills_from_gra(self) -> List[str]:
        """
        Récupère toutes les compétences uniques déclarées par les agents enregistrés auprès du GRA.
        Cible les compétences qui semblent pertinentes pour l'exécution.
        """
        self.logger.info(f"[{self.execution_plan_id}] Récupération des compétences d'exécution disponibles depuis le GRA.")
        gra_url = await self._ensure_gra_url()
        all_skills = set()

        # Liste des compétences que nous considérons comme "exécution" pour filtrer
        # Cela évite de surcharger le prompt de l'agent de décomposition avec des skills de TEAM 1.
        execution_related_skills_keywords = [
            "coding", "python", "javascript", "java", # Développement
            "research", "analysis", "synthesis",       # Recherche
            "testing", "test_case", "validation",      # Test (attention, 'validation' est aussi pour TEAM 1)
            "database_design", "api_design",           # Conception détaillée
            "documentation",                            # Documentation
            # "execution_plan_decomposition" # On ne veut pas qu'il s'appelle lui-même pour l'instant
            # Ajoutez d'autres mots-clés si nécessaire
        ]


        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{gra_url}/agents_status", timeout=10.0)
                response.raise_for_status()
                agents_list = response.json()

                if isinstance(agents_list, list):
                    for agent_info in agents_list:
                        agent_skills = agent_info.get("skills", [])
                        if isinstance(agent_skills, list):
                            for skill in agent_skills:
                                if isinstance(skill, str):
                                    # Filtrer pour ne garder que les compétences pertinentes pour l'exécution
                                    if any(keyword in skill.lower() for keyword in execution_related_skills_keywords):
                                        all_skills.add(skill)
                        else:
                            self.logger.warning(f"[{self.execution_plan_id}] Champ 'skills' mal formaté pour l'agent: {agent_info.get('name', 'Inconnu')}")
                else:
                    self.logger.error(f"[{self.execution_plan_id}] Réponse de /agents_status du GRA n'est pas une liste: {agents_list}")
            
            # S'assurer que les compétences de base sont présentes si aucune n'est trouvée ou pour robustesse
            if not all_skills:
                 default_exec_skills = ["coding_python", "web_research", "software_testing", "document_synthesis", "general_analysis", "database_design"]
                 self.logger.warning(f"[{self.execution_plan_id}] Aucune compétence d'exécution spécifique trouvée via GRA, utilisation d'une liste par défaut: {default_exec_skills}")
                 return default_exec_skills

            self.logger.info(f"[{self.execution_plan_id}] Compétences d'exécution disponibles trouvées et filtrées: {list(all_skills)}")
            return list(all_skills)

        except Exception as e:
            self.logger.error(f"[{self.execution_plan_id}] Erreur récupération compétences via GRA: {e}", exc_info=True)
            # Retourner une liste de fallback en cas d'erreur majeure
            default_exec_skills = ["coding_python", "web_research", "software_testing", "document_synthesis", "general_analysis", "database_design"]
            self.logger.warning(f"[{self.execution_plan_id}] Utilisation d'une liste de compétences par défaut due à une erreur GRA: {default_exec_skills}")
            return default_exec_skills

    async def process_plan_execution(self):
        self.logger.info(f"[{self.execution_plan_id}] Début du cycle de traitement d'exécution.")
        
        # MODIFICATION: Logguer l'état du graphe avant get_ready_tasks
        current_graph_snapshot_before_ready = self.task_graph.as_dict()
        self.logger.debug(f"[{self.execution_plan_id}] État du graphe AVANT get_ready_tasks: {json.dumps(current_graph_snapshot_before_ready.get('nodes', {}).get(f'decompose_{self.execution_plan_id}', {}), indent=2)}")

        ready_tasks_nodes = self.task_graph.get_ready_tasks() # get_ready_tasks lit aussi depuis Firestore

        if not ready_tasks_nodes:
            self.logger.info(f"[{self.execution_plan_id}] Aucune tâche d'exécution prête pour ce cycle.")
            # ... (logique de vérification de fin de plan, reste globalement la même)
            # S'assurer que self.logger est utilisé ici aussi
            overall_status = current_graph_snapshot_before_ready.get("overall_status", "UNKNOWN") # Utiliser le snapshot pris au début du cycle
            if overall_status.startswith("COMPLETED") or overall_status.startswith("FAILED") or overall_status.startswith("TIMEOUT") or overall_status == "PLAN_DECOMPOSED_EMPTY":
                 self.logger.info(f"[{self.execution_plan_id}] Plan d'exécution déjà dans un état terminal ou sans tâches enfants: {overall_status}")
                 return
            
            all_nodes_data = current_graph_snapshot_before_ready.get("nodes", {})
            if not all_nodes_data and overall_status == "PENDING_DECOMPOSITION":
                 self.logger.info(f"[{self.execution_plan_id}] En attente de la tâche de décomposition initiale (graph vide).")
                 return

            non_terminal_tasks_count = 0
            has_failures_in_graph = False
            if all_nodes_data:
                for _, node_data in all_nodes_data.items():
                    state = ExecutionTaskState(node_data.get("state", ExecutionTaskState.PENDING))
                    if state not in [ExecutionTaskState.COMPLETED, ExecutionTaskState.FAILED, ExecutionTaskState.CANCELLED]:
                        non_terminal_tasks_count += 1
                    if state == ExecutionTaskState.FAILED:
                        has_failures_in_graph = True
                
                if non_terminal_tasks_count == 0: 
                    final_status = "EXECUTION_COMPLETED_WITH_FAILURES" if has_failures_in_graph else "EXECUTION_COMPLETED_SUCCESSFULLY"
                    self.logger.info(f"[{self.execution_plan_id}] Toutes les tâches d'exécution sont terminales. Statut: {final_status}")
                    self.task_graph.set_overall_status(final_status)
            return

        for task_node_from_ready in ready_tasks_nodes:
            # Recharger explicitement la tâche pour garantir l'état le plus frais de la DB
            # avant de prendre des décisions critiques basées sur son état.
            task_node = self.task_graph.get_task(task_node_from_ready.id) 
            
            if not task_node: # Si la tâche n'existe plus (improbable)
                self.logger.warning(f"[{self.execution_plan_id}] Tâche {task_node_from_ready.id} retournée par get_ready_tasks mais non trouvée ensuite. Skipping.")
                continue
            
            # Log de l'état réel du task_node rechargé
            self.logger.debug(f"[{self.execution_plan_id}] Tâche {task_node.id} rechargée, état actuel en DB: {task_node.state.value}")

            if task_node.state != ExecutionTaskState.READY:
                # Le log précédent était trompeur s'il affichait "pending" alors que l'état était autre chose.
                self.logger.info(f"[{self.execution_plan_id}] Tâche {task_node.id} récupérée avec état '{task_node.state.value}' au lieu de READY. Skipping.")
                continue
            
            # La vérification spécifique pour la tâche DECOMPOSITION si elle est déjà traitée (overall_status)
            # est toujours pertinente comme double sécurité, mais le if ci-dessus devrait la couvrir si elle est COMPLETED.
            current_overall_status = self.task_graph.as_dict().get("overall_status") 
            if task_node.task_type == ExecutionTaskType.DECOMPOSITION and \
               current_overall_status not in ["INITIALIZING", "PENDING_DECOMPOSITION"]:
                self.logger.info(f"[{self.execution_plan_id}] Tâche de décomposition {task_node.id} est READY, mais statut global ('{current_overall_status}') indique qu'elle a déjà été traitée. Forcing COMPLETED.")
                self.task_graph.update_task_state(task_node.id, ExecutionTaskState.COMPLETED, "Forçage à COMPLETED car décomposition déjà effectuée (selon overall_status).")
                continue

            self.logger.info(f"[{self.execution_plan_id}] Prise en charge de la tâche prête: {task_node.id} ('{task_node.objective}'), Type: {task_node.task_type.value}, État: {task_node.state.value}")
            
            self.task_graph.update_task_state(task_node.id, ExecutionTaskState.ASSIGNED, "Assignation en cours...")
            
            agent_skill_needed = task_node.assigned_agent_type   
            if not agent_skill_needed:
                self.logger.error(f"[{self.execution_plan_id}] Tâche {task_node.id} n'a pas d'assigned_agent_type. Passage à FAILED.")
                self.task_graph.update_task_state(task_node.id, ExecutionTaskState.FAILED, "Type d'agent requis non spécifié.")
                continue

            agent_url = await self._get_agent_url_from_gra(agent_skill_needed)
            if not agent_url:
                self.logger.error(f"[{self.execution_plan_id}] Aucun agent pour '{agent_skill_needed}' (tâche {task_node.id}). Remise à READY.")
                self.task_graph.update_task_state(task_node.id, ExecutionTaskState.READY, f"Agent pour '{agent_skill_needed}' non trouvé, en attente.")
                continue 

            self.task_graph.update_task_state(task_node.id, ExecutionTaskState.WORKING, f"Appel de l'agent {agent_skill_needed} à {agent_url}.")
            
            input_for_agent_text: str
            if task_node.task_type == ExecutionTaskType.DECOMPOSITION:
                # Récupérer les compétences des agents d'exécution enregistrés
                all_registered_agents_skills = await self._get_all_available_execution_skills_from_gra() # Nouvelle méthode à créer

                input_payload_for_decomposition = {
                    "team1_plan_text": self.team1_plan_final_text,
                    "available_execution_skills": all_registered_agents_skills
                }
                input_for_agent_text = json.dumps(input_payload_for_decomposition)                

            else:
                input_for_agent_text = await self._prepare_input_for_execution_agent(task_node)

            a2a_task_result = await call_a2a_agent(agent_url, input_for_agent_text, self.execution_plan_id)

            if a2a_task_result and a2a_task_result.status:
                a2a_state_val = a2a_task_result.status.state.value
                
                artifact_text_content: Optional[str] = None
                artifact_id_content: Optional[str] = None
                if a2a_task_result.artifacts and len(a2a_task_result.artifacts) > 0:
                    first_artifact = a2a_task_result.artifacts[0]
                    artifact_id_content = first_artifact.artifactId
                    if first_artifact.parts and len(first_artifact.parts) > 0:
                        part_content = first_artifact.parts[0]
                        if hasattr(part_content, 'root') and hasattr(part_content.root, 'text'):
                            artifact_text_content = part_content.root.text
                        elif hasattr(part_content, 'text'):
                            artifact_text_content = part_content.text
                
                if a2a_state_val == "completed":
                    if task_node.task_type == ExecutionTaskType.DECOMPOSITION:
                        if artifact_text_content:
                            try:
                                decomposed_plan_structure = json.loads(artifact_text_content)
                                tasks_to_create = decomposed_plan_structure.get("tasks", [])
                                if isinstance(tasks_to_create, list):
                                    if not tasks_to_create:
                                        self.task_graph.update_task_state(task_node.id, ExecutionTaskState.COMPLETED, "Décomposition OK, aucune tâche enfant produite.")
                                        self.task_graph.set_overall_status("PLAN_DECOMPOSED_EMPTY")
                                    else:
                                        await self._add_and_resolve_decomposed_tasks(tasks_to_create, task_node.id)
                                        self.task_graph.update_task_state(task_node.id, ExecutionTaskState.COMPLETED, "Décomposition OK, tâches enfants ajoutées.")
                                        self.task_graph.set_overall_status("PLAN_DECOMPOSED")
                                else:
                                    self.task_graph.update_task_state(task_node.id, ExecutionTaskState.FAILED, "Format 'tasks' incorrect dans décomposition.")
                            except json.JSONDecodeError:
                                self.task_graph.update_task_state(task_node.id, ExecutionTaskState.FAILED, "Artefact décomposition JSON invalide.")
                        else:
                            self.task_graph.update_task_state(task_node.id, ExecutionTaskState.FAILED, "Agent décomposition n'a pas retourné d'artefact.")
                    
                    elif task_node.task_type == ExecutionTaskType.EXPLORATORY:
                        await self._process_completed_exploratory_task(task_node, artifact_text_content)
                        # L'état de completed_task_node est géré dans _process_completed_exploratory_task

                    elif task_node.task_type == ExecutionTaskType.EXECUTABLE:
                        summary = f"Livrable par {agent_skill_needed}."
                        if artifact_text_content and len(artifact_text_content) < 100 : summary += f" Aperçu: {artifact_text_content[:50]}..."
                        self.task_graph.update_task_output(task_node.id, artifact_ref=artifact_id_content, summary=summary)
                        self.task_graph.update_task_state(task_node.id, ExecutionTaskState.COMPLETED, "Exécution OK.")
                    
                    else: # CONTAINER, etc.
                        self.task_graph.update_task_state(task_node.id, ExecutionTaskState.COMPLETED, "Tâche traitée.")
                
                elif a2a_state_val == "failed":
                    # ... (gestion de l'échec A2A comme avant)
                    error_msg = f"Échec tâche A2A {a2a_task_result.id} pour {task_node.id} (agent {agent_skill_needed})."
                    # ... (extraction du message d'erreur)
                    self.task_graph.update_task_state(task_node.id, ExecutionTaskState.FAILED, error_msg)

                else: # Autres états A2A
                    self.task_graph.update_task_state(task_node.id, ExecutionTaskState.FAILED, f"État A2A inattendu: {a2a_state_val}")
            else: # Pas de réponse A2A valide
                self.task_graph.update_task_state(task_node.id, ExecutionTaskState.FAILED, "Réponse agent A2A invalide/absente.")
        
        self.logger.info(f"[{self.execution_plan_id}] Fin du cycle de traitement d'exécution.")

  
    async def _add_and_resolve_decomposed_tasks(self, tasks_json_list: List[Dict], initial_dependency_id: str, existing_local_id_map: Optional[Dict[str,str]] = None):
        """
        Fonction helper combinant la création de nœuds et la résolution de dépendances pour un lot de tâches.
        Les nouvelles tâches dépendront de initial_dependency_id et de leurs dépendances internes résolues.
        """
        local_id_to_global_id_map = existing_local_id_map if existing_local_id_map is not None else {}
        nodes_to_add_to_graph = {} # Clé: global_id, Valeur: (ExecutionTaskNode, task_data_dict_original)

        def first_pass_create_nodes_recursive(task_list_json: List[Dict], current_parent_global_id: Optional[str]):
            for task_json in task_list_json:
                node_obj, _ = self._create_node_from_json_data(task_json, current_parent_global_id, local_id_to_global_id_map)
                nodes_to_add_to_graph[node_obj.id] = (node_obj, task_json)
                
                json_sub_tasks = task_json.get("sous_taches", [])
                if json_sub_tasks:
                    first_pass_create_nodes_recursive(json_sub_tasks, node_obj.id)
        
        # Lancer la première passe pour ce lot de tâches
        first_pass_create_nodes_recursive(tasks_json_list, None) # Le parent_id sera None pour les tâches de premier niveau de ce lot

        # Deuxième passe : Résoudre les dépendances et ajouter au graphe
        for global_id, (node_obj, task_json_original) in nodes_to_add_to_graph.items():
            node_obj.dependencies.append(initial_dependency_id) # Dépend de la tâche "mère" (décomposition ou exploration)
            
            local_deps = task_json_original.get("dependances", [])
            for local_dep_id in local_deps:
                if local_dep_id in local_id_to_global_id_map: # Cherche dans les ID de ce lot
                    global_dep_id = local_id_to_global_id_map[local_dep_id]
                    if global_dep_id != node_obj.id:
                        node_obj.dependencies.append(global_dep_id)
                    else:
                        self.logger.warning(f"[{self.execution_plan_id}] Tentative d'auto-dépendance (lot) pour {global_id}. Ignorée.")
                else:
                    # Pourrait chercher dans une map globale des ID du plan entier si la dépendance est externe à ce lot
                    # Pour l'instant, on logue une dépendance non résolue au sein du lot.
                    self.logger.warning(f"[{self.execution_plan_id}] Dépendance locale (lot) '{local_dep_id}' pour '{task_json_original.get('id')}' non trouvée parmi les tâches de ce lot. Elle sera ignorée ou doit pointer vers une tâche existante du plan global.")
            
            node_obj.dependencies = list(set(node_obj.dependencies))
            self.task_graph.add_task(node_obj)
            self.logger.info(f"[{self.execution_plan_id}] Tâche (lot) '{node_obj.objective}' (ID: {node_obj.id}) ajoutée/résolue.")


    async def run_full_execution(self):
        """Méthode principale pour lancer et suivre l'exécution complète."""
        await self.initialize_and_decompose_plan()
        
        max_cycles = 10 # Pour éviter une boucle infinie en dév
        for i in range(max_cycles):
            self.logger.info(f"\n--- CYCLE D'EXÉCUTION TEAM 2 N°{i+1}/{max_cycles} pour le plan {self.execution_plan_id} ---")
            await self.process_plan_execution()

            current_graph_data = self.task_graph.as_dict()
            all_nodes = current_graph_data.get("nodes", {})
            overall_status = current_graph_data.get("overall_status", "UNKNOWN")

            if overall_status == "EXECUTION_COMPLETED_SUCCESSFULLY" or overall_status == "EXECUTION_COMPLETED_WITH_FAILURES" or overall_status.startswith("FAILED"):
                self.logger.info(f"[{self.execution_plan_id}] Statut global du plan d'exécution est terminal ({overall_status}). Arrêt de run_full_execution.")
                break # Sortir de la boucle for si le plan est terminé

            # ... (la logique pour vérifier non_terminal_tasks et mettre à jour overall_status si toutes sont terminales est bonne)
            # ... mais elle devrait aussi avoir un break après self.task_graph.set_overall_status(...)

            if not all_nodes and overall_status == "PENDING_DECOMPOSITION":
                await asyncio.sleep(3) 
                continue

            non_terminal_tasks = [
                nid for nid, ndata in all_nodes.items() 
                if ExecutionTaskState(ndata.get("state")) not in [
                    ExecutionTaskState.COMPLETED, ExecutionTaskState.FAILED, ExecutionTaskState.CANCELLED
                ]
            ]

            if overall_status.startswith("PLAN_DECOMPOSED") and not non_terminal_tasks: # Vérifier après PLAN_DECOMPOSED
                has_failed_tasks_in_graph = any(ExecutionTaskState(ndata.get("state")) == ExecutionTaskState.FAILED for ndata in all_nodes.values())
                final_plan_status = "EXECUTION_COMPLETED_WITH_FAILURES" if has_failed_tasks_in_graph else "EXECUTION_COMPLETED_SUCCESSFULLY"
                self.logger.info(f"[{self.execution_plan_id}] Toutes les tâches d'exécution sont terminales. Fin de l'exécution. Statut: {final_plan_status}")
                self.task_graph.set_overall_status(final_plan_status)
                break # AJOUTER CE BREAK ICI

            if i == max_cycles - 1:
                self.logger.warning(f"[{self.execution_plan_id}] Nombre maximum de cycles d'exécution ({max_cycles}) atteint.")
                if overall_status not in ["EXECUTION_COMPLETED_SUCCESSFULLY", "EXECUTION_COMPLETED_WITH_FAILURES"]: # Ne pas écraser un succès/échec déjà constaté
                    self.task_graph.set_overall_status("TIMEOUT_EXECUTION")
                break # Sortir après le log de timeout
            await asyncio.sleep(5)         
        

        final_status = self.task_graph.as_dict().get("overall_status")
        self.logger.info(f"[{self.execution_plan_id}] Exécution terminée avec le statut: {final_status}")
        # Ici, il faudrait notifier le GlobalSupervisorLogic