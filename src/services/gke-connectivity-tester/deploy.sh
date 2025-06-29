#!/bin/bash
set -e

# Configuration
PROJECT_ID="orchestrai-hackathon"
REGION="europe-west1"
VPC_CONNECTOR="my-vpc-connector"

# URLs internes de vos services GKE
DEV_AGENT_INTERNAL_URL="http://development-agent.default.svc.cluster.local:80"
ENV_MANAGER_INTERNAL_URL="http://environment-manager.default.svc.cluster.local:80"

# FIX: Supprimer les variables GKE_NETWORK et GKE_SUBNET car elles ne sont plus utilisées
# GKE_NETWORK="default"
# GKE_SUBNET="default"
cd src/services/gke-connectivity-tester
echo "🚀 Déploiement du service Cloud Run 'gke-connectivity-tester4'..."
gcloud run deploy gke-connectivity-tester3 \
  --source=. \
  --region=europe-west1 \
  --platform=managed \
  --vpc-connector=my-vpc-connector \
  --vpc-egress=all-traffic \
  --set-env-vars=DEV_AGENT_URL="http://development-agent.default.svc.cluster.local:80",ENV_MANAGER_URL="http://environment-manager.default.svc.cluster.local:80" \
  --allow-unauthenticated # Utile pour les tests, à retirer en prod

  cd ../../..