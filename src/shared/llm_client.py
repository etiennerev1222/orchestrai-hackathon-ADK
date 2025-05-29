# src/shared/llm_client.py
import os
import logging
import google.generativeai as genai
from google.generativeai.types import GenerationConfig
from typing import Optional

logger = logging.getLogger(__name__)

# --- Configuration du client Gemini ---
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
LLM_MODEL = os.environ.get("LLM_MODEL", "gemini-1.5-flash-latest")
# -----------------------------------------

# La configuration est faite une seule fois si la clé existe
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
else:
    logger.warning("La variable d'environnement GEMINI_API_KEY n'est pas définie.")


async def call_llm(prompt: str, system_prompt: Optional[str] = "You are a helpful assistant.", json_mode: bool = False) -> str:
    """
    Appelle l'API Gemini de manière asynchrone en utilisant le SDK de Google.
    """
    # CORRECTION : On vérifie la variable lue depuis l'environnement, et non "genai.conf"
    if not GEMINI_API_KEY:
        error_msg = "La clé API Gemini n'est pas configurée. Appel LLM annulé."
        logger.error(error_msg)
        return f"RÉPONSE SIMULÉE (Clé API manquante): Le traitement pour le prompt '{prompt[:50]}...' serait effectué ici."

    try:
        generation_config = GenerationConfig(
            temperature=0.5,
            response_mime_type="application/json" if json_mode else "text/plain"
        )

        model = genai.GenerativeModel(
            model_name=LLM_MODEL,
            system_instruction=system_prompt,
            generation_config=generation_config
        )

        logger.info(f"Appel au modèle Gemini ({LLM_MODEL})...")
        
        response = await model.generate_content_async(prompt)

        if not response.parts:
             if response.prompt_feedback.block_reason:
                logger.error(f"Appel bloqué par Gemini. Raison: {response.prompt_feedback.block_reason.name}")
                raise Exception(f"Gemini response was blocked due to: {response.prompt_feedback.block_reason.name}")
             else:
                raise Exception("Gemini returned an empty response.")

        logger.info("Réponse de Gemini reçue avec succès.")
        return response.text

    except Exception as e:
        logger.error(f"Erreur inattendue lors de l'appel à Gemini: {e}", exc_info=True)
        raise