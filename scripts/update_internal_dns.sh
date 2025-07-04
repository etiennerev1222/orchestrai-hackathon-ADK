#!/bin/bash

# Nom de la zone DNS et domaine racine
DNS_ZONE="internal-orchestrai"
DOMAIN="internal.orchestrai.ai"

# Récupération de l'adresse IP interne de l'ingress
INGRESS_NAME="internal-ingress-orchestrai"
IP=$(kubectl get ingress $INGRESS_NAME -o jsonpath='{.status.loadBalancer.ingress[0].ip}')

if [[ -z "$IP" ]]; then
  echo "❌ Aucune IP trouvée pour l'ingress $INGRESS_NAME"
  exit 1
fi

echo "✅ IP trouvée: $IP"
echo "📡 Mise à jour des enregistrements DNS..."

# Démarre une transaction DNS
gcloud dns record-sets transaction start --zone=$DNS_ZONE

# Supprime d'abord les anciens enregistrements si existants (safe)
for name in dev-agent env-manager; do
  gcloud dns record-sets list \
    --zone=$DNS_ZONE \
    --name="$name.$DOMAIN." \
    --type=A \
    --format=json |
  jq -c '.[]' | while read -r record; do
    TTL=$(echo $record | jq '.ttl')
    OLD_IP=$(echo $record | jq -r '.rrdatas[0]')
    gcloud dns record-sets transaction remove "$OLD_IP" \
      --name="$name.$DOMAIN." \
      --ttl=$TTL \
      --type=A \
      --zone=$DNS_ZONE
  done
done

# Ajoute les nouveaux enregistrements
for name in dev-agent env-manager; do
  gcloud dns record-sets transaction add "$IP" \
    --name="$name.$DOMAIN." \
    --ttl=300 \
    --type=A \
    --zone=$DNS_ZONE
done

# Exécute la transaction
gcloud dns record-sets transaction execute --zone=$DNS_ZONE

