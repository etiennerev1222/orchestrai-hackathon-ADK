
import asyncio
import httpx
import logging
from uuid import uuid4

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

logger = logging.getLogger(__name__)
if not logger.hasHandlers():
    logging.basicConfig(level=logging.INFO)

REFORMULATOR_AGENT_SERVER_URL = "http://localhost:8001"


def create_objective_message(objective_text: str) -> Message:
    """
    Crée un objet Message A2A simple contenant un objectif textuel.
    """
    return Message(
        messageId=str(uuid4()),
        role="user",
        parts=[
            TextPart(text=objective_text)
        ]
    )


async def run_reformulation_test():
    """
    Exécute un test en envoyant un objectif au ReformulatorAgentServer
    et en attendant sa réponse.
    """
    logger.info(f"Tentative de connexion à l'agent Reformulateur à l'adresse: {REFORMULATOR_AGENT_SERVER_URL}")

    async with httpx.AsyncClient(timeout=30.0) as http_client:
        try:
            a2a_client = await A2AClient.get_client_from_agent_card_url(
                httpx_client=http_client,
                base_url=REFORMULATOR_AGENT_SERVER_URL
            )
            logger.info(f"Connexion à l'agent et récupération de la carte réussies (URL: {REFORMULATOR_AGENT_SERVER_URL}).")
            
            

        except Exception as e:
            logger.error(f"Impossible de se connecter à l'agent ou d'obtenir sa carte: {e}", exc_info=True)
            logger.error("Veuillez vérifier que le ReformulatorAgentServer (reformulator_server/main_server.py) est bien lancé.")
            return

        objective_to_send = "planifier une réunion d'équipe urgente pour la semaine prochaine"
        message_payload = create_objective_message(objective_text=objective_to_send)
        
        send_params = MessageSendParams(message=message_payload)
        send_request = SendMessageRequest(id=str(uuid4()), params=send_params)

        logger.info(f"Envoi de l'objectif '{objective_to_send}' à l'agent...")
        try:
            send_response = await a2a_client.send_message(request=send_request)
            
            if hasattr(send_response, 'root') and hasattr(send_response.root, 'result') and isinstance(send_response.root.result, Task):
                created_task = send_response.root.result
                task_id = created_task.id
                context_id = created_task.contextId
                logger.info(f"Message envoyé avec succès. Tâche créée/mise à jour: ID={task_id}, ContextID={context_id}, Statut={created_task.status.state}")
            else:
                logger.error(f"Réponse inattendue de send_message: {send_response.model_dump_json(indent=2)}")
                return

        except Exception as e:
            logger.error(f"Erreur lors de l'envoi du message à l'agent: {e}", exc_info=True)
            return

        
        logger.info(f"Attente et récupération du résultat de la tâche {task_id}...")
        max_retries = 10
        retry_delay = 2
        final_task_result = None
        for attempt in range(max_retries):
            try:
                await asyncio.sleep(retry_delay) 
                get_task_params = TaskQueryParams(id=task_id, context_id=context_id)
                get_task_request = GetTaskRequest(id=str(uuid4()), params=get_task_params)
                
                get_task_response = await a2a_client.get_task(request=get_task_request)

                if hasattr(get_task_response, 'root') and hasattr(get_task_response.root, 'result') and isinstance(get_task_response.root.result, Task):
                    current_task_status = get_task_response.root.result
                    logger.info(f"Statut actuel de la tâche {task_id} (essai {attempt + 1}): {current_task_status.status.state}")
                    
                    if current_task_status.status.state in [TaskState.completed, TaskState.failed, TaskState.input_required, TaskState.canceled, TaskState.rejected, TaskState.auth_required]:
                        final_task_result = current_task_status
                        break 
                else:
                    logger.warning(f"Réponse inattendue de get_task (essai {attempt + 1}): {get_task_response.model_dump_json(indent=2)}")

            except Exception as e:
                logger.error(f"Erreur lors de la récupération de la tâche {task_id} (essai {attempt + 1}): {e}", exc_info=True)

        if final_task_result:
            logger.info(f"--- Résultat final de la tâche {final_task_result.id} ---")
            logger.info(f"Statut: {final_task_result.status.state}")

            if final_task_result.status.message:
                status_message_text = "N/A"
                if final_task_result.status.message.parts and \
                hasattr(final_task_result.status.message.parts[0], 'root') and \
                isinstance(final_task_result.status.message.parts[0].root, TextPart) and \
                final_task_result.status.message.parts[0].root.text:
                    status_message_text = final_task_result.status.message.parts[0].root.text
                elif final_task_result.status.message.parts and \
                    isinstance(final_task_result.status.message.parts[0], TextPart) and \
                    final_task_result.status.message.parts[0].text:
                    status_message_text = final_task_result.status.message.parts[0].text
                elif isinstance(final_task_result.status.message.parts, list) and not final_task_result.status.message.parts: 
                    status_message_text = "[Message de statut vide ou sans parties textuelles]"
                elif not final_task_result.status.message.parts: 
                    status_message_text = "[Message de statut sans parties]"
                logger.info(f"Message de statut: {status_message_text}")


            if final_task_result.artifacts:
                logger.info("Artefacts produits:")
                for artifact_item in final_task_result.artifacts: 
                    logger.info(f"  - Nom: {artifact_item.name}, Description: {artifact_item.description}, ID: {artifact_item.artifactId}")
                    
                    if artifact_item.parts and \
                    len(artifact_item.parts) > 0 and \
                    hasattr(artifact_item.parts[0], 'root') and \
                    isinstance(artifact_item.parts[0].root, TextPart) and \
                    artifact_item.parts[0].root.text is not None:
                        reformulated_text_from_artifact = artifact_item.parts[0].root.text
                        logger.info(f"    Texte de l'artefact: {reformulated_text_from_artifact}")
                    else:
                        logger.warning(f"    Impossible d'extraire le texte de l'artefact. Structure de 'parts[0]': {artifact_item.parts[0] if artifact_item.parts else 'aucune partie'}")
            else:
                logger.info("Aucun artefact produit.")
        else:
            logger.error(f"La tâche {final_task_result.id if final_task_result else task_id} n'a pas atteint un état final ou n'a pu être récupérée après {max_retries} tentatives.")


if __name__ == "__main__":
    logger.info("Lancement du client de test pour ReformulatorAgent...")
    try:
        asyncio.run(run_reformulation_test())
    except Exception as e:
        logger.error(f"Erreur lors de l'exécution du client de test: {e}", exc_info=True)


