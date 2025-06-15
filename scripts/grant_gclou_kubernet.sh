#!/bin/bash

# Script complet de configuration GCP et Kubernetes (GKE)
# Reproduit toutes les étapes effectuées pour résoudre les problèmes rencontrés.

# --- Configuration des variables ---
PROJECT_ID="orchestrai-hackathon"
CLUSTER_NAME="NOM_DU_CLUSTER"
CLUSTER_ZONE="ZONE_DU_CLUSTER" # ex : europe-west1-b
SERVICE_ACCOUNT_EMAIL="compte_service@orchestrai-hackathon.iam.gserviceaccount.com"
NAMESPACE="default"
USER_ACCOUNT_ID="105578291885468670827" # Remplacez par votre identifiant réel
CREDENTIALS_FILE="/chemin/vers/credentials.json"
CA_CERT_FILE="ca.pem"

# --- Authentification avec gcloud ---
echo "🔐 Authentification sur Google Cloud..."
gcloud auth activate-service-account "$SERVICE_ACCOUNT_EMAIL" --key-file="$CREDENTIALS_FILE"
gcloud config set project "$PROJECT_ID"

# --- Configuration ADC (Application Default Credentials) ---
echo "🗝️ Configuration des credentials ADC..."
export GOOGLE_APPLICATION_CREDENTIALS="$CREDENTIALS_FILE"

# --- Récupération du contexte Kubernetes ---
echo "📡 Récupération du contexte Kubernetes (GKE)..."
gcloud container clusters get-credentials "$CLUSTER_NAME" --zone="$CLUSTER_ZONE" --project="$PROJECT_ID"

# --- Téléchargement du certificat CA du cluster pour SSL ---
echo "📥 Téléchargement du certificat CA Kubernetes..."
gcloud container clusters describe "$CLUSTER_NAME" --zone="$CLUSTER_ZONE" \
  --format="value(masterAuth.clusterCaCertificate)" | base64 --decode > "$CA_CERT_FILE"

# --- Création du rôle RBAC personnalisé pour l'accès aux ressources nécessaires ---
echo "🛠️ Création du ClusterRole Kubernetes avec permissions nécessaires..."
cat <<EOF | kubectl apply -f -
kind: ClusterRole
apiVersion: rbac.authorization.k8s.io/v1
metadata:
  name: orchestrai-dev-access-role
rules:
- apiGroups: [""]
  resources: ["persistentvolumeclaims", "pods"]
  verbs: ["get", "list", "watch", "create", "delete", "update"]
EOF

# --- Binding du ClusterRole à l'utilisateur authentifié ---
echo "🔗 Binding du ClusterRole à l'utilisateur authentifié..."
kubectl create clusterrolebinding orchestrai-dev-access-binding \
  --clusterrole=orchestrai-dev-access-role \
  --user="$USER_ACCOUNT_ID" \
  --dry-run=client -o yaml | kubectl apply -f -

# --- Vérification explicite des permissions ---
echo "✅ Vérification explicite des permissions Kubernetes :"
kubectl auth can-i get pvc --as="$USER_ACCOUNT_ID" -n "$NAMESPACE"
kubectl auth can-i get pods --as="$USER_ACCOUNT_ID" -n "$NAMESPACE"

# --- Récapitulatif des variables d'environnement pour l'application ---
echo "📝 Variables d'environnement recommandées pour votre application :"
echo "export GOOGLE_APPLICATION_CREDENTIALS=\"$CREDENTIALS_FILE\""
echo "export GKE_CLUSTER_ENDPOINT=\"$(kubectl config view --minify -o jsonpath='{.clusters[0].cluster.server}' | sed 's|https://||')\""
echo "export GKE_SSL_CA_CERT=\"$(realpath $CA_CERT_FILE)\""

echo "🚀 Configuration terminée avec succès ! Vous pouvez maintenant relancer votre application."
