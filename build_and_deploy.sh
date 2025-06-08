#!/bin/bash

# ÉTAPE 1: Génération et correction du requirements.txt
echo "--- Génération et correction du requirements.txt ---"
# Assurez-vous que votre environnement (conda ou venv) est activé
pip freeze > requirements.txt
sed -i.bak 's|a2a-sdk @ file://.*|a2a-sdk|' requirements.txt
rm requirements.txt.bak 2>/dev/null || true # Supprime le backup, compatible Linux/macOS
echo "✅ requirements.txt prêt pour Docker."


# ÉTAPE 2: Génération de l'environnement Docker
echo "--- Génération de la configuration Docker ---"
GCP_PROJECT_ID="orchestrai-hackathon"
GCR_HOSTNAME="eu.gcr.io"
ROOT_DIR=$(pwd)
BUILD_DIR="$ROOT_DIR/docker_build"
# On sépare le GRA des autres agents pour une logique plus claire
AGENTS=(
    "decomposition_agent" "development_agent" "evaluator" "reformulator" 
    "research_agent" "testing_agent" "user_interaction_agent" "validator"
)
ALL_COMPONENTS=("gra_server" "${AGENTS[@]}")


rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"
DOCKER_COMPOSE="$BUILD_DIR/docker-compose.yml"
echo "services:" > "$DOCKER_COMPOSE"

# --- Création de la configuration pour chaque composant ---
port_counter=8101
for COMPONENT in "${ALL_COMPONENTS[@]}"; do
    COMPONENT_DIR="$BUILD_DIR/$COMPONENT"
    mkdir -p "$COMPONENT_DIR"
    cp "$ROOT_DIR/requirements.txt" "$COMPONENT_DIR/requirements.txt"
    
    # Logique de port et de commande
    if [ "$COMPONENT" == "gra_server" ]; then
        PUBLIC_PORT=8000
        AGENT_PORT="8000:8000"
        DOCKER_CMD='["python", "-m", "uvicorn", "src.services.gra.server:app", "--host", "0.0.0.0", "--port", "8000"]'
    else
        PUBLIC_PORT=$port_counter
        AGENT_PORT="${PUBLIC_PORT}:8080"
        DOCKER_CMD='["python", "-m", "uvicorn", "src.agents.'"$COMPONENT"'.server:app", "--host", "0.0.0.0", "--port", "8080"]'
        port_counter=$((port_counter + 1))
    fi
    
    # Création du Dockerfile
    cat <<EOF > "$COMPONENT_DIR/Dockerfile"
FROM python:3.11-slim
WORKDIR /app
COPY docker_build/${COMPONENT}/requirements.txt ./
RUN pip install -r requirements.txt
COPY ./src /app/src
ENV PYTHONPATH=/app
CMD ${DOCKER_CMD}
EOF

    cat <<EOF >> "$DOCKER_COMPOSE"
  ${COMPONENT}:
    # === CORRECTION CI-DESSOUS ===
    build:
      context: ..  # Le contexte est le dossier parent (racine du projet)
      dockerfile: ./docker_build/${COMPONENT}/Dockerfile # Chemin vers le Dockerfile depuis la racine
    image: orchestrai/${COMPONENT}:latest
    ports:
      - "${AGENT_PORT}"
    environment:
      - GOOGLE_APPLICATION_CREDENTIALS=/app/credentials.json
      - GEMINI_API_KEY=\${GEMINI_API_KEY}
      - GRA_PUBLIC_URL=http://gra_server:8000
      - PUBLIC_URL=http://localhost:${PUBLIC_PORT}
    volumes:
      - ./credentials.json:/app/credentials.json:ro
EOF

    if [ "$COMPONENT" != "gra_server" ]; then
        echo "    depends_on:" >> "$DOCKER_COMPOSE"
        echo "      - gra_server" >> "$DOCKER_COMPOSE"
    fi
done

# Génération des scripts d'aide...
echo "Génération des scripts d'aide..."
cat <<EOF > "$BUILD_DIR/build_all.sh"
#!/bin/bash
set -e; cd \$(dirname "\$0"); echo "--- Construction de toutes les images Docker ---"; docker compose build; echo "--- ✅ Toutes les images ont été construites avec succès ---"
EOF
chmod +x "$BUILD_DIR/build_all.sh"

cat <<EOF > "$BUILD_DIR/run_all.sh"
#!/bin/bash
cd \$(dirname "\$0"); echo "--- Lancement de tous les services avec Docker Compose ---"; docker compose up
EOF
chmod +x "$BUILD_DIR/run_all.sh"

cat <<EOF > "$BUILD_DIR/push_all.sh"
#!/bin/bash
set -e; cd \$(dirname "\$0"); echo "--- Tagging et Push des images vers ${GCR_HOSTNAME}/${GCP_PROJECT_ID} ---"
COMPONENTS=($(printf "'%s' " "${ALL_COMPONENTS[@]}"))
for COMPONENT in "\${COMPONENTS[@]}"; do
    IMAGE_NAME="orchestrai/\${COMPONENT}:latest"
    GCR_TAG="${GCR_HOSTNAME}/${GCP_PROJECT_ID}/\${IMAGE_NAME}"
    echo "Tagging \${IMAGE_NAME} -> \${GCR_TAG}"
    docker tag "\${IMAGE_NAME}" "\${GCR_TAG}"
    echo "Pushing \${GCR_TAG}"
    docker push "\${GCR_TAG}"
done
echo "--- ✅ Toutes les images ont été poussées vers GCR avec succès ---"
EOF
chmod +x "$BUILD_DIR/push_all.sh"

echo "✅ Environnement Docker généré avec succès dans $BUILD_DIR"
