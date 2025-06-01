# src/shared/firebase_init.py
import firebase_admin
from firebase_admin import credentials, firestore
import logging
import os # Pour vérifier la variable d'environnement

logger = logging.getLogger(__name__)

_db_client = None
_firebase_initialized_internally = False

def get_firestore_client():
    global _db_client
    global _firebase_initialized_internally

    # On initialise qu'une seule fois via CE module.
    if _db_client is None:
        # Vérifier si GOOGLE_APPLICATION_CREDENTIALS est défini
        if not os.getenv('GOOGLE_APPLICATION_CREDENTIALS'):
            logger.critical("CRITICAL: La variable d'environnement GOOGLE_APPLICATION_CREDENTIALS n'est pas définie. L'initialisation de Firestore va échouer.")
            # Vous pourriez vouloir lever une exception ici ou retourner None pour que les appelants gèrent.
            # Pour l'instant, laissons l'initialisation échouer naturellement ci-dessous si les crédentiels ne sont pas trouvés.

        if not firebase_admin._apps: # S'il n'y a AUCUNE application Firebase initialisée
            try:
                logger.info("Firebase Admin: Aucune application initialisée. Tentative d'initialisation de l'application par défaut...")
                cred = credentials.ApplicationDefault()
                firebase_admin.initialize_app(cred)
                _firebase_initialized_internally = True
                logger.info("Firebase Admin: Application par défaut initialisée avec succès par firebase_init.py.")
            except Exception as e:
                logger.critical(f"CRITICAL: Échec de l'initialisation de l'application Firebase par défaut dans firebase_init.py. Erreur: {e}", exc_info=True)
                # Si l'initialisation échoue, _db_client restera None, et les tentatives d'utilisation échoueront.
                return None # Ou lever l'exception
        else: # Une application Firebase (probablement la par défaut) est déjà initialisée ailleurs.
            logger.info("Firebase Admin: Application déjà initialisée (possiblement par un autre module ou test). Utilisation de la configuration existante.")

        # Essayer d'obtenir le client Firestore dans tous les cas (si l'app existe ou vient d'être créée)
        try:
            _db_client = firestore.client()
            logger.info("Client Firestore obtenu avec succès.")
        except Exception as e:
            logger.critical(f"CRITICAL: Échec de l'obtention du client Firestore après l'initialisation de l'application Firebase. Erreur: {e}", exc_info=True)
            return None # Ou lever l'exception

    return _db_client

# Mettre 'db' à disposition pour l'importation.
# La fonction get_firestore_client() sera appelée lors de la première importation de 'db'.
db = get_firestore_client()