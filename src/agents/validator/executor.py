# src/agents/validator/executor.py
import logging
import json

from src.shared.base_agent_executor import BaseAgentExecutor
from .logic import ValidatorAgentLogic

from a2a.types import Artifact, Task, Message, TextPart  # Ajout de Message, TextPart
from a2a.utils import new_text_artifact

logger = logging.getLogger(__name__)


class ValidatorAgentExecutor(BaseAgentExecutor):
    """
    Exécuteur pour l'agent Validateur.
    """

    def __init__(self):
        specific_agent_logic = ValidatorAgentLogic()
        super().__init__(
            agent_logic=specific_agent_logic,
            default_artifact_name="validation_output",
            default_artifact_description="Le résultat de la validation du plan."
        )
        logger.info("ValidatorAgentExecutor (spécifique) initialisé.")

    # Surcharger _extract_input_from_message car l'entrée est un JSON (résultat de l'évaluateur)
    # et non du texte simple.
    def _extract_input_from_message(self, message: Message) -> dict | None:
        """
        Extrait le dictionnaire JSON de l'artefact de l'évaluateur (passé en tant que texte).
        """
        raw_text_input = super()._extract_input_from_message(message)  # Utilise la méthode de la base pour obtenir le texte
        if raw_text_input:
            try:
                # Supposer que raw_text_input est une chaîne JSON venant de l'artefact de l'évaluateur
                return json.loads(raw_text_input)
            except json.JSONDecodeError as e:
                logger.error(f"Impossible de parser l'entrée JSON pour le validateur: {e}. Entrée brute: {raw_text_input}")
                return {"error": "Invalid JSON input", "raw_input": raw_text_input}
        logger.warning("Aucune entrée textuelle (JSON attendu) trouvée pour le validateur.")
        return None

    def _create_artifact_from_result(self, result_data: dict, task: Task) -> Artifact:
        """
        Crée un Artifact A2A à partir du résultat (dictionnaire) de ValidatorAgentLogic.
        """
        logger.info(f"Création de l'artefact pour la tâche de validation {task.id}.")

        try:
            result_text = json.dumps(result_data, indent=2, ensure_ascii=False)
        except TypeError as e:
            logger.error(f"Erreur de sérialisation JSON pour le résultat de la validation: {e}")
            result_text = f"Erreur de formatage du résultat: {result_data}"

        return new_text_artifact(
            name=self.default_artifact_name,
            description=self.default_artifact_description,
            text=result_text
        )
