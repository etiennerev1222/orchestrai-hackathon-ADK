
#!/bin/bash
set -e

# Manual end-to-end test of the Environment Manager. By default it expects a
# Kubernetes deployment and uses ``kubectl`` to port-forward the service. Pass
# ``--local`` to run against a locally started instance using the Docker backend.
#
#    bash tests/run_test_environment_manager.sh [--local]


NAMESPACE="default"
LABEL_SELECTOR="app=environment-manager"
LOCAL_PORT=8080
REMOTE_PORT=8080
TMP_LOG="env_mgr_port_forward.log"
# Set to 1 when running locally with the Docker backend
LOCAL_MODE=0

if [[ "$1" == "--local" ]]; then
  LOCAL_MODE=1
fi
# Environment identifiers are now derived from a global plan id (gplan_xxx).
# The manager normalises IDs to the form "exec-<gplan_id>", so we provide only
# the gplan identifier here for clarity.
TEST_ENV_ID="gplan_$(date +%s)"
BASE_IMAGE="gcr.io/orchestrai-hackathon/python-devtools:1751122256"

if [ "$LOCAL_MODE" -eq 1 ]; then
  echo "🚀 Lancement de l'Environment Manager en local (backend Docker)..."
  ENV_MANAGER_BACKEND=docker PORT=$LOCAL_PORT \
    python -m src.services.environment_manager.server > $TMP_LOG 2>&1 &
  EM_PID=$!
  for i in {1..10}; do
    if nc -z localhost $LOCAL_PORT; then
      echo "✅ Service local démarré sur le port $LOCAL_PORT"
      break
    fi
    sleep 1
  done
  if ! nc -z localhost $LOCAL_PORT; then
    echo "❌ Impossible de démarrer le service local."
    kill $EM_PID
    exit 1
  fi
  get_id_token() { echo ""; }
else
  echo "🔍 Recherche du pod de l'environment manager..."
  POD_NAME=$(kubectl get pod -n $NAMESPACE -l $LABEL_SELECTOR -o jsonpath="{.items[0].metadata.name}")

  if [ -z "$POD_NAME" ]; then
    echo "⛔ Aucun pod 'environment-manager' trouvé avec le label '$LABEL_SELECTOR'." >&2
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

  get_id_token() { gcloud auth print-identity-token; }
fi

EM_URL="http://localhost:${LOCAL_PORT}"

upload_file_to_environment() {
  local ENV_ID="$1"
  local FILE_PATH="$2"
  local CONTENT="$3"
  local FILENAME
  FILENAME=$(basename "$FILE_PATH")

  echo "➡ Upload du fichier $FILENAME dans l'environnement $ENV_ID"

  jq -n \
    --arg environment_id "$ENV_ID" \
    --arg path "$FILE_PATH" \
    --arg content "$CONTENT" \
    '{environment_id: $environment_id, path: $path, content: $content}' > tmp_upload.json

  curl -s -X POST -H "Authorization: Bearer $(get_id_token)" \
       -H "Content-Type: application/json" \
       -d @tmp_upload.json \
       "${EM_URL}/upload_to_environment" | tee "upload_${FILENAME}.json"

  echo -e "\n✅ Upload terminé pour $FILENAME"
  rm -f tmp_upload.json
}

# 1. Créer un environnement
echo "➡ Création de l'environnement : $TEST_ENV_ID"
curl -s -X POST -H "Authorization: Bearer $(get_id_token)" \
     -H "Content-Type: application/json" \
     -d "{\"environment_id\": \"$TEST_ENV_ID\", \"base_image\": \"$BASE_IMAGE\"}" \
     "$EM_URL/create_environment" | tee create_env.json
sleep 1

# 2. Upload fichier texte
TEXT_PATH="/app/test.txt"
TEXT_CONTENT="Ceci est un test\nLigne 2"
upload_file_to_environment "$TEST_ENV_ID" "$TEXT_PATH" "$TEXT_CONTENT"

# 3. Lire fichier
echo "➡ Lecture du fichier $TEXT_PATH"
curl -s -X POST -H "Authorization: Bearer $(get_id_token)" \
     -H "Content-Type: application/json" \
     -d "{\"environment_id\": \"$TEST_ENV_ID\", \"path\": \"$TEXT_PATH\"}" \
     "$EM_URL/download_from_environment" | tee read_file.json
sleep 1

# 4. Exécution d'une commande simple
echo "➡ Exécution de 'ls -l /app'"
curl -s -X POST -H "Authorization: Bearer $(get_id_token)" \
     -H "Content-Type: application/json" \
     -d "{\"environment_id\": \"$TEST_ENV_ID\", \"command\": \"ls -l /app\"}" \
     "$EM_URL/exec_in_environment" | tee exec_ls.json
sleep 1

# 5. Upload et exécution de script Python
SCRIPT_PATH="/app/test_script.py"
SCRIPT_CONTENT=$(cat <<EOF
def run():
    print("✅ Script exécuté depuis le test!")

if __name__ == "__main__":
    run()
EOF
)
upload_file_to_environment "$TEST_ENV_ID" "$SCRIPT_PATH" "$SCRIPT_CONTENT"

echo "➡ Exécution du script Python"
curl -s -X POST -H "Authorization: Bearer $(get_id_token)" \
     -H "Content-Type: application/json" \
     -d "{\"environment_id\": \"$TEST_ENV_ID\", \"command\": \"python $SCRIPT_PATH\"}" \
     "$EM_URL/exec_in_environment" | tee exec_script.json
sleep 1

# 6. Listing des fichiers
echo "➡ Listing de /app"
curl -s -X POST -H "Authorization: Bearer $(get_id_token)" \
     -H "Content-Type: application/json" \
     -d "{\"environment_id\": \"$TEST_ENV_ID\", \"path\": \"/app\"}" \
     "$EM_URL/list_files_in_environment" | tee list_files.json
sleep 1

# Clean up environment before closing the port-forward
echo "➡ Suppression de l'environnement de test"
curl -s -X POST -H "Authorization: Bearer $(get_id_token)" \
     -H "Content-Type: application/json" \
     -d "{\"environment_id\": \"$TEST_ENV_ID\"}" \
     "$EM_URL/delete_environment" | tee delete_env.json
sleep 1

# Nettoyage
if [ "$LOCAL_MODE" -eq 1 ]; then
  echo "🧹 Arrêt du serveur local ($EM_PID)"
  kill $EM_PID
else
  echo "🧹 Fermeture du port-forward ($PF_PID)"
  kill $PF_PID
fi
rm -f $TMP_LOG

echo "🎉 Test terminé. Résultats dans :"
ls -1 *.json | sed 's/^/ - /'
