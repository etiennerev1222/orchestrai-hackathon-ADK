#!/bin/bash

# Chemin racine du projet
ROOT_DIR=$(pwd)

# Liste des agents à configurer
AGENTS=(
    "decomposition_agent"
    "development_agent"
    "evaluator"
    "reformulator"
    "research_agent"
    "testing_agent"
    "user_interaction_agent"
    "validator"
)

# Créer dossier principal build
BUILD_DIR="$ROOT_DIR/docker_build"
mkdir -p "$BUILD_DIR"

# Fichier docker-compose
DOCKER_COMPOSE="$BUILD_DIR/docker-compose.yml"

echo "version: '3.8'" > "$DOCKER_COMPOSE"
echo "services:" >> "$DOCKER_COMPOSE"

# Génération Dockerfile, requirements.txt et docker-compose entries
for AGENT in "${AGENTS[@]}"; do

    AGENT_DIR="$BUILD_DIR/$AGENT"
    mkdir -p "$AGENT_DIR"

    # Dockerfile générique pour l'agent
    cat <<EOF > "$AGENT_DIR/Dockerfile"
FROM python:3.11-slim
WORKDIR /app

COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY ./src ./src

ENV PYTHONPATH=/app

CMD ["uvicorn", "src.agents.$AGENT.server:app", "--host", "0.0.0.0", "--port", "8080"]
EOF

    # requirements.txt générique
    cat <<EOF > "$AGENT_DIR/requirements.txt"
fastapi
uvicorn[standard]
firebase-admin
google-generativeai
httpx
a2a-sdk
pydantic
EOF

    # Entrée docker-compose
    PORT=$((8100 + RANDOM % 100))  # ports entre 8100-8199
    cat <<EOF >> "$DOCKER_COMPOSE"
  $AGENT:
    build:
      context: ./$AGENT
    ports:
      - "$PORT:8080"
    environment:
      GOOGLE_APPLICATION_CREDENTIALS: /app/credentials.json
      GEMINI_API_KEY: your-gemini-api-key
      GRA_PUBLIC_URL: https://gra.example.com
EOF

done

# Script build_all.sh
cat <<EOF > "$BUILD_DIR/build_all.sh"
#!/bin/bash

cd \$(dirname "\$0")

AGENTS=(
$(printf "    '%s'\n" "${AGENTS[@]}")
)

for AGENT in "\\${AGENTS[@]}"; do
    echo "Building \$AGENT..."
    docker build -t orchestrai/\$AGENT:latest -f \$AGENT/Dockerfile ./\$AGENT
done
EOF
chmod +x "$BUILD_DIR/build_all.sh"

# Script de lancement rapide run_all.sh
cat <<EOF > "$BUILD_DIR/run_all.sh"
#!/bin/bash

docker-compose up
EOF
chmod +x "$BUILD_DIR/run_all.sh"

echo "✅ Structure Docker créée avec succès dans $BUILD_DIR"

