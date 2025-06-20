#!/bin/bash

# === CONFIG ===
PROJECT_ID="orchestrai-hackathon"  # remplace si nécessaire
IMAGE_NAME="python-devtools"
IMAGE_TAG="3.9-full"
GCR_IMAGE="gcr.io/${PROJECT_ID}/${IMAGE_NAME}:${IMAGE_TAG}"

# === TEMP DIR FOR BUILD ===
BUILD_DIR="./tmp_python_devtools_image"
mkdir -p "${BUILD_DIR}"

# === DOCKERFILE ===
cat <<EOF > "${BUILD_DIR}/Dockerfile"
FROM python:3.9-slim-buster

RUN apt-get update && \\
    apt-get install -y --no-install-recommends \\
        bash \\
        jq \\
        findutils \\
        git \\
        curl \\
        wget \\
        vim \\
        build-essential \\
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
echo "✅ Image available at: ${GCR_IMAGE}"
echo ""
echo "➡️ Modify your Kubernetes manifest to use:"
echo "image: ${GCR_IMAGE}"
