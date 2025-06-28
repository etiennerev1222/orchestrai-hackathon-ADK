#!/bin/bash

AGENT_URL="http://localhost:8080" # Or your public GKE/Cloud Run URL

# Function to get a fresh ID token
get_id_token() {
    gcloud auth print-identity-token
}

echo "➡ Envoi de la requête pour générer le code..."
ID_TOKEN_GENERATE=$(get_id_token) # Get fresh token for first request
echo "ID Token pour la génération : ${ID_TOKEN_GENERATE}" # Debug output
curl -s -X POST -H "Authorization: Bearer ${ID_TOKEN_GENERATE}" \
    -H "Content-Type: application/json" \
    -d @tests/dev_agent_request_payload.json \
    "${AGENT_URL}/" | tee response_generate.json

echo -e "\n✅ Réponse de génération capturée dans response_generate.json"

sleep 5

echo "➡ Envoi de la requête pour exécuter le code..."
ID_TOKEN_EXECUTE=$(get_id_token) # <--- GET A FRESH TOKEN FOR THE SECOND REQUEST
echo "ID Token pour l'exécution : ${ID_TOKEN_EXECUTE}" # Debug output
echo "Exécution de la requête avec le token d'identité..."
curl -s -X POST -H "Authorization: Bearer ${ID_TOKEN_EXECUTE}" \
    -H "Content-Type: application/json" \
    -d @tests/dev_agent_request_payload_1.json \
    "${AGENT_URL}/" | tee response_generate_1.json

echo -e "\n✅ Réponse d'exécution capturée dans response_execute.json"

echo -e "\n📄 Contenu des réponses :"
cat response_generate.json
echo -e "\n---\n"
cat response_generate_1.json
