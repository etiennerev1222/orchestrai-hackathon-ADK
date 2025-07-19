import pytest

import pytest
from src.agents.evaluator.logic import EvaluatorAgentLogic

@pytest.mark.asyncio
async def test_evaluator_calls_capability_check():
    logic = EvaluatorAgentLogic()
    result = await logic.process(
            "Demander au DevelopmentAgent s'il peut générer une app FastAPI.",
            "dev-env-exec-default"
    )

    print("✅ Résultat final :", result)
