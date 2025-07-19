import logging
import json
import uuid
from typing import Dict, Any, Tuple, List, Optional

from src.services.environment_manager.environment_manager import EnvironmentManager
from src.shared.interaction_logger import log_collaboration_trace
from src.shared.execution_task_graph_management import (
    ExecutionTaskGraph,
    ExecutionTaskNode,
    ExecutionTaskType,
)
from src.shared.llm_client import LlmClient
from src.shared.tool_registry import ToolRegistry

from src.shared.base_agent_logic import BaseAgentLogic

logger = logging.getLogger(__name__)

ACTION_CLARIFY_OBJECTIVE = "clarify_objective"
ACTION_RECEIVE_FILE = "receive_file"

class UserInteractionAgentLogic(BaseAgentLogic):
    def __init__(self):
        super().__init__()
        logger.info("Logique du UserInteractionAgent initialisée (avec LLM pour clarification).")
        self.llm_client = LlmClient()
        self.tool_registry = ToolRegistry()
        self.tool_registry.tools[ACTION_CLARIFY_OBJECTIVE] = self.clarify_objective
        self.tool_registry.tools[ACTION_RECEIVE_FILE] = self.receive_file


    def get_active_tools(self) -> dict:
        """Expose les outils disponibles pour cet agent."""
        return {
            "workforce_information": self.tool_registry.get_tools()["workforce_information"],
        }
    def _format_conversation_history(self, history: List[Dict[str, str]]) -> str:
        if not history:
            return "No previous conversation."

        formatted_history = []
        for turn in history:
            agent_q = turn.get("agent_question", "No question from agent this turn.")
            user_a = turn.get("user_answer", "No answer from user this turn.")
            formatted_history.append(f"Previously, Agent asked: {agent_q}\nUser responded: {user_a}")
        return "\n\n".join(formatted_history)

    async def receive_file(self, input_data: Dict[str, Any], context_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Outil pour recevoir un fichier de l'utilisateur, le stocker dans l'environnement
        d'exécution et créer un artefact dans le graphe d'exécution.
        """
        file_name = input_data.get("file_name")
        file_content = input_data.get("file_content")
        environment_id = context_id

        if not all([file_name, file_content, environment_id]):
            return {"status": "error", "message": "Les champs 'file_name', 'file_content', et 'environment_id' sont requis."}

        try:
            env_manager = EnvironmentManager()
            destination_path = f"/app/{file_name}"
            content_text = file_content.decode("utf-8", errors="ignore") if isinstance(file_content, (bytes, bytearray)) else str(file_content)
            await env_manager.write_file_to_environment(
                environment_id=environment_id,
                file_path=destination_path,
                content=content_text,
            )
            logger.info(f"Fichier {file_name} stocké avec succès dans l'environnement {environment_id} à l'emplacement : {destination_path}")

            try:
                graph = ExecutionTaskGraph(execution_plan_id=environment_id)
                file_node = ExecutionTaskNode(
                    task_id=f"file_{uuid.uuid4().hex[:8]}",
                    objective=f"Artefact Fichier : {file_name}",
                    task_type=ExecutionTaskType.EXECUTABLE,
                    meta={"file_path": destination_path, "source": "user_upload", "file_name": file_name},
                )
                file_node.state = "completed"
                file_node.result_summary = f"Fichier utilisateur '{file_name}' disponible à l'emplacement : {destination_path}"
                graph.add_task(file_node, is_root=True)
                logger.info(f"Noeud artefact créé pour le fichier {file_name} dans le graphe {environment_id}.")
            except Exception as e:
                logger.error(f"Échec de la création du noeud artefact pour {file_name} : {e}", exc_info=True)

            log_collaboration_trace(
                {
                    "interaction_id": str(uuid.uuid4()),
                    "msg_type": "FILE_UPLOAD",
                    "sender_agent": "User",
                    "receiver_agent": "InteractionAgent",
                    "result_summary": f"Fichier {file_name} stocké dans {destination_path}",
                    "tool_invoked": {"name": "receive_file", "input": {"file_name": file_name, "path": destination_path}},
                },
                context_id,
            )

            return {"status": "success", "message": f"Fichier {file_name} reçu, stocké et enregistré comme artefact."}

        except Exception as e:
            logger.error(f"Erreur critique lors de la réception du fichier {file_name}: {e}", exc_info=True)
            return {"status": "error", "message": str(e)}

    async def process(self, input_data: Dict[str, Any], context_id: Optional[str] = None) -> Tuple[Dict[str, Any], str | None]:
        action = input_data.get("action")
        if action == ACTION_RECEIVE_FILE:
            result = await self.receive_file(input_data, context_id)
            status = "completed" if result.get("status") == "success" else "failed"
            return result, status
        current_text_input = input_data.get("current_objective_or_response", "").strip()
        conversation_history = input_data.get("conversation_history", [])
        objective = input_data.get("objective", "").strip()
        user_answer = input_data.get("user_answer", "").strip()
        previous_turn = input_data.get("previous_turn")
        context_id = input_data.get("context_id") or context_id

        allowed_tools = list(self.get_active_tools().keys())
        logger.info(f"Outils disponibles pour le LLM : {allowed_tools}")

        logger.info(f"UserInteractionAgentLogic - Action: {action}, Input: '{current_text_input}', Hist: {len(conversation_history)} entrées")

        # 🧠 Détermination de l’objectif réel à traiter
        if user_answer:
            current_text_input = user_answer.strip()
            logger.info(f"✅ Réponse utilisateur détectée et utilisée comme nouvel objectif: {current_text_input}")
        elif not current_text_input:
            logger.warning("⚠ Aucun objectif clair détecté. current_text_input est vide malgré les champs fournis.")

        if action == ACTION_CLARIFY_OBJECTIVE:
            # 1. Générer le prompt initial
            conversation_history_str = self._format_conversation_history(conversation_history)
            initial_prompt = f"""
    User's raw objective or latest statement to consider:
    '''
    {current_text_input}
    '''

    Full conversation history (for context):
    '''
    {conversation_history_str}
    '''

    Based on your role and instructions (analyze, estimate task type, identify missing info, propose defaults/assumptions if reasonable, build a tentative enriched objective, and ask for confirmation or critical missing details):
    Respond ONLY with the specified JSON object.
    """.strip()

            # 2. Util
            from src.shared.prompt_utils import build_dynamic_system_prompt
            active_tools = self.get_active_tools()
            system_prompt = build_dynamic_system_prompt(active_tools)

            logger.info("Lancement de la boucle reasoning+tools avec allowed_tools=['workforce_information']")
            result = await self.run_reasoning_loop_with_tools(
                objective=current_text_input,
                context_id=context_id,
                allowed_tools=allowed_tools,
                initial_prompt=initial_prompt,
                system_prompt=system_prompt
            )

            logger.info(f"Résultat brut reasoning loop: {json.dumps(result, indent=2)}")
            final = self.extract_final_result_with_fallback(result)
            status_from_llm = final.get("status")

            final["original_input_text_this_turn"] = current_text_input

            if status_from_llm == "clarified":
                logger.info(f"✅ Objectif clarifié par LLM: {final.get('clarified_objective')}")
                return final, "completed"

            elif status_from_llm == "needs_confirmation_or_clarification":
                logger.info(f"✏️ LLM demande confirmation/clarification. Question: {final.get('question_for_user')}")
                return final, "input_required"

            else:
                logger.error(f"❌ Statut inattendu du LLM: '{status_from_llm}'. Réponse: {final}")
                final["error_message_agent"] = f"Statut inattendu ('{status_from_llm}') reçu du LLM."
                return final, "failed"

        elif action == "ask_user":
            question = input_data.get("question", "Pouvez-vous clarifier ce point ?")
            logger.info(f"[UserInteractionAgent] Question à poser à l'utilisateur: {question}")
            return {
                "question_for_user": question,
                "status": "input_required"
            }, "input_required"


        else:
            logger.warning(f"⚠ Action inconnue ou non gérée reçue: {action}")
            error_payload = {"status": "error", "message": f"Action non supportée: {action}"}
            return error_payload, "failed"

