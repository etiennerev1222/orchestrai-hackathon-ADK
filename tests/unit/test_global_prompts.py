import pytest
from src.shared.prompts import BASE_PROMPTS, get_base_prompt

@pytest.mark.parametrize("key", [
    "reformulator",
    "research_agent",
    "decomposition_agent",
    "validator_agent",
    "testing_agent_tcg",
    "testing_agent_st",
])
def test_base_prompt_exists(key):
    prompt = get_base_prompt(key)
    assert isinstance(prompt, str) and prompt
