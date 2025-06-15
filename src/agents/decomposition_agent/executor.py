import logging
import json

from src.shared.base_agent_executor import BaseAgentExecutor
from .logic import DecompositionAgentLogic
from typing import Dict, Any
from a2a.types import Artifact, Task
from a2a.utils import new_text_artifact

logger = logging.getLogger(__name__)

class DecompositionAgentExecutor(BaseAgentExecutor):
    def __init__(self):
        specific_agent_logic = DecompositionAgentLogic()
        super().__init__(
            agent_logic=specific_agent_logic,
            default_artifact_name="decomposed_execution_plan_structure",
            default_artifact_description="Structure JSON complète du plan d'exécution, incluant contexte global, instructions et tâches décomposées."
        )
        logger.info("DecompositionAgentExecutor initialisé.")
    
    def _create_artifact_from_result(self, result_data: Dict[str, Any], task: Task) -> Artifact:
        """
        Crée un Artifact A2A à partir de la structure JSON globale retournée par la logique.
        Le résultat est une chaîne JSON représentant cet objet global.
        """
        logger.info(f"Création de l'artefact pour la tâche de décomposition {task.id}.")
        try:
            result_text = json.dumps(result_data, indent=2, ensure_ascii=False)
        except TypeError as e:
            logger.error(f"Erreur de sérialisation JSON pour le résultat de la décomposition: {e}")
            result_text = json.dumps({"error": "Failed to serialize result_data from logic", "original_type": str(type(result_data))})

        return new_text_artifact(
            name=self.default_artifact_name,
            description=self.default_artifact_description,
            text=result_text
        )