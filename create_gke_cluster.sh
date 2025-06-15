#!/bin/bash

# Fichier: create_gke_cluster.sh
# Description: Ce script automatise la création d'un cluster Google Kubernetes Engine (GKE)
#              et configure kubectl pour s'y connecter.

# --- Paramètres configurables ---
# Vous pouvez modifier ces valeurs ou les passer en arguments au script.
GCP_PROJECT_ID="orchestrai-hackathon" # Remplacez par l'ID de votre projet GCP
CLUSTER_NAME="dev-orchestra-cluster"
GCP_ZONE="europe-west1-b" # Ou votre zone préférée (ex: us-central1-a, europe-west1-b, etc.)
MACHINE_TYPE="e2-medium"
NUM_NODES=1
MIN_NODES=1
MAX_NODES=3
CLUSTER_VERSION="latest" # Ou une version spécifique, ex: "1.28"

# --- Vérification des prérequis ---
echo "--- Vérification des prérequis ---"

# Vérifier si gcloud CLI est installé
if ! command -v gcloud &> /dev/null; then
    echo "Erreur: gcloud CLI n'est pas installé. Veuillez l'installer et vous authentifier."
    echo "Consultez : https://cloud.google.com/sdk/docs/install"
    exit 1
fi

# Vérifier si kubectl est installé
if ! command -v kubectl &> /dev/null; then
    echo "Avertissement: kubectl n'est pas installé. Tentative d'installation via gcloud."
    gcloud components install kubectl || { echo "Erreur: Impossible d'installer kubectl. Veuillez l'installer manuellement."; exit 1; }
fi

# Vérifier l'authentification gcloud
gcloud auth print-access-token &> /dev/null
if [ $? -ne 0 ]; then
    echo "Erreur: Vous n'êtes pas authentifié avec gcloud. Exécutez 'gcloud auth login' et 'gcloud config set project [VOTRE_ID_DU_PROJET]'."
    exit 1
fi

# Définir le projet GCP (au cas où il ne l'est pas déjà)
echo "Définition du projet GCP à : ${GCP_PROJECT_ID}"
gcloud config set project "${GCP_PROJECT_ID}" || { echo "Erreur: Impossible de définir le projet GCP. Vérifiez l'ID."; exit 1; }

echo "Prérequis vérifiés avec succès."

# --- Création du Cluster GKE ---
echo ""
echo "--- Début de la création du cluster GKE '${CLUSTER_NAME}' dans la zone '${GCP_ZONE}' ---"
echo "Cela peut prendre plusieurs minutes..."

gcloud container clusters create "${CLUSTER_NAME}" \
    --zone "${GCP_ZONE}" \
    --machine-type "${MACHINE_TYPE}" \
    --num-nodes "${NUM_NODES}" \
    --cluster-version "${CLUSTER_VERSION}" \
    --enable-autoscaling --min-nodes "${MIN_NODES}" --max-nodes "${MAX_NODES}" \
    --enable-private-nodes \
    --enable-master-authorized-networks \
    --master-authorized-networks 0.0.0.0/0 \
    --enable-ip-alias \
    --network default \
    --subnetwork default \
    `# Supprimé: --enable-cloud-logging` \
    `# Supprimé: --enable-cloud-monitoring` \
    --no-enable-basic-auth \
    --no-issue-client-certificate \
    --addons HorizontalPodAutoscaling,HttpLoadBalancing,GcePersistentDiskCsiDriver \
    --project "${GCP_PROJECT_ID}"

# Vérifier si la création du cluster a réussi
if [ $? -ne 0 ]; then
    echo "Erreur: La création du cluster GKE a échoué. Veuillez vérifier les logs ci-dessus."
    exit 1
fi

echo "Cluster GKE '${CLUSTER_NAME}' créé avec succès."

# --- Configuration de kubectl ---
echo ""
echo "--- Configuration de kubectl ---"

gcloud container clusters get-credentials "${CLUSTER_NAME}" \
    --zone "${GCP_ZONE}" \
    --project "${GCP_PROJECT_ID}"

# Vérifier si la configuration de kubectl a réussi
if [ $? -ne 0 ]; then
    echo "Erreur: La configuration de kubectl a échoué."
    exit 1
fi

echo "kubectl configuré pour se connecter au cluster '${CLUSTER_NAME}'."

# --- Vérification finale ---
echo ""
echo "--- Vérification finale de la connexion au cluster ---"
kubectl get nodes

if [ $? -ne 0 ]; then
    echo "Erreur: La vérification des nœuds kubectl a échoué. Quelque chose ne va pas."
    exit 1
else
    echo ""
    echo "*****************************************************"
    echo "Félicitations ! Votre cluster GKE est prêt et kubectl est configuré."
    echo "Vous pouvez maintenant utiliser l'EnvironmentManager refactorisé."
    echo "*****************************************************"
fi