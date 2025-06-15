#!/bin/bash
set -e

# --- Configuration Globale ---
GCP_PROJECT_ID="orchestrai-hackathon" # Remplacez par l'ID de votre projet GCP
GCP_REGION="europe-west1"            # Remplacez par votre région
CLUSTER_NAME="dev-orchestra-cluster" # Assurez-vous que c'est le nom de votre cluster GKE
GKE_ZONE="europe-west1-b"            # Assurez-vous que c'est la zone de votre cluster GKE
# Nom du connecteur VPC créé à l'étape précédente
CONNECTOR_NAME="my-vpc-connector"    # Assurez-vous que c'est le nom de votre connecteur VPC


# 1. Récupérer l'endpoint du cluster GKE
echo "--- Récupération de l'endpoint du cluster GKE ---"
GKE_ENDPOINT=$(gcloud container clusters describe "${CLUSTER_NAME}" \
    --zone "${GKE_ZONE}" \
    --format="value(endpoint)" \
    --project="${GCP_PROJECT_ID}")

if [ -z "$GKE_ENDPOINT" ]; then
    echo "Erreur: Impossible de récupérer l'endpoint GKE. Le cluster n'existe peut-être pas ou les permissions sont insuffisantes."
    exit 1
fi
echo "Endpoint GKE : ${GKE_ENDPOINT}"


# 2. Construction de l'image du service de test IAM (sans cache)
echo "--- Construction de l'image du service de test IAM ---"
docker build -t gcr.io/${GCP_PROJECT_ID}/k8s-iam-test-server:latest -f src/tests/Dockerfile . > build_iam_test_server.log 2>&1 

if [ $? -ne 0 ]; then
    echo "Erreur: La construction de l'image a échoué. Voir build_iam_test_server.log pour les détails."
    exit 1
fi
echo "Image construite avec succès : gcr.io/${GCP_PROJECT_ID}/k8s-iam-test-server:latest"


# 3. Poussée de l'image vers Artifact Registry
echo "--- Poussée de l'image vers Artifact Registry ---"
docker push gcr.io/${GCP_PROJECT_ID}/k8s-iam-test-server:latest > push_iam_test_server.log 2>&1

if [ $? -ne 0 ]; then
    echo "Erreur: La poussée de l'image a échoué. Voir push_iam_test_server.log pour les détails."
    exit 1
fi
echo "Image poussée avec succès."


# 4. Déploiement du service Cloud Run de test IAM
echo "--- Déploiement du service Cloud Run de test IAM ---" # <-- C'est cette ligne (52 dans mon script)
gcloud run deploy k8s-iam-test-server \
  --image="gcr.io/${GCP_PROJECT_ID}/k8s-iam-test-server:latest" \
  --platform=managed \
  --region="${GCP_REGION}" \
  --no-allow-unauthenticated \
  --port=8080 \
  --set-env-vars="GKE_CLUSTER_ENDPOINT=${GKE_ENDPOINT},KUBERNETES_NAMESPACE=default,GCP_PROJECT_ID=${GCP_PROJECT_ID},GCP_REGION=${GCP_REGION}" \
  --vpc-connector="${CONNECTOR_NAME}" \
  --project="${GCP_PROJECT_ID}" \
  > deploy_iam_test_server.log 2>&1

if [ $? -ne 0 ]; then
    echo "Erreur: Le déploiement du service Cloud Run a échoué. Voir deploy_iam_test_server.log pour les détails."
    exit 1
fi

echo "Service k8s-iam-test-server déployé avec succès."


# 5. Appel de l'endpoint de test IAM pour vérifier les permissions
echo "--- Appel de l'endpoint de test IAM ---"
TEST_SERVER_URL=$(gcloud run services describe k8s-iam-test-server --platform=managed --region="${GCP_REGION}" --project="${GCP_PROJECT_ID}" --format='value(status.url)')
if [ -z "$TEST_SERVER_URL" ]; then
    echo "Erreur: Impossible de récupérer l'URL du service de test."
    exit 1
fi
echo "URL du service de test : ${TEST_SERVER_URL}"


ID_TOKEN=$(gcloud auth print-identity-token)
if [ -z "$ID_TOKEN" ]; then
    echo "Erreur: Impossible d'obtenir le jeton d'identité pour l'appel curl."
    exit 1
fi

echo "Appel curl à ${TEST_SERVER_URL}/test-k8s-iam-httpx..."
HTTP_STATUS=$(curl -X GET "${TEST_SERVER_URL}/test-k8s-iam-httpx" \
     -H "Authorization: Bearer ${ID_TOKEN}" \
     -s -o curl_iam_test_response.json \
     -w "%{http_code}\n")

echo "Code de statut HTTP : ${HTTP_STATUS}"

if [ ${HTTP_STATUS} -ne 200 ]; then
    echo "Erreur: L'appel curl a retourné un statut HTTP non-200."
    echo "Voir curl_iam_test_response.json et les logs Cloud Run pour plus de détails."
fi

echo "Réponse de l'agent (JSON) enregistrée dans curl_iam_test_response.json."
cat curl_iam_test_response.json | jq . || echo "Le fichier curl_iam_test_response.json n'est pas du JSON valide."

echo ""
echo "******************************************************************"
echo "Les logs de construction et déploiement sont dans les fichiers *.log."
echo "La réponse de l'agent est dans curl_iam_test_response.json."
echo "Veuillez consulter les logs du service 'k8s-iam-test-server' sur Cloud Run."
echo "Si vous voyez une erreur 403 Forbidden, c'est un problème de permissions IAM."
echo "Si le code de statut HTTP est 200, alors les permissions sont OK."
echo "******************************************************************"