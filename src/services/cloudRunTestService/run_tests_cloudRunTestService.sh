#!/bin/bash
set -e

# --- Config ---
PROJECT_ID="orchestrai-hackathon"
SERVICE_NAME="gke-connectivity-tester4"
REGION="europe-west1"
CLOUD_RUN_URL=$(gcloud run services describe $SERVICE_NAME --region=$REGION --format='value(status.url)')
AUTH_HEADER="Authorization: Bearer $(gcloud auth print-identity-token)"
JSON_HEADER="Content-Type: application/json"

# --- Paramètre cible ---
if [ -n "$1" ]; then
  TARGET_HOST="$1"
else
  read -p "Nom DNS ou IP cible (par ex. dev-agent.internal.example.com ) : " TARGET_HOST
fi

echo "🌐 URL du service Cloud Run : $CLOUD_RUN_URL"
echo "🎯 Hôte cible : $TARGET_HOST"

# --- Menu ---
echo "=== Sélectionnez le test à exécuter ==="
echo "1. Résolution DNS (FQDN)"
echo "2. Résolution dig directe"
echo "3. Ping"
echo "4. Test /run-tests (FQDN + Auth)"
echo "5. Test /run-direct-ip-tests (IP LB + Auth)"
echo "6. Tous les tests ci-dessus"
read -p "Choix [1-6] : " CHOICE

run_dns_lookup() {
    echo "🔍 DNS Lookup..."
    curl -s "${CLOUD_RUN_URL}/test-dns-lookup?hostname=$TARGET_HOST"
}

run_dig_direct() {
    echo "🔍 Dig direct via kube-dns..."
    curl -s "${CLOUD_RUN_URL}/test-dig-direct?hostname=$TARGET_HOST"
}

run_ping() {
    echo "📡 Ping..."
    curl -s "${CLOUD_RUN_URL}/test-ping?target=$TARGET_HOST&count=3"
}

run_connectivity_tests() {
    echo "🧪 Connectivité FQDN..."
    curl -s -H "$AUTH_HEADER" "$CLOUD_RUN_URL/run-tests"
}

run_connectivity_direct_ip() {
    echo "🧪 Connectivité IP directe..."
    curl -s -H "$AUTH_HEADER" "$CLOUD_RUN_URL/run-direct-ip-tests"
}

case $CHOICE in
  1) run_dns_lookup ;;
  2) run_dig_direct ;;
  3) run_ping ;;
  4) run_connectivity_tests ;;
  5) run_connectivity_direct_ip ;;
  6)
    run_dns_lookup
    echo "—"
    run_dig_direct
    echo "—"
    run_ping
    echo "—"
    run_connectivity_tests
    echo "—"
    run_connectivity_direct_ip
    ;;
  *) echo "⛔ Choix invalide" ;;
esac
