#!/bin/bash

# Paramètres (tu peux les ajuster si besoin)
REGION="europe-west1"
PROJECT="orchestrai-hackathon"
VPC_CONNECTOR_NAME="my-vpc-connector"
NETWORK="default"
IP_RANGE="192.168.99.0/28"

echo "🚀 Début du processus pour VPC connector: $VPC_CONNECTOR_NAME"

# Vérifier si un connecteur du même nom existe déjà
echo "🔍 Vérification de l'existence d'un connecteur existant..."
EXISTING=$(gcloud compute networks vpc-access connectors describe "$VPC_CONNECTOR_NAME" \
    --region="$REGION" \
    --project="$PROJECT" \
    --format="value(name)" 2>/dev/null)

if [[ "$EXISTING" == *"$VPC_CONNECTOR_NAME" ]]; then
    echo "⚠️ Un connecteur existe déjà, suppression en cours..."
    gcloud compute networks vpc-access connectors delete "$VPC_CONNECTOR_NAME" \
        --region="$REGION" \
        --quiet
    echo "✅ Connecteur précédent supprimé."
else
    echo "✅ Aucun connecteur existant avec ce nom."
fi

# Création du connecteur
echo "🚧 Création d'un nouveau connecteur avec IP range $IP_RANGE ..."
gcloud compute networks vpc-access connectors create "$VPC_CONNECTOR_NAME" \
    --region="$REGION" \
    --network="$NETWORK" \
    --range="$IP_RANGE" \
    --project="$PROJECT"

# Vérifier le statut
echo "⏳ Vérification du statut du connecteur..."
gcloud compute networks vpc-access connectors describe "$VPC_CONNECTOR_NAME" \
    --region="$REGION" \
    --project="$PROJECT" \
    --format="yaml"

echo "🎉 Script terminé."

