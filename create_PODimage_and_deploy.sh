#!/bin/bash

# === CONFIG ===
PROJECT_ID="orchestrai-hackathon"  # remplace si nécessaire
IMAGE_NAME="python-devtools"
# ✨ CORRECTION DÉFINITIVE : Un tag unique pour chaque build
TIMESTAMP=$(date +%s)
IMAGE_TAG="${TIMESTAMP}" # Utilise un timestamp comme tag unique
GCR_IMAGE="gcr.io/${PROJECT_ID}/${IMAGE_NAME}:${IMAGE_TAG}"

# === TEMP DIR FOR BUILD ===
BUILD_DIR="./tmp_python_devtools_image"
mkdir -p "${BUILD_DIR}"

# === DOCKERFILE ===
# Assurez-vous que 'jq' est bien dans cette liste
cat <<EOF > "${BUILD_DIR}/Dockerfile"
FROM python:3.11-slim-buster

RUN apt-get update && \\
    apt-get install -y --no-install-recommends \\
        bash \\
        findutils \\
        git \\
        curl \\
        wget \\
        vim \\
        build-essential \\
        jq \\
    && apt-get clean && \\
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
EOF

# === BUILD IMAGE ===
echo "🚀 Building image: ${GCR_IMAGE}"
docker build -t "${GCR_IMAGE}" "${BUILD_DIR}"

# === PUSH IMAGE ===
echo "🚀 Pushing image to GCR: ${GCR_IMAGE}"
docker push "${GCR_IMAGE}"

# === CLEANUP ===
echo "🧹 Cleaning up temp build dir"
rm -rf "${BUILD_DIR}"

# === NEXT STEPS ===
echo ""
echo "✅ Image disponible à : ${GCR_IMAGE}"
echo ""
echo "➡️ Mettez à jour src/services/environment_manager/k8s_environment_manager.py pour utiliser cette image:"
echo "base_image: \"${GCR_IMAGE}\""
