import uvicorn
import logging

import httpx
from typing import Dict, Any, List, Optional
import firebase_admin
from firebase_admin import credentials, firestore
from pydantic import BaseModel, Field
import os
import io
from datetime import datetime, timezone

import asyncio
import uuid
from collections import Counter
from fastapi import FastAPI, HTTPException, Body, Path, File, UploadFile, Form, Depends
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import json
from src.shared.execution_task_graph_management import ExecutionTaskGraph
from src.services.environment_manager.environment_manager import EnvironmentManager
from kubernetes import client
from src.orchestrators.global_supervisor_logic import GlobalSupervisorLogic, GlobalPlanState 
from starlette.websockets import WebSocket, WebSocketDisconnect
from src.shared.agent_state import AgentOperationalState
import google.auth
from google.oauth2 import id_token
from google.auth.transport.requests import Request as GoogleAuthRequest

from starlette.applications import Starlette

logger = logging.getLogger(__name__)
def json_serializer(obj):
    """
    Traducteur JSON robuste pour les objets non sérialisables par défaut.
    Utilise le "duck typing" pour éviter les problèmes d'import.
    """
    # Si l'objet vient de Firestore, il a une méthode .ToDatetime()
    # On le convertit d'abord en objet datetime standard de Python.
    if hasattr(obj, 'ToDatetime'):
        obj = obj.ToDatetime()

    # Maintenant, si l'objet a une méthode .isoformat() (comme les datetime et date),
    # on l'utilise pour le convertir en chaîne de caractères.
    if hasattr(obj, 'isoformat'):
        return obj.isoformat()

    # Si on ne peut toujours pas le sérialiser, on lève une erreur.
    raise TypeError(f"Type {type(obj)} not serializable for JSON")
# ----------------------------------------------------

# --------------------------

from src.shared.firebase_init import db
if db is None:
    logger.critical("CRITICAL: Échec de l'obtention du client Firestore depuis firebase_init. Arrêt du serveur GRA.")
    exit(1)
else:
    logger.info("GRA Server: Client Firestore obtenu avec succès depuis firebase_init.")

GRA_PUBLIC_URL = os.environ.get("GRA_PUBLIC_URL", "http://localhost:8000")
GRA_SERVICE_REGISTRY_COLLECTION = "service_registry"
GRA_CONFIG_DOCUMENT_ID = "gra_instance_config"
GLOBAL_PLANS_FIRESTORE_COLLECTION = "global_plans"

class AgentRegistration(BaseModel):
    name: str = Field(..., alias="agent_name")
    public_url: str
    internal_url: str
    skills: List[str] = []

class Artifact(BaseModel):
    task_id: str
    context_id: str | None = None
    agent_name: str
    content: Dict[str, Any] | str

class GlobalPlanCreateRequest(BaseModel):
    objective: str = Field(..., min_length=1, description="Objectif brut soumis par l'utilisateur.")
    user_id: Optional[str] = "default_user"

class GlobalPlanResponse(BaseModel):
    status: str
    message: Optional[str] = None
    question: Optional[str] = None
    clarified_objective: Optional[str] = None
    task_type_estimation: Optional[str] = None
    global_plan_id: str
    current_supervisor_state: Optional[str] = None

class UserClarificationRequest(BaseModel):
    user_response: str = Field(..., min_length=1, description="Réponse de l'utilisateur à une question de clarification.")

class GlobalPlanDetailResponse(BaseModel):
    global_plan_id: str
    user_id: str
    raw_objective: str
    clarified_objective: Optional[str] = None
    current_supervisor_state: str
    task_type_estimation: Optional[str] = None
    last_question_to_user: Optional[str] = None
    conversation_history: List[Dict[str, str]] = []
    clarification_attempts: int = 0
    team1_plan_id: Optional[str] = None
    team2_execution_plan_id: Optional[str] = None
    environment_id: Optional[str] = None
    created_at: str
    updated_at: str
    last_agent_response_artifact: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None

class GlobalPlanSummaryItem(BaseModel):
    global_plan_id: str
    raw_objective: str
    current_supervisor_state: str
    task_type_estimation: Optional[str] = None
    environment_id: Optional[str] = None
    created_at: str
    updated_at: str

from contextlib import asynccontextmanager
class NewPlanRequest(BaseModel):
    objective: str

class PlanSummary(BaseModel):
    plan_id: str
    objective: str
    status: str
    created_at: str | None = None

class AcceptObjectiveRequest(BaseModel):
    user_final_objective: Optional[str] = None 

class AgentTaskCountStat(BaseModel):
    agent_name: str
    task_count: int

class Team1AgentTasksCountResponse(BaseModel):
    stats: List[AgentTaskCountStat]
    last_updated: str

class AllAgentTaskStats(BaseModel):
    agent_name: str
    task_count: int
    source_type: str

class AllAgentTasksStatsResponse(BaseModel):
    stats: List[AllAgentTaskStats]
    last_updated: str


# --- NOUVEAU : Gestionnaire de connexions WebSocket ---
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)

manager = ConnectionManager()
# Cache in-memory des statuts des agents.
agent_statuses: Dict[str, Dict[str, Any]] = {}
# Statut interne du serveur GRA lui-même.
gra_status: Dict[str, Any] = {
    "state": "starting",
    "detail": "Initialization",
    "last_update": datetime.now(timezone.utc).isoformat(),
}
class GoogleIDTokenAuth(httpx.Auth):
    """
    Classe d'authentification pour httpx qui injecte un Google ID Token.
    """
    def __init__(self):
        try:
            self._creds, _ = google.auth.default()
            self._auth_request = GoogleAuthRequest()
        except google.auth.exceptions.DefaultCredentialsError:
            self._creds = None
            logger.warning("Auth: Impossible d'obtenir les credentials Google. Les requêtes ne seront pas authentifiées.")

    def auth_flow(self, request: httpx.Request):
        if not self._creds:
            yield request
            return
        try:
            audience = f"{request.url.scheme}://{request.url.host}"
            token = id_token.fetch_id_token(self._auth_request, audience)
            request.headers["Authorization"] = f"Bearer {token}"
            logger.debug(f"Jeton d'authentification ajouté pour l'audience : {audience}")
        except Exception as e:
            logger.error(f"Erreur lors de la récupération du jeton d'authentification Google : {e}", exc_info=True)
        yield request

# --- Fonction utilitaire pour remplacer l'import de Werkzeug ---
import re
_filename_ascii_strip_re = re.compile(r"[^A-Za-z0-9_.-]")

def secure_filename(filename: str) -> str:
    """
    Fonction de sanitisation de nom de fichier, inspirée de werkzeug.
    Cela évite d'avoir à installer la dépendance complète.
    """
    if not filename:
        return ""
    # Gère les cas avec des séparateurs de chemin pour ne garder que le nom de base
    filename = os.path.basename(filename)
    # Remplace les caractères non-ASCII et non sécurisés par un vide
    ascii_name = _filename_ascii_strip_re.sub("", filename)
    # S'assure que le nom de fichier ne commence pas par un point (fichier caché)
    if ascii_name.startswith("."):
        ascii_name = ascii_name.lstrip('.')
    if not ascii_name:
        return "_fallback_filename"
    return ascii_name

@asynccontextmanager
async def lifespan(app: Starlette):
    """
    MODIFIÉ : Gère le cycle de vie, y compris l'initialisation du cache au démarrage.
    """
    logger.info("[GRA] Démarrage du cycle de vie (lifespan)...")
    gra_status.update(
        {
            "state": "starting",
            "detail": "Loading cache",
            "last_update": datetime.now(timezone.utc).isoformat(),
        }
    )
    
    # --- BLOC À AJOUTER : Initialisation du cache des statuts ---
    logger.info("[GRA] Initialisation du cache des statuts depuis Firestore...")
    if not db:
        logger.error("[GRA] La base de données Firestore n'est pas disponible. Le cache ne sera pas initialisé.")
    else:
        try:
            docs_stream = db.collection("service_registry").stream()
            for doc in docs_stream:
                if doc.id != 'gra_instance_config':
                    agent_data = doc.to_dict()
                    agent_name = agent_data.get("name")
                    if agent_name:
                        # On initialise l'agent avec un statut "Offline" par défaut.
                        # S'il est en ligne, il enverra sa mise à jour peu après.
                        agent_data["health_status"] = {"state": "Offline"}
                        agent_statuses[agent_name] = agent_data
            logger.info(f"[GRA] Cache initialisé avec {len(agent_statuses)} agents depuis Firestore.")
        except Exception as e:
            logger.error(f"[GRA] Erreur lors de l'initialisation du cache depuis Firestore: {e}", exc_info=True)
    # -----------------------------------------------------------
    gra_status.update(
        {
            "state": "running",
            "detail": "Ready",
            "last_update": datetime.now(timezone.utc).isoformat(),
        }
    )
    await manager.broadcast(
        json.dumps({"gra_status": gra_status, "agents": list(agent_statuses.values())}, default=json_serializer)
    )
    await publish_gra_location()

    yield  # L'application tourne ici

    gra_status.update(
        {
            "state": "stopped",
            "detail": "Server shutdown",
            "last_update": datetime.now(timezone.utc).isoformat(),
        }
    )
    await manager.broadcast(
        json.dumps({"gra_status": gra_status, "agents": list(agent_statuses.values())}, default=json_serializer)
    )
    logger.info("[GRA] Arrêt du cycle de vie (lifespan)...")


app = FastAPI(
    title="Gestionnaire de Ressources et d'Agents (GRA)",
    description="Service central pour l'enregistrement des agents et le stockage des artefacts.",
    version="1.0.0",
    lifespan=lifespan
)

@app.get("/health")
async def healthcheck():
    return {"status": "ok"}


@app.get("/gra_status")
async def get_gra_status():
    """Retourne le statut actuel du serveur GRA."""
    return gra_status

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8080","https://orchestrai-hackathon.web.app","http://user_interaction_agent:8080:"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Instanciation du EnvironmentManager
try:
    environment_manager = EnvironmentManager()
    logging.info("EnvironmentManager initialized successfully.")
except Exception as e:
    logging.error(f"Failed to initialize EnvironmentManager: {e}", exc_info=True)
    environment_manager = None

@app.post("/register", status_code=201)
async def register_agent(payload: AgentRegistration):
    """Point de terminaison pour que les agents puissent s'enregistrer."""
    try:
        agent_ref = db.collection("service_registry").document(payload.name)
        
        agent_data = {
            "name": payload.name,
            "public_url": payload.public_url,
            "internal_url": payload.internal_url,
            "skills": payload.skills,
            "timestamp": firestore.SERVER_TIMESTAMP
        }
        
        await asyncio.to_thread(agent_ref.set, agent_data)
        logger.info(f"Agent '{payload.name}' enregistré/mis à jour.")
        return {"status": "success", "name": payload.name}
    except Exception as e:
        logger.error(f"Erreur enregistrement agent '{payload.name}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/register", status_code=201)
async def register_agent(payload: AgentRegistration):
    """Point de terminaison pour que les agents puissent s'enregistrer ou mettre à jour leur statut."""
    try:
        agent_ref = db.collection("service_registry").document(payload.name)
        
        agent_data = {
            "name": payload.name,
            "public_url": payload.public_url,
            "internal_url": payload.internal_url,
            "skills": payload.skills,
            "timestamp": firestore.SERVER_TIMESTAMP
        }
        
        await asyncio.to_thread(agent_ref.set, agent_data)
        
        logger.info(f"Agent '{payload.name}' enregistré/mis à jour.")
        return {"status": "success", "name": payload.name}
        
    except Exception as e:
        logger.error(f"Erreur enregistrement agent '{payload.name}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/agents", response_model=List[Dict[str, Any]])
async def get_agents(skill: Optional[str] = None):
    """
    Récupère les agents. Si une compétence ('skill') est fournie, filtre les résultats.
    Cette fonction retourne TOUJOURS une liste d'agents.
    """
    try:
        agents_ref = db.collection(GRA_SERVICE_REGISTRY_COLLECTION)

        if skill:
            logger.info(f"Recherche d'agents avec la compétence: {skill}")
            query = agents_ref.where("skills", "array_contains", skill)
        else:
            logger.info("Récupération de tous les agents enregistrés.")
            query = agents_ref

        docs_snapshots = await asyncio.to_thread(list, query.stream())
        if not docs_snapshots:
            logger.warning(f"Aucun agent trouvé pour la compétence '{skill}'. Retour de 404.")
            raise HTTPException(status_code=404, detail=f"Aucun agent trouvé avec la compétence: {skill}")
   
        agents = []
        for doc in docs_snapshots:
            if doc.id != GRA_CONFIG_DOCUMENT_ID:
                agent_data = doc.to_dict()
                agent_data['id'] = doc.id
                agents.append(agent_data)

        logger.info(f"{len(agents)} agents trouvés pour la requête.")
        return agents
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.error(f"Erreur interne lors de la recherche d'agent pour la compétence '{skill}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erreur interne du serveur lors de la recherche d'agent.")
    


@app.post("/v1/global_plans", response_model=GlobalPlanResponse, status_code=202)
async def create_global_plan(plan_request: GlobalPlanCreateRequest):
    """
    Crée un nouveau plan global et initie la clarification de l'objectif.
    """
    logger.info(f"[GRA API] Requête de création de plan global reçue. Objectif: {plan_request.objective}")
    try:
        supervisor = GlobalSupervisorLogic()
        result = await supervisor.start_new_global_plan(
            raw_objective=plan_request.objective,
            user_id=plan_request.user_id
        )
        
        return GlobalPlanResponse(**result)
    except ConnectionError as e:
        logger.error(f"[GRA API] Erreur de connexion lors de la création du plan: {e}", exc_info=True)
        raise HTTPException(status_code=503, detail=f"Erreur de service: {str(e)}")
    except Exception as e:
        logger.error(f"[GRA API] Erreur interne lors de la création du plan global: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erreur interne du serveur: {str(e)}")


@app.post("/v1/global_plans/{global_plan_id}/respond", response_model=GlobalPlanResponse)
async def respond_to_clarification_question(
    global_plan_id: str = Path(..., description="L'ID du plan global."),
    user_input: UserClarificationRequest = Body(...)
):
    """
    Soumet la réponse d'un utilisateur à une question de clarification pour un plan global.
    """
    logger.info(f"[GRA API] Réponse utilisateur pour plan '{global_plan_id}': {user_input.user_response}")
    try:
        supervisor = GlobalSupervisorLogic()
        result = await supervisor.process_user_clarification_response(
            global_plan_id=global_plan_id,
            user_response=user_input.user_response
        )

        return GlobalPlanResponse(**result)
    except Exception as e:
        logger.error(f"[GRA API] Erreur traitement réponse utilisateur pour plan '{global_plan_id}': {e}", exc_info=True)
        if "non trouvé" in str(e).lower():
             raise HTTPException(status_code=404, detail=f"Plan global '{global_plan_id}' non trouvé.")
        raise HTTPException(status_code=500, detail=f"Erreur interne du serveur: {str(e)}")


@app.get("/v1/global_plans/{global_plan_id}", response_model=GlobalPlanDetailResponse)
async def get_global_plan_details(
    global_plan_id: str = Path(..., description="L'ID du plan global.")
):
    """
    Récupère les détails complets et l'état actuel d'un plan global.
    """
    logger.info(f"[GRA API] Demande de détails pour plan global '{global_plan_id}'")
    try:
        supervisor = GlobalSupervisorLogic()
        plan_details = await supervisor._load_global_plan_state(global_plan_id)
        
        if not plan_details:
            raise HTTPException(status_code=404, detail=f"Plan global '{global_plan_id}' non trouvé.")
        
        plan_details['global_plan_id'] = global_plan_id
        
        response_data = {
            "global_plan_id": plan_details.get('global_plan_id', global_plan_id),
            "user_id": plan_details.get('user_id', 'N/A'),
            "raw_objective": plan_details.get('raw_objective', 'N/A'),
            "clarified_objective": plan_details.get('clarified_objective'),
            "current_supervisor_state": plan_details.get('current_supervisor_state', 'UNKNOWN'),
            "task_type_estimation": plan_details.get('task_type_estimation'),
            "last_question_to_user": plan_details.get('last_question_to_user'),
            "conversation_history": plan_details.get('conversation_history', []),
            "clarification_attempts": plan_details.get('clarification_attempts', 0),
            "team1_plan_id": plan_details.get('team1_plan_id'),
            "team2_execution_plan_id": plan_details.get('team2_execution_plan_id'),
            "environment_id": plan_details.get('environment_id') or EnvironmentManager.normalize_environment_id(global_plan_id),
            "created_at": plan_details.get('created_at', datetime.now(timezone.utc).isoformat()),
            "updated_at": plan_details.get('updated_at', datetime.now(timezone.utc).isoformat()),
            "last_agent_response_artifact": plan_details.get('last_agent_response_artifact'),
            "error_message": plan_details.get('error_message')
        }
        return GlobalPlanDetailResponse(**response_data)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[GRA API] Erreur récupération détails plan '{global_plan_id}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erreur interne du serveur: {str(e)}")


@app.get("/v1/global_plans_summary", response_model=List[GlobalPlanSummaryItem])
async def get_all_global_plans_summary():
    """
    Récupère un résumé de tous les plans globaux, triés par date de mise à jour descendante.
    """
    logger.info("[GRA API] Demande de résumé de tous les plans globaux.")
    summaries: List[GlobalPlanSummaryItem] = []
    if not db:
        logger.error("[GRA API] Client Firestore non disponible pour get_all_global_plans_summary.")
        raise HTTPException(status_code=500, detail="Service de base de données non disponible.")
    try:
        docs = await asyncio.to_thread(
            lambda: list(
                db.collection(GLOBAL_PLANS_FIRESTORE_COLLECTION)
                .order_by("updated_at", direction=firestore.Query.DESCENDING)
                .stream()
            )
        )

        for doc in docs:
            plan_data = doc.to_dict()
            if plan_data:
                summaries.append(GlobalPlanSummaryItem(
                    global_plan_id=doc.id,
                    raw_objective=plan_data.get("raw_objective", "Objectif non disponible"),
                    current_supervisor_state=plan_data.get("current_supervisor_state", "État inconnu"),
                    task_type_estimation=plan_data.get("task_type_estimation"),
                    environment_id=plan_data.get("environment_id") or EnvironmentManager.normalize_environment_id(doc.id),
                    created_at=plan_data.get("created_at", ""),
                    updated_at=plan_data.get("updated_at", "")
                ))
        
        logger.info(f"[GRA API] {len(summaries)} résumés de plans globaux récupérés.")
        return summaries
    except Exception as e:
        logger.error(f"[GRA API] Erreur lors de la récupération des résumés de plans globaux: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erreur interne du serveur: {str(e)}")


@app.post("/artifacts", status_code=201)
async def store_artifact(artifact: Artifact):
    """Stocke un artefact et retourne son ID unique."""
    try:
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

@app.post("/plans", status_code=202)
async def create_new_plan_endpoint(plan_request: NewPlanRequest):
    """Crée un nouveau plan et démarre son traitement."""
    from src.orchestrators.planning_supervisor_logic import PlanningSupervisorLogic
    
    plan_id = f"plan_{uuid.uuid4().hex[:12]}"
    logger.info(f"[GRA] Requête de création de plan reçue. ID: {plan_id}, Objectif: {plan_request.objective}")
    
    try:
        supervisor = PlanningSupervisorLogic(max_revisions=2)
        supervisor.create_new_plan(raw_objective=plan_request.objective, plan_id=plan_id)
        
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
        plans_ref = db.collection("task_graphs").stream() 
        
        for doc in plans_ref:
            plan_data = doc.to_dict()
            plan_id = doc.id
            root_node_data = plan_data.get("nodes", {}).get(plan_id, {})
            
            created_at_timestamp = "N/A"
            history = root_node_data.get("history", [])
            if history and isinstance(history, list) and len(history) > 0:
                first_event = history[0]
                created_at_timestamp = first_event.get("timestamp", "N/A")

            summaries.append(PlanSummary(
                plan_id=plan_id,
                objective=root_node_data.get("objective", "Objectif non trouvé"),
                status=root_node_data.get("state", "inconnu"),
                created_at=created_at_timestamp
            ))
            
        logger.info(f"[GRA] {len(summaries)} plans résumés récupérés bruts.")
        
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
        from src.shared.task_graph_management import TaskGraph
        graph_manager = TaskGraph(plan_id=plan_id)
        plan_data = graph_manager.as_dict()
        if not plan_data.get("nodes"):
            raise HTTPException(status_code=404, detail=f"Plan '{plan_id}' non trouvé ou vide.")
        logger.info(f"[GRA] Détails du plan '{plan_id}' récupérés.")
        return plan_data
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[GRA] Erreur lors de la récupération des détails du plan '{plan_id}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/agents_status")
async def get_agents_status_endpoint():
    """
    MODIFIÉ : Récupère la liste des agents et leur statut depuis le registre
    et fusionne avec le cache de statut en temps réel.
    """
    if not db:
        raise HTTPException(status_code=503, detail="Base de données non disponible.")

    agents_from_db = []
    try:
        docs_stream = db.collection("service_registry").stream()
        agents_from_db = [doc.to_dict() for doc in docs_stream if doc.id != 'gra_instance_config']
    except Exception as e:
        logger.error(f"[GRA] Erreur Firestore: {e}", exc_info=True)
        # On ne lève pas d'exception, on peut continuer avec le cache

    # Fusionner les données du registre (officielles) avec le cache de statut (temps réel)
    for agent_data in agents_from_db:
        agent_name = agent_data.get("name")
        if agent_name in agent_statuses:
            # On met à jour les infos statiques (URL, skills) au cas où elles auraient changé
            agent_statuses[agent_name].update(agent_data)
        else:
            # L'agent est dans le registre mais n'a pas encore envoyé de statut
            agent_data["health_status"] = {"state": "Offline"}
            agent_statuses[agent_name] = agent_data

    # Retourne la vue la plus à jour
    return {"gra_status": gra_status, "agents": list(agent_statuses.values())}

@app.post("/v1/global_plans/{global_plan_id}/accept_and_plan", response_model=GlobalPlanResponse)
async def accept_objective_and_trigger_team1_planning(
    global_plan_id: str = Path(..., description="L'ID du plan global."),
    request_body: AcceptObjectiveRequest = Body(None, description="Optionnellement, l'objectif finalisé par l'utilisateur.")
):
    """
    Permet à l'utilisateur d'accepter l'objectif actuel (potentiellement enrichi ou modifié)
    et de lancer la planification par TEAM 1.
    """
    logger.info(f"[GRA API] Requête d'acceptation d'objectif et lancement TEAM 1 pour plan '{global_plan_id}'.")
    final_objective_from_user = request_body.user_final_objective if request_body else None
    
    try:
        supervisor = GlobalSupervisorLogic()
        result = await supervisor.accept_objective_and_initiate_team1(
            global_plan_id=global_plan_id,
            user_provided_objective=final_objective_from_user 
        )
        return GlobalPlanResponse(**result)
    except FileNotFoundError:
        logger.warning(f"[GRA API] Tentative d'accepter l'objectif pour un plan non trouvé: {global_plan_id}")
        raise HTTPException(status_code=404, detail=f"Plan global '{global_plan_id}' non trouvé.")
    except Exception as e:
        logger.error(f"[GRA API] Erreur lors de l'acceptation de l'objectif pour plan '{global_plan_id}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erreur interne du serveur: {str(e)}")


@app.post("/v1/global_plans/{global_plan_id}/resume_execution", response_model=GlobalPlanResponse)
async def resume_team2_execution_endpoint(global_plan_id: str = Path(..., description="ID du plan global")):
    """Reprend l'exécution TEAM 2 pour un plan global existant."""
    logger.info(f"[GRA API] Requête de reprise TEAM 2 pour plan '{global_plan_id}'.")
    try:
        supervisor = GlobalSupervisorLogic()
        result = await supervisor.continue_team2_execution(global_plan_id)
        return GlobalPlanResponse(**result)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Plan global '{global_plan_id}' non trouvé.")
    except Exception as e:
        logger.error(f"[GRA API] Erreur reprise TEAM 2 pour plan '{global_plan_id}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erreur interne du serveur: {str(e)}")


@app.post("/v1/global_plans/{global_plan_id}/retry_failed_tasks", response_model=GlobalPlanResponse)
async def retry_team2_failed_tasks_endpoint(global_plan_id: str = Path(..., description="ID du plan global")):
    """Relance les tâches TEAM 2 en échec pour un plan global."""
    logger.info(f"[GRA API] Requête de relance des tâches TEAM 2 échouées pour plan '{global_plan_id}'.")
    try:
        supervisor = GlobalSupervisorLogic()
        result = await supervisor.retry_team2_failed_tasks(global_plan_id)
        return GlobalPlanResponse(**result)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Plan global '{global_plan_id}' non trouvé.")
    except Exception as e:
        logger.error(
            f"[GRA API] Erreur relance tâches TEAM 2 échouées pour plan '{global_plan_id}': {e}",
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail=f"Erreur interne du serveur: {str(e)}")

@app.get("/v1/stats/team1_agent_tasks_count", response_model=Team1AgentTasksCountResponse)
async def get_team1_agent_tasks_count_stats():
    """
    Récupère le nombre total de tâches (complétées ou échouées)
    traitées par chaque agent de la TEAM 1 à travers tous les plans.
    """
    logger.info("[GRA API] Requête pour les statistiques de comptage des tâches des agents de TEAM 1.")
    if not db:
        logger.error("[GRA API] Client Firestore non disponible pour get_team1_agent_tasks_count_stats.")
        raise HTTPException(status_code=500, detail="Service de base de données non disponible.")

    agent_task_counts = Counter()
    processed_task_ids_for_counting = set()

    try:
        global_plans_ref = db.collection(GLOBAL_PLANS_FIRESTORE_COLLECTION)
        global_plans_docs = await asyncio.to_thread(list, global_plans_ref.stream())

        for global_plan_doc in global_plans_docs:
            global_plan_data = global_plan_doc.to_dict()
            team1_plan_id = global_plan_data.get("team1_plan_id")

            if team1_plan_id:
                task_graph_doc_ref = db.collection("task_graphs").document(team1_plan_id)
                task_graph_doc = await asyncio.to_thread(task_graph_doc_ref.get)

                if task_graph_doc.exists:
                    task_graph_data = task_graph_doc.to_dict()
                    nodes = task_graph_data.get("nodes", {})
                    for task_id, task_node_data in nodes.items():
                        agent_name = task_node_data.get("assigned_agent")
                        task_state = task_node_data.get("state")

                        if agent_name and task_state in [
                            "completed", "failed",
                            "cancelled", "unable_to_complete"
                        ] and task_id not in processed_task_ids_for_counting:
                            if agent_name in ["ReformulatorAgentServer", "EvaluatorAgentServer", "ValidatorAgentServer"]:
                                agent_task_counts[agent_name] += 1
                                processed_task_ids_for_counting.add(task_id)
    except Exception as e:
        logger.error(f"[GRA API] Erreur lors de l'agrégation des statistiques des agents: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erreur interne du serveur lors de l'agrégation des statistiques: {str(e)}")

    response_stats = [
        AgentTaskCountStat(agent_name=agent, task_count=count)
        for agent, count in agent_task_counts.items()
    ]

    logger.info(f"[GRA API] Statistiques de comptage des tâches agents TEAM 1 générées: {response_stats}")
    return Team1AgentTasksCountResponse(stats=response_stats, last_updated=datetime.now(timezone.utc).isoformat())

@app.get("/v1/stats/agent_tasks", response_model=AllAgentTasksStatsResponse)
async def get_all_agent_tasks_count_stats():
    """
    Récupère le nombre total de tâches (complétées ou échouées)
    traitées par chaque agent à travers tous les global_plans (pour UserInteractionAgent)
    et tous les task_graphs (pour les agents de TEAM 1).
    """
    logger.info("[GRA API] Requête pour les statistiques de comptage de toutes les tâches agents.")
    if not db:
        logger.error("[GRA API] Client Firestore non disponible pour get_all_agent_tasks_count_stats.")
        raise HTTPException(status_code=500, detail="Service de base de données non disponible.")

    agent_task_counts = Counter()

    processed_task_ids_for_counting = set()

    try:

        global_plans_ref = db.collection(GLOBAL_PLANS_FIRESTORE_COLLECTION)
        global_plans_docs = await asyncio.to_thread(list, global_plans_ref.stream())

        for global_plan_doc in global_plans_docs:
            global_plan_data = global_plan_doc.to_dict()

            attempts = global_plan_data.get("clarification_attempts", 0)
            if attempts > 0 :
                 agent_task_counts[("UserInteractionAgentServer", "global_plan_clarification")] += attempts


            team1_plan_id = global_plan_data.get("team1_plan_id")
            if team1_plan_id:
                task_graph_doc_ref = db.collection("task_graphs").document(team1_plan_id)
                task_graph_doc = await asyncio.to_thread(task_graph_doc_ref.get)

                if task_graph_doc.exists:
                    task_graph_data = task_graph_doc.to_dict()
                    nodes = task_graph_data.get("nodes", {})
                    for task_id, task_node_data in nodes.items():
                        agent_name = task_node_data.get("assigned_agent")
                        task_state = task_node_data.get("state")

                        team1_agents = ["ReformulatorAgentServer", "EvaluatorAgentServer", "ValidatorAgentServer"]

                        if agent_name in team1_agents and task_state in [
                            "completed", "failed", "cancelled", "unable_to_complete"
                        ] and task_id not in processed_task_ids_for_counting:
                            agent_task_counts[(agent_name, "team1_plan_task")] += 1
                            processed_task_ids_for_counting.add(task_id)
                            
    except Exception as e:
        logger.error(f"[GRA API] Erreur lors de l'agrégation des statistiques de tous les agents: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erreur interne du serveur lors de l'agrégation des statistiques: {str(e)}")

    response_stats = [
        AllAgentTaskStats(agent_name=agent_key[0], task_count=count, source_type=agent_key[1])
        for agent_key, count in agent_task_counts.items()
    ]

    logger.info(f"[GRA API] Statistiques de comptage de toutes les tâches agents générées: {response_stats}")
    return AllAgentTasksStatsResponse(stats=response_stats, last_updated=datetime.now(timezone.utc).isoformat())




@app.get("/v1/execution_task_graphs/{execution_plan_id}")
async def get_execution_task_graph_details_endpoint(execution_plan_id: str):
    """Récupère les détails complets (ExecutionTaskGraph) d'un plan d'exécution spécifique."""
    try:
        graph_manager = ExecutionTaskGraph(execution_plan_id=execution_plan_id)
        plan_data = await asyncio.to_thread(graph_manager.as_dict)
        
        if not plan_data or not plan_data.get("nodes"):
            if plan_data and plan_data.get("overall_status") in ["INITIALIZING", "PENDING_DECOMPOSITION"]:
                 logger.info(f"[GRA] Plan d'exécution '{execution_plan_id}' trouvé mais en attente de décomposition.")
            else:
                logger.warning(f"[GRA] Plan d'exécution '{execution_plan_id}' non trouvé ou vide.")
                raise HTTPException(status_code=404, detail=f"Plan d'exécution '{execution_plan_id}' non trouvé ou vide.")
        
        logger.info(f"[GRA] Détails du plan d'exécution '{execution_plan_id}' récupérés.")
        return plan_data
    except HTTPException:
        raise
    except ValueError as ve:
        logger.error(f"[GRA] Erreur de valeur pour get_execution_task_graph_details_endpoint: {ve}")
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"[GRA] Erreur lors de la récupération des détails du plan d'exécution '{execution_plan_id}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erreur interne du serveur: {str(e)}")

@app.get("/v1/stats/agents")
async def get_agent_stats():
    """Récupère les statistiques de traitement des tâches pour chaque agent."""
    try:
        stats_ref = db.collection("agent_stats")
        docs_snapshots = await asyncio.to_thread(list, stats_ref.stream())
        
        all_stats = []
        for doc in docs_snapshots:
            stats_data = doc.to_dict()
            stats_data["agent_name"] = doc.id
            all_stats.append(stats_data)
            
        logger.info(f"Statistiques récupérées pour {len(all_stats)} agents.")
        return {"stats": all_stats}
        
    except Exception as e:
        logger.error(f"Erreur lors de la récupération des statistiques des agents: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erreur interne du serveur.")

@app.get("/api/environments/{environment_id}/files")
async def list_files(environment_id: str, path: Optional[str] = "."):
    """Liste les fichiers dans un environnement. Le chemin est relatif à /workspace."""
    if not environment_manager:
        raise HTTPException(status_code=503, detail="EnvironmentManager is not available.")
    try:
        env_id = EnvironmentManager.normalize_environment_id(environment_id)
        files = await environment_manager.list_files_in_environment(env_id, path)
        return files
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) # Pour un env_id non valide
    except (client.ApiException, ConnectionError, OSError, asyncio.TimeoutError) as e:
        logging.error(f"External connection error listing files for env '{environment_id}': {e}", exc_info=True)
        raise HTTPException(status_code=503, detail="Unable to communicate with environment.")
    except Exception as e:
        logging.error(f"Error listing files for env '{environment_id}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An unexpected error occurred while listing files.")

@app.get("/api/environments/{environment_id}/files/download")
async def download_file(environment_id: str, path: str):
    """Télécharge un fichier depuis un environnement."""
    if not environment_manager:
        raise HTTPException(status_code=503, detail="EnvironmentManager is not available.")
    try:
        env_id = EnvironmentManager.normalize_environment_id(environment_id)
        file_content_str = await environment_manager.read_file_from_environment(env_id, path)
        file_content_bytes = file_content_str.encode('utf-8')
        
        # Utilise StreamingResponse pour envoyer des données binaires
        return StreamingResponse(
            io.BytesIO(file_content_bytes),
            media_type='application/octet-stream',
            headers={'Content-Disposition': f'attachment; filename="{os.path.basename(path)}"'}
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except (client.ApiException, ConnectionError, OSError, asyncio.TimeoutError) as e:
        logging.error(f"External connection error downloading file for env '{environment_id}': {e}", exc_info=True)
        raise HTTPException(status_code=503, detail="Unable to communicate with environment.")
    except Exception as e:
        logging.error(f"Error downloading file for env '{environment_id}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An unexpected error occurred while downloading the file.")

@app.post("/api/environments/{environment_id}/files/upload")
async def upload_file(environment_id: str, path: Optional[str] = Form(None), file: UploadFile = File(...)):
    """Téléverse un fichier dans un environnement."""
    if not environment_manager:
        raise HTTPException(status_code=503, detail="EnvironmentManager is not available.")
        
    destination_path = path if path else file.filename
    if not destination_path:
        raise HTTPException(status_code=400, detail="File name or destination path is required.")

    try:
        filename = secure_filename(destination_path)
        file_content_bytes = await file.read()
        file_content = file_content_bytes.decode('utf-8')

        env_id = EnvironmentManager.normalize_environment_id(environment_id)
        await environment_manager.write_file_to_environment(env_id, filename, file_content)

        return {"message": f"File '{filename}' uploaded successfully to '{environment_id}'."}
    except ValueError as e:  # Erreur si l'env_id est invalide
        raise HTTPException(status_code=404, detail=str(e))
    except (client.ApiException, ConnectionError, OSError, asyncio.TimeoutError) as e:
        logging.error(f"External connection error uploading file for env '{environment_id}': {e}", exc_info=True)
        raise HTTPException(status_code=503, detail="Unable to communicate with environment.")
    except Exception as e:
        logging.error(f"Error uploading file for env '{environment_id}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An unexpected error occurred during file upload.")

# --- NOUVEAU : Endpoint pour que les frontends se connectent ---
@app.websocket("/ws/status")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        # On envoie l'état actuel dès la connexion
        # MODIFICATION ICI : ajout de default=json_serializer
        payload = {"gra_status": gra_status, "agents": list(agent_statuses.values())}
        await websocket.send_text(json.dumps(payload, default=json_serializer))
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    
@app.post("/agent_status_update")
async def update_agent_status(status_update: Dict[str, Any]):
    agent_name = status_update.get("name")
    if not agent_name:
        return {"status": "error", "message": "agent name is missing"}

    # Récupérer les infos existantes de l'agent dans le cache, ou un dict vide
    current_agent_info = agent_statuses.get(agent_name, {})

    # --- LA CORRECTION ---
    # S'assurer que la propriété 'name' de haut niveau est toujours présente.
    current_agent_info['name'] = agent_name
    # ---------------------

    # Mettre à jour le sous-objet "health_status"
    status_update['timestamp'] = datetime.now(timezone.utc).isoformat()
    current_agent_info['health_status'] = status_update

    history = current_agent_info.get('status_history', [])
    history.append(status_update)
    # Conserver uniquement les 10 dernières entrées
    current_agent_info['status_history'] = history[-10:]

    agent_statuses[agent_name] = current_agent_info

    gra_status.update(
        {
            "state": "running",
            "detail": f"Update from {agent_name}",
            "last_update": datetime.now(timezone.utc).isoformat(),
        }
    )

    payload = {"gra_status": gra_status, "agents": list(agent_statuses.values())}
    await manager.broadcast(json.dumps(payload, default=json_serializer))
    return {"status": "received"}

if __name__ == "__main__":
    
    
    is_production = 'K_SERVICE' in os.environ
    
    if is_production:
        port = int(os.environ.get("PORT", 8000))
        host = "0.0.0.0"
        log_level = "info"
        reload_flag = False
        logger.info(f"Démarrage du serveur GRA en mode PRODUCTION sur {host}:{port}...")
    else:
        port = 8000
        host = "localhost"
        log_level = "info"
        reload_flag = True
        logger.info(f"Démarrage du serveur GRA en mode DÉVELOPPEMENT sur {host}:{port}...")

    uvicorn.run("src.services.gra.server:app", host=host, port=port, log_level=log_level, reload=reload_flag)
