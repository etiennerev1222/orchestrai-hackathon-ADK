#!/bin/bash
set -e

# --- Configuration Globale ---
GCP_PROJECT_ID="orchestrai-hackathon"
GCP_REGION="europe-west1"
GCR_HOSTNAME="${GCP_REGION}-docker.pkg.dev"
IMAGE_REPO_NAME="orchestrai-images"
ROOT_DIR=$(pwd)
BUILD_DIR="$ROOT_DIR/docker_build"

# --- Définition des Services ---
AGENTS=(
    "decomposition_agent" "development_agent" "evaluator" "reformulator" 
    "research_agent" "testing_agent" "user_interaction_agent" "validator"
)
ALL_COMPONENTS=("gra_server" "${AGENTS[@]}")

# ==============================================================================
# FONCTION 1 : CONFIGURATION DES FICHIERS DE BUILD
# ==============================================================================
function configure() {
    echo "--- ÉTAPE 1: CONFIGURATION DES FICHIERS DE BUILD ---"

    # 1. Générer et nettoyer le requirements.txt
    echo "    -> Génération du fichier requirements.txt..."
    pip freeze > requirements.txt
    sed -i.bak 's|a2a-sdk @ file://.*|a2a-sdk|' requirements.txt
    rm requirements.txt.bak 2>/dev/null || true
    echo "    ✅ Fichier requirements.txt prêt."

    # 2. Préparer le dossier de build
    echo "    -> Préparation du dossier de build: $BUILD_DIR"
    rm -rf "$BUILD_DIR"
    mkdir -p "$BUILD_DIR"
    local DOCKER_COMPOSE_PATH="$BUILD_DIR/docker-compose.yml"
    echo "    -> Génération du fichier docker-compose.yml..."
    echo "services:" > "$DOCKER_COMPOSE_PATH"

    # 3. Générer les Dockerfiles et sections docker-compose
    echo "    -> Génération des Dockerfiles pour chaque service..."
    local port_counter=8101
    for COMPONENT in "${ALL_COMPONENTS[@]}"; do
        local COMPONENT_DIR="$BUILD_DIR/$COMPONENT"
        mkdir -p "$COMPONENT_DIR"
        cp "$ROOT_DIR/requirements.txt" "$COMPONENT_DIR/requirements.txt"
        
        if [ "$COMPONENT" == "gra_server" ]; then
            local PUBLIC_PORT=8000; local INTERNAL_PORT=8000
            local DOCKER_CMD='["python", "-m", "uvicorn", "src.services.gra.server:app", "--host", "0.0.0.0", "--port", "8000"]'
        else
            local PUBLIC_PORT=$port_counter; local INTERNAL_PORT=8080
            local DOCKER_CMD='["python", "-m", "uvicorn", "src.agents.'"$COMPONENT"'.server:app", "--host", "0.0.0.0", "--port", "8080"]'
            port_counter=$((port_counter + 1))
        fi
        
        cat <<EOF > "$COMPONENT_DIR/Dockerfile"
FROM python:3.11-slim
WORKDIR /app
COPY docker_build/${COMPONENT}/requirements.txt ./
RUN pip install -r requirements.txt
COPY src /app/src
ENV PYTHONPATH=/app
CMD ${DOCKER_CMD}
EOF
        cat <<EOF >> "$DOCKER_COMPOSE_PATH"
  ${COMPONENT}:
    build:
      context: ..
      dockerfile: ./docker_build/${COMPONENT}/Dockerfile
    image: ${GCR_HOSTNAME}/${GCP_PROJECT_ID}/${IMAGE_REPO_NAME}/${COMPONENT}:latest
    ports:
      - "${PUBLIC_PORT}:${INTERNAL_PORT}"
    environment:
      - GOOGLE_APPLICATION_CREDENTIALS=/app/credentials.json
      - GEMINI_API_KEY=\${GEMINI_API_KEY}
      - GRA_PUBLIC_URL=http://gra_server:8000
      - PUBLIC_URL=http://localhost:${PUBLIC_PORT}
      - INTERNAL_URL=http://${COMPONENT}:${INTERNAL_PORT}
    volumes:
      - ./credentials.json:/app/credentials.json:ro
EOF
        if [ "$COMPONENT" != "gra_server" ]; then
            echo "    depends_on: [gra_server]" >> "$DOCKER_COMPOSE_PATH"
        fi
    done

    echo "✅ ÉTAPE 1 TERMINÉE : Configuration générée."
}


# ==============================================================================
# FONCTION 2 : CONSTRUCTION DES IMAGES DOCKER
# ==============================================================================
function build_images() {
    echo ""
    echo "--- ÉTAPE 2: CONSTRUCTION DES IMAGES DOCKER ---"
    
    if [ ! -d "$BUILD_DIR" ]; then
        echo "Le dossier de build '$BUILD_DIR' n'existe pas. Lancez d'abord './deployment.sh configure'."
        exit 1
    fi
    
    cd "$BUILD_DIR"
    echo "    -> Lancement de 'docker compose build'..."
    docker compose build
    cd "$ROOT_DIR"
    
    echo "✅ ÉTAPE 2 TERMINÉE : Toutes les images ont été construites."
}

# ==============================================================================
# FONCTION 3 : PUSH DES IMAGES VERS LE REGISTRE GCP
# ==============================================================================
function push_images() {
    echo ""
    echo "--- ÉTAPE 3: PUSH DES IMAGES VERS ARTIFACT REGISTRY ---"
    
    echo "    -> Vérification de l'authentification gcloud..."
    # Petite vérification pour s'assurer que l'utilisateur est authentifié
    gcloud auth print-access-token > /dev/null || (echo "Erreur: Non authentifié sur gcloud. Lancez 'gcloud auth login' et 'gcloud auth configure-docker ${GCR_HOSTNAME}'." && exit 1)
    
    if [ ! -d "$BUILD_DIR" ]; then
        echo "Le dossier de build '$BUILD_DIR' n'existe pas. Lancez d'abord './deployment.sh configure'."
        exit 1
    fi

    cd "$BUILD_DIR"
    echo "    -> Lancement de 'docker compose push'..."
    docker compose push
    cd "$ROOT_DIR"

    echo "✅ ÉTAPE 3 TERMINÉE : Toutes les images ont été poussées vers ${GCR_HOSTNAME}."
}

# --- Logique principale du script ---
if [ -z "$1" ]; then
    echo "Usage: ./deployment.sh [commande]"
    echo ""
    echo "Commandes:"
    echo "  configure   Génère les fichiers de configuration."
    echo "  build       Construit les images Docker."
    echo "  push        Pousse les images vers GCP."
    echo "  deploy      Déploie les services sur GCP Cloud Run."
    echo "  all         Exécute configure, build, push, puis deploy."
    exit 1
fi

function deploy_gcp() {
    echo ""
    echo "--- ÉTAPE 4: DÉPLOIEMENT SUR GCP CLOUD RUN ---"

    # S'assurer que la clé API Gemini est définie
    if [ -z "$GEMINI_API_KEY" ]; then
        echo "Erreur : La variable d'environnement GEMINI_API_KEY n'est pas définie."
        echo "Veuillez l'exporter avant de lancer le déploiement, ex: export GEMINI_API_KEY='votre_cle'"
        exit 1
    fi

    # --- Déploiement du GRA en premier ---
    echo "    -> Déploiement du 'gra-server'..."
    gcloud run deploy gra-server \
      --image="${GCR_HOSTNAME}/${GCP_PROJECT_ID}/${IMAGE_REPO_NAME}/gra_server:latest" \
      --platform=managed \
      --region=${GCP_REGION} \
      --allow-unauthenticated \
      --port=8000 \
      --set-env-vars="GEMINI_API_KEY=${GEMINI_API_KEY}" \
      --project=${GCP_PROJECT_ID}
    
    # Récupérer l'URL du GRA une fois déployé
    local GRA_CLOUD_RUN_URL=$(gcloud run services describe gra-server --platform=managed --region=${GCP_REGION} --project=${GCP_PROJECT_ID} --format='value(status.url)')
    if [ -z "$GRA_CLOUD_RUN_URL" ]; then
        echo "Erreur: Impossible de récupérer l'URL du service GRA déployé."
        exit 1
    fi
    echo "    ✅ 'gra-server' déployé avec l'URL : ${GRA_CLOUD_RUN_URL}"

    # --- Déploiement des agents ---
    echo "    -> Déploiement des 8 agents..."
    for AGENT_NAME in "${AGENTS[@]}"; do
        local AGENT_SERVICE_NAME=${AGENT_NAME//_/-} # Remplace les underscores pour les noms de service Cloud Run
        echo "        -> Déploiement de '${AGENT_SERVICE_NAME}'..."

        # On déploie une première fois pour créer le service et l'URL
        gcloud run deploy ${AGENT_SERVICE_NAME} \
          --image="${GCR_HOSTNAME}/${GCP_PROJECT_ID}/${IMAGE_REPO_NAME}/${AGENT_NAME}:latest" \
          --platform=managed \
          --region=${GCP_REGION} \
          --allow-unauthenticated \
          --port=8080 \
          --set-env-vars="GEMINI_API_KEY=${GEMINI_API_KEY},GRA_PUBLIC_URL=${GRA_CLOUD_RUN_URL}" \
          --project=${GCP_PROJECT_ID}
        
        # On récupère l'URL publique de l'agent qui vient d'être créé
        local AGENT_PUBLIC_URL=$(gcloud run services describe ${AGENT_SERVICE_NAME} --platform=managed --region=${GCP_REGION} --project=${GCP_PROJECT_ID} --format='value(status.url)')
        if [ -z "$AGENT_PUBLIC_URL" ]; then
            echo "Erreur : Impossible de récupérer l'URL pour ${AGENT_SERVICE_NAME}."
            continue # Passe au suivant en cas d'erreur
        fi

        echo "        -> Mise à jour de '${AGENT_SERVICE_NAME}' avec ses URLs..."

        # On met à jour le service pour lui injecter sa propre URL publique et interne
        # Sur Cloud Run, les deux peuvent être identiques pour la communication interne authentifiée.
        gcloud run services update ${AGENT_SERVICE_NAME} \
            --region=${GCP_REGION} \
            --set-env-vars="GEMINI_API_KEY=${GEMINI_API_KEY},GRA_PUBLIC_URL=${GRA_CLOUD_RUN_URL},PUBLIC_URL=${AGENT_PUBLIC_URL},INTERNAL_URL=${AGENT_PUBLIC_URL}" \
            --project=${GCP_PROJECT_ID}

        echo "        ✅ '${AGENT_SERVICE_NAME}' déployé et configuré."
    done

    echo "✅ ÉTAPE 4 TERMINÉE : Tous les services ont été déployés sur Cloud Run."
    echo ""
    echo "----------------------------------------------------------------"
    echo "URL du Gestionnaire de Ressources et d'Agents (GRA) :"
    echo "${GRA_CLOUD_RUN_URL}"
    echo "----------------------------------------------------------------"
    echo "N'oubliez pas de mettre à jour votre front-end avec cette URL."
}
case "$1" in
    configure) configure ;;
    build) build_images ;;
    push) push_images ;;
    deploy) deploy_gcp ;;
    all)
        configure
        build_images
        push_images
        deploy_gcp
        ;;
    *)
        echo "Commande inconnue: $1"; exit 1 ;;
esac