#!/bin/bash
set -e

PROJECT_ID="$1"
TARGET="$2"  # dev, env, all
GCP_REGION="${GCP_REGION:-europe-west1}"
GCP_REGION_KUBE="europe-west1-b"
KUBERNETES_NAMESPACE="${KUBERNETES_NAMESPACE:-default}"
KEY_FILE="./gcp-sa-key.json"
TIMESTAMP=$(date +%s)

if [ -z "$PROJECT_ID" ] || [[ ! "$TARGET" =~ ^(dev|env|all)$ ]]; then
  echo "Usage: $0 <gcp-project-id> <dev|env|all>"
  exit 1
fi

# === Récupération GRA URL ===
echo "🌍 Recherche de l'URL GRA..."
GRA_PUBLIC_URL=$(gcloud run services describe gra-server \
  --platform=managed --region="$GCP_REGION" --project="$PROJECT_ID" \
  --format='value(status.url)' 2>/dev/null)
if [ -z "$GRA_PUBLIC_URL" ]; then
  echo "⛔ Impossible de découvrir le GRA."
  exit 1
fi
echo "✅ GRA_PUBLIC_URL=$GRA_PUBLIC_URL"

# === Vérifie présence clé JSON ===
if [ ! -f "$KEY_FILE" ]; then
  echo "⛔ Clé GCP absente. Exécute d'abord ./ensure_gcp_sa_key.sh $PROJECT_ID"
  exit 1
fi

# === Upload du secret (une fois pour tous les services) ===
echo "🔐 Chargement du secret Kubernetes..."
kubectl delete secret gcp-sa-key --ignore-not-found --namespace "$KUBERNETES_NAMESPACE"
kubectl create secret generic gcp-sa-key --from-file=sa-key.json="$KEY_FILE" --namespace "$KUBERNETES_NAMESPACE"

# === Fonction générique de déploiement ===
deploy_service() {
  local name="$1"
  local dockerfile_path="$2"
  local deployment_yaml="$3"
  local image="gcr.io/${PROJECT_ID}/${name}:${TIMESTAMP}"

  echo "🐳 Build image $image"
  docker build -t "$image" -f "$dockerfile_path" .
  docker push "$image"

  echo "🚀 Déploiement Kubernetes pour $name"
  export PROJECT_ID GRA_PUBLIC_URL AGENT_NAME="$name" KUBERNETES_NAMESPACE IMAGE="$image" GKE_CLUSTER_ENDPOINT=$GKE_CLUSTER_ENDPOINT DEVTOOLS_IMAGE_TAG=$DEV_ENV_BASE_IMAGE INTERNAL_URL="http://$name.default.svc.cluster.local:80"
  envsubst < "$deployment_yaml" | kubectl apply -f -
  echo "✅ $name déployé avec succès."
}

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

if [ -z "$GKE_CLUSTER_ENDPOINT" ]; then
  echo "⛔ GKE_CLUSTER_ENDPOINT introuvable."
  exit 1
fi
echo "✅ GKE_CLUSTER_ENDPOINT : ${GKE_CLUSTER_ENDPOINT}"
# === Déploiement selon cible ===


case "$TARGET" in
  dev)
    deploy_service "development-agent" "src/agents/development_agent/Dockerfile" "k8s/development-agent-deployment.yaml"
    ;;
  env)
    export DEV_ENV_BASE_IMAGE="gcr.io/orchestrai-hackathon/python-devtools:1751122256"
    deploy_service "environment-manager" "src/services/environment_manager/Dockerfile" "k8s/environment-manager-deployment.yaml"
    ;;
  all)
    export DEV_ENV_BASE_IMAGE="gcr.io/orchestrai-hackathon/python-devtools:1751122256"
    deploy_service "development-agent" "src/agents/development_agent/Dockerfile" "k8s/development-agent-deployment.yaml"
    deploy_service "environment-manager" "src/services/environment_manager/Dockerfile" "k8s/environment-manager-deployment.yaml"
    ;;
esac
echo "🌐 Déploiement de l'Ingress interne..."
kubectl apply -f k8s/internal-ingress.yaml
