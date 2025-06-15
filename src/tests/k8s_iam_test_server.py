# src/tests/k8s_iam_test_server.py
import os
import logging
import asyncio
import uvicorn
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from kubernetes import client, config
import httpx # NOUVEAU
import google.auth # NOUVEAU
from google.auth.transport.requests import Request # NOUVEAU

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# --- Configuration du client Kubernetes (pour le test K8s client) ---
# Laissons cette section telle quelle, elle est utilisée par la route /test-k8s-iam
api_client = None
v1_api = None
try:
    gke_cluster_endpoint = os.environ.get("GKE_CLUSTER_ENDPOINT")
    if gke_cluster_endpoint:
        logger.info(f"Test Server: GKE_CLUSTER_ENDPOINT found: {gke_cluster_endpoint}. Configuring Kubernetes client.")
        try:
            configuration = client.Configuration()
            configuration.host = f"https://{gke_cluster_endpoint}"
            
            configuration.verify_ssl = False # <--- N'OUBLIEZ PAS DE LAISSER CELA POUR LE TEST
            logger.warning("Test Server: SSL verification is DISABLED. DO NOT USE IN PRODUCTION.")
            
            client.Configuration.set_default(configuration)
            api_client = client.ApiClient()
            logger.info("Test Server: Kubernetes client configured with GKE_CLUSTER_ENDPOINT and ADC (implicit) with SSL verification bypassed.")
        except Exception as e:
            logger.error(f"Test Server: Failed to configure Kubernetes client with GKE_CLUSTER_ENDPOINT: {e}", exc_info=True)
    else:
        logger.error("Test Server: GKE_CLUSTER_ENDPOINT not found. Kubernetes client will likely fail or try localhost.")
except Exception as e:
    logger.error(f"Test Server: Error during global K8s client setup: {e}", exc_info=True)

if api_client:
    v1_api = client.CoreV1Api(api_client)
    logger.info("Test Server: CoreV1Api client initialized.")
else:
    logger.error("Test Server: CoreV1Api client could not be initialized due to config failure.")

# --- Endpoint de test IAM (original) ---
async def test_k8s_iam(request):
    logger.info("Test Server: Received request for /test-k8s-iam (Kubernetes client).")
    if not v1_api:
        logger.error("Test Server: Kubernetes CoreV1Api not initialized. Cannot perform API call.")
        return JSONResponse({"status": "error", "message": "Kubernetes API client not initialized."}, status_code=500)

    try:
        logger.info(f"Test Server: Attempting to list pods in namespace '{os.environ.get('KUBERNETES_NAMESPACE', 'default')}' (via K8s client)...")
        list_pods_response = await asyncio.to_thread(
            v1_api.list_namespaced_pod,
            namespace=os.environ.get('KUBERNETES_NAMESPACE', 'default'),
            limit=1
        )
        pod_names = [pod.metadata.name for pod in list_pods_response.items]
        logger.info(f"Test Server: Successfully listed pods (K8s client). Found {len(pod_names)} pod(s): {pod_names[:5]}...")
        return JSONResponse({"status": "success", "message": "Successfully listed pods on GKE via Kubernetes client.", "pods_found": len(pod_names)})
    except client.ApiException as e:
        logger.error(f"Test Server: Kubernetes API Error (Status {e.status}) for /test-k8s-iam (K8s client): Reason={e.reason}, Body={e.body}", exc_info=True)
        return JSONResponse({"status": "error", "message": f"Kubernetes API Error (K8s client): {e.reason} (Status {e.status}). Details: {e.body}"}, status_code=e.status)
    except Exception as e:
        logger.error(f"Test Server: Unexpected error for /test-k8s-iam (K8s client): {e}", exc_info=True)
        return JSONResponse({"status": "error", "message": f"Internal server error (K8s client): {str(e)}"}, status_code=500)

# --- NOUVEAU ENDPOINT DE TEST IAM AVEC HTTPX ---
async def test_k8s_iam_httpx(request):
    logger.info("Test Server: Received request for /test-k8s-iam-httpx (using httpx).")
    try:
        gke_cluster_endpoint = os.environ.get("GKE_CLUSTER_ENDPOINT")
        if not gke_cluster_endpoint:
            logger.error("Test Server: GKE_CLUSTER_ENDPOINT not set for httpx test.")
            return JSONResponse({"status": "error", "message": "GKE_CLUSTER_ENDPOINT not set."}, status_code=500)
        
        # Obtenir les Application Default Credentials (ADC)
        credentials, project_id = google.auth.default()
        if not credentials:
            logger.error("Test Server: Failed to get Application Default Credentials for httpx test.")
            return JSONResponse({"status": "error", "message": "Failed to get Application Default Credentials."}, status_code=500)
        
        # Rafraîchir le jeton d'accès si nécessaire (synchrone ici, mais bon pour un jeton à jour)
        await asyncio.to_thread(credentials.refresh, Request())
        
        # Construire l'en-tête d'autorisation
        headers = {"Authorization": f"Bearer {credentials.token}"}
        
        # URL de l'API Kubernetes (par exemple, pour lister les pods)
        api_url = f"https://{gke_cluster_endpoint}/api/v1/namespaces/{os.environ.get('KUBERNETES_NAMESPACE', 'default')}/pods?limit=1"

        logger.info(f"Test Server: Attempting httpx GET call to K8s API at {api_url} with token (first 10 chars): {credentials.token[:10]}...")

        async with httpx.AsyncClient(verify=False, headers=headers, timeout=10.0) as client_httpx:
            response = await client_httpx.get(api_url)
            response.raise_for_status() # Lèvera une exception pour les statuts 4xx/5xx
            
            logger.info(f"Test Server: httpx call successful. Status: {response.status_code}. Response body preview: {response.text[:200]}")
            return JSONResponse({"status": "success", "message": "httpx call to K8s API successful.", "status_code": response.status_code, "response_body_preview": response.text[:200]})
    except httpx.HTTPStatusError as e:
        logger.error(f"Test Server: httpx HTTP Error for /test-k8s-iam-httpx: Status={e.response.status_code}, Body={e.response.text}", exc_info=True)
        return JSONResponse({"status": "error", "message": f"httpx HTTP Error: Status={e.response.status_code}, Body={e.response.text[:200]}"}, status_code=e.response.status_code)
    except Exception as e:
        logger.error(f"Test Server: Unexpected error for /test-k8s-iam-httpx: {e}", exc_info=True)
        return JSONResponse({"status": "error", "message": f"Internal server error (httpx test): {str(e)}"}, status_code=500)


# --- Initialisation de l'application Starlette ---
routes = [
    Route("/test-k8s-iam", endpoint=test_k8s_iam, methods=["GET"]), # Garde la route originale
    Route("/test-k8s-iam-httpx", endpoint=test_k8s_iam_httpx, methods=["GET"]), # NOUVEAU
]

app = Starlette(routes=routes)

# --- Démarrage Uvicorn ---
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")