#!/bin/bash
# Simple smoke test for the Environment Manager API
set -e
BASE_URL=${1:-"http://localhost:8080"}

echo "Creating environment..."
curl -s -X POST -H "Content-Type: application/json" \
    -d '{"environment_id":"test-env"}' \
    "$BASE_URL/create_environment"
