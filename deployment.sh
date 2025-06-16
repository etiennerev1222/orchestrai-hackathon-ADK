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
    echo "--- ÉTAPE 1: CONFIGURATION DES FICHIERS DE BUILD (Python 3.11) ---"

    local REQUIREMENTS_FILE="requirements_py311.txt" # Assurez-vous que ce fichier existe
    if [ ! -f "$REQUIREMENTS_FILE" ]; then
        echo "Erreur : Le fichier de dépendances '$REQUIREMENTS_FILE' n'existe pas."
        exit 1
    fi
    echo "    ✅ Utilisation de '$REQUIREMENTS_FILE' comme base."

    rm -rf "$BUILD_DIR" && mkdir -p "$BUILD_DIR"
    local DOCKER_COMPOSE_PATH="$BUILD_DIR/docker-compose.yml"
    echo "services:" > "$DOCKER_COMPOSE_PATH"

    echo "    -> Génération des Dockerfiles pour chaque service..."
    local port_counter=8101
    for COMPONENT in "${ALL_COMPONENTS[@]}"; do
        local COMPONENT_DIR="$BUILD_DIR/$COMPONENT"
        mkdir -p "$COMPONENT_DIR"
        cp "$ROOT_DIR/$REQUIREMENTS_FILE" "$COMPONENT_DIR/requirements.txt"
        
        if [ "$COMPONENT" == "gra_server" ]; then
            local PUBLIC_PORT=8000; local INTERNAL_PORT=8000
            local DOCKER_CMD='["python", "src/services/gra/server.py"]'
        else
            local PUBLIC_PORT=$port_counter; local INTERNAL_PORT=8080
            local DOCKER_CMD='["python", "-m", "src.agents.'"$COMPONENT"'.server"]'
            port_counter=$((port_counter + 1))
        fi
        
        cat <<EOF > "$COMPONENT_DIR/Dockerfile"
FROM python:3.11-slim
WORKDIR /app
COPY docker_build/${COMPONENT}/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
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
      - GCP_PROJECT_ID=${GCP_PROJECT_ID}
      - GCP_REGION=${GCP_REGION}
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

    echo "✅ ÉTAPE 1 TERMINÉE : Configuration générée pour Python 3.11 et Vertex AI."
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

# ==============================================================================
# FONCTION UTILITAIRE : Récupérer l'endpoint GKE
# ==============================================================================
function get_gke_cluster_endpoint() {
    local cluster_name="dev-orchestra-cluster"
    local gke_zone="europe-west1-b"

    echo "    -> Récupération de l'endpoint du cluster GKE '${cluster_name}'..."
    GKE_ENDPOINT=$(gcloud container clusters describe "${cluster_name}" \
        --zone "${gke_zone}" \
        --format="value(endpoint)" \
        --project="${GCP_PROJECT_ID}" 2>/dev/null)
    
    if [ -z "$GKE_ENDPOINT" ]; then
        echo "Erreur: Impossible de récupérer l'endpoint du cluster GKE. Le cluster n'existe peut-être pas ou n'est pas prêt, ou les permissions sont insuffisantes."
        exit 1
    fi
    echo "    ✅ Endpoint GKE : ${GKE_ENDPOINT}"
}

# ==============================================================================
# FONCTION 4 : DÉPLOIEMENT SUR GCP CLOUD RUN (Mode Vertex AI)
# ==============================================================================
function deploy_gcp() {
    echo ""
    echo "--- ÉTAPE 4: DÉPLOIEMENT SUR GCP CLOUD RUN (Mode Vertex AI) ---"

    local BASE_ENV_VARS="GCP_PROJECT_ID=${GCP_PROJECT_ID},GCP_REGION=${GCP_REGION}"
    
    get_gke_cluster_endpoint
    local COMMON_AGENT_ENV_VARS="${BASE_ENV_VARS},GKE_CLUSTER_ENDPOINT=${GKE_ENDPOINT}"
    
    local CONNECTOR_NAME="my-vpc-connector" # Assurez-vous que ce nom correspond à votre connecteur VPC

    # --- Déploiement du GRA en premier ---
    echo "    -> Déploiement du 'gra-server'..."
    gcloud run deploy gra-server \
      --image="${GCR_HOSTNAME}/${GCP_PROJECT_ID}/${IMAGE_REPO_NAME}/gra_server:latest" \
      --platform=managed \
      --region=${GCP_REGION} \
      --allow-unauthenticated \
      --port=8000 \
      --set-env-vars="${COMMON_AGENT_ENV_VARS}" \
      --project=${GCP_PROJECT_ID} \
      --vpc-connector="${CONNECTOR_NAME}" \
    
    local GRA_CLOUD_RUN_URL=$(gcloud run services describe gra-server --platform=managed --region=${GCP_REGION} --project=${GCP_PROJECT_ID} --format='value(status.url)')
    if [ -z "$GRA_CLOUD_RUN_URL" ]; then
        echo "Erreur: Impossible de récupérer l'URL du service GRA déployé."
        exit 1
    fi
    echo "    ✅ 'gra-server' déployé avec l'URL : ${GRA_CLOUD_RUN_URL}"
    
    gcloud run services update gra-server \
        --region=${GCP_REGION} \
        --set-env-vars="${COMMON_AGENT_ENV_VARS},GRA_PUBLIC_URL=${GRA_CLOUD_RUN_URL}" \
        --project=${GCP_PROJECT_ID}
    echo "    -> Mise à jour de 'gra-server' avec ses URLs...Terminée."
            
    # --- Déploiement des agents ---
    echo "    -> Déploiement des 8 agents..."
    for AGENT_NAME in "${AGENTS[@]}"; do
        local AGENT_SERVICE_NAME=${AGENT_NAME//_/-}
        echo "        -> Déploiement de '${AGENT_SERVICE_NAME}'..."

        gcloud run deploy ${AGENT_SERVICE_NAME} \
          --image="${GCR_HOSTNAME}/${GCP_PROJECT_ID}/${IMAGE_REPO_NAME}/${AGENT_NAME}:latest" \
          --platform=managed \
          --region=${GCP_REGION} \
          --no-allow-unauthenticated \
          --port=8080 \
          --set-env-vars="${COMMON_AGENT_ENV_VARS},GRA_PUBLIC_URL=${GRA_CLOUD_RUN_URL}" \
          --vpc-connector="${CONNECTOR_NAME}" \
          --project=${GCP_PROJECT_ID}
        
        local AGENT_PUBLIC_URL=$(gcloud run services describe ${AGENT_SERVICE_NAME} --platform=managed --region=${GCP_REGION} --project=${GCP_PROJECT_ID} --format='value(status.url)')
        if [ -z "$AGENT_PUBLIC_URL" ]; then
            echo "Erreur : Impossible de récupérer l'URL pour ${AGENT_SERVICE_NAME}."
            continue
        fi

        echo "        -> Mise à jour de '${AGENT_SERVICE_NAME}' avec ses URLs..."
        
        gcloud run services update ${AGENT_SERVICE_NAME} \
            --region=${GCP_REGION} \
            --set-env-vars="${COMMON_AGENT_ENV_VARS},GRA_PUBLIC_URL=${GRA_CLOUD_RUN_URL},PUBLIC_URL=${AGENT_PUBLIC_URL},INTERNAL_URL=${AGENT_PUBLIC_URL}" \
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

# ==============================================================================
# FONCTION : DÉPLOIEMENT D'UN SEUL AGENT
# ==============================================================================
function deploy_single_agent() {
    local AGENT_NAME_TO_DEPLOY=$1

    if [ -z "$AGENT_NAME_TO_DEPLOY" ]; then
        echo "Erreur : Vous devez spécifier le nom de l'agent à déployer."
        echo "Usage: ./deployment.sh deploy-one <nom_de_l_agent>"
        echo "Exemple: ./deployment.sh deploy-one user_interaction_agent"
        exit 1
    fi

    if ! [[ " ${AGENTS[@]} " =~ " ${AGENT_NAME_TO_DEPLOY} " ]]; then
        echo "Erreur : Le nom d'agent '${AGENT_NAME_TO_DEPLOY}' n'est pas dans la liste des agents valides."
        exit 1
    fi

    echo ""
    echo "--- DÉPLOIEMENT DE L'AGENT UNIQUE : ${AGENT_NAME_TO_DEPLOY} ---"

    get_gke_cluster_endpoint
    local BASE_ENV_VARS="GCP_PROJECT_ID=${GCP_PROJECT_ID},GCP_REGION=${GCP_REGION}"
    local COMMON_AGENT_ENV_VARS="${BASE_ENV_VARS},GKE_CLUSTER_ENDPOINT=${GKE_ENDPOINT}"
    
    local CONNECTOR_NAME="my-vpc-connector" # Assurez-vous que ce nom correspond à votre connecteur VPC

    echo "    -> Récupération de l'URL du GRA..."
    local GRA_CLOUD_RUN_URL=$(gcloud run services describe gra-server --platform=managed --region=${GCP_REGION} --project=${GCP_PROJECT_ID} --format='value(status.url)')
    if [ -z "$GRA_CLOUD_RUN_URL" ]; then
        echo "Erreur: Impossible de récupérer l'URL du service GRA. Assurez-vous qu'il est bien déployé."
        exit 1
    fi
    echo "    -> URL du GRA : ${GRA_CLOUD_RUN_URL}"

    echo "    -> Lancement du déploiement de '${AGENT_SERVICE_NAME}'..." # Corrected: AGENT_SERVICE_NAME was not set
    local AGENT_SERVICE_NAME=${AGENT_NAME_TO_DEPLOY//_/-} # Set AGENT_SERVICE_NAME here
    gcloud run deploy ${AGENT_SERVICE_NAME} \
      --image="${GCR_HOSTNAME}/${GCP_PROJECT_ID}/${IMAGE_REPO_NAME}/${AGENT_NAME_TO_DEPLOY}:latest" \
      --platform=managed \
      --region=${GCP_REGION} \
      --no-allow-unauthenticated \
      --port=8080 \
      --set-env-vars="${COMMON_AGENT_ENV_VARS},GRA_PUBLIC_URL=${GRA_CLOUD_RUN_URL}" \
      --vpc-connector="${CONNECTOR_NAME}" \
      --project=${GCP_PROJECT_ID}
    
    local AGENT_PUBLIC_URL=$(gcloud run services describe ${AGENT_SERVICE_NAME} --platform=managed --region=${GCP_REGION} --project=${GCP_PROJECT_ID} --format='value(status.url)')
    if [ -z "$AGENT_PUBLIC_URL" ]; then
        echo "Erreur : Impossible de récupérer l'URL pour ${AGENT_SERVICE_NAME}."
        exit 1
    fi

    echo "    -> Mise à jour de '${AGENT_SERVICE_NAME}' avec ses URLs publiques..."
    gcloud run services update ${AGENT_SERVICE_NAME} \
        --region=${GCP_REGION} \
        --set-env-vars="${COMMON_AGENT_ENV_VARS},GRA_PUBLIC_URL=${GRA_CLOUD_RUN_URL},PUBLIC_URL=${AGENT_PUBLIC_URL},INTERNAL_URL=${AGENT_PUBLIC_URL}" \
        --project=${GCP_PROJECT_ID}

    echo "    ✅ Agent '${AGENT_SERVICE_NAME}' déployé et configuré avec l'URL : ${AGENT_PUBLIC_URL}"
}

function deploy_frontend() {
    echo "--- ÉTAPE 5: DÉPLOIEMENT DU FRONT-END ---"
    echo "    -> Récupération de l'URL du GRA sur Cloud Run..."
    GRA_URL=$(gcloud run services describe gra-server --platform=managed --region=${GCP_REGION} --project=${GCP_PROJECT_ID} --format='value(status.url)')

    echo "    -> Génération du fichier de configuration pour le front-end..."
    echo "window.CONFIG = { BACKEND_API_URL: '${GRA_URL}' };" > react_frontend/config.js

    echo "    -> Déploiement sur Firebase Hosting..."
    firebase deploy --only hosting --project=${GCP_PROJECT_ID}

    echo "✅ ÉTAPE 5 TERMINÉE : Front-end déployé."
}
case "$1" in
    configure) configure ;;
    build) build_images ;;
    push) push_images ;;
    deploy) deploy_gcp ;;
    deploy-one)
        deploy_single_agent "$2"
        ;;
    deploy_frontend) deploy_frontend ;;
    all)
        configure
        build_images
        push_images
        deploy_gcp
        ;;
    *)
        echo "Commande inconnue: $1"; exit 1 ;;
esac