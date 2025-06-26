#!/bin/bash
# Simple call to the development agent
set -e
AGENT_URL=${1:-"http://localhost:8080"}

echo "Calling development agent at $AGENT_URL"
curl -s -X POST -H "Content-Type: application/json" \
    -d @tests/dev_agent_request_payload.json \
    "$AGENT_URL/execute_task"
