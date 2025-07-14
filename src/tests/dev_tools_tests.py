# src/tests/dev_tools_tests.py

import pytest
from src.agents.development_agent.executor import DevelopmentAgentExecutor
from src.services.environment_manager.environment_manager import EnvironmentManager

@pytest.mark.asyncio
async def test_read_file_tool():
    executor = DevelopmentAgentExecutor()
    executor.environment_manager = EnvironmentManager()
    
    file_path = "/test_read_file.txt"
    content = "Contenu de test"
    await executor.environment_manager.write_file_to_environment("dev-env-exec-default", file_path, content)
    
    result = await executor.agent_logic.tool_registry.handle_llm_response(
        {"action": "read_file", "file_path": file_path},
        context_id="dev-env-exec-default"
    )
    print("✅ read_file:", result)
    assert result["content"] == content

@pytest.mark.asyncio
async def test_generate_code_and_write_file():
    executor = DevelopmentAgentExecutor()
    
    specs = {
        "objective": "Créer une fonction add(a, b) qui retourne la somme",
        "local_instructions": [],
        "acceptance_criteria": []
    }
    result = await executor.agent_logic.tool_registry.handle_llm_response(
        {"action": "generate_code_and_write_file", "specs": specs, "file_path": "/add.py"},
        context_id="dev-env-exec-default"
    )
    print("✅ generate_code_and_write_file:", result)
    assert result.get("status") == "success"
    assert result.get("path", "").endswith("add.py")

@pytest.mark.asyncio
async def test_execute_command():
    executor = DevelopmentAgentExecutor()
    
    result = await executor.agent_logic.tool_registry.handle_llm_response(
        {"action": "execute_command", "command": "echo Hello World"},
        context_id="dev-env-exec-default"
    )
    print("✅ execute_command:", result)
    assert "Hello World" in result.get("stdout", "")

@pytest.mark.asyncio
async def test_list_directory():
    executor = DevelopmentAgentExecutor()
    
    result = await executor.agent_logic.tool_registry.handle_llm_response(
        {"action": "list_directory", "directory_path": "."},
        context_id="dev-env-exec-default"
    )
    print("✅ list_directory:", result)
    assert isinstance(result.get("files"), list)

@pytest.mark.asyncio
async def test_complete_task():
    executor = DevelopmentAgentExecutor()
    
    result = await executor.agent_logic.tool_registry.handle_llm_response(
        {"action": "complete_task"},
        context_id="dev-env-exec-default"
    )
    print("✅ complete_task:", result)
    assert result["status"] == "complete"
    assert result["summary"] == "Objectif terminé."

@pytest.mark.asyncio
async def test_capability_check():
    executor = DevelopmentAgentExecutor()
    
    # Charger les outils génériques manuellement si non présents
    if "capability_check" not in executor.agent_logic.tool_registry.tools:
        from src.tools import generic_tools
        executor.agent_logic.tool_registry.tools["capability_check"] = generic_tools.capability_check

    result = await executor.agent_logic.tool_registry.handle_llm_response(
        {"action": "capability_check", "deliverable_description": "Generate a FastAPI app"},
        context_id="dev-env-exec-default"
    )
    print("✅ capability_check:", result)
    assert result.get("can_handle") is True

@pytest.mark.asyncio
async def test_workforce_information():
    executor = DevelopmentAgentExecutor()

    # S'assure que l'outil est bien enregistré
    if "workforce_information" not in executor.agent_logic.tool_registry.tools:
        from src.tools import generic_tools
        executor.agent_logic.tool_registry.tools["workforce_information"] = generic_tools.workforce_information

    # Appel de l'outil en direct (pas via invoke_tool)
    result = await executor.agent_logic.tool_registry.handle_llm_response(
        {
            "action": "workforce_information",
            "input": {}
        },
        context_id="dev-env-exec-default"
    )

    print("✅ workforce_information:", result)

    assert isinstance(result, dict)
    assert "agents" in result
    assert isinstance(result["agents"], list)
