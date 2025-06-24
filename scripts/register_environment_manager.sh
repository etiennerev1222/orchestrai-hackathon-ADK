#!/bin/bash
# Register the Environment Manager with the GRA
set -e
GRA_URL=${GRA_URL:-"http://gra.default.svc.cluster.local:8000"}
SERVICE_URL=${SERVICE_URL:-"http://environment-manager.default.svc.cluster.local:8080"}

payload='{"agent_name":"EnvironmentManager","public_url":"'${SERVICE_URL}'","internal_url":"'${SERVICE_URL}'","skills":["environment_manager"]}'

curl -X POST -H "Content-Type: application/json" -d "$payload" "$GRA_URL/register"

echo "Environment manager registration sent"
