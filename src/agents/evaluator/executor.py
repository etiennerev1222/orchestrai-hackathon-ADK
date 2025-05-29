# src/agents/evaluator/executor.py
import logging
import json # Pour formater la sortie du dictionnaire en JSON pour l&#39;artefact

from src.shared.base_agent_executor import BaseAgentExecutor # Ajustez si nécessaire
from .logic import EvaluatorAgentLogic # Importe la logique spécifique de ce dossier

from a2a.types import Artifact, Task
from a2a.utils import new_text_artifact # Pour créer l'artefact

logger = logging.getLogger(__name__)

class EvaluatorAgentExecutor(BaseAgentExecutor):
    """
    Exécuteur pour l'agent Évaluateur.
    Hérite de BaseAgentExecutor et utilise EvaluatorAgentLogic.
    """
    def __init__(self): # CORRECTION: init -> init
        specific_agent_logic = EvaluatorAgentLogic()
        super().__init__( # CORRECTION: init -> init
        agent_logic=specific_agent_logic,
        default_artifact_name="evaluation_result",
        default_artifact_description="Le résultat de l'évaluation du plan."
        )
        # Le logger.info est déjà dans la classe de base init
        # logger.info("EvaluatorAgentExecutor (spécifique) initialisé.")

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

        # Convertir le dictionnaire de résultat en une chaîne JSON pour l'artefact textuel
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