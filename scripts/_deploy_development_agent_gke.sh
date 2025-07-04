#!/bin/bash
set -e

PROJECT_ID=$1
if [ -z "$PROJECT_ID" ]; then
  echo "Usage: $0 <gcp-project-id>"
  exit 1
fi

echo "🧠 Déploiement de l'agent de développement sur le projet GCP: $PROJECT_ID"

GCP_REGION="${GCP_REGION:-europe-west1}"
KUBERNETES_NAMESPACE="${KUBERNETES_NAMESPACE:-default}"
GRA_PUBLIC_URL="${GRA_PUBLIC_URL:-}"

# Découverte du GRA via gcloud run
if [ -z "$GRA_PUBLIC_URL" ]; then
  echo "🔍 Tentative de découverte de l'URL du GRA via 'gcloud run'..."
  GRA_PUBLIC_URL=$(gcloud run services describe gra-server --platform=managed --region=${GCP_REGION} --project=${PROJECT_ID} --format='value(status.url)' 2>/dev/null)
  if [ -z "$GRA_PUBLIC_URL" ]; then
    echo "⛔ Impossible de découvrir l'URL du service Cloud Run 'gra-server'."
    exit 1
  else
    echo "🌐 GRA_PUBLIC_URL détecté automatiquement : $GRA_PUBLIC_URL"
  fi
fi

AGENT_NAME="DevelopmentAgentServer"
# ✨ LA CORRECTION DÉFINITIVE : Un tag unique pour chaque build
TIMESTAMP=$(date +%s)
IMAGE="gcr.io/${PROJECT_ID}/development-agent:${TIMESTAMP}"
TMP_SA_KEY="./tmp-gcp-sa-key.json"

echo "🔐 Récupération des credentials GCP..."
SERVICE_ACCOUNT_EMAIL="orchestrai-gra-firestore@${PROJECT_ID}.iam.gserviceaccount.com"
gcloud config set project "$PROJECT_ID"
gcloud iam service-accounts keys create "$TMP_SA_KEY" --iam-account="$SERVICE_ACCOUNT_EMAIL" --quiet

echo "🔐 Création du secret Kubernetes 'gcp-sa-key'..."
kubectl delete secret gcp-sa-key --ignore-not-found --namespace "$KUBERNETES_NAMESPACE"
kubectl create secret generic gcp-sa-key --from-file=sa-key.json="$TMP_SA_KEY" --namespace "$KUBERNETES_NAMESPACE"

echo "🐳 Build Docker image avec le tag unique : ${IMAGE}"
# On peut même enlever le --no-cache maintenant, car le tag change à chaque fois
docker build -t "$IMAGE" -f src/agents/development_agent/Dockerfile .
docker push "$IMAGE"

echo "🚀 Déploiement sur GKE..."
# On exporte la variable IMAGE complète pour la substitution
export PROJECT_ID GRA_PUBLIC_URL AGENT_NAME KUBERNETES_NAMESPACE IMAGE
envsubst < k8s/development-agent-deployment.yaml | kubectl apply -f -

rm -f "$TMP_SA_KEY"
echo "✅ Déploiement terminé. La nouvelle image est ${IMAGE}"
