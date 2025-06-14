# Construire le nom complet de l'image
IMAGE_URI="${GCR_HOSTNAME}/${GCP_PROJECT_ID}/${IMAGE_REPO_NAME}/gra-server:latest"

echo "Tentative de démarrage du conteneur : ${IMAGE_URI}"

# Lancer le conteneur en mode interactif
docker run --rm -it \
  -p 8000:8000 \
  -e PORT=8000 \
  -e GEMINI_API_KEY="${GEMINI_API_KEY}" \
  -e GOOGLE_APPLICATION_CREDENTIALS="/app/credentials.json" \
  -v "$(pwd)/credentials.json":/app/credentials.json:ro \
  "${IMAGE_URI}"