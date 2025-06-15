#!/bin/bash
set -e

# Fichier: grant_gke_permissions_to_cloudrun_sa.sh
# Description: Ce script accorde les rôles IAM nécessaires au compte de service par défaut
#              de Cloud Run/Compute Engine pour interagir avec GKE.

# --- Paramètres configurables ---
GCP_PROJECT_ID="orchestrai-hackathon" # Remplacez par l'ID de votre projet GCP

GCP_PROJECT_NUMBER=$(gcloud projects describe ${GCP_PROJECT_ID} --format="value(projectNumber)")
CLOUD_RUN_SERVICE_ACCOUNT="${GCP_PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

REQUIRED_ROLES=(
    "roles/container.developer"
    "roles/iam.serviceAccountUser"
)

# --- Vérification des prérequis ---
echo "--- Vérification des prérequis IAM ---"

if ! command -v gcloud &> /dev/null; then
    echo "Erreur: gcloud CLI n'est pas installé. Veuillez l'installer et vous authentifier."
    exit 1
fi

gcloud auth print-access-token > /dev/null 2>&1 # Vérifie l'authentification silencieusement
if [ $? -ne 0 ]; then
    echo "Erreur: Vous n'êtes pas authentifié avec gcloud. Exécutez 'gcloud auth login' et 'gcloud config set project [VOTRE_ID_DU_PROJET]'."
    exit 1
fi

echo "Prérequis IAM vérifiés avec succès."
echo "Compte de service à configurer : ${CLOUD_RUN_SERVICE_ACCOUNT}"
echo "Projet GCP : ${GCP_PROJECT_ID}"
echo ""

# --- Accorder les rôles IAM ---
echo "--- Accord des rôles IAM au compte de service ---"

for ROLE in "${REQUIRED_ROLES[@]}"; do
    echo "Attribution du rôle '${ROLE}' à '${CLOUD_RUN_SERVICE_ACCOUNT}' dans le projet '${GCP_PROJECT_ID}'..."
    # Utilisation de --quiet pour éviter la confirmation, et vérification du code de sortie
    gcloud projects add-iam-policy-binding "${GCP_PROJECT_ID}" \
        --member="serviceAccount:${CLOUD_RUN_SERVICE_ACCOUNT}" \
        --role="${ROLE}" \
        --condition=None \
        --quiet 
    
    if [ $? -ne 0 ]; then
        echo "Avertissement: Impossible d'attribuer le rôle '${ROLE}'. Il peut être déjà attribué ou il y a un problème de permissions de l'utilisateur qui exécute ce script."
    else
        echo "Rôle '${ROLE}' attribué avec succès."
    fi
done

echo ""
echo "***************************************************************"
echo "Les permissions IAM ont été mises à jour pour le compte de service."
echo "N'oubliez pas de REDÉPLOYER vos services Cloud Run (development-agent, orchestrateur) "
echo "pour que ces changements de permissions soient pris en compte !"
echo "***************************************************************"