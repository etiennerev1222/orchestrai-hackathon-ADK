# src/agents/development_agent/executor.py
import logging
import json # Bien que le résultat soit du code, l'input peut être JSON

from src.shared.base_agent_executor import BaseAgentExecutor
from .logic import DevelopmentAgentLogic
from .server import AGENT_NAME

from a2a.types import Artifact, Task
from a2a.utils import new_text_artifact # Le code sera stocké comme un TextArtifact

logger = logging.getLogger(__name__)

class DevelopmentAgentExecutor(BaseAgentExecutor):
    def __init__(self):
        specific_agent_logic = DevelopmentAgentLogic()
        super().__init__(
            agent_logic=specific_agent_logic,
            default_artifact_name="generated_code",
            default_artifact_description="Code source généré par l'agent de développement.",
            agent_name=AGENT_NAME,
        )
        self.logger = logging.getLogger(f"{__name__}.DevelopmentAgentExecutor")
        self.logger.info("DevelopmentAgentExecutor initialisé.")

    # L'input_text (un JSON string) sera correctement extrait par la méthode de base
    # et passé à la logique qui le parsera.

    def _create_artifact_from_result(self, result_data: str, task: Task) -> Artifact:
        """
        Crée un Artifact A2A à partir du code généré (qui est une chaîne de caractères).
        """
        self.logger.info(f"Création de l'artefact de code pour la tâche {task.id}.")
        # result_data est la chaîne de caractères contenant le code
        return new_text_artifact(
            name=self.default_artifact_name,
            description=self.default_artifact_description,
            text=result_data 
        )