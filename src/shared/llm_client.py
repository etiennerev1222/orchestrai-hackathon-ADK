import os
import logging
import vertexai
from vertexai.generative_models import GenerativeModel, GenerationConfig
from typing import Optional

logger = logging.getLogger(__name__)

GCP_PROJECT_ID = os.environ.get("GCP_PROJECT_ID")
GCP_REGION = os.environ.get("GCP_REGION")

LLM_MODEL = os.environ.get("LLM_MODEL", "gemini-1.5-flash-001")
LLM_MODEL = os.environ.get("LLM_MODEL", "gemini-2.0-flash-001")

try:
    if GCP_PROJECT_ID and GCP_REGION:
        vertexai.init(project=GCP_PROJECT_ID, location=GCP_REGION)
        logger.info(f"Client Vertex AI initialisé pour le projet '{GCP_PROJECT_ID}' dans la région '{GCP_REGION}'.")
    else:
        logger.warning("Veuillez définir GCP_PROJECT_ID et GCP_REGION pour une initialisation explicite de Vertex AI.")
except Exception as e:
    logger.error(f"Erreur lors de l'initialisation de Vertex AI : {e}")


async def call_llm(prompt: str, system_prompt: Optional[str] = "You are a helpful assistant.", json_mode: bool = False) -> str:
    """
    Appelle l'API Vertex AI de manière asynchrone en utilisant le SDK de Google Cloud.
    """
    if not (GCP_PROJECT_ID and GCP_REGION):
        error_msg = "Le projet/région GCP ne sont pas configurés. Appel LLM annulé."
        logger.error(error_msg)
        raise ValueError(error_msg)

    try:
        generation_config = GenerationConfig(
            temperature=0.5,
            response_mime_type="application/json" if json_mode else "text/plain"
        )

        model = GenerativeModel(
            model_name=LLM_MODEL,
            system_instruction=system_prompt
        )

        logger.info(f"Appel au modèle Vertex AI ({LLM_MODEL})...")
        
        response = await model.generate_content_async(prompt, generation_config=generation_config)

        if hasattr(response, 'text') and response.text:
            logger.info("Réponse de Vertex AI reçue avec succès.")
            return response.text
        else:
            if hasattr(response, 'prompt_feedback') and response.prompt_feedback.block_reason:
                block_reason = response.prompt_feedback.block_reason.name
                logger.error(f"Appel bloqué par Vertex AI. Raison: {block_reason}")
                raise Exception(f"Vertex AI response was blocked due to: {block_reason}")
            else:
                logger.error(f"Vertex AI a retourné une réponse vide ou invalide. Contenu: {response}")
                raise Exception("Vertex AI returned an empty or invalid response.")

    except Exception as e:
        logger.error(f"Erreur inattendue lors de l'appel à Vertex AI: {e}", exc_info=True)
        raise