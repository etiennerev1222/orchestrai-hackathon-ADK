# Get the URL of your deployed Cloud Run Test Service
SERVICE_URL=$(gcloud run services describe gke-connectivity-tester3 --region=europe-west1 --format="value(status.url)")
# Get an ID Token to authenticate with your Cloud Run Test Service itself
ID_TOKEN=$(gcloud auth print-identity-token)

echo "🌐 URL du service de test Cloud Run : ${SERVICE_URL}"
echo "Calling /test-dns_lookup..."
curl -H "Authorization: Bearer ${ID_TOKEN}" "${SERVICE_URL}/test-dns-lookup?hostname=development-agent.default.svc.cluster.local"

echo -e "\nCalling /test-dig..."
curl -H "Authorization: Bearer ${ID_TOKEN}" "${SERVICE_URL}/test-dig?hostname=development-agent.default.svc.cluster.local"

echo -e "\nCalling /test-ping..."
curl -H "Authorization: Bearer ${ID_TOKEN}" "${SERVICE_URL}/test-ping?target=34.118.224.10"

echo -e "\n--- Fin des invocations de test ---"
