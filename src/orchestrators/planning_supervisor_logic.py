
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
        self.task_graph = TaskGraph()
        self.max_revisions = max_revisions
        logger.info(f"PlanningSupervisorLogic initialisé. Max révisions: {self.max_revisions}")

    def create_new_plan(self, raw_objective: str, plan_id: Optional[str] = None) -> TaskNode: # <-- CORRECTION ICI
        if not plan_id:
            plan_id = f"plan_{uuid.uuid4()}"

        logger.info(f"Initialisation d'un nouveau plan '{plan_id}' avec l'objectif : {raw_objective}")

        root_task_node = self.task_graph.add_task(
            task_id=plan_id,
            objective=raw_objective,
            assigned_agent="PlanningSupervisor",
            meta={"revision_count": 0} # Ajout du compteur
        )
        logger.info(f"Tâche racine ajoutée au graphe: {root_task_node}")

        reformulation_task_id = f"reformulate_{uuid.uuid4()}"
        self.task_graph.add_task(
            task_id=reformulation_task_id,
            parent_id=plan_id,
            objective="Reformuler l'objectif initial",
            assigned_agent="ReformulatorAgentServer",
        )
        logger.info(f"Sous-tâche de reformulation ajoutée, parente de {plan_id}")

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
        if completed_task.assigned_agent == "ReformulatorAgentServer":
            await self._handle_reformulation_completion(completed_task)
        elif completed_task.assigned_agent == "EvaluatorAgentServer":
            await self._handle_evaluation_completion(completed_task)
        elif completed_task.assigned_agent == "ValidatorAgentServer":
           await self._handle_validation_completion(completed_task)
        # Ajouter des handlers pour les agents de replanification (LogAgent etc.) s'ils doivent déclencher d'autres tâches
        elif completed_task.assigned_agent in ["LogAgent", "SimpleReformulatorAgent", "AlternativeStrategyAgent"]:
         logger.info(f"Tâche de replanification/log '{completed_task.id}' assignée à {completed_task.assigned_agent} complétée (simulation).")

    async def _handle_task_failure(self, failed_task: TaskNode, details: Optional[str] = None):
        logger.error(f"La tâche '{failed_task.id}' ({failed_task.objective}) assignée à {failed_task.assigned_agent} a échoué. Détails: {details}")
       # Étendre pour inclure ValidatorAgentServer si une replanification spécifique est voulue pour lui
        if failed_task.assigned_agent in ["ReformulatorAgentServer", "EvaluatorAgentServer", "ValidatorAgentServer"]:
            logger.info(f"Tentative de replanification pour la branche de la tâche échouée '{failed_task.id}'.")
            # Simplification des noms pour les tâches de replanification
            base_id_for_replan = failed_task.id.split('_')[-1][:4] # Prendre une partie de l'ID original
            new_subtasks_data = [
                {"id": f"analyze_fail_{base_id_for_replan}_{uuid.uuid4().hex[:4]}", "objective": f"Analyser échec de {failed_task.objective}", "assigned_agent": "LogAgent"},
                {"id": f"retry_alt_{base_id_for_replan}_{uuid.uuid4().hex[:4]}", "objective": f"Tenter alternative pour {failed_task.objective}", "assigned_agent": "AlternativeStrategyAgent"}
            ]
            try:
                self.task_graph.replan_branch(failed_task.id, new_subtasks_data)
                logger.info(f"Branche de la tâche '{failed_task.id}' replanifiée avec {len(new_subtasks_data)} nouvelles sous-tâches.")
                self.task_graph.update_state(failed_task.id, TaskState.COMPLETED, 
                                            details=f"Échec initial ({details}), remplacé par replanification. Nouveaux enfants : {[st['id'] for st in new_subtasks_data]}")
                logger.info(f"Tâche '{failed_task.id}' marquée comme COMPLETED après replanification pour débloquer les enfants.")
            except Exception as e:
                logger.error(f"Erreur durant la replanification de la tâche '{failed_task.id}': {e}", exc_info=True)
        else:
            logger.warning(f"Aucune stratégie de replanification/gestion d'échec définie pour l'agent {failed_task.assigned_agent} sur la tâche {failed_task.id}.")

# DANS LA CLASSE PlanningSupervisorLogic:
    async def process_plan(self, plan_id: str):
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

        for task_node in ready_tasks:
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
                    root_objective_task = self.task_graph.get_task(task_node.parent) if task_node.parent else task_node
                    input_for_agent = root_objective_task.objective if root_objective_task and root_objective_task.objective else ""
                    if not input_for_agent: 
                        logger.error(f"Objectif source vide pour la tâche de reformulation {task_node.id}. Marquage comme FAILED.")
                        self.task_graph.update_state(task_node.id, TaskState.FAILED, details="Objectif source vide.")
                        await self._handle_task_failure(task_node, "Objectif source vide.")
                        continue 
                
                elif task_node.assigned_agent == "EvaluatorAgentServer":
                    # ... (logique identique pour obtenir input_for_agent) ...
                    agent_target_url = EVALUATOR_AGENT_URL
                    parent_node = self.task_graph.get_task(task_node.parent) if task_node.parent else None
                    found_input = False
                    if parent_node:
                        for child_id_of_root in parent_node.children:
                            sibling_task = self.task_graph.get_task(child_id_of_root)
                            if sibling_task and sibling_task.assigned_agent == "ReformulatorAgentServer" and \
                            sibling_task.state == TaskState.COMPLETED and sibling_task.artifact_ref:
                                if isinstance(sibling_task.artifact_ref, str): 
                                    input_for_agent = sibling_task.artifact_ref
                                    found_input = True
                                    logger.info(f"Input pour EvaluatorAgentServer (depuis artefact reformulation {sibling_task.id}): '{input_for_agent}'")
                                    break
                    if not found_input:
                        logger.error(f"Artefact de reformulation manquant ou de format incorrect pour l'évaluation de la tâche {task_node.id}. Marquage comme FAILED.")
                        self.task_graph.update_state(task_node.id, TaskState.FAILED, details="Artefact de reformulation manquant/incorrect.")
                        await self._handle_task_failure(task_node, "Artefact de reformulation manquant/incorrect.")
                        continue
                
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

                # --- Section commune pour l'appel A2A réel et traitement de la réponse ---
                if not agent_target_url: 
                    logger.critical(f"ERREUR DE LOGIQUE: agent_target_url non défini pour {task_node.assigned_agent}")
                    self.task_graph.update_state(task_node.id, TaskState.FAILED, details="Erreur interne: URL d'agent cible non définie.")
                    await self._handle_task_failure(task_node, "URL d'agent cible non définie.")
                    continue
                
                # S'assurer que input_for_agent est une chaîne pour call_a2a_agent
                if not isinstance(input_for_agent, str):
                    logger.warning(f"Input pour {task_node.assigned_agent} n'est pas une chaîne ({type(input_for_agent)}), tentative de conversion. Input: {input_for_agent}")
                    input_for_agent = str(input_for_agent) if input_for_agent is not None else ""

                logger.info(f"Préparation de l'appel réel à {agent_target_url} pour la tâche {task_node.id} avec l'input: '{input_for_agent}'")
                a2a_task_result: Optional[A2ATask] = await call_a2a_agent(
                    agent_url=agent_target_url,
                    input_text=input_for_agent, 
                    initial_context_id=plan_id 
                )

                if a2a_task_result and a2a_task_result.status and hasattr(a2a_task_result.status.state, 'value'):
                    try:
                        final_a2a_state = TaskState(a2a_task_result.status.state.value)
                    except ValueError:
                        logger.error(f"État A2A inconnu '{a2a_task_result.status.state.value}' reçu de {task_node.assigned_agent}.")
                        final_a2a_state = TaskState.FAILED

                    details_message = f"Réponse de {task_node.assigned_agent}."
                    extracted_artifact_content: Any = None

                    if final_a2a_state == TaskState.COMPLETED:
                        if a2a_task_result.artifacts:
                            first_artifact = a2a_task_result.artifacts[0]
                            if first_artifact.parts and \
                            hasattr(first_artifact.parts[0], 'root') and \
                            isinstance(first_artifact.parts[0].root, TextPart) and \
                            first_artifact.parts[0].root.text is not None:
                                artifact_text = first_artifact.parts[0].root.text
                                
                                if task_node.assigned_agent in ["EvaluatorAgentServer", "ValidatorAgentServer"]:
                                    try:
                                        extracted_artifact_content = json.loads(artifact_text)
                                        details_message = f"Artefact JSON reçu: {json.dumps(extracted_artifact_content, ensure_ascii=False, indent=2)}"
                                    except json.JSONDecodeError:
                                        logger.error(f"Impossible de parser l'artefact JSON de {task_node.assigned_agent}: {artifact_text}")
                                        extracted_artifact_content = {"error": "Invalid JSON artifact", "raw": artifact_text}
                                        final_a2a_state = TaskState.FAILED 
                                        details_message = f"Artefact JSON attendu de {task_node.assigned_agent} invalide."
                                else: 
                                    extracted_artifact_content = artifact_text
                                    details_message = f"Artefact textuel reçu: {extracted_artifact_content}"
                            else:
                                extracted_artifact_content = "[Artefact textuel non trouvé ou vide]"
                                details_message = "Artefact textuel non trouvé ou vide dans la réponse de l'agent."
                        else:
                            extracted_artifact_content = "[Aucun artefact]"
                            details_message = "Aucun artefact retourné par l'agent."
                        
                        task_node.artifact_ref = extracted_artifact_content 
                        self.task_graph.update_state(task_node.id, final_a2a_state, details=details_message) # Utiliser final_a2a_state ici
                        if final_a2a_state == TaskState.COMPLETED: # Re-vérifier car il a pu changer
                            logger.info(f"Tâche '{task_node.id}' complétée par {task_node.assigned_agent}. {details_message}")
                            await self._handle_task_completion(task_node)
                        else: 
                            logger.error(f"La tâche '{task_node.id}' a été marquée FAILED en raison d'un problème d'artefact avec {task_node.assigned_agent}. Msg: {details_message}")
                            await self._handle_task_failure(task_node, details_message)
                    else: 
                        error_msg_from_agent = "Échec rapporté par l'agent."
                        # ... (logique d'extraction du message d'erreur identique) ...
                        if a2a_task_result.status.message and a2a_task_result.status.message.parts:
                            first_message_part = a2a_task_result.status.message.parts[0]
                            text_content_error = ""
                            if hasattr(first_message_part, 'root') and isinstance(first_message_part.root, TextPart):
                                text_content_error = first_message_part.root.text
                            elif isinstance(first_message_part, TextPart):
                                text_content_error = first_message_part.text
                            if text_content_error: error_msg_from_agent = text_content_error
                        self.task_graph.update_state(task_node.id, TaskState.FAILED, details=error_msg_from_agent)
                        logger.error(f"La tâche '{task_node.id}' a échoué avec l'agent {task_node.assigned_agent}. Message: {error_msg_from_agent}")
                        await self._handle_task_failure(task_node, error_msg_from_agent)
                else:
                    error_details = "Aucun résultat de tâche valide retourné par l'appel A2A ou statut manquant."
                    self.task_graph.update_state(task_node.id, TaskState.FAILED, details=error_details)
                    logger.error(f"La tâche '{task_node.id}' assignée à {task_node.assigned_agent} a échoué: {error_details}")
                    await self._handle_task_failure(task_node, error_details)
            
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
        # Cette méthode est correcte
        logger.info(f"La tâche d'évaluation '{completed_evaluation_task.id}' est complétée.")
        evaluation_output = completed_evaluation_task.artifact_ref
        plan_root_id = completed_evaluation_task.parent
        if not plan_root_id or plan_root_id not in self.task_graph.nodes: return

        evaluation_is_positive = False
        evaluation_notes = "Évaluation invalide ou incomplète."

        if isinstance(evaluation_output, dict):
            evaluation_notes = evaluation_output.get("evaluation_notes", evaluation_notes)
            feasibility_score = evaluation_output.get("feasibility_score")
            if isinstance(feasibility_score, (int, float)) and feasibility_score >= 6:
                evaluation_is_positive = True
            else:
                 evaluation_notes = f"Score de faisabilité ({feasibility_score}) trop bas. " + evaluation_notes
        
        if evaluation_is_positive:
            logger.info(f"L'évaluation est positive (Score: {feasibility_score}). Création de la tâche de validation.")
            validation_task_id = f"validate_{uuid.uuid4()}"
            self.task_graph.add_task(
                task_id=validation_task_id,
                parent_id=plan_root_id,
                objective="Valider le plan évalué",
                assigned_agent="ValidatorAgentServer"
            )
            logger.info(f"Nouvelle tâche de validation '{validation_task_id}' ajoutée au plan '{plan_root_id}'.")
        else:
            logger.warning(f"L'évaluation n'est pas positive: '{evaluation_notes}'.")
            self.task_graph.update_state(plan_root_id, TaskState.FAILED, f"Évaluation non concluante: {evaluation_notes}")
            await self._handle_task_failure(self.task_graph.get_task(plan_root_id), f"Évaluation non concluante: {evaluation_notes}")

    async def _handle_reformulation_completion(self, completed_reformulation_task: TaskNode):
        # Cette méthode est correcte
        logger.info(f"La tâche de reformulation '{completed_reformulation_task.id}' est complétée.")
        plan_root_id = completed_reformulation_task.parent
        if not plan_root_id or plan_root_id not in self.task_graph.nodes: return
        evaluation_task_id = f"evaluate{uuid.uuid4()}"
        self.task_graph.add_task(
            task_id=evaluation_task_id,
            parent_id=plan_root_id,
            objective="Évaluer l'objectif reformulé",
            assigned_agent="EvaluatorAgentServer",
        )
        logger.info(f"Nouvelle tâche d'évaluation '{evaluation_task_id}' ajoutée au plan '{plan_root_id}'.")

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
            comments = "Validation non approuvée ou format d'artefact inattendu."
            if isinstance(validation_output, dict):
                comments = validation_output.get('validation_comments', comments)
            
            logger.warning(f"Le plan '{plan_root_id}' a été rejeté. Commentaires: {comments}")

            current_revision_count = plan_root_node.meta.get("revision_count", 0)
            if current_revision_count >= self.max_revisions:
                logger.error(f"Nombre maximum de révisions ({self.max_revisions}) atteint. Le plan '{plan_root_id}' échoue définitivement.")
                self.task_graph.update_state(plan_root_id, TaskState.FAILED, f"Plan rejeté après {self.max_revisions} révisions. Dernier commentaire: {comments}")
                return

            plan_root_node.meta["revision_count"] = current_revision_count + 1
            logger.info(f"Tentative de révision n°{plan_root_node.meta['revision_count']} pour le plan '{plan_root_id}'.")

            rejected_plan_text = validation_output.get("evaluated_plan", "Le plan précédent n'a pas pu être récupéré.")
            new_objective = (
                f"La version précédente du plan a été rejetée. Voici le plan rejeté et les commentaires associés.\n\n"
                f"PLAN REJETÉ:\n'''{rejected_plan_text}'''\n\n"
                f"COMMENTAIRES DE REJET:\n'''{comments}'''\n\n"
                "Ta mission est de générer une nouvelle version du plan qui prend impérativement en compte ces commentaires pour corriger les faiblesses identifiées."
            )
            
            new_reformulation_task_id = f"reformulate_rev{plan_root_node.meta['revision_count']}_{uuid.uuid4()}"
            self.task_graph.add_task(
                task_id=new_reformulation_task_id,
                parent_id=plan_root_id,
                objective=new_objective,
                assigned_agent="ReformulatorAgentServer",
            )
            logger.info(f"Nouvelle tâche de reformulation '{new_reformulation_task_id}' ajoutée pour réviser le plan.")
   


if __name__ == "__main__":
    import asyncio
    import json

    async def main_orchestrator_full_flow_test():
        logger.info("--- DÉBUT DU TEST ORCHESTRATEUR FLUX COMPLET (VALIDATION SIMULÉE) ---")
        supervisor_logic = PlanningSupervisorLogic()

        objective = "Organiser une conférence sur l'IA éthique à Genève pour la communauté locale dans les 12 prochains mois maximum. budget 10000 francs suisses."
        root_task_node = supervisor_logic.create_new_plan(
            raw_objective=objective,
            plan_id="plan_flux_complet"
        )

        print("\n--- État initial du graphe ---")
        print(json.dumps(supervisor_logic.task_graph.as_dict(), indent=2, ensure_ascii=False))

        max_cycles = 20
        for i in range(max_cycles):
            logger.info(f"\n--- CYCLE DE TRAITEMENT DU PLAN N°{i+1} ---")

            current_root_task_status = supervisor_logic.task_graph.get_task(root_task_node.id).state
            ready_tasks_before = supervisor_logic.task_graph.get_ready_tasks()

            if not ready_tasks_before and current_root_task_status in [TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED, TaskState.UNABLE]:
                logger.info(f"Aucune tâche prête et la tâche racine est dans un état final ({current_root_task_status.value}). Arrêt anticipé du plan.")
                break

            await supervisor_logic.process_plan(root_task_node.id)

            print(f"\n--- État du graphe après cycle {i+1} ---")
            current_graph_state_dict = supervisor_logic.task_graph.as_dict()
            print(json.dumps(current_graph_state_dict, indent=2, ensure_ascii=False))

        logger.info(f"\n--- ÉTAT FINAL DU PLAN '{root_task_node.id}' ---")
        final_root_status = supervisor_logic.task_graph.get_task(root_task_node.id).state.value
        logger.info(f"État final de la tâche racine: {final_root_status}")
        if final_root_status == TaskState.COMPLETED.value:
            logger.info("Le plan a été complété avec succès !")
        else:
            logger.warning(f"Le plan s'est terminé avec un statut: {final_root_status}")
        logger.info("--- FIN DU TEST ORCHESTRATEUR FLUX COMPLET ---")

    asyncio.run(main_orchestrator_full_flow_test())
