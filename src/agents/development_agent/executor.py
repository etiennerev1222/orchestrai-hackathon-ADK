# src/agents/development_agent/executor.py

import logging
import json
from src.shared.base_agent_executor import BaseAgentExecutor
from src.agents.development_agent.logic import DevelopmentAgentLogic
from a2a.types import Artifact, TextPart, Task
from src.shared.tool_registry import ToolRegistry
logger = logging.getLogger(__name__)

class DevelopmentAgentExecutor(BaseAgentExecutor):
    def __init__(self):
        super().__init__(
            agent_logic=DevelopmentAgentLogic(),
            default_artifact_name="dev_agent_result",
            default_artifact_description="Résultat produit par l'agent de développement."
        )

    def _create_artifact_from_result(self, result_data: dict, task: Task) -> Artifact:
        return Artifact(
            context_id=task.contextId,
            content=result_data,
            name="capability_check_result",
            agent_name="DevelopmentAgent",
            objective=task.objective,
            type="tool_result",
        )

    async def execute(self, request_context, event_queue):
        context_id = request_context.context_id
        user_input = request_context.input_message.get_content()

        objective = user_input.get("objective")
        last_action_result = user_input.get("last_action_result", {})

        if not objective:
            logger.error("Objectif manquant dans le message reçu.")
            await event_queue.emit_task_status_update(status="failed")
            return

        current_context = {
            "objective": objective,
            "last_action_result": last_action_result
        }

        while True:
            logger.info(f"[DevAgent] 🔁 Nouvelle itération pour l’objectif : {objective}")

            # Appel à la logique de décision (LLM)
            llm_response_str = await self.agent_logic.process(json.dumps(current_context), context_id)
            try:
                llm_action_payload = json.loads(llm_response_str)
                action_type = llm_action_payload.get("action")
            except json.JSONDecodeError:
                logger.warning("Échec parsing JSON LLM. Interruption.")
                await event_queue.emit_task_status_update(status="failed")
                return

            logger.info(f"[DevAgent] 🧠 Action choisie : {action_type}")

            if action_type == "complete_task":
                summary = llm_action_payload.get("summary", "Aucune synthèse fournie.")
                artifact = Artifact(
                    artifactId="dev-agent-output",
                    fileName="dev_agent_result.json",
                    description="Résultat final de l'agent de développement",
                    parts=[TextPart(text=summary)]
                )
                await event_queue.emit_artifact_update(artifact)
                await event_queue.emit_task_status_update(status="completed")
                logger.info(f"[DevAgent] ✅ Tâche complétée avec succès : {summary}")
                return

            # Exécution de l’action via ToolRegistry
            try:
                tool_result = await self.agent_logic.tool_registry.handle_llm_response(llm_action_payload, context_id)
            except Exception as e:
                logger.error(f"[DevAgent] ❌ Erreur pendant l'exécution de l’outil : {e}", exc_info=True)
                await event_queue.emit_task_status_update(status="failed")
                return

            logger.info(f"[DevAgent] ✅ Résultat de l’action {action_type} : {tool_result}")

            current_context["last_action_result"] = {
                "action_taken": action_type,
                "summary": tool_result.get("summary", f"Action '{action_type}' exécutée."),
                "details": tool_result
            }