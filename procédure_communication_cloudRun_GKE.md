✅ Objectif
Permettre à un service Cloud Run d’appeler un agent interne (par ex. dev-agent.internal.orchestrai.ai) hébergé dans GKE via un Ingress privé, à l’aide de DNS privé et d’un VPC connector.

1. 🏗️ Créer l'Ingress interne sur GKE
Fichier k8s/internal-ingress-orchestrai.yaml :

yaml
￼Copier
￼Modifier
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: internal-ingress-orchestrai
  annotations:
    kubernetes.io/ingress.class: "gce-internal"
    networking.gke.io/internal-load-balancer-allow-global-access: "true"
spec:
  rules:
  - host: dev-agent.internal.orchestrai.ai
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: development-agent
            port:
              name: http
  - host: env-manager.internal.orchestrai.ai
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: environment-manager
            port:
              name: http
2. 🛠️ Adapter les services GKE pour l’Ingress
Modifier les services pour exposer les ports en NodePort :

yaml
￼Copier
￼Modifier
apiVersion: v1
kind: Service
metadata:
  name: development-agent
spec:
  type: NodePort
  selector:
    app: development-agent
  ports:
  - name: http
    port: 8080
    targetPort: 8080
Répéter pour environment-manager.

3. 🩺 Ajouter readinessProbe sur les Pods (ex: deployment)
yaml
￼Copier
￼Modifier
readinessProbe:
  httpGet:
    path: /health
    port: 8080
  initialDelaySeconds: 5
  periodSeconds: 10
Et implémenter /health endpoint dans vos services (si ce n'est pas encore fait).

4. 🌐 Créer un sous-réseau Proxy-only pour Ingress interne
bash
￼Copier
￼Modifier
gcloud compute networks subnets create proxy-only-subnet \
  --purpose=REGIONAL_MANAGED_PROXY \
  --role=ACTIVE \
  --region=europe-west1 \
  --network=default \
  --range=172.16.0.0/23
5. �� Créer la zone DNS privée
bash
￼Copier
￼Modifier
gcloud dns managed-zones create internal-orchestrai \
  --description="Zone DNS interne pour orchestrai.ai" \
  --dns-name="internal.orchestrai.ai." \
  --visibility="private" \
  --networks="default"
6. 📥 Ajouter les enregistrements DNS internes
bash
￼Copier
￼Modifier
gcloud dns record-sets transaction start --zone=internal-orchestrai

gcloud dns record-sets transaction add 10.132.0.12 \
  --name="dev-agent.internal.orchestrai.ai." \
  --ttl=300 \
  --type=A \
  --zone=internal-orchestrai

gcloud dns record-sets transaction add 10.132.0.12 \
  --name="env-manager.internal.orchestrai.ai." \
  --ttl=300 \
  --type=A \
  --zone=internal-orchestrai

gcloud dns record-sets transaction execute --zone=internal-orchestrai
7. 🔌 Créer un VPC Connector pour Cloud Run
bash
￼Copier
￼Modifier
gcloud compute networks vpc-access connectors create my-vpc-connector \
  --region=europe-west1 \
  --network=default \
  --range=192.168.99.0/28
8. 🔁 Mettre à jour Cloud Run avec accès VPC
⚠️ Important : utilisez bien --vpc-egress=all-traffic (et non --egress-settings).

bash
￼Copier
￼Modifier
gcloud run services update gra-server \
  --platform=managed \
  --region=europe-west1 \
  --vpc-connector=my-vpc-connector \
  --vpc-egress=all-traffic
Répéter pour tout autre service devant accéder à GKE (ex: development-agent, validator, etc.).

9. 🔍 Vérifier la résolution DNS depuis GKE
bash
￼Copier
￼Modifier
kubectl run -it --rm dnsutils --image=busybox:1.28 --restart=Never -- sh
# Depuis le shell :
nslookup dev-agent.internal.orchestrai.ai
exit
10. ✅ Vérifier depuis Cloud Run avec un job de test
Utilisez un job Cloud Run avec l’image curlimages/curl pour faire un curl sur l’Ingress :

bash
￼Copier
￼Modifier
gcloud beta run jobs create dns-test-job \
  --image=gcr.io/orchestrai-hackathon/dns-test-job \
  --region=europe-west1 \
  --vpc-connector=my-vpc-connector \
  --vpc-egress=all-traffic \
  --command="curl" \
  --args="http://dev-agent.internal.orchestrai.ai/.well-known/agent.json"
Et exécutez :

bash
￼Copier
￼Modifier
gcloud beta run jobs execute dns-test-job --region=europe-west1
