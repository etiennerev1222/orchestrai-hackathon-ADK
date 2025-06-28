
import asyncio
import argparse
import httpx
import os
import time
from google.cloud import firestore

async def main(project_id):
    os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
    db = firestore.Client(project=project_id)

    doc = db.collection("service_registry").document("DevelopmentAgentGKEv2").get()
    if not doc.exists:
        raise RuntimeError("❌ DevelopmentAgentGKEv2 non trouvé dans Firestore.")
    base_url = doc.to_dict().get("url")
    if not base_url:
        raise RuntimeError("❌ URL manquante dans Firestore.")
    print(f"🌐 Agent URL: {base_url}")

    async with httpx.AsyncClient(timeout=15) as client:
        # Envoyer une tâche simple
        payload = {
            "input": "Créer un fichier hello.txt avec le texte 'Hello from DevAgent'",
            "input_type": "text/plain"
        }
        r = await client.post(f"{base_url}/task", json=payload)
        r.raise_for_status()
        task_id = r.json().get("id")
        assert task_id, "❌ ID de tâche manquant"
        print(f"🧠 Tâche soumise: {task_id}")

        # Poller le statut jusqu’à complétion ou timeout
        for _ in range(30):
            r = await client.get(f"{base_url}/status?id={task_id}")
            r.raise_for_status()
            status = r.json().get("state")
            print(f"⏳ Statut: {status}")
            if status in ("COMPLETED", "FAILED"):
                break
            await asyncio.sleep(2)

        if status != "COMPLETED":
            raise RuntimeError(f"❌ Tâche non complétée, état final: {status}")
        print("✅ Tâche complétée avec succès")

        # Vérifie qu’un artefact a été produit
        task_data = r.json()
        artifacts = task_data.get("artifacts", [])
        if not artifacts:
            raise RuntimeError("❌ Aucun artefact généré par le DevelopmentAgent.")
        print(f"📦 Artefact généré : {artifacts[0]}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-id", required=True)
    args = parser.parse_args()
    asyncio.run(main(args.project_id))
