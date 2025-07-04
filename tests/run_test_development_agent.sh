#!/bin/bash
set -e

NAMESPACE="default"
LABEL_SELECTOR="app=development-agent"
LOCAL_PORT=8080
REMOTE_PORT=8080
TMP_LOG="dev_agent_port_forward.log"
CONTEXT_ID="gplan-122f8758cfd7"
CONTEXT_ID="exec-gplan_858ac018ba19"
AGENT_URL="http://localhost:${LOCAL_PORT}"

echo "🔍 Recherche du pod du development-agent..."
POD_NAME=$(kubectl get pod -n $NAMESPACE -l $LABEL_SELECTOR -o jsonpath="{.items[0].metadata.name}")

if [ -z "$POD_NAME" ]; then
  echo "⛔ Aucun pod 'development-agent' trouvé avec le label '$LABEL_SELECTOR'."
  exit 1
fi

echo "✅ Pod trouvé : $POD_NAME"
echo "🔁 Démarrage du port-forward sur localhost:${LOCAL_PORT}..."
kubectl port-forward -n $NAMESPACE pod/$POD_NAME $LOCAL_PORT:$REMOTE_PORT > $TMP_LOG 2>&1 &
PF_PID=$!

for i in {1..10}; do
  if nc -z localhost $LOCAL_PORT; then
    echo "✅ Port $LOCAL_PORT disponible."
    break
  fi
  sleep 1
done

if ! nc -z localhost $LOCAL_PORT; then
  echo "❌ Port non disponible. Échec."
  kill $PF_PID
  exit 1
fi

get_id_token() {
    gcloud auth print-identity-token
}

# === Étape 1 : Envoi de la requête de génération ===
ACTION_TEXT=$(jq -n \
  --arg action "generate_code_and_write_file" \
  --arg file_path "/app/sum_util.py" \
  --arg objective "Create a Python function named 'sum_numbers' that takes two arguments and returns their sum." \
  --argjson local_instructions '["Ensure it handles both integers and floats.", "Add docstrings and type hints."]' \
  --argjson acceptance_criteria '["sum_numbers(2, 3) should return 5", "sum_numbers(2.5, 3.5) should return 6.0"]' \
  --arg environment_id "exec_${CONTEXT_ID}_env" \
  '{
    action: $action,
    file_path: $file_path,
    objective: $objective,
    local_instructions: $local_instructions,
    acceptance_criteria: $acceptance_criteria,
    environment_id: $environment_id
  }'
)

# Génère maintenant le payload final
PAYLOAD_1=$(jq -n \
  --arg context_id "$CONTEXT_ID" \
  --arg msg_id "msg-gen-$(date +%s)" \
  --arg text "$ACTION_TEXT" \
  '{
    jsonrpc: "2.0",
    method: "message/send",
    params: {
      message: {
        contextId: $context_id,
        messageId: $msg_id,
        role: "user",
        parts: [{ text: $text }]
      },
      skillId: "coding_python"
    },
    id: "1"
  }'
)


curl -s -X POST -H "Authorization: Bearer $(get_id_token)" \
     -H "Content-Type: application/json" \
     -d "$PAYLOAD_1" "$AGENT_URL" | tee response_generate.json

# === Pause pour laisser l'agent générer ===
echo "⏳ Attente de traitement..."
sleep 4

# === Étape 2 : récupération de l’historique ===
echo "📜 Requête d’historique du contexte $CONTEXT_ID..."

read -r -d '' PAYLOAD_HISTORY << EOF
{
  "jsonrpc": "2.0",
  "method": "context/history",
  "params": {
    "contextId": "$CONTEXT_ID"
  },
  "id": "history-1"
}
EOF

curl -s -X POST -H "Authorization: Bearer $(get_id_token)" \
     -H "Content-Type: application/json" \
     -d "$PAYLOAD_HISTORY" "$AGENT_URL" | tee context_history.json

# Nettoyage
echo "🧹 Fermeture du port-forward ($PF_PID)"
kill $PF_PID
rm -f $TMP_LOG

echo "🎉 Test terminé. Résultats dans :"
ls -1 *.json | sed 's/^/ - /'
