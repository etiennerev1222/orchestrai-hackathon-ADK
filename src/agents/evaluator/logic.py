import logging
import json
from typing import Dict, Any
from src.shared.base_agent_logic import BaseAgentLogic
from src.shared.llm_client import call_llm
# src/agents/evaluator/logic.py
import logging
from src.shared.base_agent_logic import BaseAgentLogic

logger = logging.getLogger(__name__)

class EvaluatorAgentLogic(BaseAgentLogic):
    def __init__(self):
        self.agent_type = "generic"
        super().__init__()
        logger.info("EvaluatorAgentLogic initialisée.")

    async def process(self, objective: str, context_id: str) -> str:
        return await self.execute_llm_action_loop(objective, context_id)







