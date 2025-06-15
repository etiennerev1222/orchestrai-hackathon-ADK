import logging
import json
from typing import Dict, Any, Tuple, List

from src.shared.base_agent_logic import BaseAgentLogic
from src.shared.llm_client import call_llm

logger = logging.getLogger(__name__)

ACTION_CLARIFY_OBJECTIVE = "clarify_objective"


SYSTEM_PROMPT_LLM = """
You are an expert project clarification assistant. Your primary role is to analyze a user's raw objective and any existing conversation history. Your goal is to ensure the objective is sufficiently detailed for a **high-level planning and decomposition phase (to be performed by a subsequent specialized planning team, TEAM 1)**. You do NOT need to extract every single detail as TEAM 1 will handle further refinement.

The teams primarily handle two types of objectives:
1.  **Software Development Tasks**: These involve creating programs or code that must be testable. For these, crucial high-level information includes: the software's main purpose/problem it solves, core functionalities envisioned, target platform (e.g., web, mobile, API), and any strictly preferred technologies. Detailed internal logic or exhaustive feature lists will be elaborated by TEAM 1.
2.  **Redaction/Research Tasks**: These involve investigating a topic and producing a document, often using internet research. For these, crucial high-level information includes: the specific topic/problem, the main objective of the document, the target audience, and the general scope or desired output format. Specific sub-sections or detailed research paths will be defined by TEAM 1.

Based on the user's objective and conversation history:
a. Determine if the objective leans more towards "Software Development" or "Redaction/Research". Set 'task_type_estimation'.
b. Identify any *major, high-level* crucial information (relevant to the task type) that is still missing and would prevent TEAM 1 from even starting its high-level planning.
c. **If such major information is missing:**
    i. You may propose sensible defaults for some secondary aspects in `proposed_elements` if it helps move forward.
    ii. Synthesize a `tentatively_enriched_objective` incorporating user input and your proposals.
    iii. Formulate a concise 'question_for_user' focused on the most critical *high-level* missing piece or to confirm your major proposals.
    iv. Set 'status' to 'needs_confirmation_or_clarification'.
d. **If the objective provides enough high-level clarity for TEAM 1 to begin its detailed planning and decomposition (even if some minor details could still be elaborated by them):**
    i. Synthesize a final 'clarified_objective' that is ready for TEAM 1.
    ii. Set 'status' to 'clarified'.
    iii. The 'question_for_user' can be null or a simple confirmation like "This objective seems ready for detailed planning by TEAM 1. Proceed?".
e. Always provide a 'missing_elements_summary' indicating what high-level information was clarified, assumed, or is still critically needed for TEAM 1 to start.

You MUST return your response exclusively in JSON format with the following structure:
{
  "task_type_estimation": "Software Development" | "Redaction/Research" | "Unclear",
  "status": "clarified" | "needs_confirmation_or_clarification",
  "clarified_objective": "...", // If status is "clarified"
  "tentatively_enriched_objective": "...", // If status is "needs_confirmation_or_clarification"
  "proposed_elements": { ... }, // Dictionary of assumptions/proposals made by you, if any
  "question_for_user": "...",   // If status is "needs_confirmation_or_clarification"
  "missing_elements_summary": "..."
}

Your aim is to prepare the objective for the next planning stage (TEAM 1), not to finalize every detail yourself. Be collaborative and make reasonable assumptions if it helps, but always seek confirmation for major ones.
"""
class UserInteractionAgentLogic(BaseAgentLogic):
    def __init__(self):
        super().__init__()
        logger.info("Logique du UserInteractionAgent initialisée (avec LLM pour clarification).")

    def _format_conversation_history(self, history: List[Dict[str, str]]) -> str:
        if not history:
            return "No previous conversation."
        
        formatted_history = []
        for turn in history:
            agent_q = turn.get("agent_question", "No question from agent this turn.")
            user_a = turn.get("user_answer", "No answer from user this turn.")
            formatted_history.append(f"Previously, Agent asked: {agent_q}\nUser responded: {user_a}")
        return "\n\n".join(formatted_history)
    async def process(self, input_data: Dict[str, Any], context_id: str | None = None) -> Tuple[Dict[str, Any], str | None]:
        action = input_data.get("action")
        current_text_input = input_data.get("current_objective_or_response", "")
        conversation_history = input_data.get("conversation_history", []) 

        logger.info(f"UserInteractionAgentLogic - Action: {action}, Input: '{current_text_input}', Hist: {len(conversation_history)} entrées")

        if action == ACTION_CLARIFY_OBJECTIVE:
            conversation_history_str = self._format_conversation_history(conversation_history)
            
            user_prompt_llm = f"""
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
"""
            try:
                logger.info(f"Appel au LLM pour clarification enrichie. User prompt (début): {user_prompt_llm[:200]}...")
                llm_response_str = await call_llm(user_prompt_llm, SYSTEM_PROMPT_LLM, json_mode=True)
                logger.info(f"Réponse brute du LLM (clarification enrichie): {llm_response_str}")
                llm_data = json.loads(llm_response_str)

                status_from_llm = llm_data.get("status")
                
                result_payload = llm_data 
                result_payload["original_input_text_this_turn"] = current_text_input

                if status_from_llm == "clarified":
                    logger.info(f"Objectif clarifié par LLM: {llm_data.get('clarified_objective')}")
                    return result_payload, "completed" 
                
                elif status_from_llm == "needs_confirmation_or_clarification":
                    logger.info(f"LLM demande confirmation/clarification. Question: {llm_data.get('question_for_user')}")
                    logger.info(f"LLM propositions: {llm_data.get('proposed_elements')}")
                    logger.info(f"LLM objectif enrichi tentative: {llm_data.get('tentatively_enriched_objective')}")
                    return result_payload, "input_required"
                
                else:
                    logger.error(f"Statut inattendu du LLM: '{status_from_llm}'. Réponse: {llm_data}")
                    result_payload["error_message_agent"] = f"Statut inattendu ('{status_from_llm}') reçu du LLM."
                    return result_payload, "failed"

            except json.JSONDecodeError as e:
                logger.error(f"Impossible de parser JSON du LLM: {e}. Réponse: '{llm_response_str}'")
                return {"status": "error", "message": "Réponse LLM non JSON.", "raw_llm_response": llm_response_str}, "failed"
            except Exception as e:
                logger.error(f"Erreur appel LLM pour clarification enrichie: {e}", exc_info=True)
                return {"status": "error", "message": f"Erreur interne appel LLM: {str(e)}"}, "failed"
        
        else:
            logger.warning(f"Action inconnue ou non gérée reçue: {action}")
            error_payload = {"status": "error", "message": f"Action non supportée: {action}"}
            return error_payload, "failed"