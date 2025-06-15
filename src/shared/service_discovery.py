import httpx
from src.shared.firebase_init import get_firestore_client
import logging
import os
import asyncio
from typing import List, Optional
logger = logging.getLogger(__name__)
if not logger.hasHandlers():
    logging.basicConfig(level=logging.INFO)

GRA_SERVICE_REGISTRY_COLLECTION = "service_registry"
GRA_CONFIG_DOCUMENT_ID = "gra_instance_config"


async def get_gra_base_url() -> str:
    """
    Détermine l'URL du GRA.
    Priorité 1: Variable d'environnement (idéal pour Docker).
    Priorité 2: Firestore (pour les déploiements plus complexes ou non-Docker).
    """
    gra_url_from_env = os.environ.get("GRA_PUBLIC_URL")
    if gra_url_from_env:
        logger.info(f"URL du GRA trouvée via la variable d'environnement : {gra_url_from_env}")
        return gra_url_from_env

    logger.info("Variable d'environnement GRA_PUBLIC_URL non trouvée, tentative via Firestore.")
    db = get_firestore_client()
    if not db:
        logger.error("Impossible d'obtenir le client Firestore. Le GRA ne sera pas joignable.")
        return ""

    doc_ref = db.collection(GRA_SERVICE_REGISTRY_COLLECTION).document(GRA_CONFIG_DOCUMENT_ID)
    try:
        doc = await asyncio.to_thread(doc_ref.get)
        if doc.exists:
            gra_url = doc.to_dict().get('url')
            if gra_url:
                logger.info(f"URL du GRA découverte depuis Firestore : {gra_url}")
                return gra_url
        logger.warning("Document de configuration du GRA non trouvé dans Firestore.")
        return ""
    except Exception as e:
        logger.error(f"Erreur lors de la découverte du GRA via Firestore : {e}", exc_info=True)
        return ""
    
async def register_self_with_gra(agent_name: str, agent_public_url: str, agent_internal_url: str, skills: List[str]):
    gra_base_url = await get_gra_base_url()
    if not gra_base_url:
        logger.error(f"[{agent_name}] URL du GRA non disponible, impossible de s'enregistrer.")
        return

    register_url = f"{gra_base_url}/register"
    payload = {
        "agent_name": agent_name,
        "public_url": agent_public_url,
        "internal_url": agent_internal_url,
        "skills": skills
    }
    
    max_retries = 4
    delay_between_retries = 2

    logger.info(f"[{agent_name}] Tentative d'enregistrement auprès du GRA à {register_url}")
    for attempt in range(1, max_retries + 1):
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(register_url, json=payload, timeout=5.0)
                response.raise_for_status()
                logger.info(f"[{agent_name}] Enregistré avec succès auprès du GRA.")
                return
        except Exception as e:
            logger.error(f"[{agent_name}] Échec de l'enregistrement (tentative {attempt}/{max_retries}) : {e}")
            if attempt < max_retries:
                logger.info(f"[{agent_name}] Nouvelle tentative dans {delay_between_retries} secondes...")
                await asyncio.sleep(delay_between_retries)
            else:
                logger.error(f"[{agent_name}] Toutes les tentatives d'enregistrement ont échoué.")
