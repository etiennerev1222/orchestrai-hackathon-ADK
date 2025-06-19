import os
import logging
from typing_extensions import override
from abc import ABC, abstractmethod
import httpx
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events.event_queue import EventQueue
from a2a.types import (
    TaskArtifactUpdateEvent, TaskState, TaskStatus,
    TaskStatusUpdateEvent, TextPart, Part, Message, Artifact,
    Task
)
from a2a.utils import new_task, new_agent_text_message

from .base_agent_logic import BaseAgentLogic
import time
from src.shared.firebase_init import db
from google.cloud import firestore
from src.shared.agent_state import AgentOperationalState
logger = logging.getLogger(__name__)

class BaseAgentExecutor(AgentExecutor, ABC):
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
        # --- NOUVEAU: Gestion de l'état ---
        self.state: AgentOperationalState = AgentOperationalState.IDLE
        self.current_task_id: str | None = None
        self.last_activity_time: float = time.time()
        # ------------------------------------

        logger.info(f"Executor de type '{self.__class__.__name__}' initialisé avec la logique '{type(agent_logic).__name__}'.")

    def get_status(self) -> dict:
        """Retourne le statut opérationnel actuel de l'agent."""
        current_display_state = self.state.value

        # Si l'agent est IDLE depuis plus de 5 minutes, on le considère "Sleeping" pour l'affichage
        # sans changer son état interne permanent.
        if self.state == AgentOperationalState.IDLE and (time.time() - self.last_activity_time > 300):
            current_display_state = AgentOperationalState.SLEEPING.value

        return {
            "state": current_display_state,
            "current_task_id": self.current_task_id if self.state == AgentOperationalState.BUSY else None,
            "last_activity_time": self.last_activity_time
        }
    # ---------------------------------------------
    # --- NOUVEAU : Méthode pour notifier le GRA ---
    async def _notify_gra_of_status_change(self):
        import os
        from src.shared.service_discovery import get_gra_base_url

        # Tente de récupérer l'URL du GRA depuis l'environnement, sinon via la
        # fonction de discovery (Firestore ou autre)
        self.gra_url = os.environ.get("GRA_PUBLIC_URL") or await get_gra_base_url()

        if not self.gra_url:
            logger.warning(
                "GRA_PUBLIC_URL non configuré et découverte impossible. "
                "Impossible de notifier le changement de statut."
            )
            return
        else:
            logger.info(
                f"Notification du statut au GRA à l'URL: {self.gra_url}/agent_status_update"
            )

        status_payload = self.get_status()
        # Ajout du nom de l'agent pour que le GRA sache qui envoie la mise à jour
        status_payload['name'] =  os.environ.get("AGENT_NAME", self.__class__.__name__) 
        logger.debug(f"Payload de statut à envoyer: {status_payload}")
        logger.info(f"Notification du statut de l'agent {status_payload['name']} au GRA.")

        try:
            # On utilise un client HTTP asynchrone pour ne pas bloquer
            async with httpx.AsyncClient() as client:
                await client.post(f"{self.gra_url}/agent_status_update", json=status_payload, timeout=5.0)
            logger.debug(f"Statut {status_payload['state']} notifié au GRA.")
        except Exception as e:
            logger.error(f"Échec de la notification du statut au GRA: {e}")
    
    def _extract_input_from_message(self, message: Message) -> str | None:
        """
        Extrait une entrée textuelle simple du message.
        Peut être surchargée par les classes filles pour une extraction plus complexe
        ou pour gérer différents types de 'Part'.
        """
        if message.parts:
            first_part_object = message.parts[0]
            if hasattr(first_part_object, 'root') and isinstance(first_part_object.root, TextPart):
                if first_part_object.root.text is not None:
                    return first_part_object.root.text
            elif isinstance(first_part_object, TextPart):
                if first_part_object.text is not None:
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


    def _update_stats(self, success: bool):
        """Met à jour les compteurs de statistiques dans Firestore."""
        try:
            agent_name = os.environ.get("AGENT_NAME", self.__class__.__name__)
            
            if not db:
                logger.error("Client Firestore (db) non initialisé, impossible de mettre à jour les stats.")
                return

            stats_ref = db.collection("agent_stats").document(agent_name)
            
            field_to_update = {}
            if success:
                field_to_update["tasks_completed"] = firestore.Increment(1)
                log_message = f"Statistiques mises à jour pour {agent_name}: +1 tâche complétée."
            else:
                field_to_update["tasks_failed"] = firestore.Increment(1)
                log_message = f"Statistiques mises à jour pour {agent_name}: +1 tâche échouée."

            stats_ref.set(field_to_update, merge=True)
            logger.info(log_message)

        except Exception as e:
            agent_name_for_log = os.environ.get("AGENT_NAME", self.__class__.__name__)
            logger.error(f"Impossible de mettre à jour les statistiques pour {agent_name_for_log}: {e}")

    @override
    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        # VÉRIFIEZ QUE CE BLOC EST PRÉSENT
        self.state = AgentOperationalState.BUSY
        self.current_task_id = context.current_task.id if context.current_task else None
        self.last_activity_time = time.time()
        await self._notify_gra_of_status_change() # Notifier le début
        try:
            task_context_id_for_log = context.context_id if context.context_id else (context.message.contextId if context.message and context.message.contextId else "N/A")
            logger.info(f"{self.__class__.__name__}.execute appelé pour le contexte: {task_context_id_for_log}")

            message = context.message
            task = context.current_task

            if not message:
                logger.error("Aucun message fourni dans le contexte.")
                return

            if not task:
                task = new_task(request=message)
                logger.info(f"Nouvelle tâche créée: ID={task.id}, ContextID={task.contextId}")
                event_queue.enqueue_event(task)

            current_task_id = task.id
            current_context_id = task.contextId

            user_input = self._extract_input_from_message(message)

            if user_input is None:
                logger.warning(f"Aucune entrée utilisateur valide extraite du message pour la tâche {current_task_id}.")
                await event_queue.enqueue_event(TaskStatusUpdateEvent(
                    status=TaskStatus(state=TaskState.failed, message=new_agent_text_message(
                        text="Aucune entrée utilisateur valide fournie ou format de partie incorrect.",
                        context_id=current_context_id, task_id=current_task_id)),
                    final=True, contextId=current_context_id, taskId=current_task_id))
                return

            logger.info(f"Entrée à traiter pour la tâche {current_task_id}: '{user_input}'")
            await event_queue.enqueue_event(TaskStatusUpdateEvent(
                status=TaskStatus(state=TaskState.working), final=False,
                contextId=current_context_id, taskId=current_task_id))

            try:
                result_data = await self.agent_logic.process(user_input, current_context_id)
                
                result_artifact = self._create_artifact_from_result(result_data, task)

                await event_queue.enqueue_event(TaskArtifactUpdateEvent(
                    append=False, contextId=current_context_id, taskId=current_task_id, lastChunk=True,
                    artifact=result_artifact
                ))
                await event_queue.enqueue_event(TaskStatusUpdateEvent(
                    status=TaskStatus(state=TaskState.completed), final=True,
                    contextId=current_context_id, taskId=current_task_id))
                logger.info(f"Tâche {current_task_id} complétée. Résultat de type: {type(result_data)}")
                self._update_stats(success=True)
            except Exception as e:
                self.state = AgentOperationalState.ERROR
                await self._notify_gra_of_status_change() # Notifier le début
                logger.error(f"Erreur pendant le traitement de la tâche {current_task_id}: {e}", exc_info=True)
                await event_queue.enqueue_event(TaskStatusUpdateEvent(
                    status=TaskStatus(state=TaskState.failed, message=new_agent_text_message(
                        text=f"Erreur interne de l'agent: {str(e)}",
                        context_id=current_context_id, task_id=current_task_id)),
                    final=True, contextId=current_context_id, taskId=current_task_id))
        except Exception as e:
              self.state = AgentOperationalState.ERROR
        finally:

            self.state = AgentOperationalState.IDLE
            self.current_task_id = None
            self.last_activity_time = time.time()
            await self._notify_gra_of_status_change() # Notifier le début

                      
    @override
    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        task_id_for_log = context.current_task.id if context.current_task else "inconnue"
        logger.warning(
            f"Tentative d'annulation pour la tâche {task_id_for_log}, non implémentée dans BaseAgentExecutor."
        )
        pass
