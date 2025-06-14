# src/shared/base_agent_executor.py
import logging
from typing_extensions import override
from abc import ABC, abstractmethod # Pour s'assurer que _create_artifact_from_result est implémenté

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events.event_queue import EventQueue
from a2a.types import (
    TaskArtifactUpdateEvent, TaskState, TaskStatus,
    TaskStatusUpdateEvent, TextPart, Part, Message, Artifact, # Ajout de Message et Artifact
    Task # Nécessaire pour l'annotation de type de _create_artifact_from_result
)
from a2a.utils import new_task, new_agent_text_message # new_text_artifact sera utilisé dans la classe fille ou une méthode abstraite

# Importation de notre BaseAgentLogic (ajustez le chemin si nécessaire, ici on suppose une structure plate dans shared)
from .base_agent_logic import BaseAgentLogic
# Ajoutez cet import en haut du fichier

from src.shared.firebase_init import db
from google.cloud import firestore
logger = logging.getLogger(__name__)

class BaseAgentExecutor(AgentExecutor, ABC): # ABC pour forcer l'implémentation de _create_artifact_from_result
    """
    Classe de base pour les AgentExecutors.
    Gère le flux commun de traitement des tâches A2A.
    """
    def __init__(self, 
                 agent_logic: BaseAgentLogic, 
                 default_artifact_name: str = "result", 
                 default_artifact_description: str = "Result from agent processing."):
        super().__init__()
        self.agent_logic = agent_logic
        self.default_artifact_name = default_artifact_name
        self.default_artifact_description = default_artifact_description
        logger.info(f"Executor de type '{self.__class__.__name__}' initialisé avec la logique '{type(agent_logic).__name__}'.")

    def _extract_input_from_message(self, message: Message) -> str | None:
        """
        Extrait une entrée textuelle simple du message.
        Peut être surchargée par les classes filles pour une extraction plus complexe
        ou pour gérer différents types de 'Part'.
        """
        if message.parts:
            first_part_object = message.parts[0]
            if hasattr(first_part_object, 'root') and isinstance(first_part_object.root, TextPart):
                if first_part_object.root.text is not None: # Vérifier que text n'est pas None
                    return first_part_object.root.text
            # Fallback si .root n'est pas la structure ou si c'est directement TextPart
            elif isinstance(first_part_object, TextPart):
                if first_part_object.text is not None: # Vérifier que text n'est pas None
                    return first_part_object.text
        logger.warning("Impossible d'extraire une entrée textuelle simple du message via _extract_input_from_message.")
        return None

    @abstractmethod
    def _create_artifact_from_result(self, result_data: any, task: Task) -> Artifact:
        """
        Méthode abstraite pour créer un objet Artifact à partir des données de résultat.
        Doit être implémentée par les classes filles pour spécifier comment
        le résultat de self.agent_logic.process() est transformé en Artifact.
        Exemple : utiliser new_text_artifact() si le résultat est du texte.
        """
        pass

# Dans la classe BaseAgentExecutor

    def _update_stats(self, success: bool):
        """Met à jour les compteurs de statistiques dans Firestore."""
        try:
            # On suppose que l'agent_logic a un nom, sinon on utilise le nom de la classe
            agent_name = getattr(self.agent_logic, 'AGENT_NAME', self.__class__.__name__)
            
            # On s'assure que db est bien initialisé
            if not db:
                logger.error("Client Firestore (db) non initialisé, impossible de mettre à jour les stats.")
                return

            stats_ref = db.collection("agent_stats").document(agent_name)
            
            field_to_update = {}
            if success:
                # --- CORRECTION ICI ---
                # On utilise la nouvelle syntaxe firestore.Increment()
                field_to_update["tasks_completed"] = firestore.Increment(1)
                log_message = f"Statistiques mises à jour pour {agent_name}: +1 tâche complétée."
            else:
                # --- CORRECTION ICI ---
                field_to_update["tasks_failed"] = firestore.Increment(1)
                log_message = f"Statistiques mises à jour pour {agent_name}: +1 tâche échouée."

            # L'appel .set(..., merge=True) est plus sûr car il crée le document s'il n'existe pas
            stats_ref.set(field_to_update, merge=True)
            logger.info(log_message)

        except Exception as e:
            # On ne veut pas que la logique de stats fasse planter l'agent
            agent_name_for_log = getattr(self.agent_logic, 'AGENT_NAME', self.__class__.__name__)
            logger.error(f"Impossible de mettre à jour les statistiques pour {agent_name_for_log}: {e}")

    @override
    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        task_context_id_for_log = context.context_id if context.context_id else (context.message.contextId if context.message and context.message.contextId else "N/A")
        logger.info(f"{self.__class__.__name__}.execute appelé pour le contexte: {task_context_id_for_log}")

        message = context.message
        task = context.current_task

        if not message:
            logger.error("Aucun message fourni dans le contexte.")
            # Idéalement, envoyer un événement d'erreur si event_queue et task sont disponibles
            return

        if not task:
            task = new_task(request=message)
            logger.info(f"Nouvelle tâche créée: ID={task.id}, ContextID={task.contextId}")
            event_queue.enqueue_event(task)

        # Assurer que task.contextId et task.id sont disponibles pour les logs et événements suivants
        current_task_id = task.id
        current_context_id = task.contextId # Doit être non-None grâce à new_task

        user_input = self._extract_input_from_message(message)

        if user_input is None: # Vérification plus robuste de l'absence d'entrée
            logger.warning(f"Aucune entrée utilisateur valide extraite du message pour la tâche {current_task_id}.")
            await event_queue.enqueue_event(TaskStatusUpdateEvent(
                status=TaskStatus(state=TaskState.failed, message=new_agent_text_message(
                    text="Aucune entrée utilisateur valide fournie ou format de partie incorrect.",
                    context_id=current_context_id, task_id=current_task_id)), # Utiliser les variables définies
                final=True, contextId=current_context_id, taskId=current_task_id))
            return

        logger.info(f"Entrée à traiter pour la tâche {current_task_id}: '{user_input}'")
        await event_queue.enqueue_event(TaskStatusUpdateEvent(
            status=TaskStatus(state=TaskState.working), final=False,
            contextId=current_context_id, taskId=current_task_id))

        try:
            result_data = await self.agent_logic.process(user_input, current_context_id)
            
            # Utiliser la méthode abstraite pour créer l'artefact
            result_artifact = self._create_artifact_from_result(result_data, task)

            await event_queue.enqueue_event(TaskArtifactUpdateEvent(
                append=False, contextId=current_context_id, taskId=current_task_id, lastChunk=True,
                artifact=result_artifact
            ))
            await event_queue.enqueue_event(TaskStatusUpdateEvent(
                status=TaskStatus(state=TaskState.completed), final=True,
                contextId=current_context_id, taskId=current_task_id))
            logger.info(f"Tâche {current_task_id} complétée. Résultat de type: {type(result_data)}")
             # --- AJOUT DE LA LOGIQUE DE STATISTIQUES ---
            self._update_stats(success=True)
        except Exception as e:
            logger.error(f"Erreur pendant le traitement de la tâche {current_task_id}: {e}", exc_info=True)
            await event_queue.enqueue_event(TaskStatusUpdateEvent(
                status=TaskStatus(state=TaskState.failed, message=new_agent_text_message(
                    text=f"Erreur interne de l'agent: {str(e)}",
                    context_id=current_context_id, task_id=current_task_id)),
                final=True, contextId=current_context_id, taskId=current_task_id))

    @override
    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        task_id_for_log = context.current_task.id if context.current_task else "inconnue"
        logger.warning(
            f"Tentative d'annulation pour la tâche {task_id_for_log}, non implémentée dans BaseAgentExecutor."
        )
        pass
