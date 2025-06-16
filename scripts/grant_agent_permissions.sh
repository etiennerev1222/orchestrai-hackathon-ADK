#!/bin/bash

# grant_agent_permissions.sh
#
# Ce script accorde au service principal (gra) l'autorisation d'invoquer
# les autres services d'agents déployés sur Cloud Run.
#
# Usage: ./grant_agent_permissions.sh <project_id> <region>
#
# Exemple: ./grant_agent_permissions.sh orchestrai-hackathon europe-west1

set -e

# --- Variables ---
PROJECT_ID=$1
REGION=$2
# Le service qui a le droit d'appeler les autres
CALLER_SERVICE="gra"

if [ -z "$PROJECT_ID" ] || [ -z "$REGION" ]; then
  echo "Erreur : L'ID du projet et la région sont requis."
  echo "Usage: $0 <project_id> <region>"
  exit 1
fi

echo "Configuration des permissions pour le projet '$PROJECT_ID' dans la région '$REGION'..."

# --- Obtenir l'identité du service appelant (gra) ---
echo "Récupération du compte de service pour le service '$CALLER_SERVICE'..."
CALLER_IDENTITY=$(gcloud run services describe $CALLER_SERVICE \
  --platform managed \
  --region $REGION \
  --project $PROJECT_ID \
  --format 'value(serviceAccountName)')

if [ -z "$CALLER_IDENTITY" ]; then
  echo "Erreur : Impossible de trouver le compte de service pour le service '$CALLER_SERVICE'."
  echo "Assurez-vous que le service '$CALLER_SERVICE' est bien déployé."
  exit 1
fi

echo "Le compte de service de '$CALLER_SERVICE' est : $CALLER_IDENTITY"

# --- Lister tous les autres services agents ---
# On cherche les services qui se terminent par "-agent"
AGENT_SERVICES=$(gcloud run services list \
  --platform managed \
  --region $REGION \
  --project $PROJECT_ID \
  --format "value(service.name)" | grep -- '-agent$')

if [ -z "$AGENT_SERVICES" ]; then
  echo "Avertissement : Aucun service agent trouvé (se terminant par '-agent')."
  exit 0
fi

echo "Agents trouvés : "
echo "$AGENT_SERVICES"

# --- Donner les permissions ---
for SERVICE in $AGENT_SERVICES
do
  echo "-----------------------------------------------------"
  echo "Attribution du rôle 'run.invoker' au service '$SERVICE' pour l'appelant '$CALLER_SERVICE'..."
  gcloud run services add-iam-policy-binding "$SERVICE" \
    --member="serviceAccount:$CALLER_IDENTITY" \
    --role="roles/run.invoker" \
    --platform=managed \
    --region="$REGION" \
    --project="$PROJECT_ID"
  echo "Permission accordée pour '$SERVICE'."
done

echo "-----------------------------------------------------"
echo "Configuration des permissions terminée avec succès."
