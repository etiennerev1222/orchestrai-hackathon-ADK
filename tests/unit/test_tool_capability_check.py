import asyncio
import pytest

from src.shared.base_agent_logic import BaseAgentLogic

class DummyAgent(BaseAgentLogic):
    async def process(self, input_text: str, context_id: str | None = None):
        return ""

    def can_deliver(self, deliverable: str) -> bool:
        return True

@pytest.mark.asyncio
async def test_tool_capability_check():
    agent = DummyAgent()
    agent.tool_registry.tools = {"tool_a": lambda x, context_id=None: None}
    result = await agent.tool_capability_check({"deliverable_description": "foo"})
    assert result["can_handle"] is True
    assert result["tools_available"] == ["tool_a"]
    assert result["agent_type"] == agent.agent_type
    assert result["deliverable_description"] == "foo"
