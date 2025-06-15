import asyncio
import httpx
import firebase_admin
from firebase_admin import credentials, firestore
import os

GCP_PROJECT_ID = "orchestrai-hackathon"
SERVICE_REGISTRY_COLLECTION = "service_registry"

try:
    print("--- Initialisation de Firestore ---")
    cred = credentials.ApplicationDefault()
    firebase_admin.initialize_app(cred, {
        'projectId': GCP_PROJECT_ID,
    })
    db = firestore.client()
    print("✅ Connexion à Firestore réussie.")
except Exception as e:
    print(f"❌ ERREUR: Impossible d'initialiser Firestore. Avez-vous lancé 'gcloud auth application-default login' ?")
    print(f"   Détail de l'erreur: {e}")
    exit(1)


async def check_agent_health(agent_info: dict, client: httpx.AsyncClient):
    """Vérifie la santé d'un seul agent en utilisant son URL interne."""
    name = agent_info.get("name", "N/A")
    url = agent_info.get("internal_url")
    
    if not url:
        return name, "OFFLINE", "URL interne manquante dans la registry."

    health_url = url.rstrip("/") + "/health"
    
    try:
        response = await client.get(health_url, timeout=5.0)
        if response.status_code == 200:
            return name, "✅ ONLINE", f"Réponse 200 OK de {health_url}"
        else:
            return name, "❌ OFFLINE", f"Réponse {response.status_code} de {health_url}"
    except httpx.RequestError as e:
        return name, "❌ OFFLINE", f"Erreur de connexion à {health_url}: {e.__class__.__name__}"
    except Exception as e:
        return name, "❌ OFFLINE", f"Erreur inattendue: {e}"


async def main():
    """Fonction principale pour lire la registry et lancer les vérifications."""
    print("\n--- Lecture de la Service Registry ---")
    docs = db.collection(SERVICE_REGISTRY_COLLECTION).stream()
    
    agents_to_check = []
    for doc in docs:
        if doc.id == "gra_instance_config":
            continue
        
        agent_data = doc.to_dict()
        print(f"\nAgent trouvé: {agent_data.get('name')}")
        print(f"  ├─ public_url: {agent_data.get('public_url')}")
        print(f"  └─ internal_url: {agent_data.get('internal_url')}")
        agents_to_check.append(agent_data)

    if not agents_to_check:
        print("Aucun agent trouvé dans la registry.")
        return

    print("\n--- Lancement des Health Checks ---")
    async with httpx.AsyncClient() as client:
        tasks = [check_agent_health(agent, client) for agent in agents_to_check]
        results = await asyncio.gather(*tasks)

    print("\n--- État des Agents ---")
    for name, status, reason in results:
        print(f"{name}: {status} ({reason})")


if __name__ == "__main__":
    asyncio.run(main())