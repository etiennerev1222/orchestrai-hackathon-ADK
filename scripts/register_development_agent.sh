#!/bin/bash
# Register the Development Agent with the GRA
set -e
GRA_URL=${GRA_URL:-"http://gra.default.svc.cluster.local:8000"}
AGENT_URL=${AGENT_URL:-"http://development-agent.default.svc.cluster.local:8080"}

payload='{"agent_name":"DevelopmentAgentServer","public_url":"'${AGENT_URL}'","internal_url":"'${AGENT_URL}'","skills":["coding_python"]}'

curl -X POST -H "Content-Type: application/json" -d "$payload" "$GRA_URL/register"

echo "Agent registration sent"
