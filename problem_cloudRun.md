Documentation : Connectivité Cloud Run vers GKE via Load Balancers Internes et Cloud DNS pour GKE

Résumé Exécutif

Ce document détaille les étapes pour résoudre les problèmes de connectivité entre un service Cloud Run et des applications exécutées dans un cluster Google Kubernetes Engine (GKE) au sein du même réseau VPC. La solution implique l'utilisation de Load Balancers TCP/UDP Internes GKE pour exposer les services de manière routable au niveau du VPC, et l'intégration de Cloud DNS pour GKE pour une résolution de noms transparente.

Problème initial :
Le service Cloud Run ne parvenait pas à joindre les services GKE via leurs ClusterIPs ou FQDNs internes, affichant des erreurs DNS (SERVFAIL, Name or service not known) ou des Request Error. Les ClusterIPs sont des IPs virtuelles non routables directement depuis l'extérieur du cluster GKE, ce qui causait une perte de paquets au niveau du routage VPC.

Solution architecturale :

Exposer les services GKE via des Load Balancers TCP/UDP Internes : Ceux-ci fournissent des IPs routables au sein du VPC.

Activer Cloud DNS pour GKE : Pour automatiser la résolution DNS des FQDNs des services GKE au niveau du VPC.

Prérequis

Un projet Google Cloud avec la facturation activée.

Un cluster GKE (dev-orchestra-cluster) déjà déployé, idéalement de type VPC-natif, dans la même région (europe-west1) et le même réseau VPC (default) que votre service Cloud Run.

Un service Cloud Run (gke-connectivity-testerX) déployé et configuré pour utiliser un connecteur d'accès VPC Serverless (my-vpc-connector, plage 192.168.99.0/28). Le trafic de sortie du service Cloud Run doit être configuré sur "Acheminer tout le trafic vers le VPC" (--vpc-egress=all-traffic).

Les outils gcloud CLI et kubectl installés et configurés pour votre projet et cluster.

Rôles IAM nécessaires pour votre compte d'utilisateur : Cloud Run Admin, Kubernetes Engine Admin, Compute Network Admin, Cloud DNS Administrator.

Fichiers de manifestes Kubernetes pour vos déploiements et services GKE (par exemple, development-agent-deployment.yaml, environment-manager-deployment.yaml).

Architecture Cible

Flux de Données : Cloud Run -> Connecteur VPC (192.168.99.0/28) -> Réseau VPC (default) -> Load Balancer Interne GKE (10.132.0.x) -> Nœud GKE -> Pod GKE.

Flux de Résolution DNS : Cloud Run -> Résolveur DNS VPC (169.254.169.254) -> Cloud DNS pour GKE -> IP du Load Balancer Interne GKE.

Étapes de Mise en Œuvre Détaillées

(Assurez-vous que votre terminal est dans le répertoire contenant vos manifestes Kubernetes, par exemple k8s/.)

Étape 1 : Vérification Initiale de la Connectivité VPC et des IPs (Avant Modifications)
Vérifiez le statut du connecteur VPC Serverless :

Allez dans la console Google Cloud > VPC Network > Serverless VPC Access.

Vérifiez que my-vpc-connector est READY (Prêt).

Confirmez que Cloud Run utilise le connecteur avec tout le trafic :

Allez dans Cloud Run > Votre service (gke-connectivity-testerX) > Onglet Réseau.

Vérifiez que le connecteur est sélectionné et que le "Routage du trafic" est sur "Acheminer tout le trafic vers le VPC".

Notez les IPs actuelles de vos services (avant la conversion en LB Interne) :

Bash
￼
kubectl get services -n default -o wide
kubectl get services -n kube-system -o wide
Notez les CLUSTER-IP de development-agent (34.118.231.33) et environment-manager (34.118.233.158).

Notez la CLUSTER-IP de kube-dns (34.118.224.10).

Étape 2 : Convertir les Services GKE en Load Balancers Internes
C'est la modification architecturale essentielle pour rendre vos services routables depuis le VPC.

Modifiez les manifestes de service Kubernetes (development-agent, environment-manager) :
Pour chaque service que Cloud Run doit joindre, ouvrez son fichier .yaml (par exemple, development-agent-deployment.yaml et environment-manager-deployment.yaml).

Trouvez la définition du Service (qui commence par apiVersion: v1 kind: Service).

Assurez-vous que spec.type est LoadBalancer.

Ajoutez l'annotation suivante sous metadata.annotations:

YAML
￼
# ... (début du fichier)
--- # Séparateur de document YAML si le Déploiement est dans le même fichier
apiVersion: v1
kind: Service
metadata:
  name: development-agent # ou environment-manager
  annotations:
    cloud.google.com/neg: '{"ingress":true}' # Gardez cette annotation si elle existe
    networking.gke.io/load-balancer-type: "Internal" # <--- AJOUTER CETTE LIGNE CLÉ
  # ... (autres metadata comme labels)
spec:
  type: LoadBalancer # S'assurer que c'est LoadBalancer
  # ... (reste de la spec du service)
Appliquez les manifestes modifiés :

Bash
￼
kubectl apply -f development-agent-deployment.yaml
kubectl apply -f environment-manager-deployment.yaml
Vous devriez voir service/development-agent configured et service/environment-manager configured (si des changements sont détectés).

Remarque : GKE va provisionner des Load Balancers Internes. Cela peut prendre quelques minutes (2-5 minutes).

Obtenez les nouvelles IPs Internes routables des services :
Attendez que le provisionnement soit terminé. Les IPs apparaîtront dans la colonne EXTERNAL-IP.

Bash
￼
kubectl get services -n default -o wide
development-agent devrait avoir une EXTERNAL-IP de 10.132.0.6.

environment-manager devrait avoir une EXTERNAL-IP de 10.132.0.5.

Notez ces IPs, elles sont cruciales.

Étape 3 : Activer Cloud DNS pour GKE (Portée VPC)
Cette étape permet la résolution DNS transparente des FQDNs de vos services GKE au sein du VPC.

Activez Cloud DNS pour GKE sur votre cluster (via la Console Google Cloud) :

Allez dans la console Google Cloud > Kubernetes Engine > Clusters.

Cliquez sur le nom de votre cluster : dev-orchestra-cluster.

Cliquez sur le bouton "MODIFIER" en haut.

Faites défiler jusqu'à la section "Mises à jour des modules complémentaires" ou "Modules complémentaires".

Recherchez l'option "Cloud DNS" (ou "Cloud DNS pour GKE") et cochez "Activer Cloud DNS pour GKE".

Dans les options de configuration, assurez-vous que la portée est bien "VPC" (VPC scope).

Si demandé pour le suffixe de domaine du cluster, entrez cluster.local (c'est la valeur par défaut pour GKE).

Cliquez sur "ENREGISTRER LES MODIFICATIONS" ou "MISE À JOUR".

Attendez que l'opération de mise à jour du cluster soit terminée (cela peut prendre du temps).

Vérifiez la création des zones DNS privées automatiques :
Une fois l'activation terminée, GKE devrait créer automatiquement des zones DNS privées dans Cloud DNS.

Allez dans la console Google Cloud > Cloud DNS > Zones DNS.

Vous devriez voir de nouvelles zones (gérées par Google) pour votre cluster, avec les noms cluster.local. et svc.cluster.local. (ou similaires) et liées à votre VPC. Le nom de la zone sera probablement gke-dev-orchestra-cluster-f5e836d0-dns.

Supprimez vos anciennes zones de redirection Cloud DNS manuelles (si elles existent) :
Si vous aviez créé manuellement des zones comme gke-cluster-dns-forwarding ou gke-cluster-local-zone, supprimez-les pour éviter les conflits :

Bash
￼
gcloud dns managed-zones delete gke-cluster-dns-forwarding
gcloud dns managed-zones delete gke-cluster-local-zone
Étape 4 : Mettre à Jour les Enregistrements DNS Manuellement (Si l'Auto-Synchronisation Échoue)
Parfois, Cloud DNS pour GKE peut pointer initialement vers les anciennes ClusterIPs (34.x.x.x). Nous allons forcer la mise à jour si nécessaire.

Vérifiez les IPs dans les enregistrements DNS automatiques :

Bash
￼
gcloud dns record-sets list --zone gke-dev-orchestra-cluster-f5e836d0-dns
Vérifiez les enregistrements A pour development-agent.default.svc.cluster.local. et environment-manager.default.svc.cluster.local..

Si elles pointent toujours vers 34.x.x.x, passez à l'étape suivante.

Mettez à jour manuellement les enregistrements A dans Cloud DNS (si les IPs sont incorrectes) :

Allez dans la console Google Cloud > Cloud DNS > Zones DNS.

Cliquez sur votre zone gke-dev-orchestra-cluster-f5e836d0-dns.

Pour development-agent.default.svc.cluster.local. :

Cliquez sur "Modifier" (crayon) à côté de l'enregistrement A.

Remplacez 34.118.231.33 par 10.132.0.6.

Enregistrer.

Pour environment-manager.default.svc.cluster.local. :

Cliquez sur "Modifier" (crayon) à côté de l'enregistrement A.

Remplacez 34.118.233.158 par 10.132.0.5.

Enregistrer.

Étape 5 : Mettre à Jour et Redéployer le Service Cloud Run
Modifiez votre fichier main.py de gke-connectivity-tester :

Assurez-vous que les variables DEV_AGENT_URL et ENV_MANAGER_URL lisent bien depuis os.environ.get() (elles ne doivent pas être commentées).

DEV_AGENT_URL_DIRECT_IP = "http://10.132.0.6:80"

ENV_MANAGER_URL_DIRECT_IP = "http://10.132.0.5:80"

La variable KUBE_DNS_IP et l'endpoint test-dig-direct peuvent être supprimés si vous ne prévoyez plus de faire de tests directs de kube-dns.

Redéployez votre service Cloud Run (gke-connectivity-tester4 ou le nom actuel) avec ce main.py mis à jour :

Bash
￼
cd src/services/gke-connectivity-tester # Assurez-vous d'être dans le bon répertoire
gcloud run deploy gke-connectivity-tester4 \
  --source=. \
  --region=europe-west1 \
  --platform=managed \
  --vpc-connector=my-vpc-connector \
  --vpc-egress=all-traffic \
  --set-env-vars=DEV_AGENT_URL="http://development-agent.default.svc.cluster.local:80",ENV_MANAGER_URL="http://environment-manager.default.svc.cluster.local:80" \
  --allow-unauthenticated
Étape 6 : Effectuer les Tests de Connectivité Finaux
Test 1 : Connectivité directe par IP (confirme que la base fonctionne) :

Bash
￼
SERVICE_URL=$(gcloud run services describe gke-connectivity-tester4 --region=europe-west1 --format="value(status.url)")
ID_TOKEN=$(gcloud auth print-identity-token)
curl -H "Authorization: Bearer ${ID_TOKEN}" "${SERVICE_URL}/run-direct-ip-tests"
Attendu : Succès.

Test 2 : Résolution DNS (le plus important) :

Bash
￼
curl -H "Authorization: Bearer ${ID_TOKEN}" "${SERVICE_URL}/test-dig?hostname=development-agent.default.svc.cluster.local"
Attendu : status: NOERROR, SERVER: 169.254.169.254#53, et une section ANSWER avec l'IP 10.132.0.6.

Test 3 : Connectivité complète via FQDN :

Bash
￼
curl -H "Authorization: Bearer ${ID_TOKEN}" "${SERVICE_URL}/run-tests"
Attendu : Les connexions à development-agent et environment-manager via leurs FQDNs devraient maintenant réussir.


Rapport d'Analyse et de Résolution des Problèmes de Connectivité entre Cloud Run et GKE (Mise à Jour)

Résumé Exécutif

Initialement, un service Cloud Run était incapable d'établir une connectivité réseau avec des services GKE via leurs ClusterIPs. Ce problème a été résolu en exposant les services GKE via des Load Balancers TCP/UDP Internes et en activant Cloud DNS pour GKE. La connectivité de bout en bout (y compris la résolution DNS via FQDN) est désormais fonctionnelle.

Cependant, de nouveaux problèmes sont apparus : des échecs de connexion WebSocket et des erreurs d'autorisation (401 Unauthorized) lorsque les applications GKE tentent d'interagir avec l'API Kubernetes.

Problèmes Résolus (Phase 1 : Connectivité Cloud Run vers GKE)

Échec de connexion aux ClusterIPs GKE :

Cause : Les ClusterIPs sont des IPs virtuelles non routables directement depuis le réseau VPC.

Solution : Services GKE (development-agent, environment-manager) convertis en Load Balancers TCP/UDP Internes avec l'annotation networking.gke.io/load-balancer-type: "Internal". Ils ont reçu des IPs internes routables (ex: 10.132.0.6, 10.132.0.5).

Statut : RÉSOLU. Le service Cloud Run peut maintenant communiquer directement avec ces IPs internes.

Échec de résolution DNS des FQDNs GKE (*.svc.cluster.local) :

Cause : La redirection DNS manuelle était inefficace, et kube-dns en ClusterIP n'était pas directement joignable par le résolveur VPC.

Solution : Activation de Cloud DNS pour GKE (champ d'application du cluster) sur le cluster GKE. Cela gère automatiquement les enregistrements DNS privés.

Statut : RÉSOLU (avec intervention manuelle). Bien que Cloud DNS pour GKE soit activé, il a été observé que les enregistrements A automatiques pointaient toujours vers les anciennes ClusterIPs (34.x.x.x). Une mise à jour manuelle des enregistrements A dans la zone Cloud DNS gérée par GKE (pour qu'ils pointent vers les IPs des Load Balancers Internes 10.x.x.x) a été nécessaire pour finaliser la résolution. La connectivité par FQDN est maintenant pleinement fonctionnelle.

Nouveaux Problèmes Actuels (Phase 2 : Communication Interne GKE et API Kubernetes)

websocket._exceptions.WebSocketBadStatusException: Handshake status 200 OK :

Contexte : Se produit lorsque les applications GKE (ex: environment-manager) tentent d'exécuter des commandes ou des opérations de flux (ex: read_namespaced_pod, exec, upload) via la bibliothèque Kubernetes Python.

Symptôme : L'API Kubernetes répond avec 200 OK au lieu du code 101 Switching Protocols attendu pour une poignée de main WebSocket, entraînant une exception.

Hypothèse : Interception/altération du trafic WebSocket, problème de configuration du client Kubernetes Python, ou incompatibilité de version.

kubernetes.client.exceptions.ApiException: (401) Reason: Unauthorized :

Contexte : Se produit lors de requêtes API Kubernetes (ex: read_namespaced_pod) depuis l'application GKE (ex: environment-manager).

Symptôme : L'API répond 401 Unauthorized, indiquant un problème d'autorisation du ServiceAccount orchestrai-sa.

Debugging : Le ServiceAccount orchestrai-sa est lié à orchestrai-sa-cluster-admin, qui devrait accorder des droits cluster-admin.

Hypothèse : Malgré le rôle cluster-admin, un problème de propagation des jetons, un problème avec le client Kubernetes Python, ou une interaction subtile avec l'API Server cause ce 401.

Prochaines Étapes pour la Phase 2 :

Résoudre le 401 Unauthorized : Assurer la propagation correcte du jeton d'authentification pour le ServiceAccount orchestrai-sa et ses permissions cluster-admin. Redémarrer les déploiements affectés après toute modification des RBAC.

Diagnostiquer la WebSocketBadStatusException : Vérifier l'URL de l'API Server utilisée par le client Kubernetes Python (privée 10.132.0.2:443 est préférée), les règles de pare-feu pour le trafic TCP/443 vers le plan de contrôle, et la compatibilité des versions de la bibliothèque Kubernetes Python.

Contacter le Support Google Cloud : Si ces problèmes persistent, ils nécessiteront un diagnostic plus approfondi par le support Google Cloud, car ils touchent à des aspects très spécifiques de la communication interne GKE et de l'authentification/autorisation.


Nouveaux Problèmes Actuels ou Prochaines Étapes pour la Phase 2) :

Problème de communication entre agents (potentiellement) :

Contexte : Les logs de development-agent montraient un ConnectTimeout lors d'une tentative de POST (probablement pour l'enregistrement ou la mise à jour de statut) vers http://10.132.0.6:80.

Symptôme : La connexion initiale (GET /.well-known/agent.json) réussissait, mais les requêtes subséquentes échouaient.

Résolution Temporaire (diagnostic) : Pour contourner ce ConnectTimeout et permettre la progression des tests, il a été nécessaire de forcer l'URL de l'agent dans les données de l'agent card (lues via /.well-known/agent.json) pour qu'elle pointe vers l'IP directe du Load Balancer interne (http://10.132.0.6:80) plutôt que vers le FQDN.

Implication : Bien que le ConnectTimeout ait été résolu par l'augmentation des timeouts de requêtes HTTP et le passage aux LoadBalancers Internes, ce contournement temporaire a été nécessaire pour les tests applicatifs inter-agents. Ce problème de ConnectTimeout était distinct de celui du WebSocketBadStatusException.

Clarification des IPs dans les logs :
Les logs montraient http://10.132.0.6:80/.well-known/agent.json qui a réussi. Puis, l'erreur ConnectTimeout s'est produite lors de "l'envoi du message" vers la même IP http://10.132.0.6:80. Ce n'était pas un problème de DNS à ce point, mais de persistance de connexion ou de timeout d'application.

Le besoin de forcer l'IP dans l'agent card était un contournement potentiel si l'agent interne lui-même publiait un FQDN que le Load Balancer Interne avait du mal à router après le premier appel, ce qui est un scénario plus rare où l'agent se réfère à lui-même via un FQDN non résolu correctement.

