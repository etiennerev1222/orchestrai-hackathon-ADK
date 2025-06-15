import logging
import firebase_admin
from firebase_admin import credentials, firestore
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

db = None

try:
    if os.environ.get('K_SERVICE'):
        logger.info("Environnement Google Cloud détecté. Initialisation avec les crédentials par défaut.")
        cred = credentials.ApplicationDefault()
    else:
        logger.info("Environnement local détecté. Utilisation du fichier GOOGLE_APPLICATION_CREDENTIALS.")
        cred_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
        if not cred_path:
            raise ValueError("En local, la variable d'environnement GOOGLE_APPLICATION_CREDENTIALS doit être définie.")
        cred = credentials.Certificate(cred_path)

    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)
    
    db = firestore.client()
    logger.info("Client Firestore initialisé avec succès.")

except Exception as e:
    logger.critical(f"Échec critique de l'initialisation de Firestore: {e}", exc_info=True)

def get_firestore_client():
    if db is None:
        logger.error("Le client Firestore n'est pas disponible car l'initialisation a échoué.")
    return db