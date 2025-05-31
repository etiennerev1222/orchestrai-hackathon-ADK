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
# --- NOUVEAUX Modèles Pydantic pour le Front-End ---
class NewPlanRequest(BaseModel):
    objective: str

class PlanSummary(BaseModel):
    plan_id: str
    objective: str
    status: str # ex: "running", "completed", "failed"
    created_at: str | None = None  # Optionnel, si vous stockez cette info

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
# --- NOUVEAUX Endpoints pour le Front-End des Plans ---

@app.post("/plans", status_code=202) # 202 Accepted car le traitement est asynchrone
async def create_new_plan_endpoint(plan_request: NewPlanRequest):
    """Crée un nouveau plan et démarre son traitement."""
    from src.orchestrators.planning_supervisor_logic import PlanningSupervisorLogic # Import local
    
    plan_id = f"plan_{uuid.uuid4().hex[:12]}"
    logger.info(f"[GRA] Requête de création de plan reçue. ID: {plan_id}, Objectif: {plan_request.objective}")
    
    try:
        # Le superviseur est instancié ici pour ce plan spécifique
        supervisor = PlanningSupervisorLogic(max_revisions=2)
        supervisor.create_new_plan(raw_objective=plan_request.objective, plan_id=plan_id)
        
        # Lancer process_plan en tâche de fond pour ne pas bloquer la requête HTTP
        # Note : Pour une application de production, un vrai gestionnaire de tâches (Celery, RQ) serait mieux.
        asyncio.create_task(supervisor.process_plan(plan_id=plan_id))
        
        logger.info(f"[GRA] Plan '{plan_id}' créé et traitement démarré en arrière-plan.")
        return {"message": "Plan creation initiated.", "plan_id": plan_id}
    except Exception as e:
        logger.error(f"[GRA] Erreur lors de la création du plan '{plan_id}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erreur interne lors de la création du plan: {str(e)}")

@app.get("/plans", response_model=List[PlanSummary])
async def get_all_plans_summary():
    """Récupère un résumé de tous les plans, triés par date de création descendante."""
    summaries: List[PlanSummary] = []
    try:
        # 'task_graphs' est la collection où les détails des plans sont stockés
        plans_ref = db.collection("task_graphs").stream() 
        
        for doc in plans_ref:
            plan_data = doc.to_dict()
            plan_id = doc.id
            # Le nœud racine du plan a le même ID que le plan lui-même
            root_node_data = plan_data.get("nodes", {}).get(plan_id, {})
            
            created_at_timestamp = "N/A" # Valeur par défaut
            history = root_node_data.get("history", [])
            if history and isinstance(history, list) and len(history) > 0:
                # Le premier enregistrement de l'historique devrait correspondre à la création/soumission
                # ou à la première mise à jour d'état, qui inclut un timestamp.
                # Si la tâche racine est créée avec un état SUBMITTED, son premier history entry
                # lors du passage à WORKING ou COMPLETED aura le timestamp.
                # Pour être plus précis, on pourrait chercher le timestamp du premier état "submitted"
                # ou simplement prendre le premier de la liste si la structure est cohérente.
                # Prenons le timestamp du tout premier événement de l'historique du nœud racine.
                first_event = history[0]
                created_at_timestamp = first_event.get("timestamp", "N/A")

            summaries.append(PlanSummary(
                plan_id=plan_id,
                objective=root_node_data.get("objective", "Objectif non trouvé"),
                status=root_node_data.get("state", "inconnu"),
                created_at=created_at_timestamp # <-- Le timestamp est maintenant inclus
            ))
            
        logger.info(f"[GRA] {len(summaries)} plans résumés récupérés bruts.")
        
        # Trier la liste summaries par created_at en ordre descendant
        # Gérer les cas où created_at pourrait être "N/A" ou None pour éviter les erreurs de tri
        summaries.sort(key=lambda p: p.created_at if p.created_at and p.created_at != "N/A" else "", reverse=True)
        
        logger.info(f"[GRA] {len(summaries)} plans résumés triés retournés.")
        return summaries
    except Exception as e:
        logger.error(f"[GRA] Erreur lors de la récupération des résumés de plans: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/plans/{plan_id}")
async def get_plan_details_endpoint(plan_id: str):
    """Récupère les détails complets (TaskGraph) d'un plan spécifique."""
    try:
        # La classe TaskGraph elle-même peut lire son document
        from src.shared.task_graph_management import TaskGraph # Import local
        graph_manager = TaskGraph(plan_id=plan_id)
        plan_data = graph_manager.as_dict() # Utilise la méthode existante qui lit depuis Firestore
        if not plan_data.get("nodes"): # Vérifie si le plan existe vraiment ou est vide
            raise HTTPException(status_code=404, detail=f"Plan '{plan_id}' non trouvé ou vide.")
        logger.info(f"[GRA] Détails du plan '{plan_id}' récupérés.")
        return plan_data
    except HTTPException:
        raise # Re-lever les exceptions HTTP pour que FastAPI les gère
    except Exception as e:
        logger.error(f"[GRA] Erreur lors de la récupération des détails du plan '{plan_id}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

# --- Endpoint pour le statut des agents (simplifié) ---
@app.get("/agents_status")
async def get_agents_status_endpoint():
    """Récupère la liste des agents enregistrés."""
    agents_list = []
    try:
        agents_ref = db.collection("agents").stream() # Nom de collection des agents enregistrés
        for doc in agents_ref:
            agents_list.append(doc.to_dict())
        logger.info(f"[GRA] Statut de {len(agents_list)} agents récupéré.")
        return agents_list
    except Exception as e:
        logger.error(f"[GRA] Erreur lors de la récupération du statut des agents: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))



if __name__ == "__main__":
    logger.info("Démarrage du serveur du Gestionnaire de Ressources et d'Agents (GRA)...")
    uvicorn.run(app, host="localhost", port=8000)
