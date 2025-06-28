#!/bin/bash
set -e

# 🛠️ Entrée minimale
PROJECT_ID=$1
if [ -z "$PROJECT_ID" ]; then
  echo "Usage: $0 <gcp-project-id>"
  exit 1
fi

echo "🧠 Déploiement de l'environnement manager sur le projet GCP: $PROJECT_ID"

# 🌍 Valeurs par défaut
GCP_REGION="${GCP_REGION:-europe-west1}"
KUBERNETES_NAMESPACE="${KUBERNETES_NAMESPACE:-default}"
GRA_PUBLIC_URL="${GRA_PUBLIC_URL:-}"

# ✨ Découverte du GRA via gcloud run
if [ -z "$GRA_PUBLIC_URL" ]; then
  echo "🔍 Tentative de découverte de l'URL du GRA via 'gcloud run'..."
  GRA_PUBLIC_URL=$(gcloud run services describe gra-server --platform=managed --region=${GCP_REGION} --project=${PROJECT_ID} --format='value(status.url)' 2>/dev/null)
  
  if [ -z "$GRA_PUBLIC_URL" ]; then
    echo "⛔ Impossible de découvrir l'URL du service Cloud Run 'gra-server' dans la région ${GCP_REGION}."
    exit 1
  else
    echo "🌐 GRA_PUBLIC_URL détecté automatiquement : $GRA_PUBLIC_URL"
  fi
fi

# ✨ Logique de découverte automatique des informations du cluster GKE
echo "🔍 Découverte du cluster GKE..."
CLUSTER_INFO=$(gcloud container clusters list --project "$PROJECT_ID" --filter="location~^${GCP_REGION}" --format="value(name,location)" --limit=1)
CLUSTER_NAME=$(echo "$CLUSTER_INFO" | cut -f1)
CLUSTER_LOCATION=$(echo "$CLUSTER_INFO" | cut -f2)

if [ -z "$CLUSTER_NAME" ]; then
    echo "⛔ Aucun cluster GKE trouvé dans la région ${GCP_REGION}."
    exit 1
fi
echo "✅ Cluster trouvé: $CLUSTER_NAME à l'emplacement $CLUSTER_LOCATION"

if [[ $(echo "$CLUSTER_LOCATION" | awk -F'-' '{print NF-1}') == 2 ]]; then
    LOCATION_FLAG="--zone"
else
    LOCATION_FLAG="--region"
fi

export GKE_CLUSTER_ENDPOINT=$(gcloud container clusters describe "$CLUSTER_NAME" --project "$PROJECT_ID" "$LOCATION_FLAG" "$CLUSTER_LOCATION" --format="value(endpoint)")
export GKE_SSL_CA_CERT=$(gcloud container clusters describe "$CLUSTER_NAME" --project "$PROJECT_ID" "$LOCATION_FLAG" "$CLUSTER_LOCATION" --format="value(masterAuth.clusterCaCertificate)")
echo "✅ Endpoint du cluster: ${GKE_CLUSTER_ENDPOINT}"

# ✨ Utilisation d'un tag unique pour l'image
TIMESTAMP=$(date +%s)
AGENT_NAME="EnvironmentManagerGKEv2"
IMAGE="gcr.io/${PROJECT_ID}/environment-manager:${TIMESTAMP}"
echo "🖼️ Image Docker: ${IMAGE}"
TMP_SA_KEY="./tmp-gcp-sa-key.json"

echo "🔐 Récupération des credentials GCP..."
SERVICE_ACCOUNT_EMAIL="orchestrai-gra-firestore@${PROJECT_ID}.iam.gserviceaccount.com"
gcloud config set project "$PROJECT_ID"
gcloud iam service-accounts keys create "$TMP_SA_KEY" --iam-account="$SERVICE_ACCOUNT_EMAIL" --quiet

echo "🔐 Création du secret Kubernetes 'gcp-sa-key'..."
kubectl delete secret gcp-sa-key --ignore-not-found --namespace "$KUBERNETES_NAMESPACE"
kubectl create secret generic gcp-sa-key --from-file=sa-key.json="$TMP_SA_KEY" --namespace "$KUBERNETES_NAMESPACE"

echo "🐳 Build Docker image avec le tag unique: ${IMAGE}"
# Assurez-vous que le chemin du Dockerfile est correct
docker build -t "$IMAGE" -f src/services/environment_manager/Dockerfile .
docker push "$IMAGE"

echo "🚀 Déploiement sur GKE..."
# ✅ CORRECTION : Ajout de la variable IMAGE à la liste d'exportation
export DEV_ENV_BASE_IMAGE=gcr.io/orchestrai-hackathon/python-devtools:1751122256
export PROJECT_ID GRA_PUBLIC_URL AGENT_NAME KUBERNETES_NAMESPACE GKE_CLUSTER_ENDPOINT GKE_SSL_CA_CERT IMAGE
envsubst < k8s/environment-manager-deployment.yaml | kubectl apply -f -

rm -f "$TMP_SA_KEY"
echo "✅ Déploiement terminé. Nouvelle image: ${IMAGE}"