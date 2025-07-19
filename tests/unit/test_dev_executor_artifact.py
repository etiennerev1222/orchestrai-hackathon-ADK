from a2a.types import Task

from src.agents.development_agent.executor import DevelopmentAgentExecutor


def test_dev_executor_create_artifact():
    executor = DevelopmentAgentExecutor()
    task = Task(id="t1", contextId="ctx", objective="do stuff")
    result = {"foo": "bar"}

    artifact = executor._create_artifact_from_result(result, task)

    assert artifact.context_id == "ctx"
    assert artifact.content == result
    assert artifact.objective == "do stuff"
    assert artifact.name == "capability_check_result"
    assert artifact.type == "tool_result"
