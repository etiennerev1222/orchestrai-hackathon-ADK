#!/bin/bash
set -e

BASE_NAME="development-agent"

echo "🔍 Recherche des services générés automatiquement..."
kubectl get svc -l app=$BASE_NAME -o json \
  | jq -r '.items[] 
      | select(.metadata.name != "'$BASE_NAME'" 
      and (.metadata.name | type == "string") 
      and (.metadata.name | startswith("'$BASE_NAME'-"))) 
      | .metadata.name' \
  | while read svc_name; do
      echo "🗑️ Suppression du service $svc_name"
      kubectl delete svc "$svc_name"
    done

