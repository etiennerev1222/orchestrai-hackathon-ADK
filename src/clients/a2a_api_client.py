
import asyncio
import httpx
import logging
from uuid import uuid4
from typing import Any, Dict, Optional

from a2a.client import A2AClient
from a2a.types import (
    SendMessageRequest,
    MessageSendParams,
    Message,
    TextPart,
    GetTaskRequest,
    TaskQueryParams,
    Task,
    TaskState,
    Artifact,
)

from a2a.client import A2AClientHTTPError, A2AClientJSONError

logger = logging.getLogger(__name__)
if not logger.hasHandlers():
    logging.basicConfig(level=logging.INFO)


def _create_agent_input_message(
    input_text: str,
    context_id: Optional[str] = None,
    task_id: Optional[str] = None,
) -> Message:
    """
    Crée un objet Message A2A à partir d'une chaîne de caractères.
    """
    return Message(
        messageId=str(uuid4()),
        role="user",
        parts=[
            TextPart(text=input_text)
        ],
        contextId=context_id,
        taskId=task_id,
    )

import httpx
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)
    

async def call_a2a_agent(
    agent_url: str,
    input_text: str,
    initial_context_id: Optional[str] = None,
    max_retries: int = 30,
    retry_delay: int = 5
) -> Optional[Task]:
    """
    Appelle un agent A2A, lui envoie un message texte, et attend sa complétion.

    Args:
        agent_url: L'URL de base de l'agent serveur A2A.
        input_text: Le texte à envoyer à l'agent.
        initial_context_id: L'ID de contexte à utiliser pour le message (optionnel).
        max_retries: Nombre maximum de tentatives pour sonder l'état de la tâche.
        retry_delay: Délai en secondes entre les tentatives de sondage.

    Returns:
        L'objet Task final (avec état completed, failed, etc.) ou None si erreur majeure.
    """
    logger.info(f"Appel à l'agent A2A à l'URL: {agent_url} avec l'entrée: '{input_text}'")

    async with httpx.AsyncClient(timeout=30.0,http2=False) as http_client:
        try:
            a2a_client = await A2AClient.get_client_from_agent_card_url(
                httpx_client=http_client,
                base_url=agent_url
            )
            logger.info(f"Connecté à l'agent: {a2a_client.card.name if hasattr(a2a_client, 'card') and a2a_client.card else agent_url}")
        except Exception as e:
            logger.error(f"Impossible de se connecter à l'agent {agent_url} ou d'obtenir sa carte: {e}", exc_info=True)
            return None

        message_payload = _create_agent_input_message(input_text, context_id=initial_context_id)
        send_params = MessageSendParams(message=message_payload)
        send_request = SendMessageRequest(id=str(uuid4()), params=send_params)

        task_id: Optional[str] = None
        context_id_for_task: Optional[str] = None

        try:
            send_response = await a2a_client.send_message(request=send_request)
            if hasattr(send_response, 'root') and hasattr(send_response.root, 'result') and isinstance(send_response.root.result, Task):
                created_task = send_response.root.result
                task_id = created_task.id
                context_id_for_task = created_task.contextId
                logger.info(f"Message envoyé. Tâche ID={task_id}, ContextID={context_id_for_task}, Statut initial={created_task.status.state}")
            else:
                error_content = send_response.model_dump_json(indent=2) if hasattr(send_response, 'model_dump_json') else str(send_response)
                logger.error(f"Réponse inattendue de send_message à {agent_url}: {error_content}")
                return None
        except A2AClientHTTPError as e:
            logger.error(f"Erreur HTTP lors de l'envoi du message à l'agent {agent_url}: {e}", exc_info=True)
            return None
        except A2AClientJSONError as e:
            logger.error(f"Erreur de parsing JSON lors de l'envoi du message à l'agent {agent_url}: {e}", exc_info=True)
            return None
        except httpx.RequestError as e:
            logger.error(f"Erreur de requête lors de l'envoi du message à l'agent {agent_url}: {e}", exc_info=True)
            return None
        except  Exception as e:
            logger.error(f"Erreur lors de l'envoi du message à l'agent {agent_url}: {e}", exc_info=True)
            return None

        if not task_id or not context_id_for_task:
            logger.error(f"Aucun task_id ou context_id valide retourné par send_message pour l'agent {agent_url}.")
            return None

        logger.info(f"Sondage de la tâche {task_id} (contexte {context_id_for_task}) pour l'agent {agent_url}...")
        final_task_result: Optional[Task] = None
        for attempt in range(max_retries):
            try:
                await asyncio.sleep(retry_delay)
                get_task_params = TaskQueryParams(id=task_id, context_id=context_id_for_task)
                get_task_request = GetTaskRequest(id=str(uuid4()), params=get_task_params)

                get_task_response = await a2a_client.get_task(request=get_task_request)

                if hasattr(get_task_response, 'root') and hasattr(get_task_response.root, 'result') and isinstance(get_task_response.root.result, Task):
                    current_task = get_task_response.root.result
                    logger.info(f"Agent {agent_url} - Tâche {task_id} - Essai {attempt + 1} - Statut: {current_task.status.state}")
                    if current_task.status.state in [
                        TaskState.submitted, TaskState.working, TaskState.completed, TaskState.failed,TaskState.input_required,TaskState.canceled, TaskState.rejected, TaskState.auth_required
                    ]:
                        final_task_result = current_task
                        break
                else:
                    error_content_get = get_task_response.model_dump_json(indent=2) if hasattr(get_task_response, 'model_dump_json') else str(get_task_response)
                    logger.warning(f"Réponse inattendue de get_task pour l'agent {agent_url} (essai {attempt + 1}): {error_content_get}")

            except Exception as e:
                logger.error(f"Erreur lors de la récupération de la tâche {task_id} de l'agent {agent_url} (essai {attempt + 1}): {e}", exc_info=True)

        if final_task_result:
            logger.info(f"Résultat final obtenu pour la tâche {task_id} de l'agent {agent_url}: Statut={final_task_result.status.state}")
        else:
            logger.error(f"La tâche {task_id} de l'agent {agent_url} n'a pas atteint un état final après {max_retries} tentatives.")

        return final_task_result
