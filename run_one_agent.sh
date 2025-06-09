#!/bin/bash
# Usage: ./run_one_agent.sh <agent_name>
AGENT=$1
if [ -z "$AGENT" ]; then
  echo "Usage: $0 <agent_name>"
  exit 1
fi
# Va toujours dans la racine du repo avant d’exécuter le compose :
cd "$(dirname "$0")"
cd "$(git rev-parse --show-toplevel 2>/dev/null || echo .)"
docker compose -f docker_build/docker-compose.yml up --build $AGENT
