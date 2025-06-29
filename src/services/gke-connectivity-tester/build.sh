# Naviguez à la racine de votre projet si ce n'est pas déjà fait
# cd ~/Documents/POC/googleAgentADKProject/orchestrai-hackathon-ADK

# Remplacez <votre-projet-id> par votre ID de projet GCP réel
PROJECT_ID="orchestrai-hackathon" 

echo "🚀 Construction de l'image Docker pour le Cloud Run Test Service..."
# FIX: Spécifiez le répertoire source où se trouve le Dockerfile
gcloud builds submit src/services/gke-connectivity-tester --tag gcr.io/${PROJECT_ID}/gke-connectivity-tester4 --project=${PROJECT_ID} 

echo "✅ Image construite et poussée : gcr.io/${PROJECT_ID}/gke-connectivity-tester4"
