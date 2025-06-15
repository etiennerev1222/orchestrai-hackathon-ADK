
import logging
from typing_extensions import override

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events.event_queue import EventQueue
from a2a.types import (
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
    Message,
    TextPart,
)
from src.shared.base_agent_executor import BaseAgentExecutor
from .logic import ReformulatorAgentLogic

from a2a.types import Artifact, Task
from a2a.utils import new_text_artifact

logger = logging.getLogger(__name__)

class ReformulatorAgentExecutor(BaseAgentExecutor):
    """
    Exécuteur pour l'agent Reformulateur.
    Hérite de BaseAgentExecutor et utilise ReformulatorAgentLogic.
    """

    def __init__(self):
        specific_agent_logic = ReformulatorAgentLogic()
        
        super().__init__(
            agent_logic=specific_agent_logic,
            default_artifact_name="reformulated_objective",
            default_artifact_description="L'objectif après reformulation par l'agent."
        )



    def _create_artifact_from_result(self, result_data: str, task: Task) -> Artifact:
        """
        Crée un Artifact A2A à partir du résultat textuel de ReformulatorAgentLogic.

        Args:
            result_data (str): Le texte reformulé retourné par agent_logic.process().
            task (Task): La tâche A2A actuelle (peut être utile pour l'artifactId, etc.,
                         bien que non utilisé directement par new_text_artifact pour son ID).

        Returns:
            Artifact: Un objet Artifact contenant le texte reformulé.
        """
        logger.info(f"Création de l'artefact pour la tâche {task.id} avec le résultat: '{result_data}'")
        return new_text_artifact(
            name=self.default_artifact_name,
            description=self.default_artifact_description,
            text=result_data
        )

