
import asyncio
import argparse
import httpx
import os
from google.cloud import firestore
import logging
import firebase_admin
from firebase_admin import credentials, firestore
import os

async def main(project_id):

    if os.environ.get('K_SERVICE'):
        cred = credentials.ApplicationDefault()
    else:
        cred_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
        if not cred_path:
            raise ValueError("En local, la variable d'environnement GOOGLE_APPLICATION_CREDENTIALS doit être définie.")
        cred = credentials.Certificate(cred_path)

    base_url = "http://localhost:8000"  # Valeur par défaut pour les tests locaux
    if not base_url:
        raise RuntimeError("❌ URL manquante dans le document Firestore.")
    print(f"🌐 URL détectée: {base_url}")

    async with httpx.AsyncClient(timeout=10) as client:
        # /health
        r = await client.get(f"{base_url}/health")
        r.raise_for_status()
        print("✅ /health OK")

        # Create environment
        payload = {"environment_id": "test-env", "base_image": "gcr.io/orchestrai-hackathon/python-devtools:1751122256"}
        r = await client.post(f"{base_url}/create_environment", json=payload)
        r.raise_for_status()
        env_id = r.json().get("environment_id")
        assert env_id, "❌ environment_id manquant dans la réponse"
        print(f"✅ Environnement créé: {env_id}")

        # Write file
        r = await client.post(f"{base_url}/upload_to_environment", json={
            "environment_id": env_id,
            "path": "/app/hello.txt",
            "content": "Hello, Environment!"
        })
        r.raise_for_status()
        print("✅ Fichier écrit")

        # Read file
        r = await client.post(f"{base_url}/download_from_environment", json={
            "environment_id": env_id,
            "path": "/app/hello.txt"
        })
        r.raise_for_status()
        content = r.json().get("content")
        assert content == "Hello, Environment!", f"❌ Contenu inattendu: {content}"
        print("✅ Fichier lu avec succès")

        # Delete environment
        r = await client.post(f"{base_url}/delete_environment", json={"environment_id": env_id})
        r.raise_for_status()
        print("✅ Environnement supprimé")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-id", required=True)
    args = parser.parse_args()
    asyncio.run(main(args.project_id))
