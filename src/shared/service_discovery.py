import os
import httpx
import logging
from typing import List
from a2a.types import AgentCard, AgentCapabilities, AgentSkill
from src.shared.firebase_init import db # <-- ADD THIS IMPORT
import google.auth
from google.auth.transport.requests import Request
from google.oauth2 import id_token

logger = logging.getLogger(__name__)

async def register_self_with_gra(
    agent_name: str,
    public_url: str,
    internal_url: str,
    skills: List[str]
):
    gra_base_url = await get_gra_base_url()
    if not gra_base_url:
        logger.warning(f"[{agent_name}] GRA URL not found, cannot register.")
        return

    registration_payload = {
        "agent_name": agent_name,
        "public_url": public_url,
        "internal_url": internal_url,
        "skills": skills
    }
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(f"{gra_base_url}/register", json=registration_payload, timeout=5.0)
            response.raise_for_status()
            logger.info(f"[{agent_name}] Enregistré avec succès auprès du GRA.")
        except httpx.HTTPStatusError as e:
            logger.error(f"[{agent_name}] Échec de l'enregistrement auprès du GRA (HTTP Error): {e.response.status_code} - {e.response.text}", exc_info=True)
            raise
        except httpx.RequestError as e:
            logger.error(f"[{agent_name}] Échec de l'enregistrement auprès du GRA (Request Error): {e}", exc_info=True)
            raise
        except Exception as e:
            logger.error(f"[{agent_name}] Erreur inattendue lors de l'enregistrement auprès du GRA: {e}", exc_info=True)
            raise

async def get_gra_base_url() -> str | None:
    gra_url = os.environ.get("GRA_PUBLIC_URL")
    if gra_url:
        logger.info(f"URL du GRA trouvée via la variable d'environnement : {gra_url}")
        return gra_url
    
    logger.warning("GRA_PUBLIC_URL non définie dans les variables d'environnement. Tentative de récupération depuis Firestore.")
    try:
        doc_ref = db.collection("service_registry").document("gra-server")
        doc = await db.loop.run_in_executor(None, doc_ref.get) # Use loop.run_in_executor for sync Firestore call
        if doc.exists:
            gra_data = doc.to_dict()
            url = gra_data.get("public_url")
            if url:
                logger.info(f"URL du GRA récupérée depuis Firestore : {url}")
                return url
        logger.warning("URL du GRA introuvable dans Firestore.")
        return None
    except Exception as e:
        logger.error(f"Erreur lors de la récupération de l'URL du GRA depuis Firestore : {e}", exc_info=True)
        return None

async def get_environment_manager_url() -> str | None:
    env_manager_url = os.environ.get("ENV_MANAGER_URL")
    if env_manager_url:
        logger.info(f"URL du Environment Manager trouvée via la variable d'environnement : {env_manager_url}")
        return env_manager_url

    logger.warning("ENV_MANAGER_URL non définie dans les variables d'environnement. Tentative de récupération depuis Firestore.")
    try:
        # Ensure 'db' is imported from src.shared.firebase_init
        doc_ref = db.collection("service_registry").document("EnvironmentManagerGKEv2")
        doc = await db.loop.run_in_executor(None, doc_ref.get) # Use loop.run_in_executor for sync Firestore call
        if doc.exists:
            env_manager_data = doc.to_dict()
            url = env_manager_data.get("internal_url") or env_manager_data.get("public_url")
            if url:
                logger.info(f"URL du Environment Manager récupérée depuis Firestore : {url}")
                return url
        logger.warning("URL du Environment Manager introuvable dans Firestore.")
        return None
    except Exception as e:
        logger.error(f"Erreur lors de la récupération de l'URL du Environment Manager depuis Firestore : {e}", exc_info=True)
        return None

async def get_agent_id_token() -> str | None:
    """
    Obtient un jeton d'identité Google pour le compte de service du pod actuel.
    Ceci est utilisé pour l'authentification auprès d'autres services Google Cloud.
    """
    try:
        # Utilise google.auth.default() pour obtenir les identifiants de l'environnement
        # Cela fonctionne avec les clés de compte de service montées ou Workload Identity
        credentials, project = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        
        if credentials and credentials.token:
            logger.debug("Using existing credentials token.")
            return credentials.token
        elif credentials and credentials.valid:
            # Si le jeton n'est pas directement disponible mais les identifiants sont valides,
            # essayez de le rafraîchir ou de le demander.
            # Pour les jetons d'identité, il faut souvent une audience spécifique.
            # Pour l'authentification de service à service, un jeton d'accès est souvent suffisant
            # ou un jeton d'identité peut être généré avec une audience spécifique si nécessaire.
            # Pour simplifier, nous allons tenter de rafraîchir ou d'obtenir un jeton d'accès.
            # Si un jeton d'identité est spécifiquement requis par le service cible,
            # vous devrez utiliser google.auth.service_account.IDTokenCredentials
            # ou une méthode spécifique pour générer un jeton d'identité pour une audience donnée.
            
            # Pour l'instant, nous allons nous appuyer sur credentials.token si déjà présent
            # ou essayer de rafraîchir pour obtenir un jeton d'accès standard si nécessaire.
            # Si le service cible attend un ID Token, cette partie pourrait devoir être plus sophistiquée.
            
            # Pour obtenir un ID Token pour une audience spécifique (par exemple, l'URL de l'Environment Manager)
            # cela nécessiterait une logique plus avancée, souvent via Workload Identity ou un appel à l'API STS.
            # Pour un pod GKE, si Workload Identity est configuré, les identifiants par défaut
            # peuvent souvent être échangés contre un ID Token pour une audience spécifique.
            
            # Pour l'authentification de service à service entre pods GKE (si le service cible ne valide pas
            # les ID Tokens mais des Access Tokens standard), credentials.token suffirait après refresh.
            
            # Pour l'authentification avec Cloud Run ou d'autres services Google qui valident les ID Tokens:
            # Il faudrait une audience spécifique.
            # Pour l'instant, nous allons retourner le token d'accès si disponible.
            
            # Si on a besoin d'un ID Token avec une audience spécifique, on ferait:
            # from google.auth.transport.requests import AuthorizedSession
            # auth_req = Request()
            # session = AuthorizedSession(credentials)
            # id_token = session.fetch_id_token("AUDIENCE_URL_OF_TARGET_SERVICE")
            # return id_token

            # Pour le contexte actuel, nous allons simplement retourner le token d'accès si disponible
            # ou lever une erreur si aucun token n'est obtenu.
            
            credentials.refresh(Request())
            if credentials.token:
                logger.debug("Credentials refreshed, returning access token.")
                return credentials.token
            else:
                logger.error("Credentials are valid but no token could be obtained after refresh.")
                return None
        else:
            logger.warning("No valid Google Cloud credentials found. Cannot obtain agent ID token.")
            return None
    except Exception as e:
        logger.error(f"Error obtaining agent ID token: {e}", exc_info=True)
        return None

