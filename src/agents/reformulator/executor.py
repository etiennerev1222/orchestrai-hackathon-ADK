# my_simple_a2a_service/reformulator_server/agent_executor.py

import logging
from typing_extensions import override

# Importations depuis le SDK A2A
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events.event_queue import EventQueue
from a2a.types import (
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
    Message, # Non utilisé directement ici, mais bon à savoir
    TextPart, # Non utilisé directement ici
)
# Ajustez les chemins d'importation si votre structure est différente
from src.shared.base_agent_executor import BaseAgentExecutor
from .logic import ReformulatorAgentLogic # Importe la logique spécifique de ce dossier

from a2a.types import Artifact, Task # Nécessaire pour l'annotation de type de _create_artifact_from_result
from a2a.utils import new_text_artifact # Utile pour créer l'artefact

logger = logging.getLogger(__name__)

class ReformulatorAgentExecutor(BaseAgentExecutor):
    """
    Exécuteur pour l'agent Reformulateur.
    Hérite de BaseAgentExecutor et utilise ReformulatorAgentLogic.
    """

    def __init__(self):
        # Crée une instance de la logique spécifique à cet agent
        specific_agent_logic = ReformulatorAgentLogic()
        
        # Appelle le constructeur de la classe de base en lui passant la logique
        # et des informations spécifiques à l'artefact que cet agent produit.
        super().__init__(
            agent_logic=specific_agent_logic,
            default_artifact_name="reformulated_objective",
            default_artifact_description="L'objectif après reformulation par l'agent."
        )
        # Le logger.info est déjà dans la classe de base __init__
        # logger.info("ReformulatorAgentExecutor (spécifique) initialisé.")


    # La méthode `execute` est héritée de BaseAgentExecutor.
    # Nous n'avons pas besoin de la redéfinir si le comportement de base nous convient.
    # La méthode _extract_input_from_message de BaseAgentExecutor sera utilisée par défaut.
    # Si le ReformulatorAgent a besoin d'une manière différente d'extraire son input,
    # nous pourrions surcharger _extract_input_from_message ici.

    # Nous DEVONS implémenter la méthode abstraite _create_artifact_from_result
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
        # Utilise les noms et descriptions par défaut définis dans __init__ ou des valeurs spécifiques
        return new_text_artifact(
            name=self.default_artifact_name,
            description=self.default_artifact_description,
            text=result_data # result_data est la chaîne retournée par ReformulatorAgentLogic.process()
        )

    # La méthode `cancel` est également héritée et peut être surchargée si nécessaire.
    # Pour l'instant, celle de BaseAgentExecutor suffit.
