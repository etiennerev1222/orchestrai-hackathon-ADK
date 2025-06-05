# app_frontend.py
import streamlit as st
import httpx
import asyncio
import json 
from typing import Dict, Any, Optional, List
import os
import graphviz
import pandas as pd # Pour manipuler les données pour le graphe
import sys
import pathlib
from streamlit_agraph import agraph, Node, Edge, Config # L'import peut varier légèrement

# Ajout pour le chemin (si app_frontend.py est dans src et vous l'exécutez depuis la racine du projet)
# Si vous exécutez streamlit run src/app_frontend.py depuis la racine,
# et que src est reconnu comme un package, cet append n'est pas toujours nécessaire.
# Mais s'il fonctionne pour vous, gardons-le.
sys.path.append(str(pathlib.Path(__file__).parent.parent))

from src.shared.execution_task_graph_management import ExecutionTaskState


# --- Constantes et Classes ---
class GlobalPlanState:
    INITIAL_OBJECTIVE_RECEIVED = "INITIAL_OBJECTIVE_RECEIVED"
    CLARIFICATION_PENDING_USER_INPUT = "CLARIFICATION_PENDING_USER_INPUT"
    OBJECTIVE_BEING_CLARIFIED_BY_AGENT = "OBJECTIVE_BEING_CLARIFIED_BY_AGENT"
    OBJECTIVE_CLARIFIED = "OBJECTIVE_CLARIFIED"
    TEAM1_PLANNING_INITIATED = "TEAM1_PLANNING_INITIATED"
    TEAM1_PLANNING_COMPLETED = "TEAM1_PLANNING_COMPLETED"
    TEAM1_PLANNING_FAILED = "TEAM1_PLANNING_FAILED"
    TEAM2_EXECUTION_INITIATING = "TEAM2_EXECUTION_INITIATING"
    TEAM2_EXECUTION_IN_PROGRESS = "TEAM2_EXECUTION_IN_PROGRESS"
    TEAM2_EXECUTION_COMPLETED = "TEAM2_EXECUTION_COMPLETED"
    TEAM2_EXECUTION_FAILED = "TEAM2_EXECUTION_FAILED"
    FAILED_MAX_CLARIFICATION_ATTEMPTS = "FAILED_MAX_CLARIFICATION_ATTEMPTS"
    FAILED_AGENT_ERROR = "FAILED_AGENT_ERROR"
   
BACKEND_API_URL = os.environ.get("GRA_BACKEND_API_URL", "http://localhost:8000")

# --- Fonctions Clientes API ---
async def get_global_plans_summary_from_api():
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{BACKEND_API_URL}/v1/global_plans_summary", timeout=10.0)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            st.error(f"Erreur récupération liste plans globaux: {e}")
            return []

async def submit_new_global_plan_to_api(objective: str, user_id: Optional[str] = "default_streamlit_user"):
    async with httpx.AsyncClient() as client:
        try:
            payload = {"objective": objective, "user_id": user_id}
            response = await client.post(f"{BACKEND_API_URL}/v1/global_plans", json=payload, timeout=30.0)
            response.raise_for_status()
            return response.json() 
        except Exception as e:
            st.error(f"Erreur soumission nouveau plan global: {e}")
            return None

async def submit_clarification_response_to_api(global_plan_id: str, user_response: str):
    async with httpx.AsyncClient() as client:
        try:
            payload = {"user_response": user_response}
            response = await client.post(f"{BACKEND_API_URL}/v1/global_plans/{global_plan_id}/respond", json=payload, timeout=30.0)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            st.error(f"Erreur soumission réponse clarification: {e}")
            return None

async def get_global_plan_details_from_api(global_plan_id: str):
    if not global_plan_id:
        return None
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{BACKEND_API_URL}/v1/global_plans/{global_plan_id}", timeout=10.0)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                st.warning(f"Plan global '{global_plan_id}' non trouvé.")
                return None
            st.error(f"Erreur HTTP récupération détails plan {global_plan_id}: {e}")
            return None
        except Exception as e:
            st.error(f"Erreur récupération détails plan {global_plan_id}: {e}")
            return None

async def get_task_graph_details_from_api(task_graph_plan_id: str): # Pour TEAM 1
    if not task_graph_plan_id:
        return None
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{BACKEND_API_URL}/plans/{task_graph_plan_id}", timeout=10.0) 
            response.raise_for_status()
            return response.json() 
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                st.warning(f"Détails du TaskGraph (TEAM 1) pour '{task_graph_plan_id}' non trouvés.")
                return None
            st.error(f"Erreur HTTP lors de la récupération du TaskGraph (TEAM 1) {task_graph_plan_id}: {e}")
            return None
        except Exception as e:
            st.error(f"Erreur lors de la récupération du TaskGraph (TEAM 1) {task_graph_plan_id}: {e}")
            return None

async def get_execution_task_graph_details_from_api(execution_plan_id: str): # Pour TEAM 2
    if not execution_plan_id:
        return None
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{BACKEND_API_URL}/v1/execution_task_graphs/{execution_plan_id}", timeout=10.0)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                st.warning(f"Détails du graphe d'exécution (TEAM 2) pour '{execution_plan_id}' non trouvés.")
                return None
            st.error(f"Erreur HTTP lors de la récupération du graphe d'exécution (TEAM 2) {execution_plan_id}: {e}")
            return None
        except Exception as e:
            st.error(f"Erreur lors de la récupération du graphe d'exécution (TEAM 2) {execution_plan_id}: {e}")
            return None

async def check_agent_health(agent_url: str, client: httpx.AsyncClient) -> bool: # Fonction check_agent_health (gardée)
    if not agent_url:
        return False
    try:
        card_url = agent_url.strip('/') + "/.well-known/agent.json"
        response = await client.get(card_url, timeout=5.0)
        return response.status_code == 200
    except Exception:
        return False

async def get_agents_status_with_health_from_api():
    async with httpx.AsyncClient() as client:
        try:
            response_agents = await client.get(f"{BACKEND_API_URL}/agents_status", timeout=10.0)
            response_agents.raise_for_status()
            agents_list = response_agents.json()
            
            enriched_agents_status = []
            for agent_info in agents_list:
                is_healthy = await check_agent_health(agent_info.get("url"), client) # Utilisation de check_agent_health
                agent_info["health_status"] = "✅ Online" if is_healthy else "⚠️ Offline"
                agent_info["health_color"] = "green" if is_healthy else "orange"
                enriched_agents_status.append(agent_info)
            return enriched_agents_status
        except Exception as e:
            st.error(f"Erreur récupération statut enrichi agents: {e}")
            return []

async def accept_and_start_planning_api(global_plan_id: str, user_final_objective: Optional[str] = None):
    async with httpx.AsyncClient() as client:
        try:
            payload = {}
            if user_final_objective: # S'assurer que la chaîne n'est pas vide non plus
                payload["user_final_objective"] = user_final_objective
            
            response = await client.post(f"{BACKEND_API_URL}/v1/global_plans/{global_plan_id}/accept_and_plan", json=payload, timeout=30.0)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            st.error(f"Erreur acceptation objectif / lancement TEAM 1: {e}")
            return None

async def get_artifact_content_from_api(gra_artifact_id: str):
    if not gra_artifact_id:
        return None
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{BACKEND_API_URL}/artifacts/{gra_artifact_id}", timeout=10.0)
            response.raise_for_status()
            artifact_data = response.json()
            return artifact_data.get("content", f"Contenu de l'artefact '{gra_artifact_id}' non trouvé dans la réponse.")
        except Exception as e:
            st.error(f"Erreur récupération contenu artefact {gra_artifact_id}: {e}")
            return f"Erreur: Impossible de récupérer l'artefact {gra_artifact_id}. {e}"

# --- Fonctions de gestion d'état ---
# Garder UNE SEULE définition de refresh_active_global_plan_details
def refresh_active_global_plan_details():
    if st.session_state.active_global_plan_id:
        details = asyncio.run(get_global_plan_details_from_api(st.session_state.active_global_plan_id))
        st.session_state.active_global_plan_details = details
        if details:
            if details.get("current_supervisor_state") == GlobalPlanState.CLARIFICATION_PENDING_USER_INPUT:
                st.session_state.last_question_to_user = details.get("last_question_to_user")
                if details.get("last_agent_response_artifact"):
                    st.session_state.editable_enriched_objective_text = details["last_agent_response_artifact"].get("tentatively_enriched_objective", details.get("raw_objective",""))
                else:
                    st.session_state.editable_enriched_objective_text = details.get("raw_objective","")
            else: 
                st.session_state.last_question_to_user = None
                st.session_state.editable_enriched_objective_text = details.get("clarified_objective", details.get("raw_objective",""))
            
            # Réinitialiser l'artefact et les graphes spécifiques si le plan change ou est rechargé
            st.session_state.selected_artifact_content = None
            st.session_state.selected_artifact_task_id = None
            # Forcer le rechargement des graphes la prochaine fois qu'ils sont nécessaires pour ce plan
            if st.session_state.current_task_graph_id_loaded == details.get("team1_plan_id"):
                pass # Ne pas réinitialiser si c'est déjà le bon
            else:
                 st.session_state.current_task_graph_id_loaded = None 
                 st.session_state.current_task_graph_details = None

            if st.session_state.current_execution_graph_id_loaded == details.get("team2_execution_plan_id"):
                pass
            else:
                st.session_state.current_execution_graph_id_loaded = None
                st.session_state.current_execution_graph_details = None
        else: 
            st.session_state.active_global_plan_details = None
            st.session_state.last_question_to_user = None
            st.session_state.editable_enriched_objective_text = ""
            st.session_state.selected_artifact_content = None
            st.session_state.selected_artifact_task_id = None
            st.session_state.current_task_graph_id_loaded = None 
            st.session_state.current_task_graph_details = None
            st.session_state.current_execution_graph_id_loaded = None
            st.session_state.current_execution_graph_details = None

def load_initial_data():
    if 'agents_status' not in st.session_state or not st.session_state.agents_status : 
        st.session_state.agents_status = asyncio.run(get_agents_status_with_health_from_api())
    if 'global_plans_summary_list' not in st.session_state or not st.session_state.global_plans_summary_list: 
        st.session_state.global_plans_summary_list = asyncio.run(get_global_plans_summary_from_api())
    
    if st.session_state.active_global_plan_id and \
       (not st.session_state.active_global_plan_details or \
        st.session_state.active_global_plan_details.get("global_plan_id") != st.session_state.active_global_plan_id):
        refresh_active_global_plan_details()

# Garder UNE SEULE définition de handle_select_task_for_artifact
def handle_select_task_for_artifact(task_id: str, artifact_ref: Optional[str]):
    st.session_state.selected_artifact_task_id = task_id
    st.session_state.selected_artifact_content = "Chargement de l'artefact..." # Message temporaire
    if artifact_ref:
        # Pas de spinner ici car le callback ne le montrera pas avant le prochain rerun
        content = asyncio.run(get_artifact_content_from_api(artifact_ref))
        st.session_state.selected_artifact_content = content
    else:
        st.session_state.selected_artifact_content = "Aucun artefact (output_artifact_ref) n'est associé à cette tâche."


# --- Callbacks --- (garder les versions uniques et correctes)
def handle_submit_clarification_response():
    user_typed_response = st.session_state.clarification_response_input_key 
    if user_typed_response and st.session_state.active_global_plan_id:
        api_response = asyncio.run(submit_clarification_response_to_api(
            st.session_state.active_global_plan_id,
            user_typed_response
        ))
        if api_response:
            st.session_state.clarification_response_input_key = "" 
            refresh_active_global_plan_details()
            st.rerun() # Forcer le rafraîchissement de l'affichage
        else:
            st.error("Échec de l'envoi de la réponse.") 
    elif not user_typed_response:
        st.warning("Veuillez entrer une réponse.")
    elif not st.session_state.active_global_plan_id:
        st.warning("Aucun plan actif sélectionné pour envoyer une réponse.")


def handle_accept_and_plan():
    if not st.session_state.active_global_plan_id:
        st.warning("Aucun plan actif sélectionné.")
        return
    final_objective_to_send = st.session_state.editable_enriched_objective_text
    payload_objective = final_objective_to_send if final_objective_to_send and final_objective_to_send.strip() else None

    api_response = asyncio.run(accept_and_start_planning_api(
        st.session_state.active_global_plan_id,
        user_final_objective=payload_objective
    ))
    if api_response:
        st.toast(f"Objectif accepté. Lancement de TEAM 1 pour plan '{st.session_state.active_global_plan_id}'.", icon="✅")
        refresh_active_global_plan_details()
        st.rerun()
    else:
        st.error("Échec de l'acceptation de l'objectif ou du lancement de TEAM 1.")

def handle_launch_global_plan():
    objective_text = st.session_state.new_objective_sidebar_key
    if objective_text:
        api_response = asyncio.run(submit_new_global_plan_to_api(objective_text))
        if api_response and api_response.get("global_plan_id"):
            new_plan_id = api_response.get("global_plan_id")
            st.session_state.active_global_plan_id = new_plan_id
            st.toast(f"Plan global '{new_plan_id}' initié.", icon="🚀")
            st.session_state.new_objective_sidebar_key = "" 
            st.session_state.clarification_response_input_key = ""
            st.session_state.editable_enriched_objective_text = ""
            st.session_state.current_task_graph_details = None
            st.session_state.current_task_graph_id_loaded = None
            st.session_state.current_execution_graph_details = None
            st.session_state.current_execution_graph_id_loaded = None
            st.session_state.selected_artifact_content = None
            st.session_state.selected_artifact_task_id = None
            st.session_state.global_plans_summary_list = asyncio.run(get_global_plans_summary_from_api())
            refresh_active_global_plan_details()
            st.rerun()
        else:
            st.error("Échec de l'initiation du plan global.")
    else:
        st.warning("Veuillez entrer un objectif.")

# --- Interface Streamlit ---
st.set_page_config(layout="wide", page_title="OrchestrAI Dashboard v2.4")
st.title("🤖 OrchestrAI - Planification & Exécution Intelligente")

# Initialisation de l'état de session (assurez-vous que toutes les clés sont là)
# ... (votre bloc d'initialisation existant, vérifiez que toutes les clés utilisées sont initialisées)
for key in ['clarification_response_input_key', 'active_global_plan_id', 
            'active_global_plan_details', 'last_question_to_user', 'agents_status',
            'global_plans_summary_list', 'editable_enriched_objective_text',
            'current_task_graph_details', 'current_task_graph_id_loaded',
            'current_execution_graph_details', 'current_execution_graph_id_loaded',
            'selected_artifact_content', 'selected_artifact_task_id', 
            'new_objective_sidebar_key', 'team1_agent_tasks_count_stats', # Ajouté pour les stats
            'team1_agent_stats_last_updated']: # Ajouté pour les stats
    if key not in st.session_state:
        st.session_state[key] = None if not key.endswith("_list") and not key.endswith("_key") else ([] if key.endswith("_list") else ("" if key.endswith("_key") else None) )


load_initial_data()

# --- Sidebar ---
with st.sidebar:
    st.header("🚀 Nouveau Plan Global")
    st.text_area("Objectif initial:", height=100, key="new_objective_sidebar_key")
    st.button("Lancer Planification", key="launch_global_plan_button_sidebar_main", on_click=handle_launch_global_plan)

    st.markdown("---")
    st.header("📋 Plans Globaux Existants")
    if not st.session_state.global_plans_summary_list:
        st.info("Aucun plan global. Lancez un nouveau plan.")
    else:
        plan_options = {plan['global_plan_id']: f"{plan['raw_objective'][:30]}{'...' if len(plan['raw_objective']) > 30 else ''} (État: {plan.get('current_supervisor_state', 'N/A')})" for plan in st.session_state.global_plans_summary_list}
        
        # S'assurer que active_global_plan_id est valide ou None
        current_active_id = st.session_state.active_global_plan_id
        if current_active_id not in plan_options:
            current_active_id = None # ou le premier de la liste si vous préférez

        selected_id = st.radio( # Radio peut être mieux pour peu d'options, sinon selectbox
            "Sélectionnez un Plan :",
            options=list(plan_options.keys()),
            format_func=lambda x: plan_options[x],
            index = list(plan_options.keys()).index(current_active_id) if current_active_id else 0,
            key="global_plan_selector_sidebar_radio"
        )
        
        if selected_id != st.session_state.active_global_plan_id:
            st.session_state.active_global_plan_id = selected_id
            refresh_active_global_plan_details() # Cela va aussi réinitialiser les artefacts/graphes chargés
            st.rerun()

    st.markdown("---")
    st.header("⚙️ Actions")
    if st.button("Rafraîchir Tout", key="refresh_all_sidebar_button"): 
        with st.spinner("Rafraîchissement..."):
            st.session_state.agents_status = asyncio.run(get_agents_status_with_health_from_api())
            st.session_state.global_plans_summary_list = asyncio.run(get_global_plans_summary_from_api())
            # Réinitialiser les graphes chargés pour forcer le rechargement si un plan est actif
            st.session_state.current_task_graph_id_loaded = None
            st.session_state.current_execution_graph_id_loaded = None
            if st.session_state.active_global_plan_id:
                refresh_active_global_plan_details()
        st.rerun()

    st.markdown("---")
    st.header("📡 Statut des Agents (Sidebar)")
    if st.session_state.agents_status:
        for agent_info in st.session_state.agents_status:
            agent_name = agent_info.get('name', 'Agent Inconnu')
            health_status_text = agent_info.get("health_status", "❓")
            health_color = agent_info.get("health_color", "grey")
            status_indicator_html = f"<span style='color: {health_color};'>●</span> {health_status_text.split(' ')[-1]}"
            with st.expander(f"{agent_name}"):
                st.markdown(status_indicator_html, unsafe_allow_html=True)
                st.caption(f"URL: {agent_info.get('url', 'N/A')}")
                st.caption(f"Compétences: {', '.join(agent_info.get('skills', []))}")
    else:
        st.info("Statut des agents non disponible.")

# --- Zone d'affichage principale ---
# Statut des agents en haut (peut être redondant avec la sidebar, à vous de choisir)
# st.subheader("📡 Aperçu des Agents Enregistrés") 
# ... (votre logique d'affichage horizontal si vous la gardez) ...
# st.markdown("---")

main_col, artifact_col = st.columns([0.65, 0.35]) # Ajuster les proportions

with main_col:
    st.header("🔍 Plan Actif & Graphes")
    if not st.session_state.active_global_plan_id or not st.session_state.active_global_plan_details:
        st.info("Sélectionnez un plan dans la barre latérale ou lancez un nouveau plan.")
    else:
        plan = st.session_state.active_global_plan_details
        st.subheader(f"Plan Global : `{plan.get('global_plan_id')}`")
        # ... (affichage des détails du plan global comme Objectif, Etat, etc.)
        st.text_area("Objectif Initial:", value=plan.get('raw_objective', 'N/A'), height=75, disabled=True, key=f"raw_obj_display_{plan.get('global_plan_id')}")
        st.info(f"État Actuel: **{plan.get('current_supervisor_state', 'N/A')}**")
        if plan.get("task_type_estimation"): st.caption(f"Type estimé: {plan.get('task_type_estimation')}")
        if plan.get("clarification_attempts"): st.caption(f"Tentatives de clarification: {plan.get('clarification_attempts')}")


        # --- Section Dialogue pour la Clarification ---
        if plan.get("current_supervisor_state") == GlobalPlanState.CLARIFICATION_PENDING_USER_INPUT:
            st.markdown("---")
            st.subheader("❓ Clarification et Enrichissement")
            agent_artifact = plan.get("last_agent_response_artifact", {})
            tentative_obj = agent_artifact.get("tentatively_enriched_objective", st.session_state.editable_enriched_objective_text)
            if not tentative_obj : tentative_obj = plan.get("raw_objective","") # Fallback
            st.session_state.editable_enriched_objective_text = st.text_area(
                "Objectif Enrichi/Modifiable (proposé par l'agent ou votre dernière version) :", 
                value=tentative_obj, height=150, key="editable_obj_clarification"
            )
            if agent_artifact.get("proposed_elements"):
                st.markdown("**Éléments Proposés/Assumés par l'Agent :**")
                st.json(agent_artifact.get("proposed_elements"))
            if st.session_state.last_question_to_user:
                st.info(f"**Agent demande :** {st.session_state.last_question_to_user}")
            
            st.text_area("Votre réponse/commentaires :", height=75, key="clarification_response_input_key" )
            
            btn_cols = st.columns(2)
            with btn_cols[0]:
                st.button("Soumettre Réponse", key="submit_clarification_main_btn", on_click=handle_submit_clarification_response )
            with btn_cols[1]:
                st.button("✅ Valider Objectif & Lancer TEAM 1", key="accept_and_plan_main_btn", on_click=handle_accept_and_plan )
        
        elif plan.get("current_supervisor_state") == GlobalPlanState.OBJECTIVE_CLARIFIED:
             st.success(f"Objectif clarifié. Prêt pour TEAM 1. Objectif final:\n_{plan.get('clarified_objective')}_")
             if st.button("Lancer TEAM 1 manuellement (si pas auto)", key="manual_launch_team1"): # Au cas où
                handle_accept_and_plan() # Cette fonction devrait utiliser l'objectif déjà clarifié

        # ... (Autres messages d'état pour TEAM1 et TEAM2 comme avant) ...
        if plan.get("current_supervisor_state", "").startswith("TEAM1_"):
             st.info(f"Statut TEAM 1 ({plan.get('team1_plan_id', 'N/A')}): {plan.get('team1_status', 'En cours...')}")
        if plan.get("current_supervisor_state", "").startswith("TEAM2_"):
             st.info(f"Statut TEAM 2 ({plan.get('team2_execution_plan_id', 'N/A')}): {plan.get('team2_status', 'En cours...')}")


        # --- Affichage du Graphe TEAM 1 ---
        team1_plan_id = plan.get("team1_plan_id")
        if team1_plan_id:
            st.markdown("---")
            st.subheader(f"📊 Graphe de Planification (TEAM 1 : `{team1_plan_id}`)")
            if st.session_state.current_task_graph_id_loaded != team1_plan_id:
                with st.spinner(f"Chargement du graphe TEAM 1 {team1_plan_id}..."):
                    st.session_state.current_task_graph_details = asyncio.run(get_task_graph_details_from_api(team1_plan_id))
                    st.session_state.current_task_graph_id_loaded = team1_plan_id
                    st.rerun()
            
            if st.session_state.current_task_graph_details:
                # ... (votre code graphviz pour TEAM 1, avec boutons pour handle_select_task_for_artifact)
                # Exemple simplifié pour un bouton d'artefact (à adapter pour tous les noeuds avec artefacts)
                nodes_t1 = st.session_state.current_task_graph_details.get("nodes", {})
                for node_id, node_info in nodes_t1.items():
                    if node_info.get("artifact_ref"): # Si la tâche a un artefact
                        if st.button(f"Artefact T1: {node_id[:8]} ({node_info.get('objective', '')[:20]}...)", key=f"art_btn_t1_{node_id}"):
                            handle_select_task_for_artifact(node_id, node_info.get("artifact_ref"))
                            # Pas besoin de rerun ici, l'affichage de l'artefact se mettra à jour
                # ... (le reste de votre code graphviz pour TEAM 1) ...
                # Affichage du graphe... (votre code graphviz existant pour TEAM 1)
                with st.expander("Données brutes graphe TEAM 1", expanded=False):
                    st.json(st.session_state.current_task_graph_details)


        # --- Affichage du Graphe TEAM 2 ---
        team2_exec_id = plan.get("team2_execution_plan_id")
        if team2_exec_id and plan.get("current_supervisor_state", "").startswith("TEAM2_"):
            st.markdown("---")
            st.subheader(f"📈 Graphe d'Exécution (TEAM 2 : `{team2_exec_id}`)")


            
            if st.session_state.current_execution_graph_id_loaded != team2_exec_id:
                with st.spinner(f"Chargement du graphe d'exécution {team2_exec_id}..."):
                    st.session_state.current_execution_graph_details = asyncio.run(get_execution_task_graph_details_from_api(team2_exec_id))
                    st.session_state.current_execution_graph_id_loaded = team2_exec_id
                    st.rerun()

            if st.session_state.current_execution_graph_details:
                exec_graph_data = st.session_state.current_execution_graph_details
                nodes_data_t2 = exec_graph_data.get("nodes", {})
                if not nodes_data_t2 and exec_graph_data.get("overall_status") == "PENDING_DECOMPOSITION":
                    st.info("Plan d'exécution en attente de décomposition...")
                elif not nodes_data_t2:
                    st.info("Aucun nœud à afficher pour le graphe d'exécution.")
                else:
                    # Affichage des boutons d'artefacts pour TEAM 2 AVANT le graphe
                    st.markdown("##### Artefacts produits par TEAM 2 :")
                    for node_id, node_info in nodes_data_t2.items():
                        if node_info.get("state") == ExecutionTaskState.COMPLETED.value and node_info.get("output_artifact_ref"):
                            btn_label = f"Artefact: {node_id[:12]}... ({node_info.get('objective', 'N/A')[:25]}...)"
                            if st.button(btn_label, key=f"art_btn_t2_{node_id}"):
                                handle_select_task_for_artifact(node_id, node_info.get("output_artifact_ref"))
                                # st.rerun() # Le rerun est géré par handle_select_task si besoin d'update immédiat de la colonne artifact
                    
                    # Affichage du graphe interactif via streamlit-agraph pour TEAM 2
                    try:
                        a_nodes: List[Node] = []
                        a_edges: List[Edge] = []
                        start_node_id = f"decompose_{team2_exec_id}"
                        start_added = False
                        for node_id, node_info in nodes_data_t2.items():
                            node_state_val = node_info.get("state")
                            color = "grey"
                            if node_state_val == ExecutionTaskState.COMPLETED.value:
                                color = "lightgreen"
                            elif node_state_val == ExecutionTaskState.FAILED.value:
                                color = "lightcoral"

                            label = node_info.get("objective", node_id)[:30]
                            a_nodes.append(
                                Node(
                                    id=node_id,
                                    title=node_id,
                                    label=label,
                                    color=color,
                                    shape="box",
                                )
                            )

                            for dep_id in node_info.get("dependencies", []):
                                if dep_id in nodes_data_t2:
                                    a_edges.append(Edge(source=dep_id, target=node_id))
                                elif dep_id == start_node_id:
                                    if not start_added:
                                        a_nodes.append(
                                            Node(
                                                id=start_node_id,
                                                label="Start: Decomp.",
                                                color="purple",
                                                shape="ellipse",
                                            )
                                        )
                                        start_added = True
                                    a_edges.append(Edge(source=start_node_id, target=node_id))

                        config = Config(
                            height=600,
                            width=800,
                            directed=True,
                            hierarchical=True,
                        )
                        agraph(nodes=a_nodes, edges=a_edges, config=config)
                    except Exception as e:
                        st.error(f"Erreur génération graphe TEAM 2 avec agraph: {e}")
                
                with st.expander("Données brutes graphe TEAM 2", expanded=False):
                    st.json(st.session_state.current_execution_graph_details)
            elif st.session_state.current_execution_graph_id_loaded == team2_exec_id:
                st.info(f"Aucun détail de graphe pour TEAM 2 '{team2_exec_id}'.")


with artifact_col:
    st.header("📄 Artefacts Produits (TEAM 2)")
    if st.session_state.current_execution_graph_details:
        exec_nodes = st.session_state.current_execution_graph_details.get("nodes", {})
        found_artifacts = False
        for node_id, node_info in exec_nodes.items():
            if node_info.get("state") == ExecutionTaskState.COMPLETED.value and node_info.get("output_artifact_ref"):
                found_artifacts = True
                artifact_button_label = node_info.get("meta", {}).get("local_nom_from_agent", node_info.get("objective", node_id))
                if st.button(f"Voir: {artifact_button_label[:40]}...", key=f"view_art_t2_{node_id}"):
                    handle_select_task_for_artifact(node_id, node_info.get("output_artifact_ref"))
                    # Pas besoin de st.rerun() ici, la colonne d'artefact se mettra à jour
        if not found_artifacts:
            st.caption("Aucun artefact produit pour TEAM 2 pour l'instant.")    
    st.header("📄 Artefact Sélectionné")
    if st.session_state.selected_artifact_task_id:
        st.markdown(f"**Artefact de la tâche :**")
        st.code(st.session_state.selected_artifact_task_id, language=None) # Utiliser st.code pour les ID longs
        
        if st.session_state.selected_artifact_content == "Chargement de l'artefact...":
            st.info("Chargement de l'artefact...")
        elif st.session_state.selected_artifact_content:
            content_to_display = st.session_state.selected_artifact_content
            try:
                # Essayer de pretty-print si c'est un JSON string
                parsed_json = json.loads(content_to_display)
                st.json(parsed_json)
            except (json.JSONDecodeError, TypeError):
                # Sinon, afficher comme texte (pourrait être du code, etc.)
                # Utiliser st.code pour le code, ou st.text_area pour du texte plus long
                if "```python" in content_to_display or "import " in content_to_display or "def " in content_to_display :
                    st.code(content_to_display, language="python", line_numbers=True)
                else:
                    st.text_area("Contenu :", value=str(content_to_display), height=600, disabled=True, key="artifact_display_text_area")
        else:
            st.info("Aucun contenu d'artefact à afficher (ou l'artefact est vide).")
    else:
        st.info("Cliquez sur un bouton 'Artefact...' pour afficher son contenu ici.")
