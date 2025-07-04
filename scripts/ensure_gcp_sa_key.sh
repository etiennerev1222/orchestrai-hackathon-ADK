#!/bin/bash
set -e

# === Configuration ===
PROJECT_ID="$1"
SA_NAME="orchestrai-gra-firestore"
SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
KEY_FILE="gcp-sa-key.json"

if [ -z "$PROJECT_ID" ]; then
  echo "Usage: $0 <gcp-project-id>"
  exit 1
fi

echo "🔍 Vérification de l'existence de la clé locale : $KEY_FILE"
if [ -f "$KEY_FILE" ]; then
  echo "✅ Clé déjà présente localement."
else
  echo "⛔ Clé absente. Tentative de création..."
  gcloud iam service-accounts keys create "$KEY_FILE" \
    --iam-account="$SA_EMAIL" \
    --project="$PROJECT_ID"
  echo "✅ Clé générée et enregistrée dans $KEY_FILE"
fi
