import asyncio
import httpx
import logging
from uuid import uuid4
import json

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

DECOMPOSITION_AGENT_SERVER_URL = "http://localhost:8005"

def create_plan_to_decompose_message(plan_text: str) -> Message:
    """Crée un objet Message A2A simple contenant le plan textuel à décomposer."""
    return Message(
        messageId=str(uuid4()),
        role="user",
        parts=[
            TextPart(text=plan_text)
        ]
    )

async def run_decomposition_test(plan_text_to_decompose: str):
    logger.info(f"Tentative de connexion à l'agent de Décomposition à: {DECOMPOSITION_AGENT_SERVER_URL}")

    async with httpx.AsyncClient(timeout=60.0) as http_client:
        try:
            a2a_client = await A2AClient.get_client_from_agent_card_url(
                httpx_client=http_client,
                base_url=DECOMPOSITION_AGENT_SERVER_URL
            )
            logger.info(f"Connexion à l'agent de Décomposition et récupération de la carte réussies.")
        except Exception as e:
            logger.error(f"Impossible de se connecter à l'agent de Décomposition: {e}", exc_info=True)
            logger.error(f"Vérifiez que le DecompositionAgentServer (src/agents/decomposition_agent/server.py) est lancé sur le port {DECOMPOSITION_AGENT_SERVER_URL.split(':')[-1]}.")
            return

        message_payload = create_plan_to_decompose_message(plan_text=plan_text_to_decompose)
        send_params = MessageSendParams(message=message_payload)
        send_request = SendMessageRequest(id=str(uuid4()), params=send_params)

        logger.info(f"Envoi du plan à décomposer à l'agent...")
        created_task_id: str | None = None
        created_context_id: str | None = None

        try:
            send_response = await a2a_client.send_message(request=send_request)
            if hasattr(send_response, 'root') and hasattr(send_response.root, 'result') and isinstance(send_response.root.result, Task):
                created_task = send_response.root.result
                created_task_id = created_task.id
                created_context_id = created_task.contextId
                logger.info(f"Message envoyé. Tâche créée: ID={created_task_id}, ContextID={created_context_id}, Statut={created_task.status.state}")
            else:
                logger.error(f"Réponse inattendue de send_message: {send_response.model_dump_json(indent=2) if hasattr(send_response, 'model_dump_json') else send_response}")
                return
        except Exception as e:
            logger.error(f"Erreur lors de l'envoi du message: {e}", exc_info=True)
            return

        if not created_task_id or not created_context_id:
            logger.error("Task ID ou Context ID non retourné par l'agent.")
            return

        logger.info(f"Attente et récupération du résultat de la tâche {created_task_id}...")
        max_retries = 20
        retry_delay = 5
        final_task_result: Task | None = None

        for attempt in range(max_retries):
            try:
                await asyncio.sleep(retry_delay)
                get_task_params = TaskQueryParams(id=created_task_id, context_id=created_context_id)
                get_task_request = GetTaskRequest(id=str(uuid4()), params=get_task_params)
                
                get_task_response = await a2a_client.get_task(request=get_task_request)

                if hasattr(get_task_response, 'root') and hasattr(get_task_response.root, 'result') and isinstance(get_task_response.root.result, Task):
                    current_task_status = get_task_response.root.result
                    logger.info(f"Statut tâche {created_task_id} (essai {attempt + 1}): {current_task_status.status.state}")
                    
                    if current_task_status.status.state in [TaskState.completed, TaskState.failed, TaskState.input_required, TaskState.canceled, TaskState.rejected, TaskState.auth_required]:
                        final_task_result = current_task_status
                        break
                else:
                    logger.warning(f"Réponse inattendue de get_task (essai {attempt + 1}): {get_task_response.model_dump_json(indent=2) if hasattr(get_task_response, 'model_dump_json') else get_task_response}")
            except Exception as e:
                logger.error(f"Erreur lors de la récupération de la tâche {created_task_id} (essai {attempt + 1}): {e}", exc_info=True)
        
        if final_task_result:
            logger.info(f"--- Résultat final de la tâche {final_task_result.id} ---")
            logger.info(f"Statut: {final_task_result.status.state}")

            if final_task_result.status.message and final_task_result.status.message.parts and \
               isinstance(final_task_result.status.message.parts[0].root, TextPart):
                logger.info(f"Message de statut: {final_task_result.status.message.parts[0].root.text}")

            if final_task_result.artifacts:
                logger.info("Artefacts produits:")
                for artifact_item in final_task_result.artifacts:
                    logger.info(f"  - Nom: {artifact_item.name}, Description: {artifact_item.description}, ID: {artifact_item.artifactId}")
                    if artifact_item.parts and len(artifact_item.parts) > 0 and \
                       hasattr(artifact_item.parts[0], 'root') and \
                       isinstance(artifact_item.parts[0].root, TextPart) and \
                       artifact_item.parts[0].root.text is not None:
                        decomposed_plan_json_str = artifact_item.parts[0].root.text
                        logger.info(f"    Contenu de l'artefact (JSON brut): {decomposed_plan_json_str}")
                        try:
                            decomposed_data = json.loads(decomposed_plan_json_str)
                            logger.info(f"    Données de décomposition (parsées):")
                            logger.info(json.dumps(decomposed_data, indent=2, ensure_ascii=False))
                        except json.JSONDecodeError:
                            logger.error("    Impossible de parser le JSON de l'artefact.")
                    else:
                        logger.warning("    Impossible d'extraire le texte de l'artefact.")
            else:
                logger.info("Aucun artefact produit.")
        else:
            task_id_to_log = created_task_id if created_task_id else "inconnue"
            logger.error(f"La tâche {task_id_to_log} n'a pas atteint un état final après {max_retries} tentatives.")


if __name__ == "__main__":
    sample_plan_text = """
    Objectif Principal: Créer un prototype de jeu d'aventure textuel en Python.
    Phase 1: Conception Initiale
    - Définir le thème et l'univers du jeu.
    - Écrire un scénario de base avec 3 lieux interconnectés.
    - Concevoir le mécanisme d'inventaire simple (ramasser/utiliser objets).
    Phase 2: Développement du Moteur de Jeu
    - Implémenter la navigation entre les lieux.
    - Développer le système d'inventaire.
    - Créer le parser de commandes utilisateur basique.
    Phase 3: Contenu et Test
    - Intégrer le scénario et les descriptions des lieux.
    - Placer les objets interactifs.
    - Tester le flux de jeu et corriger les bugs.
    Livrable: Un script Python exécutable du prototype.
    """
    
    logger.info("Lancement du client de test pour DecompositionAgent...")
    try:
        asyncio.run(run_decomposition_test(sample_plan_text))
    except Exception as e:
        logger.error(f"Erreur lors de l'exécution du client de test: {e}", exc_info=True)
