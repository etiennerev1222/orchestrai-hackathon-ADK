
import asyncio
import pytest

from src.agents.development_agent.executor import DevelopmentAgentExecutor

@pytest.mark.asyncio
async def test_capability_check_tool():
    executor = DevelopmentAgentExecutor()

    context_id = "test-thread-dev-agent"
    deliverable = "Créer un serveur FastAPI avec un endpoint POST /upload acceptant des fichiers"
    tool_payload = {
        "action": "capability_check",
        "deliverable_description": deliverable
    }

    result = await executor.agent_logic.tool_registry.handle_llm_response(tool_payload, context_id)

    assert isinstance(result, dict)
    assert "can_handle" in result
    assert "confidence" in result
    assert "comment" in result
    print("✅ Résultat:", result)
