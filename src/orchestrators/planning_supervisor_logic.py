
# src/orchestrators/planning_supervisor_logic.py
# Les imports restent les mêmes...
import logging
from typing import List, Dict, Any, Optional
import uuid
import asyncio
import json

from src.shared.task_graph_management import TaskGraph, TaskNode, TaskState

from src.clients.a2a_api_client import call_a2a_agent
from a2a.types import Task as A2ATask, TaskState as A2ATaskStateEnum, TextPart

logger = logging.getLogger(__name__)
if not logger.hasHandlers():
    logging.basicConfig(level=logging.INFO)

REFORMULATOR_AGENT_URL = "http://localhost:8001"
EVALUATOR_AGENT_URL = "http://localhost:8002"
VALIDATOR_AGENT_URL = "http://localhost:8003"


class PlanningSupervisorLogic:
    def __init__(self, max_revisions: int = 2): # <-- CORRECTION ICI
        self.task_graph: Optional[TaskGraph] = None
        
        self.max_revisions = max_revisions
        logger.info(f"PlanningSupervisorLogic initialisé. Max révisions: {self.max_revisions}")
    def create_new_plan(self, raw_objective: str, plan_id: str) -> TaskNode:
        self.task_graph = TaskGraph(plan_id=plan_id)
        logger.info(f"Initialisation du TaskGraph pour le plan '{plan_id}' sur Firestore.")

        # On crée un objet TaskNode avant de l'ajouter
        root_task_node = TaskNode(
            task_id=plan_id,
            objective=raw_objective,
            assigned_agent="PlanningSupervisor",
            meta={"revision_count": 0}
        )
        self.task_graph.add_task(root_task_node)

        reformulation_task = TaskNode(
            task_id=f"reformulate_{uuid.uuid4().hex[:12]}",
            parent=plan_id,
            objective="Reformuler l'objectif initial",
            assigned_agent="ReformulatorAgentServer",
        )
        self.task_graph.add_task(reformulation_task)
        logger.info(f"Tâche de reformulation initiale '{reformulation_task.id}' ajoutée au plan.")
        return root_task_node
    
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

# DANS LA CLASSE PlanningSupervisorLogic:
    async def process_plan(self, plan_id: str):
        if not self.task_graph or self.task_graph.plan_id != plan_id:
            self.task_graph = TaskGraph(plan_id=plan_id)
            logger.info(f"Chargement du TaskGraph existant '{plan_id}' depuis Firestore.")

        logger.info(f"Traitement du plan ID: {plan_id}")
        
        ready_tasks = self.task_graph.get_ready_tasks()
        logger.info(f"Tâches prêtes à être exécutées: {[task.id for task in ready_tasks]}")

        if not ready_tasks:
            # ... (logique de fin de plan, si la tâche racine est terminée)
            root_task_node_check = self.task_graph.get_task(plan_id) # Récupérer le nœud racine mis à jour
            if root_task_node_check and root_task_node_check.state in [TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED, TaskState.UNABLE]:
                logger.info(f"Aucune tâche prête et la tâche racine est dans un état final ({root_task_node_check.state.value}).")
            else:
                logger.info("Aucune tâche prête à exécuter pour ce cycle, mais le plan n'est pas encore terminé.")
            return
        # Mouchard pour le début de la boucle sur les tâches prêtes
        current_cycle_log_id = uuid.uuid4().hex[:6] 
        logger.info(f"[MOUCHARD_CYCLE_START - {current_cycle_log_id}] Début du traitement des tâches prêtes pour le plan {plan_id}.")

        for task_node in ready_tasks:
          # --- MOUCHARD A ---
            logger.info(f"[MOUCHARD_A - {current_cycle_log_id}] Traitement de la tâche PRÊTE: {task_node.id}, état actuel (avant traitement): {task_node.state.value}, agent: {task_node.assigned_agent}")

            logger.info(f"Traitement de la tâche prête: {task_node.id} ({task_node.objective}) assignée à {task_node.assigned_agent}")

            if task_node.assigned_agent == "PlanningSupervisor":
                if task_node.state == TaskState.SUBMITTED:
                    self.task_graph.update_state(task_node.id, TaskState.WORKING, details="Décomposition par le superviseur.")
                    self.task_graph.update_state(task_node.id, TaskState.COMPLETED, details="Décomposition initiale terminée.")
                    logger.info(f"Tâche racine {task_node.id} marquée comme COMPLETED par le superviseur.")
            elif task_node.assigned_agent in ["ReformulatorAgentServer", "EvaluatorAgentServer", "ValidatorAgentServer"]: # ValidatorAgentServer est maintenant géré ici
                self.task_graph.update_state(task_node.id, TaskState.WORKING, details=f"Appel à l'agent {task_node.assigned_agent}.")
                
                input_for_agent: Any = ""
                agent_target_url: str = "" 

                if task_node.assigned_agent == "ReformulatorAgentServer":
                    # ... (logique identique pour obtenir input_for_agent) ...
                    agent_target_url = REFORMULATOR_AGENT_URL
                    if task_node.id.startswith("reformulate_rev"):
                            input_for_agent = task_node.objective # L'objectif contient déjà le feedback
                    else: # C'est la première reformulation
                        root_objective_task = self.task_graph.get_task(task_node.parent) if task_node.parent else task_node
                        input_for_agent = root_objective_task.objective if root_objective_task and root_objective_task.objective else ""

                    if not input_for_agent: 
                        logger.error(f"Objectif source vide pour la tâche de reformulation {task_node.id}. Marquage comme FAILED.")
                        self.task_graph.update_state(task_node.id, TaskState.FAILED, details="Objectif source vide.")
                        await self._handle_task_failure(task_node, "Objectif source vide.")
                        continue 
# Dans PlanningSupervisorLogic.process_plan, section pour EvaluatorAgentServer

                elif task_node.assigned_agent == "EvaluatorAgentServer":
                    agent_target_url = EVALUATOR_AGENT_URL
                    parent_node = self.task_graph.get_task(task_node.parent) # Le parent est le plan_root_node
                    found_input = False
                    if parent_node:
                        logger.info(f"Recherche d'artefact pour l'évaluateur. Parent '{parent_node.id}'. Enfants du parent: {parent_node.children}")
                        child_tasks_details = []
                        raw_child_tasks = [self.task_graph.get_task(child_id) for child_id in parent_node.children]

                        for t_idx, t_obj in enumerate(raw_child_tasks):
                            if t_obj:
                                child_tasks_details.append({
                                    "id": t_obj.id,
                                    "agent": t_obj.assigned_agent,
                                    "state": t_obj.state.value if hasattr(t_obj.state, 'value') else str(t_obj.state),
                                    "has_artifact": t_obj.artifact_ref is not None,
                                    "artifact_type": str(type(t_obj.artifact_ref)),
                                    "artifact_preview": str(t_obj.artifact_ref)[:100] if t_obj.artifact_ref else None
                                })
                            else:
                                child_tasks_details.append({"id": parent_node.children[t_idx], "status": "Non trouvé/None"})
                        logger.info(f"Détails des tâches enfants récupérées: {json.dumps(child_tasks_details, indent=2)}")

                        completed_reformulation_tasks = [
                            t for t in raw_child_tasks 
                            if t and t.assigned_agent == "ReformulatorAgentServer" and \
                            t.state == TaskState.COMPLETED and t.artifact_ref
                        ]
                        logger.info(f"Nombre de tâches de reformulation complétées avec artefact trouvées: {len(completed_reformulation_tasks)}")

                        if completed_reformulation_tasks:                    
                            # Trier par date/heure de la dernière mise à jour d'état pour trouver la plus récente
                            # (L'historique stocke les timestamps)
                            def get_completion_time(task: TaskNode):
                                for entry in reversed(task.history): # Cherche à partir de la fin
                                    if entry.get("to_state") == TaskState.COMPLETED.value:
                                        return entry.get("timestamp", "")
                                return "" # Si pas trouvé, mettre au début

                            completed_reformulation_tasks.sort(key=get_completion_time, reverse=True)
                            
                            latest_reformulation_task = completed_reformulation_tasks[0] # La plus récente
                            if isinstance(latest_reformulation_task.artifact_ref, str):
                                input_for_agent = latest_reformulation_task.artifact_ref
                                found_input = True
                                logger.info(f"Input pour EvaluatorAgentServer (depuis la reformulation la plus récente {latest_reformulation_task.id}): '{input_for_agent[:100]}...'")
                            else:
                                logger.error(f"L'artefact de la reformulation la plus récente {latest_reformulation_task.id} n'est pas une chaîne.")
                    else:
                            logger.error(f"Aucune tâche de reformulation complétée trouvée pour le plan {parent_node.id}.")

                    if not found_input:
                        logger.error(f"Artefact de reformulation manquant ou de format incorrect pour l'évaluation de la tâche {task_node.id}. Marquage comme FAILED.")
                        self.task_graph.update_state(task_node.id, TaskState.FAILED, details="Artefact de reformulation manquant/incorrect.")
                        await self._handle_task_failure(task_node, "Artefact de reformulation manquant/incorrect.")
                        continue # Passe à la tâche suivante dans ready_tasks                

                elif task_node.assigned_agent == "ValidatorAgentServer": # LOGIQUE POUR APPEL RÉEL AU VALIDATEUR
                    agent_target_url = VALIDATOR_AGENT_URL
                    parent_node = self.task_graph.get_task(task_node.parent) if task_node.parent else None
                    found_input = False
                    input_dict_for_validator: Optional[Dict[str, Any]] = None
                    if parent_node:
                        for child_id_of_root in parent_node.children:
                            sibling_task = self.task_graph.get_task(child_id_of_root)
                            if sibling_task and sibling_task.assigned_agent == "EvaluatorAgentServer" and \
                            sibling_task.state == TaskState.COMPLETED and isinstance(sibling_task.artifact_ref, dict): 
                                input_dict_for_validator = sibling_task.artifact_ref # C'est déjà un dict
                                found_input = True
                                logger.info(f"Input (dict) pour ValidatorAgentServer (depuis artefact évaluateur {sibling_task.id}): {input_dict_for_validator}")
                                break
                    if not found_input or not input_dict_for_validator:
                        logger.error(f"Artefact d'évaluation (dict) manquant ou de format incorrect pour la validation de la tâche {task_node.id}. Marquage comme FAILED.")
                        self.task_graph.update_state(task_node.id, TaskState.FAILED, details="Artefact d'évaluation (dict) manquant/incorrect.")
                        await self._handle_task_failure(task_node, "Artefact d'évaluation (dict) manquant/incorrect.")
                        continue
                    try:
                        input_for_agent = json.dumps(input_dict_for_validator) # Sérialiser le dict en chaîne JSON
                    except TypeError as e:
                        logger.error(f"Erreur de sérialisation JSON de l'input pour ValidatorAgent: {e}", exc_info=True)
                        self.task_graph.update_state(task_node.id, TaskState.FAILED, details="Erreur de formatage de l'input pour Validator.")
                        await self._handle_task_failure(task_node, "Erreur de formatage de l'input pour Validator.")
                        continue

              
                # --- Section commune pour l'appel A2A réel et traitement de la réponse (CORRIGÉE ET FINALISÉE) ---
  
               
                if not agent_target_url: 
                    logger.critical(f"ERREUR DE LOGIQUE: agent_target_url non défini pour {task_node.assigned_agent}")
                    # S'assurer de passer artifact_ref=None même en cas d'erreur avant l'appel
                    self.task_graph.update_state(task_node.id, TaskState.FAILED, details="Erreur interne: URL d'agent cible non définie.", artifact_ref=None)
                    updated_failed_node = self.task_graph.get_task(task_node.id)
                    if updated_failed_node:
                        await self._handle_task_failure(updated_failed_node, "URL d'agent cible non définie.")
                    continue # Passe à la tâche suivante
                
                if not isinstance(input_for_agent, str):
                    logger.warning(f"Input pour {task_node.assigned_agent} n'est pas une chaîne ({type(input_for_agent)}), tentative de conversion.")
                    input_for_agent = str(input_for_agent) if input_for_agent is not None else ""

                logger.info(f"Préparation de l'appel réel à {agent_target_url} pour la tâche {task_node.id} avec l'input: '{input_for_agent[:200]}...'")
                a2a_task_result: Optional[A2ATask] = await call_a2a_agent(
                    agent_url=agent_target_url,
                    input_text=input_for_agent, 
                    initial_context_id=plan_id 
                )

                final_a2a_state: TaskState = TaskState.FAILED # Par défaut
                details_message: str = "Réponse de l'agent non initialisée."
                extracted_artifact_content: Any = None
  
                if a2a_task_result and a2a_task_result.status and hasattr(a2a_task_result.status.state, 'value'):
                    try:
                        final_a2a_state = TaskState(a2a_task_result.status.state.value)
                    except ValueError:
                        logger.error(f"État A2A inconnu '{a2a_task_result.status.state.value}' pour {task_node.assigned_agent}.")
                        final_a2a_state = TaskState.FAILED 

                    details_message = f"Réponse de l'agent {task_node.assigned_agent} reçue."

                    if final_a2a_state == TaskState.COMPLETED:
                        if a2a_task_result.artifacts and len(a2a_task_result.artifacts) > 0:
                            first_artifact = a2a_task_result.artifacts[0]
                            artifact_text = None
                            if first_artifact.parts and len(first_artifact.parts) > 0:
                                part_content = first_artifact.parts[0]
                                if hasattr(part_content, 'root') and isinstance(part_content.root, TextPart):
                                    artifact_text = part_content.root.text
                                elif isinstance(part_content, TextPart):
                                     artifact_text = part_content.text
                            
                            if artifact_text is not None:
                                if task_node.assigned_agent in ["EvaluatorAgentServer", "ValidatorAgentServer"]:
                                    try:
                                        extracted_artifact_content = json.loads(artifact_text)
                                        details_message += " Artefact JSON reçu et parsé."
                                    except json.JSONDecodeError as e:
                                        logger.error(f"Impossible de parser JSON de {task_node.assigned_agent}: {e}. Artefact: {artifact_text[:200]}")
                                        extracted_artifact_content = {"error": "Invalid JSON artifact", "raw": artifact_text}
                                        final_a2a_state = TaskState.FAILED 
                                        details_message = f"Artefact JSON attendu de {task_node.assigned_agent} invalide."
                                else: 
                                    extracted_artifact_content = artifact_text
                                    details_message += " Artefact textuel reçu."
                            else:
                                extracted_artifact_content = "[Artefact textuel A2A non trouvé ou vide]"
                                details_message += " Artefact textuel A2A non trouvé ou vide."
                        else:
                            extracted_artifact_content = "[Aucun artefact A2A retourné]"
                            details_message += " Aucun artefact A2A retourné."
                        # --- MOUCHARD B ---
                        logger.info(f"[MOUCHARD_B - {current_cycle_log_id}] Tâche {task_node.id} - Réponse agent: état A2A final={final_a2a_state.value}, artifact_present={extracted_artifact_content is not None}")
                    
                    else: # Si l'agent A2A retourne FAILED, etc.
                        error_msg_from_agent = "Échec rapporté par l'agent."
                        if a2a_task_result.status.message and a2a_task_result.status.message.parts:
                            part_content = a2a_task_result.status.message.parts[0]
                            text_content_error = ""
                            if hasattr(part_content, 'root') and isinstance(part_content.root, TextPart):
                                text_content_error = part_content.root.text
                            elif isinstance(part_content, TextPart):
                                text_content_error = part_content.text
                            if text_content_error: error_msg_from_agent = text_content_error
                        details_message = error_msg_from_agent
                
                else: # Si a2a_task_result est None ou invalide structurellement
                    details_message = "Réponse A2A invalide ou statut manquant."
                    final_a2a_state = TaskState.FAILED

                # --- POINT CRUCIAL : SAUVEGARDE DE L'ÉTAT ET DE L'ARTEFACT ---
                self.task_graph.update_state(
                    task_node.id, 
                    final_a2a_state, 
                    details=details_message, 
                    artifact_ref=extracted_artifact_content # L'artefact est passé ici !
                )

                # On récupère le nœud *après* la mise à jour pour avoir la version persistée
                updated_task_node_from_db = self.task_graph.get_task(task_node.id)

                if updated_task_node_from_db:
                    if final_a2a_state == TaskState.COMPLETED:
                        logger.info(f"Tâche '{updated_task_node_from_db.id}' complétée par {updated_task_node_from_db.assigned_agent}. Log: {details_message}")
                        await self._handle_task_completion(updated_task_node_from_db) # APPEL UNIQUE
                    else: 
                        logger.error(f"La tâche '{updated_task_node_from_db.id}' a échoué. Message: {details_message}")
                        await self._handle_task_failure(updated_task_node_from_db, details_message)
                else:
                    logger.critical(f"Impossible de récupérer la tâche {task_node.id} de Firestore après mise à jour.")
                # --- FIN DE LA SECTION COMMUNE ---
                
                
            else: # Agents de replanification (LogAgent, SimpleReformulatorAgent, AlternativeStrategyAgent etc.)
                # ... (logique de simulation identique, utilisant _simulate_agent_call) ...
                logger.info(f"Traitement simulé pour l'agent '{task_node.assigned_agent}' sur la tâche {task_node.id}")
                self.task_graph.update_state(task_node.id, TaskState.WORKING, details=f"Simulation pour {task_node.assigned_agent}.")
                simulated_input = task_node.objective 
                simulated_response = await self._simulate_agent_call(task_node, simulated_input)
                response_status_sim = TaskState(simulated_response.get("status", TaskState.FAILED).value) 
                task_node.artifact_ref = simulated_response.get("artifact_content") if response_status_sim == TaskState.COMPLETED else None
                details_message_sim = f"Traitement simulé par {task_node.assigned_agent}"
                if response_status_sim == TaskState.FAILED:
                    details_message_sim = simulated_response.get("error_message", details_message_sim)
                self.task_graph.update_state(task_node.id, response_status_sim, details=details_message_sim)
                logger.info(f"Tâche '{task_node.id}' ({task_node.assigned_agent}) mise à jour à {response_status_sim.value} par simulation. Artefact: {task_node.artifact_ref}")
                if response_status_sim == TaskState.COMPLETED:
                    await self._handle_task_completion(task_node)
                elif response_status_sim == TaskState.FAILED: 
                    await self._handle_task_failure(task_node, details_message_sim)
            
        logger.info("État actuel du TaskGraph après traitement du cycle:")
        for node_id_iter, node_details_iter in self.task_graph.as_dict()["nodes"].items():
            logger.info(f"  - Tâche {node_id_iter}: {node_details_iter['objective']} - État: {node_details_iter['state']} - Agent: {node_details_iter['assigned_agent']}")

    # ... (le reste des méthodes _handle_..._completion et _handle_task_failure) ...

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

            rejected_plan_text = validation_output.get("evaluated_plan", "")
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
  
