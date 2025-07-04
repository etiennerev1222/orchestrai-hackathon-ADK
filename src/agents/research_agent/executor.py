import logging
import json

from src.shared.base_agent_executor import BaseAgentExecutor
from .logic import ResearchAgentLogic

from a2a.types import Artifact, Task
from a2a.utils import new_text_artifact

logger = logging.getLogger(__name__)

class ResearchAgentExecutor(BaseAgentExecutor):
    def __init__(self):
        specific_agent_logic = ResearchAgentLogic()
        super().__init__(
            agent_logic=specific_agent_logic,
            default_artifact_name="research_analysis_output",
            default_artifact_description="Résultat de la recherche ou de l'analyse effectuée."
        )
        self.logger = logging.getLogger(f"{__name__}.ResearchAgentExecutor")
        self.logger.info("ResearchAgentExecutor initialisé.")


    def _create_artifact_from_result(self, result_data: str, task: Task) -> Artifact:
        """
        Crée un Artifact A2A. result_data est la chaîne (potentiellement JSON) retournée par la logique.
        """
        self.logger.info(f"Création de l'artefact pour la tâche de recherche/analyse {task.id}.")
        return new_text_artifact(
            name=self.default_artifact_name,
            description=self.default_artifact_description,
            text=result_data 
        )