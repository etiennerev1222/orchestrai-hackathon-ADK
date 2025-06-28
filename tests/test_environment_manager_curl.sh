#!/bin/bash

# URL de l'Environment Manager.
# Utilisez http://localhost:8080 si vous faites un port-forward depuis votre PC.
# Sinon, utilisez l'URL publique de votre service Cloud Run ou LoadBalancer.
ENVIRONMENT_MANAGER_URL="http://localhost:8080"

# Un ID d'environnement unique pour ce test
TEST_ENV_ID="test-env-$(date +%s)"
TEST_FILE_PATH="/app/test_file.txt"
TEST_FILE_CONTENT="Ceci est un contenu de test pour le fichier.\nLigne deux."
TEST_CODE_FILE_PATH="/app/my_script.py"
# FIX: Use a heredoc for multi-line string content
read -r -d '' TEST_CODE_CONTENT << EOF
def hello_world():
    print("Hello from the environment!")

if __name__ == "__main__":
    hello_world()
EOF

echo "--- Démarrage du script de test de l'Environment Manager ---"
echo "URL de l'Environment Manager: ${ENVIRONMENT_MANAGER_URL}"
echo "ID de l'environnement de test: ${TEST_ENV_ID}"

# Fonction pour obtenir un jeton d'identité frais
get_id_token() {
    gcloud auth print-identity-token
}

# 1. Créer un environnement
echo -e "\n➡ 1. Création de l'environnement '${TEST_ENV_ID}'..."
ID_TOKEN=$(get_id_token)
curl -s -X POST -H "Authorization: Bearer ${ID_TOKEN}" \
    -H "Content-Type: application/json" \
    -d "{\"environment_id\": \"${TEST_ENV_ID}\", \"base_image\": \"gcr.io/orchestrai-hackathon/python-devtools:1751122256\"}" \
    "${ENVIRONMENT_MANAGER_URL}/create_environment" | tee create_env_response.json
echo -e "\n✅ Réponse de création d'environnement capturée dans create_env_response.json"
sleep 2

# 2. Uploader un fichier de test
echo -e "\n➡ 2. Upload du fichier '${TEST_FILE_PATH}'..."
ID_TOKEN=$(get_id_token)
curl -s -X POST -H "Authorization: Bearer ${ID_TOKEN}" \
    -H "Content-Type: application/json" \
    -d "{\"environment_id\": \"${TEST_ENV_ID}\", \"path\": \"${TEST_FILE_PATH}\", \"content\": \"${TEST_FILE_CONTENT}\"}" \
    "${ENVIRONMENT_MANAGER_URL}/upload_to_environment" | tee upload_file_response.json
echo -e "\n✅ Réponse d'upload de fichier capturée dans upload_file_response.json"
sleep 2

# 3. Lire le fichier uploadé
echo -e "\n➡ 3. Lecture du fichier '${TEST_FILE_PATH}'..."
ID_TOKEN=$(get_id_token)
curl -s -X POST -H "Authorization: Bearer ${ID_TOKEN}" \
    -H "Content-Type: application/json" \
    -d "{\"environment_id\": \"${TEST_ENV_ID}\", \"path\": \"${TEST_FILE_PATH}\"}" \
    "${ENVIRONMENT_MANAGER_URL}/download_from_environment" | tee download_file_response.json
echo -e "\n✅ Réponse de lecture de fichier capturée dans download_file_response.json"
sleep 2

# 4. Exécuter une commande (ls -l /app)
echo -e "\n➡ 4. Exécution de la commande 'ls -l /app'..."
ID_TOKEN=$(get_id_token)
curl -s -X POST -H "Authorization: Bearer ${ID_TOKEN}" \
    -H "Content-Type: application/json" \
    -d "{\"environment_id\": \"${TEST_ENV_ID}\", \"command\": \"ls -l /app\"}" \
    "${ENVIRONMENT_MANAGER_URL}/exec_in_environment" | tee exec_ls_response.json
echo -e "\n✅ Réponse d'exécution de commande capturée dans exec_ls_response.json"
sleep 2

# 5. Exécuter un script Python simple
echo -e "\n➡ 5. Upload du script Python '${TEST_CODE_FILE_PATH}'..."
ID_TOKEN=$(get_id_token)
curl -s -X POST -H "Authorization: Bearer ${ID_TOKEN}" \
    -H "Content-Type: application/json" \
    -d "$(jq -n --arg env_id "${TEST_ENV_ID}" --arg path "${TEST_CODE_FILE_PATH}" --arg content "${TEST_CODE_CONTENT}" \
         '{environment_id: $env_id, path: $path, content: $content}')" \
    "${ENVIRONMENT_MANAGER_URL}/upload_to_environment" | tee upload_code_response.json
echo -e "\n✅ Réponse d'upload de code capturée dans upload_code_response.json"
sleep 2

echo -e "\n➡ 6. Exécution du script Python '${TEST_CODE_FILE_PATH}'..."
ID_TOKEN=$(get_id_token)
curl -s -X POST -H "Authorization: Bearer ${ID_TOKEN}" \
    -H "Content-Type: application/json" \
    -d "{\"environment_id\": \"${TEST_ENV_ID}\", \"command\": \"python ${TEST_CODE_FILE_PATH}\"}" \
    "${ENVIRONMENT_MANAGER_URL}/exec_in_environment" | tee exec_python_response.json # FIX: Changed endpoint
echo -e "\n✅ Réponse d'exécution de script Python capturée dans exec_python_response.json"
sleep 2

# 7. Lister le contenu du répertoire /app
echo -e "\n➡ 7. Listage du répertoire '/app'..."
ID_TOKEN=$(get_id_token)
curl -s -X POST -H "Authorization: Bearer ${ID_TOKEN}" \
    -H "Content-Type: application/json" \
    -d "{\"environment_id\": \"${TEST_ENV_ID}\", \"path\": \"/app\"}" \
    "${ENVIRONMENT_MANAGER_URL}/list_files_in_environment" | tee list_dir_response.json # FIX: Changed endpoint
echo -e "\n✅ Réponse de listage de répertoire capturée dans list_dir_response.json"
sleep 2

# 8. Supprimer l'environnement
echo -e "\n➡ 8. Suppression de l'environnement '${TEST_ENV_ID}'..."
ID_TOKEN=$(get_id_token)
curl -s -X POST -H "Authorization: Bearer ${ID_TOKEN}" \
    -H "Content-Type: application/json" \
    -d "{\"environment_id\": \"${TEST_ENV_ID}\"}" \
    "${ENVIRONMENT_MANAGER_URL}/delete_environment" | tee delete_env_response.json
echo -e "\n✅ Réponse de suppression d'environnement capturée dans delete_env_response.json"
sleep 2

echo -e "\n--- Fin du script de test ---"
echo "Vérifiez les fichiers *.json créés pour les réponses détaillées."
