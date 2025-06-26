#!/bin/bash
# Build, push and deploy the Development Agent to GKE
set -e
PROJECT_ID=$1
IMAGE="gcr.io/${PROJECT_ID}/development-agent:latest"

if [ -z "$PROJECT_ID" ]; then
  echo "Usage: $0 <gcp-project-id>"
  exit 1
fi

docker build -t "$IMAGE" -f src/tests/Dockerfile .
docker push "$IMAGE"

kubectl apply -f k8s/development-agent-deployment.yaml

echo "Development agent deployed"
