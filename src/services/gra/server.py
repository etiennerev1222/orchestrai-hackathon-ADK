# src/services/gra/server.py
import uvicorn
import logging
from fastapi import FastAPI, HTTPException, Body, Path
from fastapi.middleware.cors import CORSMiddleware
import httpx
from typing import Dict, Any, List, Optional
import firebase_admin
from firebase_admin import credentials, firestore
from pydantic import BaseModel, Field
import os # <-- AJOUT
from datetime import datetime, timezone # <-- AJOUT
import asyncio
# --- Nouveaux Imports ---
from src.orchestrators.global_supervisor_logic import GlobalSupervisorLogic, GlobalPlanState 
import os
import uuid
from collections import Counter # Pour compter facilement
from src.shared.execution_task_graph_management import ExecutionTaskGraph # Assurez-vous de l'importer


logger = logging.getLogger(__name__)

# --- Initialisation de Firestore ---
# firebase_admin s'authentifiera automatiquement via la variable d'environnement

from src.shared.firebase_init import db # Importez le client db centralisé
if db is None:
    logger.critical("CRITICAL: Échec de l'obtention du client Firestore depuis firebase_init. Arrêt du serveur GRA.")
    exit(1)
else:
    logger.info("GRA Server: Client Firestore obtenu avec succès depuis firebase_init.")

# --- AJOUT : Configuration de l'URL publique du GRA ---
# Cette URL sera celle à laquelle les autres services peuvent atteindre le GRA.
# Dans un environnement cloud, elle pourrait être injectée via une variable d'env.
# Pour le développement local, vous pouvez la coder en dur ou la mettre dans une var d'env.
GRA_PUBLIC_URL = os.environ.get("GRA_PUBLIC_URL", "http://localhost:8000")
GRA_SERVICE_REGISTRY_COLLECTION = "service_registry"
GRA_CONFIG_DOCUMENT_ID = "gra_instance_config"
GLOBAL_PLANS_FIRESTORE_COLLECTION = "global_plans" # Nom de la collection pour les plans globaux

# --- Modèles de données Pydantic pour la validation ---
# Ce modèle accepte exactement ce que les agents envoient maintenant,
# y compris les compétences (skills) que nous allons rajouter à l'envoi.
class AgentRegistration(BaseModel):
    name: str = Field(..., alias="agent_name")
    public_url: str
    internal_url: str
    skills: List[str] = [] # La liste des compétences, optionnelle pour l'instant

class Artifact(BaseModel):
    task_id: str
    context_id: str | None = None
    agent_name: str
    content: Dict[str, Any] | str

# --- NOUVEAUX Modèles Pydantic pour les Global Plans ---
class GlobalPlanCreateRequest(BaseModel):
    objective: str = Field(..., min_length=1, description="Objectif brut soumis par l'utilisateur.")
    user_id: Optional[str] = "default_user" # Optionnel, avec une valeur par défaut

class GlobalPlanResponse(BaseModel): # Réponse générique pour la création et la clarification
    status: str # ex: "clarification_pending", "objective_clarified", "error", "max_clarification_attempts_reached"
    message: Optional[str] = None
    question: Optional[str] = None
    clarified_objective: Optional[str] = None
    task_type_estimation: Optional[str] = None
    global_plan_id: str
    current_supervisor_state: Optional[str] = None # Pourrait être utile pour le frontend

class UserClarificationRequest(BaseModel):
    user_response: str = Field(..., min_length=1, description="Réponse de l'utilisateur à une question de clarification.")

class GlobalPlanDetailResponse(BaseModel): # Pour GET /global_plans/{global_plan_id}
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
    created_at: str # ISO format string
    updated_at: str # ISO format string
    last_agent_response_artifact: Optional[Dict[str, Any]] = None # Pourrait être verbeux, mais utile pour debug
    error_message: Optional[str] = None

# --- NOUVEAU Modèle Pydantic pour le résumé des plans globaux ---
class GlobalPlanSummaryItem(BaseModel):
    global_plan_id: str
    raw_objective: str
    current_supervisor_state: str
    task_type_estimation: Optional[str] = None
    created_at: str
    updated_at: str

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

# --- NOUVEAU Modèle Pydantic pour la requête d'acceptation d'objectif ---
class AcceptObjectiveRequest(BaseModel):
    # L'utilisateur peut optionnellement fournir une version finale de l'objectif.
    # S'il est None, GlobalSupervisorLogic utilisera le dernier objectif enrichi ou clarifié.
    user_final_objective: Optional[str] = None 

class AgentTaskCountStat(BaseModel):
    agent_name: str
    task_count: int

class Team1AgentTasksCountResponse(BaseModel):
    stats: List[AgentTaskCountStat]
    last_updated: str

class AllAgentTaskStats(BaseModel): # Nouveau modèle pour une réponse plus globale
    agent_name: str
    task_count: int
    source_type: str # "global_plan" ou "team1_plan"

class AllAgentTasksStatsResponse(BaseModel):
    stats: List[AllAgentTaskStats]
    last_updated: str

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

# Allow CORS for the React interface served on http://localhost:8080
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8080"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# --- ROUTE /register MISE À JOUR ---
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

# --- ROUTE /agents MISE À JOUR AVEC HEALTH CHECK ---
@app.get("/agents")
async def get_agents_with_status():
    """Récupère tous les agents enregistrés et vérifie leur statut."""
    try:
        agents_ref = db.collection("service_registry")
        docs_stream = agents_ref.stream()
        agents = []
        
        async with httpx.AsyncClient(timeout=3.0) as client:
            tasks = []
            agent_docs = []

            async for doc in docs_stream:
                if doc.id != 'gra_instance_config':
                    agent_data = doc.to_dict()
                    agent_data['id'] = doc.id
                    agent_docs.append(agent_data)
                    # On vérifie la santé en utilisant l'URL INTERNE
                    health_check_url = agent_data.get("internal_url")
                    if health_check_url:
                        # Ajoute une coroutine à la liste des tâches à exécuter
                        tasks.append(client.get(f"{health_check_url}/health"))

            # Exécute toutes les vérifications de santé en parallèle
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for i, agent_data in enumerate(agent_docs):
                result = results[i]
                if isinstance(result, httpx.Response) and result.status_code == 200:
                    agent_data['status'] = 'running' # Vert !
                else:
                    agent_data['status'] = 'unhealthy' # Jaune/Rouge
                    # Log l'erreur si ce n'est pas une simple réponse négative
                    if not isinstance(result, httpx.Response):
                         logger.warning(f"Health check a échoué pour {agent_data['name']}: {result}")

                agents.append(agent_data)

        return agents
    except Exception as e:
        logger.error(f"Erreur lors de la récupération des agents: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve agents")

# === CORRECTION DANS LA FONCTION CI-DESSOUS ===
@app.post("/register", status_code=201)
async def register_agent(payload: AgentRegistration):
    """Point de terminaison pour que les agents puissent s'enregistrer ou mettre à jour leur statut."""
    try:
        # On utilise payload.name ici, car c'est le nom de l'attribut dans le modèle Pydantic
        agent_ref = db.collection("service_registry").document(payload.name)
        
        agent_data = {
            "name": payload.name, # Utiliser payload.name
            "public_url": payload.public_url,
            "internal_url": payload.internal_url,
            "skills": payload.skills,
            "timestamp": firestore.SERVER_TIMESTAMP
        }
        
        await asyncio.to_thread(agent_ref.set, agent_data)
        
        logger.info(f"Agent '{payload.name}' enregistré/mis à jour.") # Utiliser payload.name
        return {"status": "success", "name": payload.name} # Utiliser payload.name
        
    except Exception as e:
        logger.error(f"Erreur enregistrement agent '{payload.name}': {e}", exc_info=True) # Utiliser payload.name
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/agents") # Renommé de find_agent pour plus de clarté sur ce qu'il retourne
async def get_agents_by_skill(skill: str): # Renommé le paramètre pour la clarté
    # ... (identique, mais vérifier le nom de la collection)
    try:
        agents_ref = db.collection("agents").where(field_path="skills", op_string="array_contains", value=skill).limit(1)
        # Utiliser asyncio.to_thread pour les opérations Firestore bloquantes
        agent_docs = await asyncio.to_thread(list, agents_ref.stream()) # Convertir le stream en liste dans le thread
        
        if not agent_docs:
            raise HTTPException(status_code=404, detail=f"Aucun agent trouvé avec la compétence: {skill}")
        
        agent_data = agent_docs[0].to_dict()
        logger.info(f"Agent trouvé pour la compétence '{skill}': {agent_data.get('name')}")
        return {"name": agent_data.get("name"), "url": agent_data.get("url")} # Conforme à ce que _get_agent_url_from_gra attend
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur recherche agent par compétence '{skill}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    


@app.post("/v1/global_plans", response_model=GlobalPlanResponse, status_code=202) # 202 Accepted
async def create_global_plan(plan_request: GlobalPlanCreateRequest):
    """
    Crée un nouveau plan global et initie la clarification de l'objectif.
    """
    logger.info(f"[GRA API] Requête de création de plan global reçue. Objectif: {plan_request.objective}")
    try:
        supervisor = GlobalSupervisorLogic() # Instancié par requête
        # La méthode start_new_global_plan est maintenant asynchrone
        result = await supervisor.start_new_global_plan(
            raw_objective=plan_request.objective,
            user_id=plan_request.user_id
        )
        # result est un dict comme: {"status": "...", "question": "...", "global_plan_id": "..."}
        # Il faut s'assurer qu'il correspond à GlobalPlanResponse
        return GlobalPlanResponse(**result)
    except ConnectionError as e: # Si le GRA ne peut pas être découvert par le superviseur
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
        # Vérifier si le plan n'existe pas pour un 404 potentiel
        if "non trouvé" in str(e).lower(): # Heuristique simple
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
        # Nous devons ajouter cette méthode à GlobalSupervisorLogic
        plan_details = await supervisor._load_global_plan_state(global_plan_id) # Utilise la méthode existante
        
        if not plan_details:
            raise HTTPException(status_code=404, detail=f"Plan global '{global_plan_id}' non trouvé.")
        
        # S'assurer que la réponse correspond au modèle GlobalPlanDetailResponse
        # Il faudra peut-être mapper les champs si _load_global_plan_state ne retourne pas exactement ce format.
        # Pour l'instant, on suppose que _load_global_plan_state retourne un dict compatible.
        # Ajoutons global_plan_id au dictionnaire s'il n'y est pas déjà (c'est la clé du doc)
        plan_details['global_plan_id'] = global_plan_id
        
        # Vérifier les champs obligatoires pour GlobalPlanDetailResponse et fournir des valeurs par défaut si manquant
        # pour éviter les erreurs Pydantic.
        # Ceci est important car _load_global_plan_state retourne ce qui est dans la DB,
        # qui pourrait ne pas avoir tous les champs si le plan est à une étape précoce.
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
            "team2_execution_plan_id": plan_details.get('team2_execution_plan_id'), # <--- VÉRIFIEZ/AJOUTEZ CETTE LIGNE
            "created_at": plan_details.get('created_at', datetime.now(timezone.utc).isoformat()), # Fallback
            "updated_at": plan_details.get('updated_at', datetime.now(timezone.utc).isoformat()), # Fallback
            "last_agent_response_artifact": plan_details.get('last_agent_response_artifact'),
            "error_message": plan_details.get('error_message')
        }
        return GlobalPlanDetailResponse(**response_data)
        
    except HTTPException: # Re-lever les exceptions HTTP pour que FastAPI les gère
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
        # Récupérer la liste des documents dans un thread pour éviter de bloquer l'event loop
        docs = await asyncio.to_thread(
            lambda: list(
                db.collection(GLOBAL_PLANS_FIRESTORE_COLLECTION)
                .order_by("updated_at", direction=firestore.Query.DESCENDING)
                .stream()
            )
        )

        for doc in docs:  # doc est un DocumentSnapshot
            plan_data = doc.to_dict()
            if plan_data: # S'assurer que les données existent
                summaries.append(GlobalPlanSummaryItem(
                    global_plan_id=doc.id, # L'ID du document est l'ID du plan
                    raw_objective=plan_data.get("raw_objective", "Objectif non disponible"),
                    current_supervisor_state=plan_data.get("current_supervisor_state", "État inconnu"),
                    task_type_estimation=plan_data.get("task_type_estimation"),
                    created_at=plan_data.get("created_at", ""),
                    updated_at=plan_data.get("updated_at", "")
                ))
        
        logger.info(f"[GRA API] {len(summaries)} résumés de plans globaux récupérés.")
        return summaries
    except Exception as e:
        logger.error(f"[GRA API] Erreur lors de la récupération des résumés de plans globaux: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erreur interne du serveur: {str(e)}")

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
    """Récupère la liste des agents enregistrés et leur statut de santé."""
    agents_list: List[Dict[str, Any]] = []
    try:
        docs = await asyncio.to_thread(lambda: list(db.collection("agents").stream()))
        agents_list = [doc.to_dict() for doc in docs]
    except Exception as e:
        logger.error(f"[GRA] Erreur lors de la récupération du statut des agents: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

    async with httpx.AsyncClient() as client:
        async def check(url: str) -> bool:
            if not url:
                return False
            try:
                res = await client.get(url.rstrip("/") + "/.well-known/agent.json", timeout=5.0)
                return res.status_code == 200
            except Exception:
                return False

        results = await asyncio.gather(*(check(a.get("url")) for a in agents_list))

    for agent, ok in zip(agents_list, results):
        agent["health_status"] = "✅ Online" if ok else "⚠️ Offline"

    logger.info(f"[GRA] Statut de {len(agents_list)} agents récupéré avec santé.")
    return agents_list


# --- NOUVEL Endpoint pour accepter l'objectif et lancer TEAM 1 ---
@app.post("/v1/global_plans/{global_plan_id}/accept_and_plan", response_model=GlobalPlanResponse)
async def accept_objective_and_trigger_team1_planning(
    global_plan_id: str = Path(..., description="L'ID du plan global."),
    request_body: AcceptObjectiveRequest = Body(None, description="Optionnellement, l'objectif finalisé par l'utilisateur.") # None comme défaut si corps vide
):
    """
    Permet à l'utilisateur d'accepter l'objectif actuel (potentiellement enrichi ou modifié)
    et de lancer la planification par TEAM 1.
    """
    logger.info(f"[GRA API] Requête d'acceptation d'objectif et lancement TEAM 1 pour plan '{global_plan_id}'.")
    final_objective_from_user = request_body.user_final_objective if request_body else None
    
    try:
        supervisor = GlobalSupervisorLogic()
        # La méthode accept_objective_and_initiate_team1 s'occupe de choisir le meilleur objectif
        # si user_final_objective est None.
        result = await supervisor.accept_objective_and_initiate_team1(
            global_plan_id=global_plan_id,
            user_provided_objective=final_objective_from_user 
        )
        # La réponse de accept_objective_and_initiate_team1 devrait déjà être compatible
        # avec GlobalPlanResponse (ou nous l'ajusterons si besoin).
        # Elle devrait indiquer un statut comme OBJECTIVE_CLARIFIED ou TEAM1_PLANNING_INITIATED
        return GlobalPlanResponse(**result)
    except FileNotFoundError: # Si _load_global_plan_state retourne None et que accept_objective... le gère mal
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
    processed_task_ids_for_counting = set() # Pour éviter de compter une tâche plusieurs fois si elle apparaît dans plusieurs snapshots

    try:
        # 1. Récupérer tous les plans globaux pour trouver les team1_plan_id
        global_plans_ref = db.collection(GLOBAL_PLANS_FIRESTORE_COLLECTION)
        global_plans_docs = await asyncio.to_thread(list, global_plans_ref.stream())

        for global_plan_doc in global_plans_docs:
            global_plan_data = global_plan_doc.to_dict()
            team1_plan_id = global_plan_data.get("team1_plan_id")

            if team1_plan_id:
                # 2. Pour chaque team1_plan_id, récupérer son TaskGraph
                task_graph_doc_ref = db.collection("task_graphs").document(team1_plan_id)
                task_graph_doc = await asyncio.to_thread(task_graph_doc_ref.get)

                if task_graph_doc.exists:
                    task_graph_data = task_graph_doc.to_dict()
                    nodes = task_graph_data.get("nodes", {})
                    for task_id, task_node_data in nodes.items():
                        # On ne compte que les tâches qui ont un agent assigné et sont dans un état terminal.
                        # Et qui n'ont pas déjà été comptées (au cas où, bien que peu probable ici).
                        agent_name = task_node_data.get("assigned_agent")
                        task_state = task_node_data.get("state")

                        if agent_name and task_state in [
                            "completed", "failed", # États terminaux de TaskState dans task_graph_management.py
                            "cancelled", "unable_to_complete" # Autres états terminaux potentiels
                        ] and task_id not in processed_task_ids_for_counting:
                            # On s'intéresse aux agents de la TEAM 1
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

    # Utiliser des compteurs séparés ou un compteur avec des clés composites
    agent_task_counts = Counter() # Clé sera (agent_name, source_type)

    processed_task_ids_for_counting = set() # Pour éviter double comptage si une logique complexe le permettait

    try:
        # 1. Traiter les tâches du UserInteractionAgent depuis les global_plans
        #    On pourrait inférer l'achèvement d'une "tâche" de clarification par le UserInteractionAgent
        #    en regardant le nombre de fois qu'un global_plan est passé à CLARIFICATION_PENDING_USER_INPUT
        #    ou quand OBJECTIVE_CLARIFIED est atteint après des interactions.
        #    Pour une approche plus directe, si le UserInteractionAgent crée des "tâches" A2A réelles
        #    qui sont tracées, on les chercherait. Actuellement, son "travail" est plus implicite
        #    dans l'état du global_plan.
        #
        #    Simplification : On va se baser sur le nombre de fois où l'agent UI a été sollicité et a répondu
        #    (ce qui est stocké dans `last_agent_response_artifact` et `clarification_attempts`).
        #    Ou, si l'on considère chaque appel A2A au UserInteractionAgent comme une "tâche traitée".
        #    Adoptons une approche où chaque réponse de l'agent UI est comptée.

        global_plans_ref = db.collection(GLOBAL_PLANS_FIRESTORE_COLLECTION)
        global_plans_docs = await asyncio.to_thread(list, global_plans_ref.stream())

        for global_plan_doc in global_plans_docs:
            global_plan_data = global_plan_doc.to_dict()
            # Chaque fois qu'il y a un last_agent_response_artifact, on peut considérer que l'agent UI a "traité" une demande.
            # Ou, plus simplement, le nombre de clarification_attempts peut donner une idée.
            # Si `clarification_attempts` > 0, l'agent UI a travaillé au moins une fois.
            # Si l'état est `OBJECTIVE_CLARIFIED` ou `TEAM1_PLANNING_INITIATED`, et `clarification_attempts` > 0
            # on peut compter cela comme une "tâche complétée" pour UserInteractionAgent.
            # Si l'état est `FAILED_MAX_CLARIFICATION_ATTEMPTS` ou `FAILED_AGENT_ERROR` après des tentatives,
            # on peut compter cela comme un "échec".

            attempts = global_plan_data.get("clarification_attempts", 0)
            if attempts > 0 : # Signifie que l'agent UI a été appelé au moins une fois
                 # On pourrait affiner cela en vérifiant si l'objectif a été clarifié ou si on a atteint max_attempts
                 # Pour la simplicité, on compte chaque "cycle" de clarification comme une tâche.
                 # Ou, mieux, si l'agent UserInteractionAgent était un agent A2A standard dont on suivait les tâches,
                 # on lirait ses tâches. Ici, on se base sur les traces laissées dans global_plan.
                 # On va assumer pour cette stat que chaque appel (tentative) est une "tâche".
                 agent_task_counts[("UserInteractionAgentServer", "global_plan_clarification")] += attempts


            # 2. Traiter les tâches des agents de TEAM 1 depuis les task_graphs
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

                        # Agents de TEAM 1 spécifiques
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
        plan_data = await asyncio.to_thread(graph_manager.as_dict) # Utiliser to_thread pour les opérations bloquantes de Firestore
        
        # Vérifier si le graphe existe réellement ou est vide après la lecture
        if not plan_data or not plan_data.get("nodes"): # Si "nodes" est vide ou absent, le graphe n'a pas été peuplé
            # Vérifier aussi le overall_status pour voir s'il est juste en PENDING_DECOMPOSITION
            if plan_data and plan_data.get("overall_status") in ["INITIALIZING", "PENDING_DECOMPOSITION"]:
                 logger.info(f"[GRA] Plan d'exécution '{execution_plan_id}' trouvé mais en attente de décomposition.")
                 # Retourner quand même les données pour que le frontend puisse afficher le statut
            else:
                logger.warning(f"[GRA] Plan d'exécution '{execution_plan_id}' non trouvé ou vide.")
                raise HTTPException(status_code=404, detail=f"Plan d'exécution '{execution_plan_id}' non trouvé ou vide.")
        
        logger.info(f"[GRA] Détails du plan d'exécution '{execution_plan_id}' récupérés.")
        return plan_data
    except HTTPException: # Re-lever les exceptions HTTP
        raise
    except ValueError as ve: # Par exemple, si execution_plan_id est vide dans le constructeur de ExecutionTaskGraph
        logger.error(f"[GRA] Erreur de valeur pour get_execution_task_graph_details_endpoint: {ve}")
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"[GRA] Erreur lors de la récupération des détails du plan d'exécution '{execution_plan_id}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erreur interne du serveur: {str(e)}")

if __name__ == "__main__":
    logger.info("Démarrage du serveur du Gestionnaire de Ressources et d'Agents (GRA)...")
    uvicorn.run(app, host="localhost", port=8000)
