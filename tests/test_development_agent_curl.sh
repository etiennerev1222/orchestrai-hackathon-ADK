#!/bin/bash

AGENT_URL="https://development-agent-o3o3chxieq-ew.a.run.app"

echo "➡ Envoi de la requête pour générer le code..."
ID_TOKEN=$(gcloud auth print-identity-token)
curl -s -X POST -H "Authorization: Bearer ${ID_TOKEN}" \
    -H "Content-Type: application/json" \
    -d @tests/dev_agent_request_payload.json \
    "${AGENT_URL}/" | tee response_generate.json

echo -e "\n✅ Réponse de génération capturée dans response_generate.json"

# Attendre quelques secondes pour laisser l'agent traiter
sleep 5

echo "➡ Envoi de la requête pour exécuter le code..."
ID_TOKEN=$(gcloud auth print-identity-token)
curl -s -X POST -H "Authorization: Bearer ${ID_TOKEN}" \
    -H "Content-Type: application/json" \
    -d @tests/dev_agent_request_payload_1.json \
    "${AGENT_URL}/" | tee response_generate_1.json

echo -e "\n✅ Réponse d'exécution capturée dans response_execute.json"

echo -e "\n📄 Contenu des réponses :"
cat response_generate.json
echo -e "\n---"
cat response_execute.json
