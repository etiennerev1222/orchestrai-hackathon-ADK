# src/agents/development_agent/logic.py

import logging
import json

from src.shared.base_agent_logic import BaseAgentLogic
from src.shared.llm_client import call_llm
from src.services.environment_manager.environment_manager import EnvironmentManager # Import for type hinting/static methods
from src.shared.prompt_utils import build_development_agent_system_prompt
logger = logging.getLogger(__name__)

AGENT_SKILL_CODING_PYTHON = "coding_python"

class DevelopmentAgentLogic(BaseAgentLogic):
    """Logic handling the reasoning of the development agent."""
    def __init__(self):
        self.agent_type = "coding_python"  # 🔹 avant super()
        super().__init__()
        import os
        self.agent_name = os.environ.get("AGENT_NAME", "DevelopmentAgentGKEv2")
        self.logger = logging.getLogger(f"{__name__}.{self.agent_name}.DevelopmentAgentLogic")
        self.logger.info("Logique du DevelopmentAgent initialisée.")
        self.environment_manager: EnvironmentManager | None = None # Add type hint

    def set_environment_manager(self, manager: EnvironmentManager):
        """Sets the EnvironmentManager instance for the logic to use."""
        self.environment_manager = manager
        self.logger.info("EnvironmentManager set for DevelopmentAgentLogic.")
    def build_tool_functions(self) -> dict:
        return {
            "generate_code": self._generate_code,
            "explain_code": self._explain_code,
            "modify_code": self._modify_code,
            "test_code": self._test_code,
            "generate_test": self._generate_test,
            "format_code": self._format_code,
            "complete_code": self._complete_code,
            "refactor_code": self._refactor_code,
            "validate_code": self._validate_code,
            "capability_check": self._capability_check
        }



    def _get_system_prompt(self) -> str:
        return build_development_agent_system_prompt(self.tool_registry.get_tools())

    async def process(self, input_data_str: str, context_id: str) -> str:
        input_data = json.loads(input_data_str)
        objective = input_data.get("objective")
        last_action_result = input_data.get("last_action_result")

        if not objective:
            self.logger.error("DevelopmentAgentLogic - Objectif manquant dans l'input.")
            return json.dumps(
                {"action": "complete_task", "summary": "Tâche échouée: objectif non spécifié."}
            )

        self.logger.info(f"DevelopmentAgentLogic - Décision d'action pour l'objectif: '{objective}'")
        if last_action_result:
            self.logger.info(f"Résultat de la dernière action pour informer la décision: {json.dumps(last_action_result, indent=2)}")

        system_prompt = self._get_system_prompt()

        prompt = (
            f"Objectif de développement global : {objective}\n\n"
            f"Résultat de la dernière action exécutée : {json.dumps(last_action_result, indent=2)}\n\n"
            "En te basant sur l'objectif et le résultat de la dernière action, quelle est la **PROCHAINE action unique et atomique que tu dois planifier** ? "
            "Quand tu choisis `complete_task`, fournis un résumé structuré (avec fichiers générés, commandes exécutées, résultats des tests)."
            " Réponds UNIQUEMENT avec l'objet JSON correspondant à l'action choisie."
        )
        try:
            llm_response_str = await call_llm(prompt, system_prompt, json_mode=True)
            self.logger.info(f"DevelopmentAgentLogic - Réponse LLM (prochaine action): {llm_response_str}")
            logger.debug(f"Action LLM décidée: - Payload: {llm_response_str}")
            return llm_response_str
        except Exception as e:
            self.logger.error(f"DevelopmentAgentLogic - Échec lors de la décision de l'action par le LLM: {e}", exc_info=True)
            # Fallback to a failure message if LLM call fails
            return json.dumps({"action": "complete_task", "summary": f"Échec de la décision de l'action par le LLM: {str(e)}", "status": "failed"})

