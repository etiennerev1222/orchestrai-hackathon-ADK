# src/orchestrators/planning_supervisor_logic.py
import logging
from typing import List, Dict, Any, Optional
import uuid
import asyncio
import json
import httpx

from src.shared.task_graph_management import TaskGraph, TaskNode, TaskState
from src.clients.a2a_api_client import call_a2a_agent
from a2a.types import Task as A2ATask, TaskState as A2ATaskStateEnum, TextPart
from src.shared.service_discovery import get_gra_base_url

logger = logging.getLogger(__name__)
if not logger.hasHandlers():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Les URLs en dur sont supprimées, nous utiliserons le GRA

class PlanningSupervisorLogic:
    def __init__(self, max_revisions: int = 2):
        self.task_graph: Optional[TaskGraph] = None
        self.max_revisions = max_revisions
        self._gra_base_url: Optional[str] = None
        logger.info(f"PlanningSupervisorLogic initialisé. Max révisions: {self.max_revisions}")

    async def _ensure_gra_url(self):
        if not self._gra_base_url:
            self._gra_base_url = await get_gra_base_url()
            if not self._gra_base_url:
                logger.error("[Superviseur] Impossible de découvrir l'URL du GRA. Les appels aux agents échoueront.")
        return self._gra_base_url

    async def _get_agent_url_from_gra(self, skill: str) -> Optional[str]:
        gra_url = await self._ensure_gra_url()
        if not gra_url:
            return None

        agent_target_url = None
        try:
            async with httpx.AsyncClient() as client:
                logger.info(f"[Superviseur] Demande au GRA ({gra_url}) un agent avec la compétence: '{skill}'")
                response = await client.get(f"{gra_url}/agents", params={"skill": skill}, timeout=10.0)
                response.raise_for_status()
                data = response.json()
                agent_target_url = data[0].get("internal_url")
                if agent_target_url:
                    logger.info(f"[Superviseur] URL pour '{skill}' obtenue du GRA: {agent_target_url} (Agent: {data[0].get('name')}, url: {agent_target_url})")
                else:
                    logger.error(f"[Superviseur] Aucune URL retournée par le GRA pour la compétence '{skill}'. Réponse: {data}")
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.error(f"[Superviseur] Aucun agent trouvé pour '{skill}' dans le GRA à {e.request.url}.")
            else:
                logger.error(f"[Superviseur] Erreur HTTP ({e.response.status_code}) en contactant le GRA pour '{skill}': {e.response.text}")
        except httpx.RequestError as e:
            logger.error(f"[Superviseur] Erreur de requête en contactant le GRA pour '{skill}': {e}")
        except Exception as e:
            logger.error(f"[Superviseur] Erreur inattendue en contactant le GRA pour '{skill}': {e}")
        return agent_target_url

    def create_new_plan(self, raw_objective: str, plan_id: str) -> TaskNode:
        self.task_graph = TaskGraph(plan_id=plan_id)
        logger.info(f"Initialisation du TaskGraph pour le plan '{plan_id}' sur Firestore.")
        root_task_node = TaskNode(
            task_id=plan_id, objective=raw_objective,
            assigned_agent="PlanningSupervisor", meta={"revision_count": 0}
        )
        self.task_graph.add_task(root_task_node)
        reformulation_task = TaskNode(
            task_id=f"reformulate_{uuid.uuid4().hex[:12]}", parent=plan_id,
            objective="Reformuler l'objectif initial",
            assigned_agent="ReformulatorAgentServer"
        )
        self.task_graph.add_task(reformulation_task)
        logger.info(f"Tâche de reformulation initiale '{reformulation_task.id}' ajoutée au plan.")
        return root_task_node

    
    async def _handle_reformulation_completion(self, completed_reformulation_task: TaskNode):
        logger.info(f"La tâche de reformulation '{completed_reformulation_task.id}' est complétée.")
        plan_root_id = completed_reformulation_task.parent
        if not self.task_graph:
            logger.error("TaskGraph non initialisé dans _handle_reformulation_completion.")
            return
        plan_root_node = self.task_graph.get_task(plan_root_id)
        if not plan_root_id or not plan_root_node:
            logger.warning(f"Parent (plan racine) '{plan_root_id}' introuvable pour la tâche de reformulation '{completed_reformulation_task.id}'.")
            return
        evaluation_task = TaskNode(
            task_id=f"evaluate_{uuid.uuid4().hex[:12]}", parent=plan_root_id,
            objective="Évaluer l'objectif reformulé", assigned_agent="EvaluatorAgentServer"
        )
        self.task_graph.add_task(evaluation_task)
        logger.info(f"Nouvelle tâche d'évaluation '{evaluation_task.id}' ajoutée au plan '{plan_root_id}'.")

    
    async def _simulate_agent_call(self, task_node: TaskNode, input_data: Any) -> Dict[str, Any]:
        # Ne simule plus que les agents de replanification
        agent_type = task_node.assigned_agent
        logger.info(f"SIMULATION: Appel à {agent_type} pour la tâche '{task_node.id}' avec l'entrée: '{input_data}'")
        await asyncio.sleep(0.1)

        if agent_type in ["LogAgent", "SimpleReformulatorAgent", "AlternativeStrategyAgent"]: # Agents de replanification
            return {"status": TaskState.COMPLETED, "artifact_content": f"Tâche {task_node.objective} simulée complétée pour {agent_type}.", "artifact_type": "text"}

        logger.warning(f"SIMULATION: Type d'agent inconnu ou non géré pour la simulation directe: {agent_type}")
        return {"status": TaskState.FAILED, "error_message": f"Agent simulé {agent_type} non implémenté."}
    async def _handle_task_completion(self, completed_task: TaskNode):
        logger.info(f"Gestion de la complétion pour la tâche '{completed_task.id}' (agent: {completed_task.assigned_agent}).")
        # --- MOUCHARD E ---
        log_call_id = uuid.uuid4().hex[:6] 
        current_state_in_db = "Non vérifié"
        if self.task_graph:
            task_from_db = self.task_graph.get_task(completed_task.id)
            if task_from_db:
                current_state_in_db = task_from_db.state.value
        logger.info(f"[MOUCHARD_E - HANDLE_COMPLETION_ENTER - Appel ID: {log_call_id}] Entrée pour tâche: {completed_task.id} (agent: {completed_task.assigned_agent}). État actuel dans DB: {current_state_in_db}")

        if completed_task.assigned_agent == "ReformulatorAgentServer":
            await self._handle_reformulation_completion(completed_task)
        elif completed_task.assigned_agent == "EvaluatorAgentServer":
            await self._handle_evaluation_completion(completed_task)
        elif completed_task.assigned_agent == "ValidatorAgentServer":
           await self._handle_validation_completion(completed_task)
        # Ajouter des handlers pour les agents de replanification (LogAgent etc.) s'ils doivent déclencher d'autres tâches
        elif completed_task.assigned_agent in ["LogAgent", "SimpleReformulatorAgent", "AlternativeStrategyAgent"]:
         logger.info(f"Tâche de replanification/log '{completed_task.id}' assignée à {completed_task.assigned_agent} complétée (simulation).")


# Dans PlanningSupervisorLogic

    async def _handle_task_failure(self, failed_task: TaskNode, details: Optional[str] = None):
        logger.error(f"La tâche '{failed_task.id}' ({failed_task.objective}) assignée à {failed_task.assigned_agent} a échoué. Détails: {details}")
        
        if not self.task_graph:
            logger.error("TaskGraph non initialisé dans _handle_task_failure.")
            return

        # Exemple simple de replanification (vous pouvez le rendre plus intelligent)
        if failed_task.assigned_agent in ["ReformulatorAgentServer", "EvaluatorAgentServer", "ValidatorAgentServer"]:
            logger.info(f"Tentative de replanification pour la branche de la tâche échouée '{failed_task.id}'.")
            
            # --- CORRECTION : Créer des objets TaskNode ---
            new_subtasks_nodes: List[TaskNode] = []
            base_id_for_replan = failed_task.id.split('_')[-1][:4]

            analyze_task_data = {
                "task_id": f"analyze_fail_{base_id_for_replan}_{uuid.uuid4().hex[:4]}",
                "parent": failed_task.id, # Les tâches de replanification deviennent enfants de la tâche échouée
                "objective": f"Analyser l'échec de : {failed_task.objective}",
                "assigned_agent": "LogAgent" # Agent simulé pour l'instant
            }
            new_subtasks_nodes.append(TaskNode(**analyze_task_data))

            retry_task_data = {
                "task_id": f"retry_alt_{base_id_for_replan}_{uuid.uuid4().hex[:4]}",
                "parent": failed_task.id,
                "objective": f"Tenter une alternative pour : {failed_task.objective}",
                "assigned_agent": "AlternativeStrategyAgent" # Agent simulé
            }
            new_subtasks_nodes.append(TaskNode(**retry_task_data))
            # --- FIN CORRECTION ---

            try:
                # `replan_branch` attend une liste de TaskNode
                self.task_graph.replan_branch(failed_task.id, new_subtasks_nodes)
                logger.info(f"Branche de la tâche '{failed_task.id}' replanifiée avec {len(new_subtasks_nodes)} nouvelles sous-tâches.")
                
                # On marque la tâche échouée comme "FAILED" mais son traitement de l'échec est complété
                # Ou, si la replanification la remplace, on peut la mettre à COMPLETED.
                # Pour l'instant, laissons FAILED pour indiquer l'échec initial.
                # L'état COMPLETED serait si la tâche elle-même a géré son échec et se considère "résolue".
                # Ici, on remplace ses enfants, donc la tâche originale est "traitée" du point de vue de son échec.
                # Pour que la logique de get_ready_tasks fonctionne sur les nouveaux enfants,
                # failed_task doit être COMPLETED.
                self.task_graph.update_state(failed_task.id, TaskState.COMPLETED, 
                                            details=f"Échec initial ({details}), remplacé par replanification. Nouveaux enfants : {[t.id for t in new_subtasks_nodes]}")
                logger.info(f"Tâche '{failed_task.id}' marquée comme COMPLETED après replanification pour débloquer les enfants.")

            except Exception as e:
                logger.error(f"Erreur durant la replanification de la tâche '{failed_task.id}': {e}", exc_info=True)
        else:
            logger.warning(f"Aucune stratégie de replanification définie pour l'agent {failed_task.assigned_agent} sur la tâche {failed_task.id}.")


    async def process_plan(self, plan_id: str):
        if not self.task_graph or self.task_graph.plan_id != plan_id:
            self.task_graph = TaskGraph(plan_id=plan_id)
            logger.info(f"[Superviseur] (Re)chargé pour le plan '{plan_id}' depuis Firestore.")
        
        logger.info(f"[Superviseur] Traitement du plan ID: {plan_id}")
        ready_tasks = self.task_graph.get_ready_tasks()
        
        current_cycle_log_id = uuid.uuid4().hex[:6]
        logger.info(f"[MOUCHARD_CYCLE_START - {current_cycle_log_id}] Début du traitement. Tâches prêtes: {[task.id for task in ready_tasks]}")

        if not ready_tasks:
            root_task_node_check = self.task_graph.get_task(plan_id)
            if root_task_node_check and root_task_node_check.state in [TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED, TaskState.UNABLE]:
                logger.info(f"Aucune tâche prête et la tâche racine '{plan_id}' est dans un état final ({root_task_node_check.state.value}).")
            else:
                logger.info(f"Aucune tâche prête à exécuter pour le plan '{plan_id}', mais le plan n'est pas encore terminé.")
            return

        for task_node in ready_tasks:
            logger.info(f"[MOUCHARD_A - {current_cycle_log_id}] Traitement tâche PRÊTE: {task_node.id}, état: {task_node.state.value}, agent: {task_node.assigned_agent}")

            if task_node.assigned_agent == "PlanningSupervisor":
                if task_node.state == TaskState.SUBMITTED:
                    self.task_graph.update_state(task_node.id, TaskState.WORKING, details="Décomposition initiale par le superviseur.")
                    self.task_graph.update_state(task_node.id, TaskState.COMPLETED, details="Décomposition initiale terminée, en attente des sous-tâches enfants.")
                    logger.info(f"Tâche racine '{task_node.id}' décomposée et marquée comme COMPLETED pour débloquer les enfants.")
            
            elif task_node.assigned_agent in ["ReformulatorAgentServer", "EvaluatorAgentServer", "ValidatorAgentServer"]:
                self.task_graph.update_state(task_node.id, TaskState.WORKING, details=f"Préparation de l'appel à l'agent {task_node.assigned_agent}.")
                
                input_for_agent: Any = ""
                agent_target_url: Optional[str] = None
                skill_to_find: str = ""

                if task_node.assigned_agent == "ReformulatorAgentServer":
                    skill_to_find = "reformulation" # Compétence clé
                    if task_node.id.startswith("reformulate_rev"):
                        input_for_agent = task_node.objective
                        logger.info(f"Input pour Reformulator (révision) {task_node.id} est son propre objectif.")
                    else:
                        root_task_node = self.task_graph.get_task(task_node.parent) if task_node.parent else task_node
                        input_for_agent = root_task_node.objective if root_task_node and root_task_node.objective else ""
                        logger.info(f"Input pour Reformulator (initial) {task_node.id} est l'objectif racine.")
                    
                    if not input_for_agent: 
                        details = "Objectif source vide."
                        logger.error(f"{details} pour la tâche de reformulation {task_node.id}.")
                        self.task_graph.update_state(task_node.id, TaskState.FAILED, details=details, artifact_ref=None)
                        await self._handle_task_failure(self.task_graph.get_task(task_node.id), details)
                        continue

                elif task_node.assigned_agent == "EvaluatorAgentServer":
                    skill_to_find = "evaluation"
                    parent_node = self.task_graph.get_task(task_node.parent)
                    found_input = False
                    if parent_node:
                        # Logique de recherche de l'artefact de reformulation le plus récent
                        child_tasks_details = [] # Pour le log de débogage
                        raw_child_tasks = [self.task_graph.get_task(child_id) for child_id in parent_node.children]
                        for t_obj in raw_child_tasks: # Log de débogage
                            if t_obj: child_tasks_details.append({"id": t_obj.id, "agent": t_obj.assigned_agent, "state": t_obj.state.value, "has_artifact": t_obj.artifact_ref is not None})
                        logger.info(f"Recherche artefact pour évaluateur. Parent '{parent_node.id}'. Enfants: {json.dumps(child_tasks_details)}")

                        completed_reformulation_tasks = [
                            t for t in raw_child_tasks 
                            if t and t.assigned_agent == "ReformulatorAgentServer" and \
                            t.state == TaskState.COMPLETED and t.artifact_ref
                        ]
                        logger.info(f"Nb tâches reformulation complétées avec artefact: {len(completed_reformulation_tasks)}")
                        if completed_reformulation_tasks:
                            def get_completion_time(task: TaskNode):
                                for entry in reversed(task.history):
                                    if entry.get("to_state") == TaskState.COMPLETED.value: return entry.get("timestamp", "")
                                return ""
                            completed_reformulation_tasks.sort(key=get_completion_time, reverse=True)
                            latest_reformulation_task = completed_reformulation_tasks[0]
                            if isinstance(latest_reformulation_task.artifact_ref, str):
                                input_for_agent = latest_reformulation_task.artifact_ref
                                found_input = True
                                logger.info(f"Input pour Evaluator (depuis {latest_reformulation_task.id}): '{input_for_agent[:100]}...'")
                            else: logger.error(f"Artefact de {latest_reformulation_task.id} n'est pas une chaîne.")
                        else: logger.info(f"Aucune tâche de reformulation pertinente trouvée pour le plan {parent_node.id}.")
                    
                    if not found_input:
                        details = "Artefact de reformulation manquant/incorrect."
                        logger.error(f"{details} pour tâche évaluation {task_node.id}.")
                        self.task_graph.update_state(task_node.id, TaskState.FAILED, details=details, artifact_ref=None)
                        await self._handle_task_failure(self.task_graph.get_task(task_node.id), details)
                        continue

                elif task_node.assigned_agent == "ValidatorAgentServer":
                    skill_to_find = "validation"
                    parent_node = self.task_graph.get_task(task_node.parent)
                    found_input = False
                    input_dict_for_validator: Optional[Dict[str, Any]] = None
                    if parent_node:
                        # Logique de recherche de l'artefact d'évaluation le plus récent
                        child_tasks = [self.task_graph.get_task(child_id) for child_id in parent_node.children]
                        completed_evaluation_tasks = [
                            t for t in child_tasks if t and t.assigned_agent == "EvaluatorAgentServer" and \
                            t.state == TaskState.COMPLETED and isinstance(t.artifact_ref, dict)
                        ]
                        if completed_evaluation_tasks:
                            def get_completion_time(task: TaskNode): # Fonction utilitaire locale
                                for entry in reversed(task.history):
                                    if entry.get("to_state") == TaskState.COMPLETED.value: return entry.get("timestamp", "")
                                return ""
                            completed_evaluation_tasks.sort(key=get_completion_time, reverse=True)
                            latest_evaluation_task = completed_evaluation_tasks[0]
                            input_dict_for_validator = latest_evaluation_task.artifact_ref
                            found_input = True
                            logger.info(f"Input pour Validator (depuis {latest_evaluation_task.id}): {input_dict_for_validator}")
                    
                    if not found_input or not input_dict_for_validator:
                        details = "Artefact d'évaluation (dict) manquant/incorrect."
                        logger.error(f"{details} pour tâche validation {task_node.id}.")
                        self.task_graph.update_state(task_node.id, TaskState.FAILED, details=details, artifact_ref=None)
                        await self._handle_task_failure(self.task_graph.get_task(task_node.id), details)
                        continue
                    try:
                        input_for_agent = json.dumps(input_dict_for_validator)
                    except TypeError as e:
                        details = "Erreur formatage input pour Validator."
                        logger.error(f"Erreur JSON dump pour Validator: {e}", exc_info=True)
                        self.task_graph.update_state(task_node.id, TaskState.FAILED, details=details, artifact_ref=None)
                        await self._handle_task_failure(self.task_graph.get_task(task_node.id), details)
                        continue
                
                # --- APPEL AU GRA POUR OBTENIR L'URL DE L'AGENT ---
                if skill_to_find:
                    agent_target_url = await self._get_agent_url_from_gra(skill_to_find)
                
                # --- SECTION COMMUNE POUR L'APPEL A2A (version corrigée) ---
                if not agent_target_url: 
                    details = f"URL agent pour '{skill_to_find}' non trouvée via GRA."
                    logger.critical(f"{details} Impossible de traiter {task_node.id}")
                    self.task_graph.update_state(task_node.id, TaskState.FAILED, details=details, artifact_ref=None)
                    await self._handle_task_failure(self.task_graph.get_task(task_node.id), details)
                    continue
                
                if not isinstance(input_for_agent, str): # Déjà fait pour Validator, mais bon pour les autres
                    input_for_agent = str(input_for_agent) if input_for_agent is not None else ""

                logger.info(f"Appel réel à {agent_target_url} pour {task_node.id} avec input: '{str(input_for_agent)[:200]}...'")
                a2a_task_result = await call_a2a_agent(agent_url=agent_target_url, input_text=input_for_agent, initial_context_id=plan_id)
                
                final_a2a_state = TaskState.FAILED
                details_message = "Réponse agent non traitée."
                extracted_artifact_content = None

                if a2a_task_result and a2a_task_result.status and hasattr(a2a_task_result.status.state, 'value'):
                    try:
                        final_a2a_state = TaskState(a2a_task_result.status.state.value)
                    except ValueError:
                        final_a2a_state = TaskState.FAILED
                        details_message = f"État A2A inconnu: {a2a_task_result.status.state.value}"
                        logger.error(details_message)

                    if final_a2a_state == TaskState.COMPLETED:
                        details_message = f"Réponse agent {task_node.assigned_agent} reçue."
                        if a2a_task_result.artifacts and len(a2a_task_result.artifacts) > 0:
                            # ... (logique d'extraction d'artefact comme dans votre dernière version complète) ...
                            first_artifact = a2a_task_result.artifacts[0]
                            artifact_text = None
                            if first_artifact.parts and len(first_artifact.parts) > 0:
                                part_content = first_artifact.parts[0]
                                if hasattr(part_content, 'root') and isinstance(part_content.root, TextPart): artifact_text = part_content.root.text
                                elif isinstance(part_content, TextPart): artifact_text = part_content.text
                            if artifact_text is not None:
                                if task_node.assigned_agent in ["EvaluatorAgentServer", "ValidatorAgentServer"]:
                                    try:
                                        extracted_artifact_content = json.loads(artifact_text)
                                        details_message += " Artefact JSON parsé."
                                    except json.JSONDecodeError as e:
                                        extracted_artifact_content = {"error": "Invalid JSON", "raw": artifact_text}
                                        final_a2a_state = TaskState.FAILED
                                        details_message = f"JSON invalide de {task_node.assigned_agent}: {e}"
                                else:
                                    extracted_artifact_content = artifact_text
                                    details_message += " Artefact textuel reçu."
                            else: extracted_artifact_content = "[Artefact A2A vide]"
                        else: extracted_artifact_content = "[Aucun artefact A2A]"
                    else: # Échec rapporté par l'agent A2A
                        # ... (logique d'extraction du message d'erreur de l'agent A2A) ...
                        details_message = "Échec rapporté par l'agent A2A." # Simplifié
                else:
                    details_message = "Réponse A2A invalide."
                    final_a2a_state = TaskState.FAILED

                self.task_graph.update_state(task_node.id, final_a2a_state, details=details_message, artifact_ref=extracted_artifact_content)
                updated_node_from_db = self.task_graph.get_task(task_node.id)

                if updated_node_from_db:
                    if final_a2a_state == TaskState.COMPLETED:
                        logger.info(f"[MOUCHARD_D - {current_cycle_log_id}] Tâche {updated_node_from_db.id} ({updated_node_from_db.assigned_agent}) VA APPELER _handle_task_completion. État DB: {updated_node_from_db.state.value}")
                        await self._handle_task_completion(updated_node_from_db)
                    else:
                        await self._handle_task_failure(updated_node_from_db, details_message)
                else:
                    logger.error(f"CRITICAL: Impossible de récupérer {task_node.id} après update_state.")
            
            else: # Agents de replanification simulés
                # ... (votre logique de simulation) ...
                pass # Omis pour la clarté

        logger.info(f"[MOUCHARD_CYCLE_END - {current_cycle_log_id}] Fin du traitement des tâches prêtes.")
        # ... (log de l'état du graphe, si désiré) ...

        # ... (log de l'état du graphe) ...
# src/orchestrators/planning_supervisor_logic.py
    async def _handle_evaluation_completion(self, completed_evaluation_task: TaskNode):
        logger.info(f"La tâche d'évaluation '{completed_evaluation_task.id}' est complétée.")
        evaluation_output = completed_evaluation_task.artifact_ref
        plan_root_id = completed_evaluation_task.parent

        if not self.task_graph:
            logger.error("TaskGraph non initialisé dans _handle_evaluation_completion.")
            return

        plan_root_node = self.task_graph.get_task(plan_root_id)
        
        # --- CORRECTION 1: Message de log ---
        if not plan_root_id or not plan_root_node:
            # Utilisation de completed_evaluation_task.id ici
            logger.warning(f"Parent (plan racine) '{plan_root_id}' introuvable pour la tâche d'évaluation '{completed_evaluation_task.id}'. Arrêt du traitement de cette branche.")
            return

        evaluation_is_positive = False
        evaluation_notes = "Évaluation invalide ou incomplète."
        feasibility_score = "N/A" # Initialisation pour le log si le score n'est pas trouvé

        if isinstance(evaluation_output, dict):
            evaluation_notes = evaluation_output.get("evaluation_notes", evaluation_notes)
            feasibility_score = evaluation_output.get("feasibility_score") # Récupère le score
            if isinstance(feasibility_score, (int, float)) and feasibility_score >= 6:
                evaluation_is_positive = True
            else:
                 evaluation_notes = f"Score de faisabilité ({feasibility_score}) trop bas. " + evaluation_notes
        
        if evaluation_is_positive:
            logger.info(f"L'évaluation est positive (Score: {feasibility_score}). Création de la tâche de validation.")
            
            # --- CORRECTION 2: Création d'un objet TaskNode ---
            validation_task = TaskNode(
                task_id=f"validate_{uuid.uuid4().hex[:12]}", # Utilisation de uuid plus court pour la lisibilité
                parent=plan_root_id,
                objective="Valider le plan évalué",
                assigned_agent="ValidatorAgentServer"
            )
            self.task_graph.add_task(validation_task) # On passe l'objet TaskNode
            # --- FIN CORRECTION 2 ---
            
            logger.info(f"Nouvelle tâche de validation '{validation_task.id}' ajoutée au plan '{plan_root_id}'.")
        else:
            logger.warning(f"L'évaluation n'est pas positive: '{evaluation_notes}'.")
            # S'assurer que get_task retourne bien un objet utilisable par _handle_task_failure
            failed_parent_task = self.task_graph.get_task(plan_root_id)
            if failed_parent_task:
                 self.task_graph.update_state(plan_root_id, TaskState.FAILED, f"Évaluation non concluante: {evaluation_notes}")
                 await self._handle_task_failure(failed_parent_task, f"Évaluation non concluante: {evaluation_notes}")
            else:
                logger.error(f"Impossible de récupérer la tâche parente {plan_root_id} pour la marquer comme échouée après évaluation.")
# Dans la classe PlanningSupervisorLogic, dans src/orchestrators/planning_supervisor_logic.py

    async def _handle_reformulation_completion(self, completed_reformulation_task: TaskNode):
        # --- MOUCHARD F ---
        log_call_id = uuid.uuid4().hex[:6]
        logger.info(f"[MOUCHARD_F - HANDLE_REFORM_COMPLETION_ENTER - Appel ID: {log_call_id}] Entrée pour tâche de reformulation: {completed_reformulation_task.id} (ID objet: {id(completed_reformulation_task)})")

        logger.info(f"La tâche de reformulation '{completed_reformulation_task.id}' est complétée.")
        plan_root_id = completed_reformulation_task.parent # C'est l'ID du plan racine
        
        if not self.task_graph:
            logger.error("TaskGraph non initialisé dans _handle_reformulation_completion.")
            return
        
        # --- CORRECTION DE LA VÉRIFICATION ---
        # 1. On récupère le nœud parent (le plan racine) en utilisant son ID.
        plan_root_node = self.task_graph.get_task(plan_root_id) 

        # 2. On vérifie si plan_root_id est valide ET si plan_root_node a bien été trouvé.
        if not plan_root_id or not plan_root_node:
            logger.warning(f"Parent (plan racine) '{plan_root_id}' introuvable pour la tâche de reformulation '{completed_reformulation_task.id}'. Arrêt du traitement de cette branche.")
            return
        # --- FIN DE LA CORRECTION ---

        # Si on arrive ici, plan_root_node existe.
        # La suite de la logique pour créer la tâche d'évaluation est correcte.
        evaluation_task = TaskNode(
            task_id=f"evaluate_{uuid.uuid4().hex[:12]}",
            parent=plan_root_id, # On utilise l'ID du parent
            objective="Évaluer l'objectif reformulé",
            assigned_agent="EvaluatorAgentServer",
        )
        self.task_graph.add_task(evaluation_task)
        logger.info(f"Nouvelle tâche d'évaluation '{evaluation_task.id}' ajoutée au plan '{plan_root_id}'.")

    async def _handle_validation_completion(self, completed_validation_task: TaskNode): # <-- CORRECTION ICI
        logger.info(f"La tâche de validation '{completed_validation_task.id}' est complétée.")
        validation_output = completed_validation_task.artifact_ref
        logger.info(f"Résultat de la validation (artefact du TaskNode): {validation_output}")
        
        plan_root_id = completed_validation_task.parent
        plan_root_node = self.task_graph.get_task(plan_root_id)

        if not plan_root_node:
            logger.error(f"Nœud racine du plan {plan_root_id} introuvable. Arrêt.")
            return

        if isinstance(validation_output, dict) and validation_output.get("validation_status") == "approved":
            logger.info(f"Le plan '{plan_root_id}' est finalisé et approuvé !")
            self.task_graph.update_state(plan_root_id, TaskState.COMPLETED, "Plan global approuvé et complété.")
        else:
            comments = validation_output.get('validation_comments', "Validation non approuvée.")
            logger.warning(f"Le plan '{plan_root_id}' a été rejeté. Commentaires: {comments}")

            current_revision_count = plan_root_node.meta.get("revision_count", 0)
            if current_revision_count >= self.max_revisions:
                logger.error(f"Nombre maximum de révisions atteint. Le plan '{plan_root_id}' échoue.")
                self.task_graph.update_state(plan_root_id, TaskState.FAILED, f"Plan rejeté après {self.max_revisions} révisions.")
                return

            plan_root_node.meta["revision_count"] = current_revision_count + 1
            self.task_graph.add_task(plan_root_node) # Sauvegarde la mise à jour du compteur

            rejected_plan_text = validation_output[0].get("evaluated_plan", "")
            new_objective = (f"La version précédente du plan a été rejetée. Commentaires: '{comments}'. "
                             f"Plan rejeté: '{rejected_plan_text}'. Ta mission est de générer une nouvelle version qui corrige ces problèmes.")
            
            new_reformulation_task = TaskNode(
                task_id=f"reformulate_rev{plan_root_node.meta['revision_count']}_{uuid.uuid4()}",
                parent=plan_root_id,
                objective=new_objective,
                assigned_agent="ReformulatorAgentServer",
            )
            self.task_graph.add_task(new_reformulation_task)
            logger.info(f"Nouvelle tâche de reformulation '{new_reformulation_task.id}' ajoutée pour réviser le plan.")
  
