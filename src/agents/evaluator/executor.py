import logging
import json

from src.shared.base_agent_executor import BaseAgentExecutor
from .logic import EvaluatorAgentLogic

from a2a.types import Artifact, Task
from a2a.utils import new_text_artifact

logger = logging.getLogger(__name__)

class EvaluatorAgentExecutor(BaseAgentExecutor):
    """
    Exécuteur pour l'agent Évaluateur.
    Hérite de BaseAgentExecutor et utilise EvaluatorAgentLogic.
    """
    def __init__(self):
        specific_agent_logic = EvaluatorAgentLogic()
        super().__init__(
        agent_logic=specific_agent_logic,
        default_artifact_name="evaluation_result",
        default_artifact_description="Le résultat de l'évaluation du plan."
        )

    def _create_artifact_from_result(self, result_data: dict, task: Task) -> Artifact:
        """
        Crée un Artifact A2A à partir du résultat (dictionnaire) de EvaluatorAgentLogic.
        Le résultat est converti en une chaîne JSON pour cet exemple.

        Args:
            result_data (dict): Le dictionnaire retourné par EvaluatorAgentLogic.process().
                                Ex: {"evaluation_notes": "...", "evaluated_plan": "..."}
            task (Task): La tâche A2A actuelle.

        Returns:
            Artifact: Un objet Artifact contenant le résultat de l'évaluation en JSON.
        """
        logger.info(f"Création de l'artefact pour la tâche {task.id} avec le résultat d'évaluation.")

        try:
            result_text = json.dumps(result_data, indent=2, ensure_ascii=False)
        except TypeError as e:
            logger.error(f"Erreur de sérialisation JSON pour le résultat de l'évaluation: {e}")
            result_text = f"Erreur de formatage du résultat: {result_data}"

        return new_text_artifact(
            name=self.default_artifact_name,
            description=self.default_artifact_description,
            text=result_text 
        )