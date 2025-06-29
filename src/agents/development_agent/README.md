Development Agent
Le Development Agent est un agent IA autonome capable d'interpréter des objectifs de développement, de planifier des actions, de générer du code, d'interagir avec un environnement d'exécution (via l'Environment Manager), et de valider ses propres accomplissements. Il est le "cerveau" de l'opération de développement.

Fonctionnalités Clés
Planification d'Actions : Utilise un grand modèle de langage (LLM) pour décider de la prochaine action atomique (générer du code, exécuter des commandes, lire des fichiers, lister des répertoires, compléter la tâche).

Génération de Code : Génère du code Python fonctionnel basé sur des spécifications, en nettoyant les formats Markdown.

Interaction avec l'Environnement : Délègue les opérations d'exécution et de manipulation de fichiers à l'Environment Manager.

Suivi de Tâche : Met à jour le statut de la tâche et crée des artefacts de développement.

Authentification : S'authentifie auprès de l'Environment Manager et du Global Registry Agent (GRA) en utilisant son propre jeton d'identité.

Enregistrement GRA : S'enregistre auprès du Global Registry Agent pour être découvert par d'autres services.

Déploiement sur Google Kubernetes Engine (GKE)
Le déploiement du Development Agent implique la configuration de ses permissions et sa connexion à l'Environment Manager et au GRA.

Prérequis
Un projet Google Cloud actif.

Un cluster GKE en cours d'exécution.

gcloud CLI configuré et authentifié.

kubectl configuré pour se connecter à votre cluster GKE.

Docker installé localement.

L'Environment Manager doit être déployé et opérationnel.

Le Global Registry Agent (GRA) doit être déployé et accessible (souvent sur Cloud Run).

1. Comptes de Service GCP et IAM
Le Development Agent a besoin de permissions pour interagir avec Vertex AI (pour le LLM), Firestore, et pour s'authentifier auprès de l'Environment Manager et du GRA.

Compte de Service GCP (orchestrai-gra-firestore@<PROJECT_ID>.iam.gserviceaccount.com) : Le même GSA que pour l'Environment Manager est souvent réutilisé.

Rôles IAM requis pour ce GSA :

Vertex AI User (roles/aiplatform.user) : Pour appeler les modèles Vertex AI (LLM).

Cloud Datastore User ou Cloud Firestore User : Pour interagir avec Firestore (enregistrement de service, mise à jour des graphes de tâches).

Service Account Token Creator (roles/iam.serviceAccountTokenCreator) : Pour générer des jetons d'identité pour s'authentifier auprès d'autres services (comme l'Environment Manager).

Service Account User (roles/iam.serviceAccountUser) sur lui-même : Pour que le pod puisse obtenir des jetons pour son propre compte de service.

Très important pour la communication Cloud Run -> GKE : Si un service Cloud Run appelle votre agent de développement, le Service Account GCP de votre service Cloud Run (<project-number>-compute@developer.gserviceaccount.com) doit avoir le rôle Service Account User (roles/iam.serviceAccountUser) sur ce GSA (orchestrai-gra-firestore@...).

2. Fichiers de l'Agent de Développement
src/agents/development_agent/server.py : L'application FastAPI de l'Agent de Développement.

src/agents/development_agent/logic.py : Logique de décision de l'agent.

src/agents/development_agent/executor.py : Orchestre les actions de l'agent.

Important : Dans executor.py, la méthode _generate_code_from_specs doit nettoyer les balises Markdown du code généré par le LLM.

# Dans executor.py, méthode _generate_code_from_specs
import re # Assurez-vous que c'est importé
# ...
raw_code = await call_llm(...)
stripped_code = re.sub(r'^\s*```(?:[a-zA-Z0-9]+\s*)?\n|\n\s*```\s*$', '', raw_code, flags=re.MULTILINE)
return stripped_code.strip()

Important : L'initialisation de EnvironmentManager dans executor.py doit se faire de manière asynchrone et passer le jeton d'authentification de l'agent :

# Dans executor.py, méthode execute
if self.environment_manager is None:
    env_url = await get_environment_manager_url()
    agent_auth_token = await get_agent_id_token() # Obtient le jeton
    self.environment_manager = EnvironmentManager(base_url=env_url, auth_token=agent_auth_token) # Passe le jeton
    self.agent_logic.set_environment_manager(self.environment_manager)

src/shared/service_discovery.py : Contient la fonction get_agent_id_token pour obtenir le jeton d'identité de l'agent.

3. Déploiement Kubernetes de l'Agent de Développement
Kubernetes Service Account (KSA) : (orchestrai-sa)
Le même KSA que pour l'Environment Manager peut être utilisé.

Secret Kubernetes pour la clé du GSA : (gcp-sa-key)
Le même secret que pour l'Environment Manager peut être réutilisé.

Fichier YAML de Déploiement : (k8s/development-agent-deployment.yaml)
Définit le Deployment et le Service Kubernetes pour l'Agent.

apiVersion: apps/v1
kind: Deployment
metadata:
  name: development-agent
  labels:
    app: development-agent
spec:
  replicas: 1
  selector:
    matchLabels:
      app: development-agent
  template:
    metadata:
      labels:
        app: development-agent
    spec:
      serviceAccountName: orchestrai-sa # Le KSA
      volumes:
        - name: gcp-sa-key-volume
          secret:
            secretName: gcp-sa-key # Le secret
      containers:
      - name: development-agent
        image: gcr.io/${PROJECT_ID}/development-agent:${IMAGE_TAG} # Tag de l'image de l'Agent de Développement
        imagePullPolicy: Always # Très important
        ports:
        - containerPort: 8080
        env:
        - name: PORT
          value: "8080"
        - name: AGENT_NAME
          value: "DevelopmentAgentGKEv2"
        - name: PUBLIC_URL
          value: "${GRA_PUBLIC_URL}/development-agent"
        - name: INTERNAL_URL
          value: "http://development-agent.default.svc.cluster.local:8080"
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
        - name: ENV_MANAGER_URL # <--- URL INTERNE DE L'ENVIRONMENT MANAGER
          value: "http://environment-manager.default.svc.cluster.local:80" # Port du service K8s
        volumeMounts:
        - name: gcp-sa-key-volume
          mountPath: "/var/secrets/google"
          readOnly: true
      restartPolicy: Always
---
apiVersion: v1
kind: Service
metadata:
  name: development-agent
spec:
  selector:
    app: development-agent
  ports:
    - protocol: TCP
      port: 80
      targetPort: 8080
  type: LoadBalancer

Script de Déploiement : (deploy_development_agent_gke.sh)
Ce script orchestre la construction de l'image de l'Agent de Développement et l'application du YAML.

#!/bin/bash
set -e
# ... (définition des variables PROJECT_ID, GRA_PUBLIC_URL, GKE_CLUSTER_ENDPOINT, GKE_SSL_CA_CERT) ...

# 1. Construire et pousser l'image de l'Agent de Développement
TIMESTAMP=$(date +%s)
IMAGE="gcr.io/${PROJECT_ID}/development-agent:${TIMESTAMP}"
docker build -t "$IMAGE" -f src/agents/development_agent/Dockerfile .
docker push "$IMAGE"

# 2. (Optionnel) Recréer le secret Kubernetes pour les credentials du Service Account (si nécessaire)
# ... (code pour créer gcp-sa-key) ...

# 3. Déployer sur GKE en utilisant envsubst
export PROJECT_ID GRA_PUBLIC_URL AGENT_NAME KUBERNETES_NAMESPACE IMAGE ENV_MANAGER_URL GKE_CLUSTER_ENDPOINT GKE_SSL_CA_CERT
envsubst < k8s/development-agent-deployment.yaml | kubectl apply -f -

4. Vérification des Endpoints et Tests
Endpoint exposé par le Development Agent :

POST / (pour les messages JSON-RPC)

GET /health

GET /status

GET /card

Script de Test : (tests/test_development_agent_curl.sh)
Utilisez ce script pour valider le bon fonctionnement de l'agent.

#!/bin/bash
# ... (définition de AGENT_URL, get_id_token) ...
ID_TOKEN_GENERATE=$(get_id_token)
curl -s -X POST -H "Authorization: Bearer ${ID_TOKEN_GENERATE}" \
    -H "Content-Type: application/json" \
    -d @tests/dev_agent_request_payload.json \
    "${AGENT_URL}/" | tee response_generate.json
# ... (sleep) ...
ID_TOKEN_EXECUTE=$(get_id_token)
curl -s -X POST -H "Authorization: Bearer ${ID_TOKEN_EXECUTE}" \
    -H "Content-Type: application/json" \
    -d @tests/dev_agent_request_payload_1.json \
    "${AGENT_URL}/" | tee response_generate_1.json
# ... (affichage des réponses) ...

