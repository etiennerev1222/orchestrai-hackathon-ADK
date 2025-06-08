# src/shared/service_discovery.py
import httpx
from src.shared.firebase_init import get_firestore_client
import logging
import os

logger = logging.getLogger(__name__)
if not logger.hasHandlers():
    logging.basicConfig(level=logging.INFO)

GRA_SERVICE_REGISTRY_COLLECTION = "service_registry"
GRA_CONFIG_DOCUMENT_ID = "gra_instance_config"

# On ne cache plus l'URL, on la redemande pour plus de flexibilité
# _cached_gra_url: Optional[str] = None

async def get_gra_base_url() -> str:
    """
    Détermine l'URL du GRA.
    Priorité 1: Variable d'environnement (idéal pour Docker).
    Priorité 2: Firestore (pour les déploiements plus complexes ou non-Docker).
    """
    # Priorité 1: Variable d'environnement
    gra_url_from_env = os.environ.get("GRA_PUBLIC_URL")
    if gra_url_from_env:
        logger.info(f"URL du GRA trouvée via la variable d'environnement : {gra_url_from_env}")
        return gra_url_from_env

    # Priorité 2: Firestore (méthode de secours)
    logger.info("Variable d'environnement GRA_PUBLIC_URL non trouvée, tentative via Firestore.")
    db = get_firestore_client()
    if not db:
        logger.error("Impossible d'obtenir le client Firestore. Le GRA ne sera pas joignable.")
        return ""

    doc_ref = db.collection(GRA_SERVICE_REGISTRY_COLLECTION).document(GRA_CONFIG_DOCUMENT_ID)
    try:
        doc = await doc_ref.get()
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


async def register_self_with_gra(agent_name: str, agent_url: str):
    """
    Enregistre l'URL d'un agent dans Firestore pour que le GRA puisse le découvrir.
    """
    gra_base_url = await get_gra_base_url()
    if not gra_base_url:
        logger.error(f"[{agent_name}] URL du GRA non disponible, impossible de s'enregistrer.")
        return

    register_url = f"{gra_base_url}/register"
    logger.info(f"[{agent_name}] Tentative d'enregistrement ({agent_url}) auprès du GRA à {register_url}")
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(register_url, json={"agent_name": agent_name, "agent_url": agent_url}, timeout=5.0)
            response.raise_for_status()
            logger.info(f"[{agent_name}] Enregistré avec succès auprès du GRA. Réponse: {response.json()}")
    except httpx.RequestError as e:
        logger.error(f"[{agent_name}] Échec de l'enregistrement auprès du GRA : Erreur réseau {e}")
    except Exception as e:
        logger.error(f"[{agent_name}] Erreur inattendue lors de l'enregistrement : {e}", exc_info=True)