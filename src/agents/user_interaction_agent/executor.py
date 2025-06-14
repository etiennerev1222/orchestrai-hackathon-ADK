# src/agents/user_interaction_agent/executor.py
import logging
import json

from src.shared.base_agent_executor import BaseAgentExecutor
from .logic import UserInteractionAgentLogic, ACTION_CLARIFY_OBJECTIVE

from a2a.types import Artifact, Task, Message, TaskState, TaskStatus # Ajout de TaskState, TaskStatus
from a2a.utils import new_text_artifact, new_agent_text_message # Ajout de new_agent_text_message
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events.event_queue import EventQueue
from a2a.utils import new_task, new_agent_text_message
from a2a.types import (
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
    Message, # Non utilisé directement ici, mais bon à savoir
    TextPart, # Non utilisé directement ici
)

logger = logging.getLogger(__name__)

class UserInteractionAgentExecutor(BaseAgentExecutor):
    """
    Exécuteur pour l'agent d'interaction utilisateur.
    """

    def __init__(self):
        specific_agent_logic = UserInteractionAgentLogic()
        super().__init__(
            agent_logic=specific_agent_logic,
            default_artifact_name="user_interaction_output",
            default_artifact_description="Résultat de l'interaction avec l'utilisateur."
        )
        logger.info("UserInteractionAgentExecutor initialisé.")

    def _extract_input_from_message(self, message: Message) -> dict | None:
        """
        Extrait l'entrée (qui devrait être un JSON) du message A2A.
        Le GlobalSupervisor enverra un JSON comme {"action": "...", "raw_objective": "..."}.
        """
        raw_text_input = super()._extract_input_from_message(message)
        if raw_text_input:
            try:
                return json.loads(raw_text_input)
            except json.JSONDecodeError as e:
                logger.error(f"Impossible de parser l'entrée JSON pour UserInteractionAgent: {e}. Entrée brute: {raw_text_input}")
                # Retourner une structure d'erreur que la logique peut interpréter
                return {"error": "Invalid JSON input", "raw_input": raw_text_input}
        logger.warning("Aucune entrée textuelle (JSON attendu) trouvée pour UserInteractionAgent.")
        return None

    # Surcharge de la méthode execute pour gérer les états de tâche A2A spécifiques
    # retournés par la logique (completed, input_required, failed).
    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        task_context_id_for_log = context.context_id if context.context_id else (context.message.contextId if context.message and context.message.contextId else "N/A")
        logger.info(f"{self.__class__.__name__}.execute appelé pour le contexte: {task_context_id_for_log}")

        message = context.message
        task = context.current_task
        # --- DÉBUT DE LA CORRECTION NÉCESSAIRE ---
        if not task: # Si context.current_task est None
            if message: # new_task requiert un 'request', qui est le 'message' ici.
                task = new_task(request=message)
                logger.info(f"Nouvelle tâche créée par UserInteractionAgentExecutor: ID={task.id}, ContextID={task.contextId}")
                event_queue.enqueue_event(task) # Enqueue l'objet tâche lui-même
            else:
                logger.error("Impossible de créer une tâche car le message est manquant pour UserInteractionAgentExecutor.")
                return 
        # --- FIN DE LA CORRECTION NÉCESSAIRE ---

        if not message: # Devrait être géré par le SDK A2A en amont mais bonne pratique de vérifier
            logger.error("Aucun message fourni dans le contexte.")
            return

        if not task: # Devrait être géré par le SDK A2A en amont
            logger.error("Aucune tâche actuelle dans le contexte.")
            return

        # Utiliser les IDs de la tâche existante passée dans le contexte
        current_task_id = task.id
        current_context_id = task.contextId

        user_input_dict = self._extract_input_from_message(message)

        if user_input_dict is None or "error" in user_input_dict:
            error_message_text = user_input_dict.get("raw_input", "Entrée invalide ou manquante.") if isinstance(user_input_dict, dict) else "Entrée invalide."
            logger.warning(f"Entrée utilisateur invalide pour la tâche {current_task_id}: {error_message_text}")
            status_message = new_agent_text_message(
                text=f"Format d'entrée incorrect pour UserInteractionAgent: {error_message_text}",
                context_id=current_context_id, task_id=current_task_id
            )
            event_queue.enqueue_event(TaskStatusUpdateEvent(
                status=TaskStatus(state=TaskState.failed, message=status_message),
                final=True, contextId=current_context_id, taskId=current_task_id
            ))
            return

        logger.info(f"Entrée à traiter pour la tâche {current_task_id}: {user_input_dict}")
        event_queue.enqueue_event(TaskStatusUpdateEvent(
            status=TaskStatus(state=TaskState.working), final=False,
            contextId=current_context_id, taskId=current_task_id
        ))

        try:
            # La méthode process de UserInteractionAgentLogic retourne (result_payload, a2a_task_state_str)
            result_payload, a2a_task_state_str = await self.agent_logic.process(user_input_dict, current_context_id)
            
            result_artifact = self._create_artifact_from_result(result_payload, task)
            event_queue.enqueue_event(TaskArtifactUpdateEvent(
                append=False, contextId=current_context_id, taskId=current_task_id, lastChunk=True,
                artifact=result_artifact
            ))

            final_a2a_state = TaskState.completed # Par défaut
            status_message_text = "Traitement terminé."

            if a2a_task_state_str == "input_required":
                final_a2a_state = TaskState.input_required
                status_message_text = result_payload.get("question_for_user", "En attente d'une entrée utilisateur supplémentaire.")
            elif a2a_task_state_str == "failed":
                final_a2a_state = TaskState.failed
                status_message_text = result_payload.get("message", "Échec du traitement de l'interaction.")
            elif result_payload.get("status") == "clarified":
                 status_message_text = result_payload.get("message_for_supervisor", "Objectif clarifié.")


            status_update_message = new_agent_text_message(
                text=status_message_text,
                context_id=current_context_id,
                task_id=current_task_id
            )
            event_queue.enqueue_event(TaskStatusUpdateEvent(
                status=TaskStatus(state=final_a2a_state, message=status_update_message),
                final=True, contextId=current_context_id, taskId=current_task_id
            ))
            logger.info(f"Tâche {current_task_id} terminée avec l'état A2A: {final_a2a_state}. Résultat: {result_payload}")

        except Exception as e:
            logger.error(f"Erreur pendant le traitement de la tâche {current_task_id}: {e}", exc_info=True)
            error_status_message = new_agent_text_message(
                text=f"Erreur interne de UserInteractionAgent: {str(e)}",
                context_id=current_context_id, task_id=current_task_id
            )
            event_queue.enqueue_event(TaskStatusUpdateEvent(
                status=TaskStatus(state=TaskState.failed, message=error_status_message),
                final=True, contextId=current_context_id, taskId=current_task_id
            ))


    def _create_artifact_from_result(self, result_data: dict, task: Task) -> Artifact:
        """
        Crée un Artifact A2A à partir du résultat (dictionnaire) de UserInteractionAgentLogic.
        Le résultat est converti en une chaîne JSON.
        """
        logger.info(f"Création de l'artefact pour la tâche d'interaction {task.id}.")
        try:
            # Le result_data est déjà un dictionnaire préparé par la logique
            result_text = json.dumps(result_data, indent=2, ensure_ascii=False)
        except TypeError as e:
            logger.error(f"Erreur de sérialisation JSON pour le résultat de UserInteractionAgent: {e}")
            # Fournir un fallback en cas d'erreur de sérialisation
            result_text = json.dumps({"error": "Failed to serialize result_data", "original_type": str(type(result_data))})

        return new_text_artifact(
            name=self.default_artifact_name,
            description=self.default_artifact_description,
            text=result_text
        )