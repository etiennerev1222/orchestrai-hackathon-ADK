#!/bin/bash
# Build, push and deploy the Environment Manager to GKE
set -e
PROJECT_ID=$1
NAMESPACE=${NAMESPACE:-default}
IMAGE="gcr.io/${PROJECT_ID}/environment-manager:latest"

if [ -z "$PROJECT_ID" ]; then
  echo "Usage: $0 <gcp-project-id>"
  exit 1
fi

docker build -t "$IMAGE" -f src/tests/Dockerfile .
docker push "$IMAGE"

kubectl apply -n "$NAMESPACE" -f k8s/environment-manager-deployment.yaml

echo "Environment manager deployed"
