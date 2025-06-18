#!/bin/bash

# Fichier: tests/test_develeper_agent_curl.sh
# Description: Script pour tester directement l'agent de développement via une requête curl.

# --- Paramètres configurables ---
GCP_PROJECT_ID="orchestrai-hackathon" # Remplacez par l'ID de votre projet GCP
AGENT_URL="https://development-agent-434296769439.europe-west1.run.app/" # Assurez-vous que c'est VOTRE URL
# Note: TEST_ENVIRONMENT_ID et messageId sont maintenant gérés dans le fichier JSON directement.
# Si vous voulez un nouvel environnement ou messageId, mettez à jour le fichier tests/dev_agent_request_payload.json

# --- Nom du fichier payload JSON ---
PAYLOAD_FILE="tests/dev_agent_request_payload.json"
#PAYLOAD_FILE="tests/dev_agent_request_payload_1.json"
# --- Récupération du jeton d'identité ---
echo "--- Récupération du jeton d'identité Google Cloud ---"
ID_TOKEN=$(gcloud auth print-identity-token)
if [ -z "$ID_TOKEN" ]; then
    echo "Erreur: Impossible d'obtenir le jeton d'identité. Assurez-vous d'être authentifié avec gcloud."
    exit 1
fi
echo "Jeton d'identité obtenu."

# --- Envoi de la requête curl depuis le fichier JSON ---
echo "--- Envoi de la requête à l'agent de développement ---"
echo "URL de l'agent: ${AGENT_URL}"
echo "Payload fichier: ${PAYLOAD_FILE}"

# Vérifier si le fichier payload existe
if [ ! -f "$PAYLOAD_FILE" ]; then
    echo "Erreur: Fichier payload non trouvé à ${PAYLOAD_FILE}. Veuillez le créer."
    exit 1
fi

# Extraction de l'environment_id utilisé dans le payload pour information
ENV_ID=$(jq -r '.params.message.parts[0].text | fromjson | .environment_id' "$PAYLOAD_FILE")
echo "Environnement utilisé: ${ENV_ID}"

RESPONSE=$(curl -X POST "${AGENT_URL}" \
     -H "Authorization: Bearer ${ID_TOKEN}" \
     -H "Content-Type: application/json" \
     -d @"${PAYLOAD_FILE}" \
     -s) # L'option -d @filename lit le corps de la requête depuis le fichier

echo "Réponse de l'agent:"
echo "${RESPONSE}" | jq .