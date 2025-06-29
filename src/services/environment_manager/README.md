Environment Manager
L'Environment Manager est un service crucial dans notre architecture, responsable de la création, de la gestion et de l'interaction avec des environnements d'exécution isolés basés sur Kubernetes. Ces environnements sont utilisés par les agents (comme le Development Agent) pour exécuter du code, des commandes shell, et manipuler des fichiers de manière sécurisée et isolée.

Fonctionnalités Clés
Création et Destruction d'Environnements : Provisionne et déprovisionne des pods Kubernetes (avec Persistent Volume Claims pour la persistance des données) à la demande.

Exécution de Commandes : Permet d'exécuter des commandes shell arbitraires à l'intérieur des conteneurs d'environnement.

Gestion de Fichiers : Supporte l'upload, le download et le listage de fichiers/répertoires dans les environnements.

Intégration Cloud Storage : Capacité d'uploader des artefacts vers Google Cloud Storage et de les indexer dans Firestore.

Authentification : S'authentifie auprès de l'API Kubernetes et d'autres services Google Cloud en utilisant les identifiants du compte de service.

Enregistrement GRA : S'enregistre auprès du Global Registry Agent (GRA) pour la découverte de services.

Déploiement sur Google Kubernetes Engine (GKE)
Le déploiement de l'Environment Manager implique plusieurs étapes pour configurer l'image de base des environnements, les permissions IAM, et le service lui-même.

Prérequis
Un projet Google Cloud actif.

Un cluster GKE en cours d'exécution.

gcloud CLI configuré et authentifié pour votre projet.

kubectl configuré pour se connecter à votre cluster GKE.

Docker installé localement.

jq installé localement (pour les scripts).

Un VPC Connector configuré et READY si vous prévoyez une communication depuis Cloud Run.

1. Comptes de Service GCP et IAM
L'Environment Manager interagit directement avec l'API Kubernetes pour créer des pods et des PVCs. Il a besoin de permissions spécifiques.

Compte de Service GCP (orchestrai-gra-firestore@<PROJECT_ID>.iam.gserviceaccount.com) : C'est le compte de service Google Cloud que vos pods GKE utiliseront.

Rôles IAM requis pour ce GSA :

Kubernetes Engine Developer (roles/container.developer) : Pour gérer les ressources Kubernetes (pods, PVCs).

Service Account User (roles/iam.serviceAccountUser) sur lui-même : Pour que le pod puisse obtenir des jetons pour son propre compte de service.

Storage Admin (roles/storage.admin) : Si vous utilisez la fonctionnalité upload_to_cloud_and_index.

Cloud Datastore User ou Cloud Firestore User (roles/datastore.user ou roles/datastore.viewer/writer si plus granulaire) : Pour interagir avec Firestore (enregistrement des environnements).

2. Image de Base des Environnements (python-devtools)
C'est l'image Docker qui sera utilisée pour les pods d'exécution réels créés par l'Environment Manager. Elle doit contenir tous les outils nécessaires (Python, jq, findutils, etc.).

Dockerfile : (Exemple typique, chemin: src/services/environment_manager/Dockerfile ou similaire)

FROM python:3.11-slim-buster

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        bash \
        jq \
        findutils \
        git \
        curl \
        wget \
        vim \
        build-essential \
    && apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
CMD ["tail", "-f", "/dev/null"]

Script de Construction et Push : (create_PODimage_and_deploy.sh)
Ce script construit l'image python-devtools avec un tag unique (timestamp) et la pousse vers GCR.

#!/bin/bash
# ... (extrait) ...
PROJECT_ID="orchestrai-hackathon"
IMAGE_NAME="python-devtools"
TIMESTAMP=$(date +%s)
IMAGE_TAG="${TIMESTAMP}"
GCR_IMAGE="gcr.io/${PROJECT_ID}/${IMAGE_NAME}:${IMAGE_TAG}"
# ... (Dockerfile cat, docker build, docker push) ...
echo "✅ Image disponible à : ${GCR_IMAGE}" # Notez ce tag !

Action : Exécutez ce script et notez le tag complet de l'image générée (ex: gcr.io/orchestrai-hackathon/python-devtools:1751122256).

3. Fichiers de l'Environment Manager
src/services/environment_manager/server.py : L'application FastAPI de l'Environment Manager.

src/services/environment_manager/logic.py : Logique métier de l'Environment Manager.

src/services/environment_manager/k8s_environment_manager.py : Implémentation de l'interaction avec l'API Kubernetes.

Important : Dans k8s_environment_manager.py, la fonction create_isolated_environment doit utiliser la variable d'environnement DEV_ENV_BASE_IMAGE pour la base_image :

# Dans k8s_environment_manager.py
async def create_isolated_environment(self, environment_id: str, base_image: str | None = None) -> str:
    effective_base_image = base_image or os.environ.get("DEV_ENV_BASE_IMAGE", "python:3.11-slim-buster")
    # ... utilisez effective_base_image dans pod_manifest ...

src/services/environment_manager/environment_manager.py : Client HTTP pour les appels internes.

Important : Son __init__ doit accepter auth_token et ses méthodes _post doivent utiliser self._get_headers() pour inclure le jeton d'authentification.

4. Déploiement Kubernetes de l'Environment Manager
Kubernetes Service Account (KSA) : (orchestrai-sa)
Ce KSA est utilisé par les pods de l'Environment Manager. Il doit être lié au GSA (orchestrai-gra-firestore@...) via Workload Identity ou avoir le secret de la clé du GSA monté.

# Exemple de Role et RoleBinding pour orchestrai-sa (si non déjà fait)
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: environment-manager-pod-manager
  namespace: default
rules:
- apiGroups: [""]
  resources: ["pods", "pods/exec", "persistentvolumeclaims"]
  verbs: ["get", "list", "watch", "create", "delete", "update", "patch"]
- apiGroups: ["apps"]
  resources: ["deployments"]
  verbs: ["get", "list", "watch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: environment-manager-bind-pod-manager
  namespace: default
subjects:
- kind: ServiceAccount
  name: orchestrai-sa
  namespace: default
roleRef:
  kind: Role
  name: environment-manager-pod-manager
  apiGroup: rbac.authorization.k8s.io

Action : Appliquez ce YAML (kubectl apply -f ...).

Secret Kubernetes pour la clé du GSA : (gcp-sa-key)
Ce secret contient la clé JSON du GSA et est monté dans le pod de l'Environment Manager.

# Exemple de création du secret (à exécuter après avoir généré la clé du GSA)
TMP_SA_KEY="./tmp-gcp-sa-key.json"
SERVICE_ACCOUNT_EMAIL="orchestrai-gra-firestore@${PROJECT_ID}.iam.gserviceaccount.com"
gcloud iam service-accounts keys create "$TMP_SA_KEY" --iam-account="$SERVICE_ACCOUNT_EMAIL" --quiet
kubectl create secret generic gcp-sa-key --from-file=sa-key.json="$TMP_SA_KEY" --namespace default --dry-run=client -o yaml | kubectl apply -f -
rm -f "$TMP_SA_KEY"

Fichier YAML de Déploiement : (k8s/environment-manager-deployment.yaml)
Ce fichier définit le Deployment et le Service Kubernetes pour l'Environment Manager.

apiVersion: apps/v1
kind: Deployment
metadata:
  name: environment-manager
  labels:
    app: environment-manager
spec:
  replicas: 1
  selector:
    matchLabels:
      app: environment-manager
  template:
    metadata:
      labels:
        app: environment-manager
    spec:
      serviceAccountName: orchestrai-sa # Le KSA
      volumes:
        - name: gcp-sa-key-volume
          secret:
            secretName: gcp-sa-key # Le secret
      containers:
      - name: environment-manager
        image: gcr.io/${PROJECT_ID}/environment-manager:${ENV_MANAGER_IMAGE_TAG} # Tag de l'image de l'Environment Manager
        imagePullPolicy: Always # Très important pour les mises à jour
        ports:
        - containerPort: 8080
        env:
        - name: PORT
          value: "8080"
        - name: AGENT_NAME
          value: "EnvironmentManagerGKEv2"
        - name: PUBLIC_URL
          value: "${GRA_PUBLIC_URL}/environment-manager"
        - name: INTERNAL_URL
          value: "http://environment-manager.default.svc.cluster.local:8080"
        - name: GRA_PUBLIC_URL
          value: "${GRA_PUBLIC_URL}"
        - name: GKE_CLUSTER_ENDPOINT
          value: "${GKE_CLUSTER_ENDPOINT}"
        - name: GKE_SSL_CA_CERT
          value: "${GKE_SSL_CA_CERT}"
        - name: GOOGLE_APPLICATION_CREDENTIALS
          value: "/var/secrets/google/sa-key.json"
        - name: KUBERNETES_NAMESPACE
          value: "default"
        - name: DEV_ENV_BASE_IMAGE # <--- PASSE LE TAG DE L'IMAGE PYTHON-DEVTOOLS AU MANAGER
          value: "${DEVTOOLS_IMAGE_TAG}" # Sera substitué par envsubst
        volumeMounts:
        - name: gcp-sa-key-volume
          mountPath: "/var/secrets/google"
          readOnly: true
      restartPolicy: Always
---
apiVersion: v1
kind: Service
metadata:
  name: environment-manager
spec:
  selector:
    app: environment-manager
  ports:
    - protocol: TCP
      port: 80 # Port du service
      targetPort: 8080 # Port du conteneur
  type: LoadBalancer # Ou ClusterIP si seulement interne

Script de Déploiement : (deploy_environment_manager_gke.sh)
Ce script orchestre la construction de l'image de l'Environment Manager et l'application du YAML.

#!/bin/bash
set -e
# ... (définition des variables PROJECT_ID, DEVTOOLS_IMAGE_TAG, GRA_PUBLIC_URL, GKE_CLUSTER_ENDPOINT, GKE_SSL_CA_CERT) ...

# 1. Construire et pousser l'image de l'Environment Manager
TIMESTAMP=$(date +%s)
ENV_MANAGER_IMAGE="gcr.io/${PROJECT_ID}/environment-manager:${TIMESTAMP}"
docker build -t "${ENV_MANAGER_IMAGE}" -f src/services/environment_manager/Dockerfile .
docker push "${ENV_MANAGER_IMAGE}"

# 2. (Optionnel) Recréer le secret Kubernetes pour les credentials du Service Account (si nécessaire)
# ... (code pour créer gcp-sa-key) ...

# 3. Déployer sur GKE en utilisant envsubst
export PROJECT_ID ENV_MANAGER_IMAGE_TAG=${TIMESTAMP} DEVTOOLS_IMAGE_TAG GRA_PUBLIC_URL GKE_CLUSTER_ENDPOINT GKE_SSL_CA_CERT KUBERNETES_NAMESPACE
envsubst < k8s/environment-manager-deployment.yaml | kubectl apply -f -

5. Vérification des Endpoints et Tests
Endpoints exposés par l'Environment Manager :

POST /create_environment

POST /delete_environment

POST /exec_in_environment

POST /upload_to_environment

POST /download_from_environment

POST /list_files_in_environment

POST /upload_to_cloud_and_index

GET /health

GET /status

Script de Test : (tests/test_environment_manager_curl.sh)
Utilisez ce script pour valider le bon fonctionnement de tous les endpoints après le déploiement.
