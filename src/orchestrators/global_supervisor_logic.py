# src/orchestrators/global_supervisor_logic.py
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
# Assurez-vous que TaskGraph et son TaskState sont importés correctement
from src.shared.task_graph_management import TaskGraph, TaskState as Team1TaskStateEnum # Renommé pour clarté

from a2a.types import Task, TaskState, TextPart

logger = logging.getLogger(__name__)
if not logger.hasHandlers():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

GLOBAL_PLANS_FIRESTORE_COLLECTION = "global_plans"
MAX_CLARIFICATION_ATTEMPTS = 3 # Définir un maximum de tours de clarification

class GlobalPlanState:
    INITIAL_OBJECTIVE_RECEIVED = "INITIAL_OBJECTIVE_RECEIVED"
    CLARIFICATION_PENDING_USER_INPUT = "CLARIFICATION_PENDING_USER_INPUT"
    OBJECTIVE_BEING_CLARIFIED_BY_AGENT = "OBJECTIVE_BEING_CLARIFIED_BY_AGENT"
    OBJECTIVE_CLARIFIED = "OBJECTIVE_CLARIFIED"
    TEAM1_PLANNING_INITIATED = "TEAM1_PLANNING_INITIATED"
    TEAM1_PLANNING_COMPLETED = "TEAM1_PLANNING_COMPLETED"
    TEAM1_PLANNING_FAILED = "TEAM1_PLANNING_FAILED"
    FAILED_MAX_CLARIFICATION_ATTEMPTS = "FAILED_MAX_CLARIFICATION_ATTEMPTS" # Nouvel état
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
        # ... (identique)
        if not self._gra_base_url:
            self._gra_base_url = await get_gra_base_url()
            if not self._gra_base_url:
                logger.error("[GlobalSupervisor] Impossible de découvrir l'URL du GRA.")
                raise ConnectionError("GRA URL could not be discovered.")
        return self._gra_base_url

    async def _get_agent_url_from_gra(self, skill: str) -> Optional[str]:
        # ... (identique)
        gra_url = await self._ensure_gra_url()
        agent_target_url = None
        try:
            async with httpx.AsyncClient() as client:
                logger.info(f"[GlobalSupervisor] Demande au GRA ({gra_url}) un agent avec la compétence: '{skill}'")
                response = await client.get(f"{gra_url}/agents", params={"skill": skill}, timeout=10.0)
                response.raise_for_status() 
                data = response.json()
                agent_target_url = data.get("url")
                if agent_target_url:
                    logger.info(f"[GlobalSupervisor] URL pour '{skill}' obtenue du GRA: {agent_target_url} (Agent: {data.get('name')})")
                else:
                    logger.error(f"[GlobalSupervisor] Aucune URL retournée par le GRA pour la compétence '{skill}'. Réponse: {data}")
        except httpx.HTTPStatusError as e:
            logger.error(f"[GlobalSupervisor] Erreur HTTP ({e.response.status_code}) en contactant le GRA pour '{skill}' à {e.request.url}: {e.response.text}")
        except httpx.RequestError as e:
            logger.error(f"[GlobalSupervisor] Erreur de requête en contactant le GRA pour '{skill}': {e}")
        except Exception as e:
            logger.error(f"[GlobalSupervisor] Erreur inattendue en contactant le GRA pour '{skill}': {e}", exc_info=True)
        return agent_target_url


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
        # ... (Initialisation du plan_data avec clarification_attempts = 0 - identique) ...
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
        # ... (Début identique : mise à jour état, découverte agent, préparation payload) ...
        await self._save_global_plan_state(global_plan_id, {"current_supervisor_state": GlobalPlanState.OBJECTIVE_BEING_CLARIFIED_BY_AGENT})
        ui_agent_skill = ACTION_CLARIFY_OBJECTIVE
        ui_agent_url = await self._get_agent_url_from_gra(ui_agent_skill)
        if not ui_agent_url: # Gestion d'erreur identique
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

        # ... (Gestion si a2a_task_result est None - identique) ...
        if not a2a_task_result or not a2a_task_result.status:
            logger.error(f"[GlobalSupervisor] Échec appel/réponse invalide de UserInteractionAgent pour plan '{global_plan_id}'.")
            await self._save_global_plan_state(global_plan_id, {"current_supervisor_state": GlobalPlanState.FAILED_AGENT_ERROR, "error_message": "UserInteractionAgent call failed or invalid response"})
            return {"status": "error", "message": "Failed call or invalid response from UserInteractionAgent", "global_plan_id": global_plan_id}

        raw_artifact_text = None # <<< --- CORRECTION : Définir raw_artifact_text à None initialement

        if a2a_task_result.artifacts and len(a2a_task_result.artifacts) > 0:
            first_artifact = a2a_task_result.artifacts[0] #
            if first_artifact.parts and len(first_artifact.parts) > 0:
                part_content = first_artifact.parts[0] #
                # raw_artifact_text était utilisé avant d'être défini dans la version précédente
                if hasattr(part_content, 'root') and isinstance(part_content.root, TextPart) and part_content.root.text:
                    raw_artifact_text = part_content.root.text #
                elif isinstance(part_content, TextPart) and part_content.text: # Fallback
                     raw_artifact_text = part_content.text #
                
                if raw_artifact_text:
                    try:
                        clarification_artifact_content = json.loads(raw_artifact_text) #
                    except json.JSONDecodeError as e:
                        logger.error(f"[GlobalSupervisor] Impossible de parser l'artefact JSON de UI Agent: {e} - Data: {raw_artifact_text}") #
        
        if clarification_artifact_content is None: 
            logger.warning(f"[GlobalSupervisor] Aucun artefact JSON valide reçu de UserInteractionAgent. État A2A: {a2a_task_result.status.state.value}") #
            await self._save_global_plan_state(global_plan_id, {"current_supervisor_state": GlobalPlanState.FAILED_AGENT_ERROR, "error_message": "UserInteractionAgent missing valid artifact"}) #
            return {"status": "error", "message": "UserInteractionAgent did not return a valid artifact", "global_plan_id": global_plan_id} #


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
            "last_agent_response_artifact": clarification_artifact_content, # Stocker l'artefact complet
            "tentatively_enriched_objective_from_agent": tentative_objective, # Stocker l'objectif enrichi
            "proposed_elements_from_agent": proposed_elements
        }

        # Utilisation de .value pour comparer les chaînes des énumérations
        if a2a_task_result.status.state.value == TaskState.completed.value and agent_payload_status == "clarified":
            final_clarified_objective = clarification_artifact_content.get("clarified_objective", tentative_objective) # Fallback sur tentative
            if not final_clarified_objective: final_clarified_objective = text_for_clarification # Ultime fallback
            
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
            # La réponse de l'API GRA doit refléter le payload de l'agent pour que Streamlit puisse l'afficher
            return {
                "status": "clarification_pending", # Pour Streamlit
                "question": question_for_user, 
                "task_type_estimation": task_type_estimation, 
                "global_plan_id": global_plan_id,
                "tentatively_enriched_objective": tentative_objective, # Pour affichage dans Streamlit
                "proposed_elements": proposed_elements # Pour affichage dans Streamlit
            }
        else:
            # ... (gestion d'erreur identique)
            error_msg = f"État A2A ({a2a_task_result.status.state.value}) et/ou statut payload agent ('{agent_payload_status}') incohérents ou échec."
            logger.error(f"[GS] Plan '{global_plan_id}': {error_msg} Artefact: {clarification_artifact_content}")
            updated_plan_fields["current_supervisor_state"] = GlobalPlanState.FAILED_AGENT_ERROR
            updated_plan_fields["error_message"] = error_msg
            await self._save_global_plan_state(global_plan_id, updated_plan_fields)
            return {"status": "error", "message": error_msg, "global_plan_id": global_plan_id, "artifact": clarification_artifact_content}


    async def process_user_clarification_response(self, global_plan_id: str, user_response: str) -> Dict[str, Any]:
        logger.info(f"[GS] Plan '{global_plan_id}': Réponse utilisateur: '{user_response}'")
        current_plan_data = await self._load_global_plan_state(global_plan_id)
        if not current_plan_data: # Gestion d'erreur identique
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
        else: # L'utilisateur fournit une info sans question explicite en attente
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

        objective_to_use = user_provided_objective # Si l'utilisateur a modifié et soumis un objectif final
        if not objective_to_use:
            # Prioriser l'objectif enrichi par l'agent, sinon l'objectif clarifié (s'il existe), sinon le brut
            objective_to_use = current_plan_data.get("last_agent_response_artifact", {}).get("tentatively_enriched_objective")
            if not objective_to_use:
                 objective_to_use = current_plan_data.get("clarified_objective") # Peut-être déjà clarifié par un cycle précédent
            if not objective_to_use:
                objective_to_use = current_plan_data.get("raw_objective") # En dernier recours

        if not objective_to_use: # Devrait être rare
             logger.error(f"[GS] Plan '{global_plan_id}': Aucun objectif (brut, enrichi, ou clarifié) à utiliser pour TEAM 1.")
             await self._save_global_plan_state(global_plan_id, {"current_supervisor_state": GlobalPlanState.FAILED_AGENT_ERROR, "error_message": "No objective found to start TEAM1 planning."})
             return {"status": "error", "message": "No objective available to start planning.", "global_plan_id": global_plan_id}

        logger.info(f"[GS] Plan '{global_plan_id}': Utilisation de l'objectif suivant pour TEAM 1: '{objective_to_use}'")
        
        await self._save_global_plan_state(global_plan_id, {
            "clarified_objective": objective_to_use, # Considérer cet objectif comme le "clarifié"
            "current_supervisor_state": GlobalPlanState.OBJECTIVE_CLARIFIED, # Marquer comme clarifié
            "last_question_to_user": None, # Plus de question en attente
            "user_forced_clarification": True # Indicateur optionnel
        })

        await self._initiate_team1_planning(global_plan_id, objective_to_use)
        return {
            "status": GlobalPlanState.OBJECTIVE_CLARIFIED, # ou TEAM1_PLANNING_INITIATED
            "message": "Objectif accepté par l'utilisateur, planification TEAM 1 initiée.",
            "clarified_objective": objective_to_use,
            "global_plan_id": global_plan_id
        }
    async def _initiate_team1_planning(self, global_plan_id: str, final_clarified_objective: str):
        logger.info(f"[GS] Plan '{global_plan_id}': Lancement planification TEAM 1. Objectif: '{final_clarified_objective}'") #
        
        # Charger l'état actuel pour obtenir le nombre de tentatives pour TEAM 1
        current_plan_data = await self._load_global_plan_state(global_plan_id) or {} #
        attempt_count = current_plan_data.get("team1_planning_attempts", 0) + 1 # Incrémenter pour cette tentative #
        
        # --- CORRECTION : Définir team1_plan_id AVANT de l'utiliser ---
        team1_plan_id = f"team1_{global_plan_id}_attempt{attempt_count}_{uuid.uuid4().hex[:6]}" #

        await self._save_global_plan_state(global_plan_id, { #
            "team1_plan_id": team1_plan_id, # Maintenant, team1_plan_id est défini
            "team1_planning_attempts": attempt_count, #
            "clarified_objective_for_team1": final_clarified_objective, #
            "current_supervisor_state": GlobalPlanState.TEAM1_PLANNING_INITIATED, #
            "team1_status": "INITIATED" #
        })
        
        try:
            team1_supervisor = PlanningSupervisorLogic() #
            team1_supervisor.create_new_plan(raw_objective=final_clarified_objective, plan_id=team1_plan_id) #
            logger.info(f"[GS] Plan TEAM 1 '{team1_plan_id}' (structure Firestore) créé pour plan global '{global_plan_id}'.") #
            
            # Lancer le traitement complet de TEAM 1 en tâche de fond
            asyncio.create_task(self._process_team1_plan_fully(team1_supervisor, team1_plan_id, global_plan_id)) #
            logger.info(f"[GS] Tâche de fond lancée pour traiter entièrement TEAM 1 '{team1_plan_id}'.") #
        except Exception as e:
            logger.error(f"[GS] Erreur initiation/lancement TEAM 1 pour '{team1_plan_id}': {e}", exc_info=True) #
            await self._save_global_plan_state(global_plan_id, { #
                "current_supervisor_state": GlobalPlanState.TEAM1_PLANNING_FAILED, #
                "team1_status": "FAILED_INITIATION", #
                "error_message": f"Erreur d'initiation TEAM 1: {str(e)}" #
            })

    async def _process_team1_plan_fully(self, team1_supervisor: PlanningSupervisorLogic, team1_plan_id: str, global_plan_id: str):
        """
        Appelle team1_supervisor.process_plan en boucle jusqu'à ce que TOUTES les tâches
        du plan TEAM 1 (TaskGraph) soient dans un état terminal.
        Met à jour l'état du plan global en conséquence.
        """
        max_cycles_team1 = 20  # Limite pour éviter boucle infinie
        check_interval_seconds = 10 # Délai entre les vérifications de l'état complet du graphe TEAM 1
        
        logger.info(f"[GS] Démarrage du traitement complet et monitoring pour TEAM 1 plan '{team1_plan_id}' (global: '{global_plan_id}')")
        await self._save_global_plan_state(global_plan_id, {"team1_status": "PROCESSING_ACTIVE"})

        for i in range(max_cycles_team1):
            logger.info(f"[GS] Cycle de traitement TEAM 1 N°{i+1}/{max_cycles_team1} pour plan '{team1_plan_id}'")
            
            # Exécuter un cycle de process_plan de TEAM 1 pour faire avancer ses tâches
            await team1_supervisor.process_plan(plan_id=team1_plan_id)

            # Attendre un peu pour laisser le temps aux agents de TEAM 1 de potentiellement terminer leurs tâches
            # et pour que Firestore soit mis à jour.
            await asyncio.sleep(check_interval_seconds) 

            # Vérifier l'état de toutes les tâches dans le TaskGraph de TEAM 1
            team1_task_graph_reader = TaskGraph(plan_id=team1_plan_id)
            
            # Utiliser .as_dict() pour obtenir toutes les données du graphe, puis vérifier les nœuds.
            # Cette méthode lit depuis Firestore.
            all_team1_tasks_data = await asyncio.to_thread(team1_task_graph_reader.as_dict)
            nodes_in_team1_plan = all_team1_tasks_data.get("nodes", {})

            if not nodes_in_team1_plan:
                logger.warning(f"[GS] Plan TEAM 1 '{team1_plan_id}': Aucun nœud trouvé dans le TaskGraph. Cela peut être un état initial ou une erreur.")
                # Si c'est le premier cycle et qu'il n'y a pas de nœuds, c'est peut-être normal (le temps que create_new_plan popule).
                # Si cela persiste, c'est un problème.
                if i > 1: # Laisser quelques cycles pour l'initialisation
                    logger.error(f"[GS] Plan TEAM 1 '{team1_plan_id}': Aucun nœud après plusieurs cycles. Échec présumé.")
                    await self._save_global_plan_state(global_plan_id, {
                        "current_supervisor_state": GlobalPlanState.TEAM1_PLANNING_FAILED,
                        "team1_status": "FAILED_EMPTY_TASK_GRAPH"
                    })
                    return
                continue # Continuer la boucle pour laisser le temps aux nœuds d'apparaître


            non_terminal_tasks_count = 0
            has_any_failed_tasks = False
            
            for task_id, task_data in nodes_in_team1_plan.items():
                task_state_str = task_data.get("state")
                # Comparer avec les valeurs de l'enum Team1TaskStateEnum
                if task_state_str not in [
                    Team1TaskStateEnum.COMPLETED.value, 
                    Team1TaskStateEnum.FAILED.value, 
                    Team1TaskStateEnum.CANCELLED.value, # Ajouter d'autres états terminaux si pertinent
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
                    logger.info(f"[GS] Plan TEAM 1 '{team1_plan_id}' complété avec succès (toutes les tâches terminales et aucune en échec).")
                    await self._save_global_plan_state(global_plan_id, {
                        "current_supervisor_state": GlobalPlanState.TEAM1_PLANNING_COMPLETED,
                        "team1_status": "COMPLETED_SUCCESSFULLY"
                    })
                return # Sortir de la boucle de traitement de _process_team1_plan_fully

            # Si une tâche a échoué et qu'il n'y a pas de mécanisme de replanification dans PlanningSupervisorLogic
            # qui pourrait la remettre en état non-terminal, la boucle pourrait continuer inutilement
            # jusqu'à max_cycles_team1. Mais la condition ci-dessus (non_terminal_tasks_count == 0) gère cela.
            # Si on veut arrêter dès qu'une tâche échoue et qu'il n'y a plus de tâches "submitted" ou "working" :
            if has_any_failed_tasks:
                # Vérifier s'il reste des tâches actives qui pourraient résoudre l'échec
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


        # Si la boucle se termine sans que toutes les tâches soient terminales
        logger.warning(f"[GS] Plan TEAM 1 '{team1_plan_id}' n'a pas atteint un état terminal complet après {max_cycles_team1} cycles de traitement/vérification.")
        await self._save_global_plan_state(global_plan_id, {
            "current_supervisor_state": GlobalPlanState.TEAM1_PLANNING_FAILED,
            "team1_status": "FAILED_TIMEOUT_MAX_CYCLES"
        })

    # ... (main_test_global_supervisor - il faudra l'adapter pour tester la "force validation")
async def main_test_global_supervisor():
    supervisor = GlobalSupervisorLogic()
    if not supervisor.db:
        logger.error("Échec initialisation Firestore. Arrêt test.")
        return

    # Scénario : Objectif -> Clarification -> Forcer l'acceptation -> Lancer TEAM 1
    objective = "Créer un jeu de serpent en Pygame pour desktop."
    logger.info(f"\n--- Test 'Force Acceptation': Objectif initial = '{objective}' ---")
    
    # 1. Démarrer le plan global (devrait demander clarification)
    response_step1 = await supervisor.start_new_global_plan(objective)
    global_plan_id = response_step1.get("global_plan_id")
    logger.info(f"Réponse Étape 1 (start_new_global_plan): {json.dumps(response_step1, indent=2, ensure_ascii=False)}")
    if not global_plan_id: return
    
    current_state_s1 = await supervisor._load_global_plan_state(global_plan_id)
    logger.info(f"État Firestore après Étape 1: {json.dumps(current_state_s1, indent=2, ensure_ascii=False)}")

    if response_step1.get("status") == "clarification_pending":
        logger.info(f"Question de l'agent: {response_step1.get('question')}")
        # Simuler que l'utilisateur ne répond pas, mais décide de forcer.
        # L'objectif enrichi est dans last_agent_response_artifact.tentatively_enriched_objective
        # Ou l'utilisateur pourrait fournir une version finale dans Streamlit.
        # Pour le test, accept_objective_and_initiate_team1 va essayer de le trouver.
        
        logger.info(f"\n--- Test 'Force Acceptation': L'utilisateur force la clarification pour {global_plan_id} ---")
        response_step2 = await supervisor.accept_objective_and_initiate_team1(global_plan_id)
        logger.info(f"Réponse Étape 2 (accept_objective_and_initiate_team1): {json.dumps(response_step2, indent=2, ensure_ascii=False)}")
        
        current_state_s2 = await supervisor._load_global_plan_state(global_plan_id)
        logger.info(f"État Firestore après Étape 2: {json.dumps(current_state_s2, indent=2, ensure_ascii=False)}")

        if current_state_s2 and current_state_s2.get("current_supervisor_state") == GlobalPlanState.TEAM1_PLANNING_INITIATED:
            logger.info("TEAM 1 initiée. Laisser quelques secondes pour traitement en arrière-plan...")
            # Laisser le temps à la tâche _process_team1_plan_fully de s'exécuter
            # Le test se terminera ici, mais vous devriez voir les logs de TEAM 1 si elle s'exécute.
            # Pour un test complet, il faudrait attendre la fin de la tâche asyncio.
            await asyncio.sleep(30) # Augmenter pour laisser plus de temps à TEAM 1
            final_state = await supervisor._load_global_plan_state(global_plan_id)
            logger.info(f"État final (après attente pour TEAM 1) pour {global_plan_id}: {json.dumps(final_state, indent=2, ensure_ascii=False)}")
    else:
        logger.info(f"L'objectif a été clarifié du premier coup ou une erreur est survenue : {response_step1.get('status')}")
        if response_step1.get("status") == GlobalPlanState.OBJECTIVE_CLARIFIED: # Si c'est déjà clarifié
             # _initiate_team1_planning a déjà été appelé par _trigger_clarification_step
            logger.info("TEAM 1 devrait déjà être initiée. Laisser quelques secondes...")
            await asyncio.sleep(30)
            final_state = await supervisor._load_global_plan_state(global_plan_id)
            logger.info(f"État final (après attente pour TEAM 1) pour {global_plan_id}: {json.dumps(final_state, indent=2, ensure_ascii=False)}")


if __name__ == "__main__":
    asyncio.run(main_test_global_supervisor())