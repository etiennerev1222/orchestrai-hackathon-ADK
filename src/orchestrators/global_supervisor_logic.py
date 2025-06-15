import asyncio
import logging
import uuid
import json
import httpx
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone

import firebase_admin
from firebase_admin import credentials, firestore

from src.shared.service_discovery import get_gra_base_url
from src.clients.a2a_api_client import call_a2a_agent
from src.agents.user_interaction_agent.logic import ACTION_CLARIFY_OBJECTIVE
from src.orchestrators.planning_supervisor_logic import PlanningSupervisorLogic
from src.shared.task_graph_management import TaskGraph, TaskState as Team1TaskStateEnum
from src.orchestrators.execution_supervisor_logic import ExecutionSupervisorLogic
from src.shared.execution_task_graph_management import ExecutionTaskGraph

from a2a.types import Task, TaskState, TextPart

logger = logging.getLogger(__name__)
if not logger.hasHandlers():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

GLOBAL_PLANS_FIRESTORE_COLLECTION = "global_plans"
MAX_CLARIFICATION_ATTEMPTS = 3

class GlobalPlanState:
    INITIAL_OBJECTIVE_RECEIVED = "INITIAL_OBJECTIVE_RECEIVED"
    CLARIFICATION_PENDING_USER_INPUT = "CLARIFICATION_PENDING_USER_INPUT"
    OBJECTIVE_BEING_CLARIFIED_BY_AGENT = "OBJECTIVE_BEING_CLARIFIED_BY_AGENT"
    OBJECTIVE_CLARIFIED = "OBJECTIVE_CLARIFIED"
    TEAM1_PLANNING_INITIATED = "TEAM1_PLANNING_INITIATED"
    TEAM1_PLANNING_COMPLETED = "TEAM1_PLANNING_COMPLETED"
    TEAM1_PLANNING_FAILED = "TEAM1_PLANNING_FAILED"

    TEAM2_EXECUTION_INITIATING = "TEAM2_EXECUTION_INITIATING"
    TEAM2_EXECUTION_IN_PROGRESS = "TEAM2_EXECUTION_IN_PROGRESS"
    TEAM2_EXECUTION_COMPLETED = "TEAM2_EXECUTION_COMPLETED"
    TEAM2_EXECUTION_FAILED = "TEAM2_EXECUTION_FAILED"

    FAILED_MAX_CLARIFICATION_ATTEMPTS = "FAILED_MAX_CLARIFICATION_ATTEMPTS"
    FAILED_AGENT_ERROR = "FAILED_AGENT_ERROR"

class GlobalSupervisorLogic:
    def __init__(self):
        self._gra_base_url: Optional[str] = None
        self.db = None
        logger.info("GlobalSupervisorLogic initialisé.")
        
        try:
            if not firebase_admin._apps:
                cred = credentials.ApplicationDefault()
                firebase_admin.initialize_app(cred)
                logger.info("[GlobalSupervisor] Firebase Admin initialisé.")
            self.db = firestore.client()
            logger.info("[GlobalSupervisor] Client Firestore obtenu.")
        except Exception as e:
            logger.critical(f"[GlobalSupervisor] Échec de l'initialisation de Firestore: {e}.", exc_info=True)

    async def _ensure_gra_url(self):
        if not self._gra_base_url:
            self._gra_base_url = await get_gra_base_url()
            if not self._gra_base_url:
                logger.error("[GlobalSupervisor] Impossible de découvrir l'URL du GRA.")
                raise ConnectionError("GRA URL could not be discovered.")
        return self._gra_base_url

    async def _get_agent_url_from_gra(self, skill: str) -> Optional[str]:
        gra_url = await self._ensure_gra_url()
        if not gra_url:
            return None

        logger.info(f"[GlobalSupervisor] Demande au GRA ({gra_url}) un agent avec la compétence: '{skill}'")
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{gra_url}/agents", params={"skill": skill}, timeout=30.0)
                response.raise_for_status()
                data = response.json()

                if data and isinstance(data, list) and len(data) > 0:
                    agent = data[0]
                    
                    agent_target_url = agent.get('internal_url')
                    
                    logger.info(f"[GlobalSupervisor] Agent trouvé pour '{skill}': {agent.get('name')} à l'URL {agent_target_url}")
                    return agent_target_url
                else:
                    logger.error(f"[GlobalSupervisor] Aucun agent trouvé pour la compétence '{skill}'. Réponse du GRA: {data}")
                    return None

        except httpx.HTTPStatusError as e:
            logger.error(f"[GlobalSupervisor] Erreur HTTP en contactant le GRA : {e.response.text}")
        except httpx.RequestError as e:
            logger.error(f"[GlobalSupervisor] Erreur de requête en contactant le GRA : {e}")
        except Exception as e:
            logger.error(f"[GlobalSupervisor] Erreur inattendue en contactant le GRA : {e}", exc_info=True)
        
        return None
    

    async def _save_global_plan_state(self, global_plan_id: str, plan_data_to_update: Dict[str, Any]):
        if not self.db:
            logger.error(f"[GlobalSupervisor] Client Firestore non disponible. Impossible de sauvegarder plan '{global_plan_id}'.")
            return

        doc_ref = self.db.collection(GLOBAL_PLANS_FIRESTORE_COLLECTION).document(global_plan_id)
        plan_data_to_update['updated_at'] = datetime.now(timezone.utc).isoformat()
        
        try:
            await asyncio.to_thread(doc_ref.set, plan_data_to_update, merge=True)
            logger.info(f"[GlobalSupervisor] État plan global '{global_plan_id}' sauvegardé/mis à jour sur Firestore. Données: {plan_data_to_update}")
        except Exception as e:
            logger.error(f"[GlobalSupervisor] Erreur sauvegarde plan '{global_plan_id}' sur Firestore: {e}", exc_info=True)

    async def _load_global_plan_state(self, global_plan_id: str) -> Optional[Dict[str, Any]]:
        if not self.db:
            logger.error(f"[GlobalSupervisor] Client Firestore non disponible. Impossible de charger plan '{global_plan_id}'.")
            return None
            
        doc_ref = self.db.collection(GLOBAL_PLANS_FIRESTORE_COLLECTION).document(global_plan_id)
        try:
            doc = await asyncio.to_thread(doc_ref.get)
            if doc.exists:
                logger.info(f"[GlobalSupervisor] État plan global '{global_plan_id}' chargé depuis Firestore.")
                return doc.to_dict()
            else:
                logger.warning(f"[GlobalSupervisor] Plan global '{global_plan_id}' non trouvé sur Firestore.")
                return None
        except Exception as e:
            logger.error(f"[GlobalSupervisor] Erreur chargement plan '{global_plan_id}' depuis Firestore: {e}", exc_info=True)
            return None
    async def start_new_global_plan(self, raw_objective: str, user_id: Optional[str] = "default_user") -> Dict[str, Any]:
        global_plan_id = f"gplan_{uuid.uuid4().hex[:12]}"
        logger.info(f"[GlobalSupervisor] Démarrage nouveau plan global '{global_plan_id}' pour objectif: '{raw_objective}'")
        plan_data = {
            "user_id": user_id, "raw_objective": raw_objective, "clarified_objective": None,
            "current_supervisor_state": GlobalPlanState.INITIAL_OBJECTIVE_RECEIVED,
            "task_type_estimation": None, "last_question_to_user": None,
            "conversation_history": [], "clarification_attempts": 0,
            "team1_plan_id": None, "created_at": datetime.now(timezone.utc).isoformat()
        }
        await self._save_global_plan_state(global_plan_id, plan_data)
        return await self._trigger_clarification_step(global_plan_id, raw_objective, [])

    async def _trigger_clarification_step(self, global_plan_id: str, text_for_clarification: str, conversation_history: List[Dict[str,str]]) -> Dict[str, Any]:
        await self._save_global_plan_state(global_plan_id, {"current_supervisor_state": GlobalPlanState.OBJECTIVE_BEING_CLARIFIED_BY_AGENT})
        ui_agent_skill = ACTION_CLARIFY_OBJECTIVE
        
        ui_agent_url = await self._get_agent_url_from_gra(ui_agent_skill)
        logger.info(f"[GlobalSupervisor] Plan '{global_plan_id}': Appel à l'agent de clarification d'objectif ({ui_agent_skill}) à l'URL {ui_agent_url}")
        if not ui_agent_url:
            logger.error(f"[GlobalSupervisor] UserInteractionAgent introuvable pour '{ui_agent_skill}'. Plan '{global_plan_id}'.")
            await self._save_global_plan_state(global_plan_id, {"current_supervisor_state": GlobalPlanState.FAILED_AGENT_ERROR, "error_message": "UserInteractionAgent not found"})
            return {"status": "error", "message": "UserInteractionAgent not found", "global_plan_id": global_plan_id}

        agent_input_payload = {
            "action": ACTION_CLARIFY_OBJECTIVE,
            "current_objective_or_response": text_for_clarification,
            "conversation_history": conversation_history
        }
        agent_input_json_str = json.dumps(agent_input_payload)
        logger.info(f"[GlobalSupervisor] Appel UI Agent ({ui_agent_url}) pour plan '{global_plan_id}'. Payload: {agent_input_payload}")
        a2a_task_result: Optional[Task] = await call_a2a_agent(
            agent_url=ui_agent_url, input_text=agent_input_json_str, initial_context_id=global_plan_id
        )

        if not a2a_task_result or not a2a_task_result.status:
            logger.error(f"[GlobalSupervisor] Échec appel/réponse invalide de UserInteractionAgent pour plan '{global_plan_id}'.")
            await self._save_global_plan_state(global_plan_id, {"current_supervisor_state": GlobalPlanState.FAILED_AGENT_ERROR, "error_message": "UserInteractionAgent call failed or invalid response"})
            return {"status": "error", "message": "Failed call or invalid response from UserInteractionAgent", "global_plan_id": global_plan_id}

        raw_artifact_text = None

        if a2a_task_result.artifacts and len(a2a_task_result.artifacts) > 0:
            first_artifact = a2a_task_result.artifacts[0]
            if first_artifact.parts and len(first_artifact.parts) > 0:
                part_content = first_artifact.parts[0]
                if hasattr(part_content, 'root') and isinstance(part_content.root, TextPart) and part_content.root.text:
                    raw_artifact_text = part_content.root.text
                elif isinstance(part_content, TextPart) and part_content.text:
                     raw_artifact_text = part_content.text
                
                if raw_artifact_text:
                    try:
                        clarification_artifact_content = json.loads(raw_artifact_text)
                    except json.JSONDecodeError as e:
                        logger.error(f"[GlobalSupervisor] Impossible de parser l'artefact JSON de UI Agent: {e} - Data: {raw_artifact_text}")
        
        if clarification_artifact_content is None: 
            logger.warning(f"[GlobalSupervisor] Aucun artefact JSON valide reçu de UserInteractionAgent. État A2A: {a2a_task_result.status.state.value}")
            await self._save_global_plan_state(global_plan_id, {"current_supervisor_state": GlobalPlanState.FAILED_AGENT_ERROR, "error_message": "UserInteractionAgent missing valid artifact"})
            return {"status": "error", "message": "UserInteractionAgent did not return a valid artifact", "global_plan_id": global_plan_id}


        agent_payload_status = clarification_artifact_content.get("status")
        task_type_estimation = clarification_artifact_content.get("task_type_estimation")
        missing_summary = clarification_artifact_content.get("missing_elements_summary")
        tentative_objective = clarification_artifact_content.get("tentatively_enriched_objective")
        proposed_elements = clarification_artifact_content.get("proposed_elements")
        
        logger.info(f"[GS] Plan '{global_plan_id}' - UI Agent payload: status='{agent_payload_status}', type='{task_type_estimation}'")

        current_plan_data_for_attempts = await self._load_global_plan_state(global_plan_id) or {}
        current_attempts = current_plan_data_for_attempts.get("clarification_attempts", 0)

        updated_plan_fields = {
            "task_type_estimation": task_type_estimation,
            "missing_elements_summary": missing_summary,
            "last_agent_response_artifact": clarification_artifact_content,
            "tentatively_enriched_objective_from_agent": tentative_objective,
            "proposed_elements_from_agent": proposed_elements
        }

        if a2a_task_result.status.state.value == TaskState.completed.value and agent_payload_status == "clarified":
            final_clarified_objective = clarification_artifact_content.get("clarified_objective", tentative_objective)
            if not final_clarified_objective: final_clarified_objective = text_for_clarification
            
            logger.info(f"[GS] Plan '{global_plan_id}': Objectif clarifié par LLM: '{final_clarified_objective}'")
            updated_plan_fields["clarified_objective"] = final_clarified_objective
            updated_plan_fields["current_supervisor_state"] = GlobalPlanState.OBJECTIVE_CLARIFIED
            updated_plan_fields["last_question_to_user"] = None
            await self._save_global_plan_state(global_plan_id, updated_plan_fields)
            
            await self._initiate_team1_planning(global_plan_id, final_clarified_objective)
            return {"status": GlobalPlanState.OBJECTIVE_CLARIFIED, "clarified_objective": final_clarified_objective, "task_type_estimation": task_type_estimation, "global_plan_id": global_plan_id}

        elif a2a_task_result.status.state.value == TaskState.input_required.value and agent_payload_status == "needs_confirmation_or_clarification":
            question_for_user = clarification_artifact_content.get("question_for_user")
            logger.info(f"[GS] Plan '{global_plan_id}': UI Agent requiert entrée. Question: '{question_for_user}'")
            
            updated_plan_fields["last_question_to_user"] = question_for_user
            updated_plan_fields["current_supervisor_state"] = GlobalPlanState.CLARIFICATION_PENDING_USER_INPUT
            updated_plan_fields["clarification_attempts"] = current_attempts + 1
            await self._save_global_plan_state(global_plan_id, updated_plan_fields)
            return {
                "status": "clarification_pending",
                "question": question_for_user, 
                "task_type_estimation": task_type_estimation, 
                "global_plan_id": global_plan_id,
                "tentatively_enriched_objective": tentative_objective,
                "proposed_elements": proposed_elements
            }
        else:
            error_msg = f"État A2A ({a2a_task_result.status.state.value}) et/ou statut payload agent ('{agent_payload_status}') incohérents ou échec."
            logger.error(f"[GS] Plan '{global_plan_id}': {error_msg} Artefact: {clarification_artifact_content}")
            updated_plan_fields["current_supervisor_state"] = GlobalPlanState.FAILED_AGENT_ERROR
            updated_plan_fields["error_message"] = error_msg
            await self._save_global_plan_state(global_plan_id, updated_plan_fields)
            return {"status": "error", "message": error_msg, "global_plan_id": global_plan_id, "artifact": clarification_artifact_content}


    async def process_user_clarification_response(self, global_plan_id: str, user_response: str) -> Dict[str, Any]:
        logger.info(f"[GS] Plan '{global_plan_id}': Réponse utilisateur: '{user_response}'")
        current_plan_data = await self._load_global_plan_state(global_plan_id)
        if not current_plan_data:
            return {"status": "error", "message": f"Plan global '{global_plan_id}' non trouvé.", "global_plan_id": global_plan_id}

        current_attempts = current_plan_data.get("clarification_attempts", 0)
        if current_attempts >= MAX_CLARIFICATION_ATTEMPTS:
            logger.warning(f"[GS] Plan '{global_plan_id}': Max tentatives ({MAX_CLARIFICATION_ATTEMPTS}) atteint. Échec.")
            await self._save_global_plan_state(global_plan_id, {"current_supervisor_state": GlobalPlanState.FAILED_MAX_CLARIFICATION_ATTEMPTS})
            return {"status": "max_clarification_attempts_reached", "message": f"Max {MAX_CLARIFICATION_ATTEMPTS} tentatives atteintes.", "global_plan_id": global_plan_id}
        
        last_question = current_plan_data.get("last_question_to_user")
        updated_conversation_history: List[Dict[str,str]] = current_plan_data.get("conversation_history", [])
        if last_question: 
            updated_conversation_history.append({"agent_question": last_question, "user_answer": user_response})
        else:
            updated_conversation_history.append({"agent_question": "N/A (User provided additional info)", "user_answer": user_response})
        
        await self._save_global_plan_state(global_plan_id, {
            "conversation_history": updated_conversation_history,
            "last_question_to_user": None 
        })
        return await self._trigger_clarification_step(global_plan_id, user_response, updated_conversation_history)

    async def accept_objective_and_initiate_team1(self, global_plan_id: str, user_provided_objective: Optional[str] = None) -> Dict[str, Any]:
        """
        L'utilisateur force l'acceptation de l'objectif actuel (ou d'une version fournie)
        et lance la planification TEAM 1.
        """
        logger.info(f"[GS] Plan '{global_plan_id}': Acceptation forcée de l'objectif par l'utilisateur.")
        current_plan_data = await self._load_global_plan_state(global_plan_id)
        if not current_plan_data:
            return {"status": "error", "message": f"Plan global '{global_plan_id}' non trouvé.", "global_plan_id": global_plan_id}

        objective_to_use = user_provided_objective
        if not objective_to_use:
            objective_to_use = current_plan_data.get("last_agent_response_artifact", {}).get("tentatively_enriched_objective")
            if not objective_to_use:
                 objective_to_use = current_plan_data.get("clarified_objective")
            if not objective_to_use:
                objective_to_use = current_plan_data.get("raw_objective")

        if not objective_to_use:
             logger.error(f"[GS] Plan '{global_plan_id}': Aucun objectif (brut, enrichi, ou clarifié) à utiliser pour TEAM 1.")
             await self._save_global_plan_state(global_plan_id, {"current_supervisor_state": GlobalPlanState.FAILED_AGENT_ERROR, "error_message": "No objective found to start TEAM1 planning."})
             return {"status": "error", "message": "No objective available to start planning.", "global_plan_id": global_plan_id}

        logger.info(f"[GS] Plan '{global_plan_id}': Utilisation de l'objectif suivant pour TEAM 1: '{objective_to_use}'")
        
        await self._save_global_plan_state(global_plan_id, {
            "clarified_objective": objective_to_use,
            "current_supervisor_state": GlobalPlanState.OBJECTIVE_CLARIFIED,
            "last_question_to_user": None,
            "user_forced_clarification": True
        })

        await self._initiate_team1_planning(global_plan_id, objective_to_use)
        return {
            "status": GlobalPlanState.OBJECTIVE_CLARIFIED,
            "message": "Objectif accepté par l'utilisateur, planification TEAM 1 initiée.",
            "clarified_objective": objective_to_use,
            "global_plan_id": global_plan_id
        }
    async def _initiate_team1_planning(self, global_plan_id: str, final_clarified_objective: str):
        logger.info(f"[GS] Plan '{global_plan_id}': Lancement planification TEAM 1. Objectif: '{final_clarified_objective}'")
        
        current_plan_data = await self._load_global_plan_state(global_plan_id) or {}
        attempt_count = current_plan_data.get("team1_planning_attempts", 0) + 1
        
        team1_plan_id = f"team1_{global_plan_id}_attempt{attempt_count}_{uuid.uuid4().hex[:6]}"

        await self._save_global_plan_state(global_plan_id, {
            "team1_plan_id": team1_plan_id,
            "team1_planning_attempts": attempt_count,
            "clarified_objective_for_team1": final_clarified_objective,
            "current_supervisor_state": GlobalPlanState.TEAM1_PLANNING_INITIATED,
            "team1_status": "INITIATED"
        })
        
        try:
            team1_supervisor = PlanningSupervisorLogic()
            team1_supervisor.create_new_plan(raw_objective=final_clarified_objective, plan_id=team1_plan_id)
            logger.info(f"[GS] Plan TEAM 1 '{team1_plan_id}' (structure Firestore) créé pour plan global '{global_plan_id}'.")
            
            asyncio.create_task(self._process_team1_plan_fully(team1_supervisor, team1_plan_id, global_plan_id))
            logger.info(f"[GS] Tâche de fond lancée pour traiter entièrement TEAM 1 '{team1_plan_id}'.")
        except Exception as e:
            logger.error(f"[GS] Erreur initiation/lancement TEAM 1 pour '{team1_plan_id}': {e}", exc_info=True)
            await self._save_global_plan_state(global_plan_id, {
                "current_supervisor_state": GlobalPlanState.TEAM1_PLANNING_FAILED,
                "team1_status": "FAILED_INITIATION",
                "error_message": f"Erreur d'initiation TEAM 1: {str(e)}"
            })

    async def _process_team1_plan_fully(self, team1_supervisor: PlanningSupervisorLogic, team1_plan_id: str, global_plan_id: str):
        """
        Appelle team1_supervisor.process_plan en boucle jusqu'à ce que TOUTES les tâches
        du plan TEAM 1 (TaskGraph) soient dans un état terminal.
        Met à jour l'état du plan global en conséquence.
        """
        max_cycles_team1 = 20
        check_interval_seconds = 10
        
        logger.info(f"[GS] Démarrage du traitement complet et monitoring pour TEAM 1 plan '{team1_plan_id}' (global: '{global_plan_id}')")
        await self._save_global_plan_state(global_plan_id, {"team1_status": "PROCESSING_ACTIVE"})

        for i in range(max_cycles_team1):
            logger.info(f"[GS] Cycle de traitement TEAM 1 N°{i+1}/{max_cycles_team1} pour plan '{team1_plan_id}'")
            
            await team1_supervisor.process_plan(plan_id=team1_plan_id)

            await asyncio.sleep(check_interval_seconds) 

            team1_task_graph_reader = TaskGraph(plan_id=team1_plan_id)
            
            all_team1_tasks_data = await asyncio.to_thread(team1_task_graph_reader.as_dict)
            nodes_in_team1_plan = all_team1_tasks_data.get("nodes", {})

            if not nodes_in_team1_plan:
                logger.warning(f"[GS] Plan TEAM 1 '{team1_plan_id}': Aucun nœud trouvé dans le TaskGraph. Cela peut être un état initial ou une erreur.")
                if i > 1:
                    logger.error(f"[GS] Plan TEAM 1 '{team1_plan_id}': Aucun nœud après plusieurs cycles. Échec présumé.")
                    await self._save_global_plan_state(global_plan_id, {
                        "current_supervisor_state": GlobalPlanState.TEAM1_PLANNING_FAILED,
                        "team1_status": "FAILED_EMPTY_TASK_GRAPH"
                    })
                    return
                continue


            non_terminal_tasks_count = 0
            has_any_failed_tasks = False
            
            for task_id, task_data in nodes_in_team1_plan.items():
                task_state_str = task_data.get("state")
                if task_state_str not in [
                    Team1TaskStateEnum.COMPLETED.value, 
                    Team1TaskStateEnum.FAILED.value, 
                    Team1TaskStateEnum.CANCELLED.value,
                    Team1TaskStateEnum.UNABLE.value
                ]:
                    non_terminal_tasks_count += 1
                
                if task_state_str == Team1TaskStateEnum.FAILED.value:
                    has_any_failed_tasks = True
            
            logger.info(f"[GS] Plan TEAM 1 '{team1_plan_id}': {non_terminal_tasks_count} tâches non terminales, y a-t-il des échecs ? {has_any_failed_tasks}.")

            if non_terminal_tasks_count == 0:
                if has_any_failed_tasks:
                    logger.error(f"[GS] Plan TEAM 1 '{team1_plan_id}' terminé mais avec au moins une tâche en échec.")
                    await self._save_global_plan_state(global_plan_id, {
                        "current_supervisor_state": GlobalPlanState.TEAM1_PLANNING_FAILED,
                        "team1_status": "COMPLETED_WITH_FAILURES"
                    })
                else:
                    logger.info(f"[GS] Plan TEAM 1 '{team1_plan_id}' complété avec succès.")
                    await self._save_global_plan_state(global_plan_id, {
                        "current_supervisor_state": GlobalPlanState.TEAM1_PLANNING_COMPLETED,
                        "team1_status": "COMPLETED_SUCCESSFULLY"
                    })
                    
                    logger.info(f"[GS] Plan TEAM 1 complété, initiation de TEAM 2 pour plan global '{global_plan_id}'.")
                    current_global_plan_data = await self._load_global_plan_state(global_plan_id)
                    team1_final_plan_text = self._get_final_plan_text_from_team1(team1_plan_id)

                    if team1_final_plan_text:
                        await self._save_global_plan_state(global_plan_id, {
                             "current_supervisor_state": "TEAM2_EXECUTION_INITIATING",
                             "team2_status": "PENDING_INITIALIZATION"
                        })
                        execution_supervisor = ExecutionSupervisorLogic(
                            global_plan_id=global_plan_id,
                            team1_plan_final_text=team1_final_plan_text
                        )
                        asyncio.create_task(self._run_and_monitor_team2_execution(execution_supervisor, global_plan_id))
                    else:
                        logger.error(f"[GS] Impossible de récupérer le texte final du plan TEAM 1 '{team1_plan_id}'. TEAM 2 ne sera pas lancée.")
                        await self._save_global_plan_state(global_plan_id, {
                            "current_supervisor_state": GlobalPlanState.TEAM1_PLANNING_COMPLETED,
                            "team2_status": "NOT_STARTED_NO_PLAN_TEXT",
                            "error_message": "TEAM 1 final plan text could not be retrieved."
                        })
                return                    

            if has_any_failed_tasks:
                active_tasks_count = 0
                for task_data_inner in nodes_in_team1_plan.values():
                    if task_data_inner.get("state") in [Team1TaskStateEnum.SUBMITTED.value, Team1TaskStateEnum.WORKING.value]:
                        active_tasks_count +=1
                        break
                if active_tasks_count == 0:
                    logger.error(f"[GS] Plan TEAM 1 '{team1_plan_id}' a des tâches en échec et aucune tâche active restante.")
                    await self._save_global_plan_state(global_plan_id, {
                        "current_supervisor_state": GlobalPlanState.TEAM1_PLANNING_FAILED,
                        "team1_status": "FAILED_WITH_NO_ACTIVE_TASKS"
                    })
                    return


        logger.warning(f"[GS] Plan TEAM 1 '{team1_plan_id}' n'a pas atteint un état terminal complet après {max_cycles_team1} cycles de traitement/vérification.")
        await self._save_global_plan_state(global_plan_id, {
            "current_supervisor_state": GlobalPlanState.TEAM1_PLANNING_FAILED,
            "team1_status": "FAILED_TIMEOUT_MAX_CYCLES"
        })

    def _get_final_plan_text_from_team1(self, team1_plan_id: str) -> Optional[str]:
        """
        Récupère le texte du plan final approuvé par le ValidatorAgent de TEAM 1.
        Ceci est une placeholder - la logique exacte dépendra de comment/où ce texte est stocké.
        Probablement l'artefact de la dernière tâche de validation réussie du TaskGraph de TEAM 1.
        """
        logger.info(f"[GS] Tentative de récupération du texte final du plan TEAM 1 '{team1_plan_id}'.")
        
        team1_graph_manager = TaskGraph(plan_id=team1_plan_id)
        graph_data = team1_graph_manager.as_dict()
        nodes = graph_data.get("nodes", {})
        
        validation_tasks_completed = []
        for task_id, node_data in nodes.items():
            if node_data.get("assigned_agent") == "ValidatorAgentServer" and \
               node_data.get("state") == "completed" and \
               isinstance(node_data.get("artifact_ref"), dict):
                artifact_content = node_data.get("artifact_ref")
                if artifact_content.get("validation_status") == "approved":
                    validation_tasks_completed.append({
                        "timestamp": node_data.get("history", [{}])[-1].get("timestamp", ""),
                        "plan_text": artifact_content.get("final_plan", artifact_content.get("evaluated_plan"))
                    })
        
        if not validation_tasks_completed:
            logger.warning(f"[GS] Aucune tâche de validation approuvée trouvée pour TEAM 1 '{team1_plan_id}'.")
            return None
            
        validation_tasks_completed.sort(key=lambda x: x["timestamp"], reverse=True)
        final_plan_text = validation_tasks_completed[0].get("plan_text")

        if final_plan_text:
            logger.info(f"[GS] Texte final du plan TEAM 1 récupéré pour '{team1_plan_id}'.")
            return final_plan_text
        else:
            logger.warning(f"[GS] Texte final du plan TEAM 1 non trouvé dans l'artefact de validation pour '{team1_plan_id}'.")
            return None


    async def _run_and_monitor_team2_execution(self, execution_supervisor: ExecutionSupervisorLogic, global_plan_id: str):
        logger.info(f"[GS] Lancement du traitement complet de TEAM 2 pour plan global '{global_plan_id}' (exec_id: {execution_supervisor.execution_plan_id})")
        await self._save_global_plan_state(global_plan_id, {
            "current_supervisor_state": "TEAM2_EXECUTION_IN_PROGRESS",
            "team2_execution_plan_id": execution_supervisor.execution_plan_id,
            "team2_status": "RUNNING"
        })
        try:
            await execution_supervisor.run_full_execution()
            
            final_exec_status = execution_supervisor.task_graph.as_dict().get("overall_status", "UNKNOWN")
            logger.info(f"[GS] TEAM 2 pour plan global '{global_plan_id}' terminée. Statut final exécution: {final_exec_status}")
            
            new_global_state = "TEAM2_EXECUTION_COMPLETED" if "COMPLETED" in final_exec_status.upper() else "TEAM2_EXECUTION_FAILED"
            await self._save_global_plan_state(global_plan_id, {
                "current_supervisor_state": new_global_state,
                "team2_status": final_exec_status
            })
        except Exception as e:
            logger.error(f"[GS] Erreur majeure durant l'exécution de TEAM 2 pour '{global_plan_id}': {e}", exc_info=True)
            await self._save_global_plan_state(global_plan_id, {
                "current_supervisor_state": "TEAM2_EXECUTION_FAILED",
                "team2_status": "SUPERVISOR_ERROR",
                "error_message": f"Erreur superviseur TEAM 2: {str(e)}"
            })

    async def continue_team2_execution(self, global_plan_id: str) -> Dict[str, Any]:
        """Reprend l'exécution TEAM 2 pour un plan global existant."""
        current_plan = await self._load_global_plan_state(global_plan_id)
        if not current_plan:
            return {
                "status": "error",
                "message": f"Plan global '{global_plan_id}' non trouvé.",
                "global_plan_id": global_plan_id,
            }

        exec_plan_id = current_plan.get("team2_execution_plan_id")
        if not exec_plan_id:
            return {
                "status": "error",
                "message": "Aucune exécution TEAM 2 associée à ce plan.",
                "global_plan_id": global_plan_id,
            }

        team1_plan_id = current_plan.get("team1_plan_id")
        if not team1_plan_id:
            return {
                "status": "error",
                "message": "team1_plan_id manquant pour reprendre TEAM 2.",
                "global_plan_id": global_plan_id,
            }

        team1_text = self._get_final_plan_text_from_team1(team1_plan_id)
        if not team1_text:
            return {
                "status": "error",
                "message": "Impossible de récupérer le plan TEAM 1 final.",
                "global_plan_id": global_plan_id,
            }

        exec_supervisor = ExecutionSupervisorLogic(
            global_plan_id=global_plan_id,
            team1_plan_final_text=team1_text,
            execution_plan_id=exec_plan_id,
        )

        await exec_supervisor.continue_execution()

        final_exec_status = exec_supervisor.task_graph.as_dict().get("overall_status", "UNKNOWN")

        new_state = (
            "TEAM2_EXECUTION_COMPLETED"
            if final_exec_status.startswith("EXECUTION_COMPLETED")
            else current_plan.get("current_supervisor_state", "TEAM2_EXECUTION_IN_PROGRESS")
        )

        await self._save_global_plan_state(global_plan_id, {
            "current_supervisor_state": new_state,
            "team2_status": final_exec_status,
        })

        return {
            "status": "team2_execution_resumed",
            "message": final_exec_status,
            "global_plan_id": global_plan_id,
            "current_supervisor_state": new_state,
        }
async def main_test_global_supervisor():
    supervisor = GlobalSupervisorLogic()
    if not supervisor.db:
        logger.error("Échec initialisation Firestore. Arrêt test.")
        return

    
    objective = "Planifier et exécuter le développement d'une petite application CLI de visualisation de Fractale standard en Python, une application éducative pour les ado."
    user_id_for_test = f"test_user_{uuid.uuid4().hex[:6]}"

    logger.info(f"\n--- TEST COMPLET GlobalSupervisor: Objectif initial = '{objective}' ---")
    
    response_step1 = await supervisor.start_new_global_plan(raw_objective=objective, user_id=user_id_for_test)
    global_plan_id = response_step1.get("global_plan_id")
    logger.info(f"Réponse Étape 1 (start_new_global_plan pour '{global_plan_id}'): {json.dumps(response_step1, indent=2, ensure_ascii=False)}")
    if not global_plan_id:
        logger.error("Aucun global_plan_id retourné. Arrêt du test.")
        return
    
    current_state_s1 = await supervisor._load_global_plan_state(global_plan_id)
    if current_state_s1 and current_state_s1.get("current_supervisor_state") == GlobalPlanState.CLARIFICATION_PENDING_USER_INPUT:
        logger.info(f"Clarification demandée, réponse simulée pour '{global_plan_id}'...")
        simulated_user_response = "Oui, la proposition me convient, les fonctionnalités de base sont suffisantes pour un CLI."
        await supervisor.process_user_clarification_response(global_plan_id, simulated_user_response)
        current_state_s1 = await supervisor._load_global_plan_state(global_plan_id)

    if not (current_state_s1 and current_state_s1.get("current_supervisor_state") == GlobalPlanState.OBJECTIVE_CLARIFIED):
        logger.info(f"Objectif non clarifié, forçage de l'acceptation pour '{global_plan_id}' pour passer à TEAM 1...")
        await supervisor.accept_objective_and_initiate_team1(global_plan_id, current_state_s1.get("tentatively_enriched_objective_from_agent", objective))
    
    logger.info(f"\n--- Attente de la complétion de TEAM 1 pour '{global_plan_id}' ---")
    max_wait_cycles_team1 = 25
    team1_completed_successfully = False
    for cycle in range(max_wait_cycles_team1):
        await asyncio.sleep(15)
        current_global_state = await supervisor._load_global_plan_state(global_plan_id)
        supervisor_state = current_global_state.get("current_supervisor_state")
        team1_status = current_global_state.get("team1_status")
        logger.info(f"Cycle d'attente TEAM 1 ({cycle+1}/{max_wait_cycles_team1}) pour '{global_plan_id}': État Global = {supervisor_state}, Statut TEAM 1 = {team1_status}")

        if supervisor_state == GlobalPlanState.TEAM1_PLANNING_COMPLETED:
            logger.info(f"TEAM 1 COMPLÉTÉE avec succès pour '{global_plan_id}'.")
            team1_completed_successfully = True
            
        elif supervisor_state == GlobalPlanState.TEAM1_PLANNING_FAILED:
            logger.error(f"TEAM 1 ÉCHOUÉE pour '{global_plan_id}'. Arrêt du test.")
            return
    
    if not team1_completed_successfully:
        logger.error(f"TEAM 1 n'a pas terminé avec succès après {max_wait_cycles_team1} cycles pour '{global_plan_id}'.")
        final_state_doc_error = await supervisor._load_global_plan_state(global_plan_id)
        logger.info(f"État final (erreur TEAM 1) pour '{global_plan_id}': {json.dumps(final_state_doc_error, indent=2, ensure_ascii=False)}")
        return

    logger.info(f"\n--- Vérification de l'initiation et de la décomposition par TEAM 2 pour '{global_plan_id}' ---")
    max_wait_cycles_team2_decomp = 10
    team2_decomposition_done = False
    execution_plan_id_for_team2 = None
    max_overall_cycles = 40
    final_plan_status_reached = False

    for cycle in range(max_overall_cycles):
        await asyncio.sleep(10)
        current_global_plan_doc = await supervisor._load_global_plan_state(global_plan_id)
        if not current_global_plan_doc:
            logger.error(f"Impossible de charger l'état du plan global '{global_plan_id}'. Arrêt.")
            break

        current_supervisor_state = current_global_plan_doc.get("current_supervisor_state")
        team1_status = current_global_plan_doc.get("team1_status")
        team2_status = current_global_plan_doc.get("team2_status")
        team1_plan_id = current_global_plan_doc.get("team1_plan_id", "N/A")
        team2_exec_id = current_global_plan_doc.get("team2_execution_plan_id", "N/A")

        logger.info(f"Cycle Global {cycle+1}/{max_overall_cycles} pour '{global_plan_id}': "
                    f"État Sup Glob='{current_supervisor_state}', T1 Stat='{team1_status}' (ID:{team1_plan_id}), T2 Stat='{team2_status}' (ID:{team2_exec_id})")

        if current_supervisor_state == GlobalPlanState.TEAM2_EXECUTION_COMPLETED:
            if team2_status == "EXECUTION_COMPLETED_SUCCESSFULLY":
                logger.info(f"🎉 Plan Global '{global_plan_id}' COMPLÉTÉ AVEC SUCCÈS (TEAM 1 & TEAM 2 OK).")
            else:
                logger.warning(f"🏁 Plan Global '{global_plan_id}' : TEAM 2 terminée mais avec statut '{team2_status}'.")
            final_plan_status_reached = True
            break
        elif current_supervisor_state == GlobalPlanState.TEAM1_PLANNING_FAILED or \
             current_supervisor_state == GlobalPlanState.TEAM2_EXECUTION_FAILED or \
             current_supervisor_state == GlobalPlanState.FAILED_MAX_CLARIFICATION_ATTEMPTS or \
             current_supervisor_state == GlobalPlanState.FAILED_AGENT_ERROR:
            logger.error(f"❌ Échec du Plan Global '{global_plan_id}'. État: {current_supervisor_state}.")
            final_plan_status_reached = True
            break
        
        if cycle == max_overall_cycles - 1:
            logger.error(f"TIMEOUT: Le plan global '{global_plan_id}' n'a pas atteint un état final après {max_overall_cycles} cycles.")
            break

    final_doc = await supervisor._load_global_plan_state(global_plan_id)
    logger.info(f"\n--- État final complet du document Firestore pour Global Plan ID '{global_plan_id}' ---")
    logger.info(f"{json.dumps(final_doc, indent=2, ensure_ascii=False)}")
    logger.info(f"--- FIN DU TEST pour Global Plan ID '{global_plan_id}' ---")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logging.getLogger("src.orchestrators.global_supervisor_logic").setLevel(logging.DEBUG)
    logging.getLogger("src.orchestrators.execution_supervisor_logic").setLevel(logging.DEBUG)
    logging.getLogger("src.shared.execution_task_graph_management").setLevel(logging.DEBUG) 
    logging.getLogger("src.agents.decomposition_agent.logic").setLevel(logging.DEBUG)
    logging.getLogger("src.agents.research_agent.logic").setLevel(logging.DEBUG)
    logging.getLogger("src.agents.development_agent.logic").setLevel(logging.DEBUG)
    logging.getLogger("src.agents.testing_agent.logic").setLevel(logging.DEBUG)
    logging.getLogger("src.shared.llm_client").setLevel(logging.DEBUG)

    asyncio.run(main_test_global_supervisor())