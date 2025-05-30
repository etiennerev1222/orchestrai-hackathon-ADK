# src/services/gra/server.py
import uvicorn
import logging
from fastapi import FastAPI, HTTPException, Body
from typing import Dict, Any, List
import firebase_admin
from firebase_admin import credentials, firestore
from pydantic import BaseModel, Field
import os # <-- AJOUT
from datetime import datetime, timezone # <-- AJOUT


# --- Initialisation de Firestore ---
# firebase_admin s'authentifiera automatiquement via la variable d'environnement
# GOOGLE_APPLICATION_CREDENTIALS que vous avez définie.
try:
    cred = credentials.ApplicationDefault()
    firebase_admin.initialize_app(cred)
    db = firestore.client()
    logger = logging.getLogger("uvicorn")
    logger.info("Connexion à Firestore réussie.")
except Exception as e:
    logging.basicConfig()
    logging.critical(f"Impossible de se connecter à Firestore. Assurez-vous que GOOGLE_APPLICATION_CREDENTIALS est bien configuré. Erreur: {e}")
    exit(1)
# ------------------------------------


# --- AJOUT : Configuration de l'URL publique du GRA ---
# Cette URL sera celle à laquelle les autres services peuvent atteindre le GRA.
# Dans un environnement cloud, elle pourrait être injectée via une variable d'env.
# Pour le développement local, vous pouvez la coder en dur ou la mettre dans une var d'env.
GRA_PUBLIC_URL = os.environ.get("GRA_PUBLIC_URL", "http://localhost:8000")
GRA_SERVICE_REGISTRY_COLLECTION = "service_registry"
GRA_CONFIG_DOCUMENT_ID = "gra_instance_config"

# --- Modèles de données Pydantic pour la validation ---
class AgentRegistration(BaseModel):
    name: str = Field(..., description="Nom unique de l'agent, ex: 'ReformulatorAgent'")
    url: str = Field(..., description="URL de base de l'agent, ex: 'http://localhost:8001'")
    skills: List[str] = Field(..., description="Liste des compétences, ex: ['reformulation']")

class Artifact(BaseModel):
    task_id: str
    context_id: str | None = None
    agent_name: str
    content: Dict[str, Any] | str

# --- Endpoints du Registre d'Agents ---
# --- AJOUT : Gestionnaire de durée de vie de l'application FastAPI ---
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    await publish_gra_location()
    yield
    # Ajoutez ici tout nettoyage nécessaire lors de l'arrêt de l'application

app = FastAPI(
    title="Gestionnaire de Ressources et d'Agents (GRA)",
    description="Service central pour l'enregistrement des agents et le stockage des artefacts.",
    version="1.0.0",
    lifespan=lifespan
)
@app.post("/register", status_code=201)
async def register_agent(agent: AgentRegistration):
    """Enregistre un agent ou met à jour ses informations."""
    try:
        agent_ref = db.collection("agents").document(agent.name)
        agent_ref.set(agent.model_dump())
        logger.info(f"Agent '{agent.name}' enregistré/mis à jour.")
        return {"status": "success", "agent_name": agent.name}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/agents")
async def find_agent(skill: str):
    """Trouve un agent possédant une compétence spécifique."""
    try:
        agents_ref = db.collection("agents").where("skills", "array_contains", skill).limit(1)
        agents = list(agents_ref.stream())
        if not agents:
            raise HTTPException(status_code=404, detail=f"Aucun agent trouvé avec la compétence: {skill}")
        
        agent_data = agents[0].to_dict()
        logger.info(f"Agent trouvé pour la compétence '{skill}': {agent_data.get('name')}")
        return {"name": agent_data.get("name"), "url": agent_data.get("url")}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- Endpoints du Magasin d'Artefacts ---

@app.post("/artifacts", status_code=201)
async def store_artifact(artifact: Artifact):
    """Stocke un artefact et retourne son ID unique."""
    try:
        # Ajoute l'artefact à la collection, Firestore génère un ID unique
        update_time, doc_ref = db.collection("artifacts").add(artifact.model_dump())
        logger.info(f"Artefact stocké avec l'ID: {doc_ref.id}")
        return {"status": "success", "artifact_id": doc_ref.id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/artifacts/{artifact_id}")
async def get_artifact(artifact_id: str):
    """Récupère un artefact par son ID."""
    try:
        doc_ref = db.collection("artifacts").document(artifact_id)
        doc = doc_ref.get()
        if not doc.exists:
            raise HTTPException(status_code=404, detail="Artefact non trouvé")
        logger.info(f"Artefact '{artifact_id}' récupéré.")
        return doc.to_dict()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- AJOUT : Fonction pour publier l'URL du GRA ---
async def publish_gra_location():
    try:
        doc_ref = db.collection(GRA_SERVICE_REGISTRY_COLLECTION).document(GRA_CONFIG_DOCUMENT_ID)
        doc_data = {
            "service_name": "GestionnaireRessourcesAgents",
            "current_url": GRA_PUBLIC_URL,
            "last_heartbeat": datetime.now(timezone.utc).isoformat()
        }
        doc_ref.set(doc_data)
        logger.info(f"URL du GRA ({GRA_PUBLIC_URL}) publiée dans Firestore sur '{GRA_SERVICE_REGISTRY_COLLECTION}/{GRA_CONFIG_DOCUMENT_ID}'.")
    except Exception as e:
        logger.error(f"Impossible de publier l'URL du GRA dans Firestore : {e}")
# -------------------------------------------------


if __name__ == "__main__":
    logger.info("Démarrage du serveur du Gestionnaire de Ressources et d'Agents (GRA)...")
    uvicorn.run(app, host="localhost", port=8000)
