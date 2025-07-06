#!/bin/bash
# --- SCRIPT DE SIMULATION DE NETTOYAGE GCR (Corrigé) ---

set -e

# --- Paramètres ---
PROJECT_ID="orchestrai-hackathon"
REGION="europe-west1"
JOB_NAME="gcr-cleaner-script-job"
KEEP_COUNT=10

# --- Logique du Script ---

echo "--- Étape 1: Création du job (s'il n'existe pas) ---"
# On tente de créer le job. S'il échoue parce qu'il existe déjà, ce n'est pas grave.
# Le '|| true' à la fin assure que le script ne s'arrêtera pas en cas d'erreur "already exists".
gcloud beta run jobs create ${JOB_NAME} \
  --image=gcr.io/gcr-cleaner/gcr-cleaner \
  --region=${REGION} \
  --quiet || true

echo
echo "--- Étape 2: Récupération de la liste des dépôts ---"
REPOS=$(gcloud container images list --repository="gcr.io/${PROJECT_ID}" --format='value(name)')

echo "Les dépôts suivants vont être analysés :"
echo "${REPOS}"
echo

# Boucle sur chaque dépôt trouvé
for REPO in ${REPOS}; do
  echo "--------------------------------------------------------------------"
  echo "DRY RUN pour le dépôt : ${REPO}"
  echo "Règle : garder les ${KEEP_COUNT} plus récentes."
  echo "--------------------------------------------------------------------"

  gcloud beta run jobs execute ${JOB_NAME} \
    --region=${REGION} \
    --wait \
    --args="--repository=${REPO}" \
    --args="--keep=${KEEP_COUNT}" \
    --args="--dry-run"

  echo
done

echo "--- SIMULATION TERMINÉE ---"
echo "Aucune image n'a été supprimée. Vérifiez les logs ci-dessus pour voir ce qui aurait été effacé."
