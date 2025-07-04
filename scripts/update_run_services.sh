#!/bin/bash

# Paramètres
REGION="europe-west1"
VPC_CONNECTOR="my-vpc-connector"

# Liste des services Cloud Run à mettre à jour
SERVICES=(
  decomposition-agent
  development-agent
  evaluator
  gra-server
  reformulator
  research-agent
  testing-agent
  user-interaction-agent
  validator
)

# Boucle de mise à jour
for SERVICE in "${SERVICES[@]}"; do
  echo "🔧 Mise à jour du service: $SERVICE"
  gcloud run services update "$SERVICE" \
    --region="$REGION" \
    --platform=managed \
    --vpc-connector="$VPC_CONNECTOR" \
    --vpc-egress=all-traffic \
    --quiet
done

echo "✅ Mise à jour terminée."

