#!/bin/bash
# Simple call to the development agent
set -e
AGENT_URL=${1:-"http://localhost:8080"}

echo "Calling development agent at $AGENT_URL"
ID_TOKEN=$(gcloud auth print-identity-token)
curl -s -X POST -H "Authorization: Bearer ${ID_TOKEN}" \
    -H "Content-Type: application/json" \
    -d @tests/dev_agent_request_payload.json \
    "${AGENT_URL}/" | tee response_generate.json
