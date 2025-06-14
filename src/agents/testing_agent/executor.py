# src/agents/testing_agent/executor.py
import logging
import json

from src.shared.base_agent_executor import BaseAgentExecutor
from .logic import TestingAgentLogic
from .server import AGENT_NAME

from a2a.types import Artifact, Task
from a2a.utils import new_text_artifact # Le rapport de test JSON sera un TextArtifact

logger = logging.getLogger(__name__)

class TestingAgentExecutor(BaseAgentExecutor):
    def __init__(self):
        specific_agent_logic = TestingAgentLogic()
        super().__init__(
            agent_logic=specific_agent_logic,
            default_artifact_name="test_report",
            default_artifact_description="Rapport de test généré pour un livrable.",
            agent_name=AGENT_NAME,
        )
        self.logger = logging.getLogger(f"{__name__}.TestingAgentExecutor")
        self.logger.info("TestingAgentExecutor initialisé.")

    # L'input (JSON string) est géré par la base et la logique.

    def _create_artifact_from_result(self, result_data: str, task: Task) -> Artifact:
        """
        Crée un Artifact A2A à partir du rapport de test (chaîne JSON) retourné par la logique.
        """
        self.logger.info(f"Création de l'artefact du rapport de test pour la tâche {task.id}.")
        # result_data est la chaîne JSON du rapport de test
        return new_text_artifact(
            name=self.default_artifact_name,
            description=self.default_artifact_description,
            text=result_data 
        )