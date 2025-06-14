# src/shared/llm_client.py
import os
import logging
import vertexai  # NOUVEAU : Import du SDK Vertex AI
from vertexai.generative_models import GenerativeModel, GenerationConfig  # NOUVEAU : Imports depuis Vertex AI
from typing import Optional

logger = logging.getLogger(__name__)

# --- Configuration du client Vertex AI ---
# MODIFIÉ : Plus besoin de clé API. On utilise le projet et la région.
GCP_PROJECT_ID = os.environ.get("GCP_PROJECT_ID")
GCP_REGION = os.environ.get("GCP_REGION")
LLM_MODEL = os.environ.get("LLM_MODEL", "gemini-1.5-flash-001") # Modèle recommandé pour Vertex
# -----------------------------------------

# NOUVEAU : Initialisation du client Vertex AI au démarrage.
# Cette opération doit être faite une seule fois.
# Dans un environnement GCP (comme Cloud Run), l'authentification est automatique.
if GCP_PROJECT_ID and GCP_REGION:
    vertexai.init(project=GCP_PROJECT_ID, location=GCP_REGION)
else:
    logger.warning("Les variables d'environnement GCP_PROJECT_ID et GCP_REGION ne sont pas définies. L'initialisation de Vertex AI pourrait échouer.")


async def call_llm(prompt: str, system_prompt: Optional[str] = "You are a helpful assistant.", json_mode: bool = False) -> str:
    """
    Appelle l'API Vertex AI de manière asynchrone en utilisant le SDK de Google Cloud.
    """
    # MODIFIÉ : Le check de la clé API est supprimé. L'authentification est gérée par vertexai.init().
    if not (GCP_PROJECT_ID and GCP_REGION):
        error_msg = "Le projet/région GCP ne sont pas configurés. Appel LLM annulé."
        logger.error(error_msg)
        # On peut retourner une erreur ou une réponse simulée
        raise Exception(error_msg)

    try:
        # La configuration de génération reste très similaire.
        generation_config = GenerationConfig(
            temperature=0.5,
            response_mime_type="application/json" if json_mode else "text/plain"
        )

        # L'instanciation du modèle est quasi-identique.
        model = GenerativeModel(
            model_name=LLM_MODEL,
            system_instruction=system_prompt
        )

        logger.info(f"Appel au modèle Vertex AI ({LLM_MODEL})...")

        # MODIFIÉ : La config est passée dans la méthode generate_content_async.
        response = await model.generate_content_async(
            prompt,
            generation_config=generation_config
        )

        # La gestion de la réponse est identique.
        if not response.parts:
             if response.prompt_feedback.block_reason:
                logger.error(f"Appel bloqué par Vertex AI. Raison: {response.prompt_feedback.block_reason.name}")
                raise Exception(f"Vertex AI response was blocked due to: {response.prompt_feedback.block_reason.name}")
             else:
                raise Exception("Vertex AI returned an empty response.")

        logger.info("Réponse de Vertex AI reçue avec succès.")
        return response.text

    except Exception as e:
        logger.error(f"Erreur inattendue lors de l'appel à Vertex AI: {e}", exc_info=True)
        raise
