# src/shared/service_discovery.py
import logging
import firebase_admin
from firebase_admin import firestore, credentials
from typing import Optional

logger = logging.getLogger(__name__)

from src.shared.firebase_init import db # Importez le client db centralisé
# Vérification optionnelle
if db is None:
    logger.critical("CRITICAL: service_discovery - Firestore client not available from firebase_init.")
    # Gérer l'erreur

GRA_SERVICE_REGISTRY_COLLECTION = "service_registry"
GRA_CONFIG_DOCUMENT_ID = "gra_instance_config"

_cached_gra_url: Optional[str] = None

async def get_gra_base_url() -> Optional[str]:
    global _cached_gra_url
    if _cached_gra_url:
        return _cached_gra_url

    try:
        doc_ref = db.collection(GRA_SERVICE_REGISTRY_COLLECTION).document(GRA_CONFIG_DOCUMENT_ID)
        doc = doc_ref.get()
        if doc.exists:
            data = doc.to_dict()
            url = data.get("current_url")
            if url:
                logger.info(f"URL du GRA découverte depuis Firestore: {url}")
                _cached_gra_url = url
                return url
            else:
                logger.error(f"Le document de configuration du GRA '{GRA_CONFIG_DOCUMENT_ID}' ne contient pas de 'current_url'.")
        else:
            logger.error(f"Document de configuration du GRA '{GRA_CONFIG_DOCUMENT_ID}' non trouvé dans Firestore.")
    except Exception as e:
        logger.error(f"Erreur lors de la découverte de l'URL du GRA depuis Firestore: {e}")
    
    return None # Échec de la découverte