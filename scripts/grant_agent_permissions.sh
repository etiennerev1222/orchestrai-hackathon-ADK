#!/bin/bash

# grant_agent_permissions.sh
#
# Ce script accorde au service principal (gra) l'autorisation d'invoquer
# les autres services d'agents déployés sur Cloud Run. Il inclut une logique de
# tentatives multiples et peut accepter un compte de service directement.
#
# Usage:
#   1. Découverte automatique :
#      ./grant_agent_permissions.sh <project_id> <region> [caller_service_name]
#
#   2. En fournissant le compte de service :
#      ./grant_agent_permissions.sh <project_id> <region> --service-account <compte_de_service_email>
#
# Exemples:
#   ./grant_agent_permissions.sh orchestrai-hackathon europe-west1 gra-server
#   ./grant_agent_permissions.sh orchestrai-hackathon europe-west1 --service-account 434296769439-compute@developer.gserviceaccount.com

set -e

# --- Variables ---
PROJECT_ID=$1
REGION=$2

if [ -z "$PROJECT_ID" ] || [ -z "$REGION" ]; then
  echo "Erreur : L'ID du projet et la région sont requis."
  echo "Usage: $0 <project_id> <region> [caller_service_name | --service-account <email>]"
  exit 1
fi

echo "Configuration des permissions pour le projet '$PROJECT_ID' dans la région '$REGION'..."

CALLER_IDENTITY=""

# --- Obtenir l'identité de l'appelant ---
if [ "$3" == "--service-account" ]; then
  if [ -z "$4" ]; then
    echo "Erreur : L'email du compte de service est requis après l'option --service-account."
    exit 1
  fi
  CALLER_IDENTITY=$4
  echo "Utilisation du compte de service fourni directement : $CALLER_IDENTITY"
else
  # Logique existante pour découvrir le compte de service
  CALLER_SERVICE=${3:-gra-server}
  echo "Récupération du compte de service pour le service '$CALLER_SERVICE'..."
  
  MAX_RETRIES=5
  RETRY_DELAY=10 # secondes

  for i in $(seq 1 $MAX_RETRIES); do
    CALLER_IDENTITY=$(gcloud run services describe "$CALLER_SERVICE" \
      --platform managed \
      --region "$REGION" \
      --project "$PROJECT_ID" \
      --format 'value(serviceAccountName)' 2>/dev/null || true)

    if [ -n "$CALLER_IDENTITY" ]; then
      echo "Compte de service trouvé avec succès."
      break
    fi

    if [ $i -lt $MAX_RETRIES ]; then
      echo "Tentative $i/$MAX_RETRIES: Impossible de trouver le compte de service. Nouvelle tentative dans $RETRY_DELAY secondes..."
      sleep $RETRY_DELAY
    fi
  done
fi

if [ -z "$CALLER_IDENTITY" ]; then
  echo "Erreur : Impossible d'obtenir l'identité de l'appelant."
  exit 1
fi

echo "Le compte de service qui effectuera les appels est : $CALLER_IDENTITY"

# --- Lister tous les autres services agents ---
# On cherche les services qui se terminent par "-agent"
AGENT_SERVICES=$(gcloud run services list \
  --platform managed \
  --region "$REGION" \
  --project "$PROJECT_ID" \
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
  echo "Attribution du rôle 'run.invoker' au service '$SERVICE' pour '$CALLER_IDENTITY'..."
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
