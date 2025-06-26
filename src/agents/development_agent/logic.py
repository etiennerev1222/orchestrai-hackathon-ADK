import json
import logging
from src.shared.base_agent_logic import BaseAgentLogic
from src.shared.llm_client import call_llm

logger = logging.getLogger(__name__)

AGENT_SKILL_CODING_PYTHON = "coding_python"

class DevelopmentAgentLogic(BaseAgentLogic):
    """Simple logic to generate Python code and write it to a file."""

    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(f"{__name__}.DevelopmentAgentLogic")

    async def process(self, input_data: str, context_id: str | None = None) -> str:
        data = json.loads(input_data)
        objective = data.get("objective", "Print hello world")
        file_path = data.get("file_path", "/app/main.py")
        environment_id = data.get("environment_id", "exec_default")

        system_prompt = "You are a senior Python developer."
        prompt = f"Write the Python code to accomplish the following objective:\n{objective}\nReturn only the code."
        code = await call_llm(prompt, system_prompt, json_mode=False)

        if not self.environment_manager:
            raise RuntimeError("Environment manager not configured")
        await self.environment_manager.upload_to_environment(environment_id, file_path, code)

        return json.dumps({"file_path": file_path, "code": code})
