# app_frontend.py
import streamlit as st
import httpx
import asyncio
import graphviz
import json # Pour un affichage joli des dicts/JSON
from shared.task_graph_management import TaskGraph, TaskNode, TaskState
from datetime import datetime # Pour parser les timestamps
# URL de votre backend API (le GRA)
BACKEND_API_URL = "http://localhost:8000"

# --- Fonctions Asynchrones pour appeler le Backend ---
async def submit_new_plan(objective: str):
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(f"{BACKEND_API_URL}/plans", json={"objective": objective}, timeout=30.0)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            st.error(f"Erreur lors de la soumission du plan: {e}")
            return None

async def get_all_plans_summary_from_api(): # Renommé pour éviter confusion
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{BACKEND_API_URL}/plans", timeout=10.0)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            st.error(f"Erreur lors de la récupération des plans: {e}")
            return []

async def get_plan_details_from_api(plan_id: str): # Renommé
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{BACKEND_API_URL}/plans/{plan_id}", timeout=10.0)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            st.error(f"Erreur lors de la récupération des détails du plan {plan_id}: {e}")
            return None

async def get_agents_status_from_api(): # Renommé
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{BACKEND_API_URL}/agents_status", timeout=10.0)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            st.error(f"Erreur lors de la récupération du statut des agents: {e}")
            return []

# --- Fonctions pour charger les données ---
def load_plans_summary():
    st.session_state.plans_summary = asyncio.run(get_all_plans_summary_from_api())

def load_selected_plan_details():
    if st.session_state.selected_plan_id:
        st.session_state.selected_plan_details = asyncio.run(get_plan_details_from_api(st.session_state.selected_plan_id))
    else:
        st.session_state.selected_plan_details = None

def load_agents_status():
    st.session_state.agents_status = asyncio.run(get_agents_status_from_api())


# --- Interface Streamlit ---
st.set_page_config(layout="wide", page_title="OrchestrAI Dashboard")
st.title("🤖 Tableau de Bord OrchestrAI")

# Initialiser l'état de session
if 'plans_summary' not in st.session_state:
    st.session_state.plans_summary = []
if 'selected_plan_details' not in st.session_state:
    st.session_state.selected_plan_details = None
if 'agents_status' not in st.session_state:
    st.session_state.agents_status = []
if 'selected_plan_id' not in st.session_state:
    st.session_state.selected_plan_id = None
if 'plan_filter_text' not in st.session_state:
    st.session_state.plan_filter_text = ""
if 'plan_status_filter' not in st.session_state:
    st.session_state.plan_status_filter = "Tous"
    
# Chargement initial des données
if not st.session_state.plans_summary:
    load_plans_summary()
if not st.session_state.agents_status:
    load_agents_status()

# --- Sidebar pour les actions ---
with st.sidebar:
    st.header("🚀 Lancer un Nouveau Plan")
    new_objective = st.text_area("Objectif:", height=100, key="new_objective_input_sidebar")
    if st.button("Lancer Plan", key="launch_plan_button_sidebar"):
        if new_objective:
            result = asyncio.run(submit_new_plan(new_objective))
            if result and result.get("plan_id"):
                st.success(f"Plan '{result.get('plan_id')}' soumis !")
                st.session_state.new_objective_input_sidebar = "" # Vider le champ
                load_plans_summary() # Rafraîchir
                st.session_state.selected_plan_id = result.get("plan_id") # Sélectionner le nouveau plan
                load_selected_plan_details()
                st.rerun()
            else:
                st.error("Échec de la soumission.")
        else:
            st.warning("Veuillez entrer un objectif.")
    
    st.markdown("---")
    st.header("⚙️ Filtres et Actions")
    if st.button("Rafraîchir Tout", key="refresh_all_button_sidebar"):
        load_plans_summary()
        load_selected_plan_details() # Recharge les détails du plan sélectionné s'il y en a un
        load_agents_status()
        st.rerun()

    st.session_state.plan_filter_text = st.text_input(
        "Filtrer par ID ou mot-clé objectif:", 
        value=st.session_state.plan_filter_text,
        key="text_filter_sidebar"
    )
    status_options = ["Tous"] + [s.value for s in TaskState] # Assurez-vous que TaskState est importable ou défini
    st.session_state.plan_status_filter = st.selectbox(
        "Filtrer par état:", 
        options=status_options, 
        index=status_options.index(st.session_state.plan_status_filter),
        key="status_filter_sidebar"
    )



# --- Colonnes Principales ---
col1, col2 = st.columns([1, 2]) # Définir la largeur relative des colonnes
with col1:
    st.header("📋 Liste des Plans")
    
    filtered_plans = st.session_state.plans_summary
    if st.session_state.plan_filter_text:
        filter_lower = st.session_state.plan_filter_text.lower()
        filtered_plans = [
            p for p in filtered_plans 
            if filter_lower in p['plan_id'].lower() or filter_lower in p['objective'].lower()
        ]
    if st.session_state.plan_status_filter != "Tous":
        filtered_plans = [
            p for p in filtered_plans if p['status'] == st.session_state.plan_status_filter
        ]

    if filtered_plans:
        # Afficher l'objectif en premier, puis l'ID et l'état.
        # Utiliser l'attribut `help` pour l'objectif complet si trop long.
        plan_display_options = {
            p['plan_id']: f"{p['objective'][:40]}{'...' if len(p['objective']) > 40 else ''} (ID: {p['plan_id']}, État: {p['status']})"
            for p in filtered_plans
        }
        
        # Tooltip pour chaque option du radio
        captions = [p['objective'] for p in filtered_plans]

        if not filtered_plans: # Si le filtre ne retourne rien
            st.info("Aucun plan ne correspond à vos filtres.")
        elif st.session_state.selected_plan_id not in plan_display_options and list(plan_display_options.keys()):
            # Si l'ancien ID sélectionné n'est plus dans les options filtrées, sélectionner le premier
            st.session_state.selected_plan_id = list(plan_display_options.keys())[0]
            load_selected_plan_details() # Charger les détails du nouveau plan sélectionné
            st.rerun() # Forcer le rechargement pour appliquer la nouvelle sélection

        if plan_display_options: # S'il y a des plans à afficher après filtrage
            selected_id_from_radio = st.radio(
                "Sélectionnez un plan:",
                options=list(plan_display_options.keys()),
                format_func=lambda x: plan_display_options[x],
                captions=captions, # Affiche l'objectif complet au survol de l'option
                index=list(plan_display_options.keys()).index(st.session_state.selected_plan_id) if st.session_state.selected_plan_id in plan_display_options else 0,
                key="plan_selector_col1"
            )

            if selected_id_from_radio != st.session_state.selected_plan_id:
                st.session_state.selected_plan_id = selected_id_from_radio
                load_selected_plan_details()
                st.rerun()
            elif st.session_state.selected_plan_id and not st.session_state.selected_plan_details:
                 load_selected_plan_details()
                 st.rerun()

        else: # Si filtered_plans est vide après filtrage
             st.info("Aucun plan ne correspond à vos filtres.")
    else:
        st.info("Aucun plan à afficher pour le moment.")

    st.markdown("---")
    st.header("📡 Statut des Agents")
    if not st.session_state.agents_status:
        st.session_state.agents_status = asyncio.run(get_agents_status_from_api())
    
    if st.session_state.agents_status:
        for agent_info in st.session_state.agents_status:
            with st.expander(f"{agent_info.get('name', 'Agent Inconnu')}"):
                st.write(f"**URL:** {agent_info.get('url', 'N/A')}")
                st.write(f"**Compétences:** {', '.join(agent_info.get('skills', []))}")
                # Pour un vrai statut "online", il faudrait que le GRA le gère (via heartbeats)
                st.caption(f"Statut: En ligne (supposé)") 
    else:
        st.info("Aucun agent enregistré ou statut indisponible.")


with col2:
    st.header("🔍 Détails du Plan Sélectionné")
    if st.session_state.selected_plan_id and st.session_state.selected_plan_details:
        plan_details = st.session_state.selected_plan_details
        
        root_node_data = plan_details["nodes"].get(st.session_state.selected_plan_id, {})
        st.markdown(f"**ID:** `{st.session_state.selected_plan_id}`")
        st.markdown(f"**Objectif Initial:** {root_node_data.get('objective', 'N/A')}")
        st.markdown(f"**État Global:** `{root_node_data.get('state', 'N/A')}`")
        st.markdown(f"**Tentatives de Révision:** `{root_node_data.get('meta', {}).get('revision_count', 0)}`")

        # Créer le graphe
        dot = graphviz.Digraph(comment=f'Task Graph for {st.session_state.selected_plan_id}')
        dot.attr(rankdir='LR', size='8,5') # Graphe de gauche à droite, taille indicative

        task_nodes = plan_details.get("nodes", {})
        for task_id, task_data in task_nodes.items():
            label_lines = [
                f"ID: {task_id}",
                f"Obj: {task_data.get('objective', 'N/A')[:35]}...", # Tronquer l'objectif
                f"Agent: {task_data.get('assigned_agent', 'N/A')}",
                f"État: {task_data.get('state', 'N/A')}"
            ]
            label = "\n".join(label_lines)
            
            color = "grey"
            if task_data.get('state') == TaskState.COMPLETED.value: color = "lightgreen"
            elif task_data.get('state') == TaskState.FAILED.value: color = "lightcoral"
            elif task_data.get('state') == TaskState.WORKING.value: color = "lightblue"
            
            dot.node(task_id, label=label, shape="box", style="filled", fillcolor=color)
            
            parent_id = task_data.get("parent")
            if parent_id and parent_id in task_nodes:
                dot.edge(parent_id, task_id)
        
        try:
            st.graphviz_chart(dot, use_container_width=True)
        except Exception as e:
            st.error(f"Erreur lors de l'affichage du graphe: {e}")
            st.text("Graphviz n'est peut-être pas correctement installé ou accessible.")

        # Afficher les artefacts
        st.subheader("🔬 Artefacts")
        task_ids_for_artifacts = [tid for tid, tdata in task_nodes.items() if tdata.get("artifact_ref") is not None]
        if task_ids_for_artifacts:
            selected_task_artifact_id = st.selectbox("Voir l'artefact de la tâche:", options=task_ids_for_artifacts, key=f"artifact_sel_{st.session_state.selected_plan_id}")
            if selected_task_artifact_id:
                artifact_data = task_nodes[selected_task_artifact_id].get("artifact_ref")
                with st.expander(f"Artefact pour {selected_task_artifact_id}", expanded=True):
                    if isinstance(artifact_data, dict):
                        st.json(artifact_data)
                    else:
                        st.text_area("", value=str(artifact_data), height=200, key=f"art_text_{selected_task_artifact_id}")
        else:
            st.info("Aucun artefact avec contenu pour ce plan.")
            
        with st.expander("Données brutes du plan (JSON)"):
            st.json(plan_details)
            
    elif st.session_state.selected_plan_id:
        st.info("Chargement des détails du plan...")
    else:
        st.info("Sélectionnez un plan dans la liste pour voir ses détails.")

