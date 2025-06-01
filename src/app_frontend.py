# app_frontend.py
import streamlit as st
import httpx
import asyncio
import json 
from typing import Dict, Any, Optional, List
import os
import graphviz

# --- Constantes et Classes ---
class GlobalPlanState:
    INITIAL_OBJECTIVE_RECEIVED = "INITIAL_OBJECTIVE_RECEIVED"
    CLARIFICATION_PENDING_USER_INPUT = "CLARIFICATION_PENDING_USER_INPUT"
    OBJECTIVE_BEING_CLARIFIED_BY_AGENT = "OBJECTIVE_BEING_CLARIFIED_BY_AGENT"
    OBJECTIVE_CLARIFIED = "OBJECTIVE_CLARIFIED"
    TEAM1_PLANNING_INITIATED = "TEAM1_PLANNING_INITIATED"
    TEAM1_PLANNING_COMPLETED = "TEAM1_PLANNING_COMPLETED"
    TEAM1_PLANNING_FAILED = "TEAM1_PLANNING_FAILED"
    FAILED_MAX_CLARIFICATION_ATTEMPTS = "FAILED_MAX_CLARIFICATION_ATTEMPTS"
    FAILED_AGENT_ERROR = "FAILED_AGENT_ERROR"

BACKEND_API_URL = os.environ.get("GRA_BACKEND_API_URL", "http://localhost:8000")

# --- Fonctions Clientes API ---
async def get_global_plans_summary_from_api():
    # ... (identique à votre version)
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{BACKEND_API_URL}/v1/global_plans_summary", timeout=10.0)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            st.error(f"Erreur récupération liste plans globaux: {e}")
            return []

async def submit_new_global_plan_to_api(objective: str, user_id: Optional[str] = "default_streamlit_user"):
    # ... (identique à votre version)
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
    # ... (identique à votre version)
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
    # ... (identique à votre version)
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

async def get_task_graph_details_from_api(task_graph_plan_id: str):
    # ... (identique à ma proposition précédente)
    if not task_graph_plan_id:
        return None
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{BACKEND_API_URL}/plans/{task_graph_plan_id}", timeout=10.0) 
            response.raise_for_status()
            return response.json() 
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                st.warning(f"Détails du TaskGraph pour '{task_graph_plan_id}' non trouvés.")
                return None
            st.error(f"Erreur HTTP lors de la récupération du TaskGraph {task_graph_plan_id}: {e}")
            return None
        except Exception as e:
            st.error(f"Erreur lors de la récupération du TaskGraph {task_graph_plan_id}: {e}")
            return None

async def get_agents_status_from_api():
    # ... (identique à votre version)
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{BACKEND_API_URL}/agents_status", timeout=10.0)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            st.error(f"Erreur récupération statut agents: {e}")
            return []

# --- NOUVELLE Fonction API pour Accepter l'Objectif ---
async def accept_and_start_planning_api(global_plan_id: str, user_final_objective: Optional[str] = None):
    async with httpx.AsyncClient() as client:
        try:
            payload = {}
            if user_final_objective is not None: # Envoyer seulement si non None ou non vide
                payload["user_final_objective"] = user_final_objective
            
            response = await client.post(f"{BACKEND_API_URL}/v1/global_plans/{global_plan_id}/accept_and_plan", json=payload, timeout=30.0)
            response.raise_for_status()
            return response.json() # Devrait correspondre à GlobalPlanResponse
        except Exception as e:
            st.error(f"Erreur lors de l'acceptation de l'objectif et du lancement de TEAM 1: {e}")
            return None

# --- Fonctions de gestion d'état ---
def refresh_active_global_plan_details():
    if st.session_state.active_global_plan_id:
        details = asyncio.run(get_global_plan_details_from_api(st.session_state.active_global_plan_id))
        st.session_state.active_global_plan_details = details
        if details:
            if details.get("current_supervisor_state") == GlobalPlanState.CLARIFICATION_PENDING_USER_INPUT:
                st.session_state.last_question_to_user = details.get("last_question_to_user")
                # Pré-remplir l'objectif éditable avec la dernière proposition de l'agent
                if details.get("last_agent_response_artifact"):
                    st.session_state.editable_enriched_objective_text = details["last_agent_response_artifact"].get("tentatively_enriched_objective", "")
                else: # Fallback si pas d'artefact ou d'objectif enrichi
                    st.session_state.editable_enriched_objective_text = details.get("raw_objective","")
            else:
                st.session_state.last_question_to_user = None
                st.session_state.editable_enriched_objective_text = details.get("clarified_objective", details.get("raw_objective",""))
    else:
        st.session_state.active_global_plan_details = None
        st.session_state.last_question_to_user = None
        st.session_state.editable_enriched_objective_text = ""

def load_initial_data():
    # ... (identique à ma proposition précédente)
    if 'agents_status' not in st.session_state or not st.session_state.agents_status : 
        st.session_state.agents_status = asyncio.run(get_agents_status_from_api())
    if 'global_plans_summary_list' not in st.session_state or not st.session_state.global_plans_summary_list: 
        st.session_state.global_plans_summary_list = asyncio.run(get_global_plans_summary_from_api())
    if st.session_state.active_global_plan_id and not st.session_state.active_global_plan_details:
        refresh_active_global_plan_details()

# --- NOUVELLES Fonctions Callback ---
def handle_submit_clarification_response():
    # ... (identique à ma proposition précédente)
    user_typed_response = st.session_state.clarification_response_input_key 
    if user_typed_response:
        api_response = asyncio.run(submit_clarification_response_to_api(
            st.session_state.active_global_plan_id,
            user_typed_response
        ))
        if api_response:
            st.session_state.clarification_response_input_key = "" 
            refresh_active_global_plan_details() 
        else:
            st.error("Échec de l'envoi de la réponse lors du callback.") 
    else:
        st.warning("Veuillez entrer une réponse avant de soumettre.")

def handle_accept_and_plan(): # NOUVEAU CALLBACK
    final_objective_to_send = st.session_state.editable_enriched_objective_text # Récupérer l'objectif potentiellement modifié
    
    # On peut choisir de ne l'envoyer que s'il est non vide, sinon le backend prendra le dernier connu.
    # Pour être explicite, on l'envoie s'il est non vide.
    payload_objective = final_objective_to_send if final_objective_to_send and final_objective_to_send.strip() else None

    api_response = asyncio.run(accept_and_start_planning_api(
        st.session_state.active_global_plan_id,
        user_final_objective=payload_objective
    ))
    if api_response:
        st.toast(f"Objectif accepté. Lancement de TEAM 1 pour plan '{st.session_state.active_global_plan_id}'.", icon="✅")
        refresh_active_global_plan_details() # Pour obtenir le nouvel état (ex: TEAM1_PLANNING_INITIATED)
    else:
        st.error("Échec de l'acceptation de l'objectif ou du lancement de TEAM 1.")

# --- NOUVELLE FONCTION CALLBACK pour le lancement de plan ---
def handle_launch_global_plan():
    objective_text = st.session_state.new_objective_sb_key # Lire la valeur via la clé
    if objective_text:
        # Le spinner ici ne sera pas visible pendant l'exécution du callback direct
        # avant le prochain rerun. Pour un feedback utilisateur pendant l'appel API,
        # des techniques plus avancées ou un simple message pourraient être utilisés.
        # Pour l'instant, la logique principale :
        api_response = asyncio.run(submit_new_global_plan_to_api(objective_text))
        if api_response and api_response.get("global_plan_id"):
            st.session_state.active_global_plan_id = api_response.get("global_plan_id")
            # st.success s'affichera au prochain rerun
            st.toast(f"Plan global '{st.session_state.active_global_plan_id}' initié.", icon="🚀")


            # Vider les champs pour le prochain rendu
            st.session_state.new_objective_sb_key = "" 
            if 'clarification_response_input_key' in st.session_state: # S'assurer que cette clé existe
                st.session_state.clarification_response_input_key = "" 
            
            # Rafraîchir les données pour le prochain rendu
            st.session_state.global_plans_summary_list = asyncio.run(get_global_plans_summary_from_api())
            refresh_active_global_plan_details()
            # Streamlit gère le rerun automatiquement après un callback qui modifie l'état.
            # st.rerun() n'est généralement pas nécessaire ici, et peut même parfois causer des doubles exécutions.
        else:
            st.error("Échec de l'initiation du plan global.") # S'affichera au prochain rerun
    else:
        st.warning("Veuillez entrer un objectif.") # S'affichera au prochain rerun


# --- Interface Streamlit ---
st.set_page_config(layout="wide", page_title="OrchestrAI Dashboard v2.2")
st.title("🤖 OrchestrAI - Planification Intelligente et Itérative")

# Initialiser l'état de session (si pas déjà fait)
if 'clarification_response_input_key' not in st.session_state: st.session_state.clarification_response_input_key = ""
if 'active_global_plan_id' not in st.session_state: st.session_state.active_global_plan_id = None
if 'active_global_plan_details' not in st.session_state: st.session_state.active_global_plan_details = None
if 'last_question_to_user' not in st.session_state: st.session_state.last_question_to_user = None
if 'agents_status' not in st.session_state: st.session_state.agents_status = []
if 'global_plans_summary_list' not in st.session_state: st.session_state.global_plans_summary_list = []
if 'current_task_graph_details' not in st.session_state: st.session_state.current_task_graph_details = None
if 'current_task_graph_id_loaded' not in st.session_state: st.session_state.current_task_graph_id_loaded = None
# NOUVEL état pour l'objectif éditable
if 'editable_enriched_objective_text' not in st.session_state:
    st.session_state.editable_enriched_objective_text = ""


load_initial_data()

# --- Sidebar ---
# ... (identique à ma proposition précédente, avec le callback handle_launch_global_plan)
with st.sidebar:
    st.header("🚀 Nouveau Plan Global")
    if 'new_objective_sb_key' not in st.session_state: st.session_state.new_objective_sb_key = ""
    st.text_area("Objectif initial:", height=100, key="new_objective_sb_key")
    
    st.button(
        "Lancer Planification", 
        key="launch_global_plan_button_sidebar_main_cb_v2", 
        on_click=handle_launch_global_plan # Le callback que vous aviez déjà pour le lancement
    )
    # ... (Reste de la sidebar : Rafraîchir Tout, Statut des Agents - identique) ...
    st.markdown("---")
    st.header("⚙️ Actions")
    if st.button("Rafraîchir Tout", key="refresh_all_button_sidebar_cb_main_v2"): 
        with st.spinner("Rafraîchissement..."):
            st.session_state.agents_status = asyncio.run(get_agents_status_from_api())
            st.session_state.global_plans_summary_list = asyncio.run(get_global_plans_summary_from_api())
            if st.session_state.active_global_plan_id:
                refresh_active_global_plan_details()
            if st.session_state.active_global_plan_details and st.session_state.active_global_plan_details.get("team1_plan_id"):
                 st.session_state.current_task_graph_details = asyncio.run(get_task_graph_details_from_api(st.session_state.active_global_plan_details.get("team1_plan_id")))
                 st.session_state.current_task_graph_id_loaded = st.session_state.active_global_plan_details.get("team1_plan_id")
        st.rerun()

    st.sidebar.markdown("---")
    st.sidebar.header("📡 Statut des Agents")
    if 'agents_status' in st.session_state and st.session_state.agents_status:
        for agent_info in st.session_state.agents_status:
            st.sidebar.expander(f"{agent_info.get('name', 'Agent Inconnu')}").json(agent_info)
    else:
        st.sidebar.info("Aucun agent enregistré ou statut indisponible.")


# --- Colonnes Principales ---
col1, col2 = st.columns([1, 2])

with col1:
    # ... (Affichage de la liste des plans globaux - identique à ma proposition précédente) ...
    st.header("📋 Plans Globaux")
    if not st.session_state.global_plans_summary_list:
        st.info("Aucun plan global. Cliquez sur 'Rafraîchir Tout' ou lancez un nouveau plan.")
    else:
        plan_display_options = { plan['global_plan_id']: (f"{plan['raw_objective'][:30]}{'...' if len(plan['raw_objective']) > 30 else ''} (État: {plan.get('current_supervisor_state', 'N/A')})") for plan in st.session_state.global_plans_summary_list }
        active_plan_index = 0
        options_keys = list(plan_display_options.keys())
        if st.session_state.active_global_plan_id and st.session_state.active_global_plan_id in options_keys: active_plan_index = options_keys.index(st.session_state.active_global_plan_id)
        if options_keys: 
            selected_global_plan_id_from_list = st.radio( "Sélectionnez un Plan Global:", options=options_keys, format_func=lambda x: plan_display_options[x], index=active_plan_index, key="global_plan_selector_radio_key_v2" )
            if selected_global_plan_id_from_list != st.session_state.active_global_plan_id:
                st.session_state.active_global_plan_id = selected_global_plan_id_from_list
                st.session_state.clarification_response_input_key = ""; st.session_state.editable_enriched_objective_text = ""
                st.session_state.current_task_graph_details = None; st.session_state.current_task_graph_id_loaded = None
                refresh_active_global_plan_details()
                st.rerun()
        else: st.info("Aucun plan global à afficher dans la liste.")


with col2:
    st.header("🔍 Détails et Interaction du Plan Actif")
    # ... (Logique d'affichage des détails du plan - identique jusqu'à la section de clarification) ...
    if not st.session_state.active_global_plan_id:
        st.info("Sélectionnez un plan dans la liste de gauche ou lancez un nouveau plan.")
    else:
        if not st.session_state.active_global_plan_details:
            refresh_active_global_plan_details()
            if not st.session_state.active_global_plan_details:
                 st.warning(f"Impossible de charger les détails pour {st.session_state.active_global_plan_id}.")
                 st.stop()
            else: st.rerun() 

        plan = st.session_state.active_global_plan_details

        if plan:
            st.subheader(f"Plan : `{plan.get('global_plan_id')}`")
            # ... (Affichage Objectif Initial, État, Type Tâche, Tentatives - identique) ...
            st.markdown(f"**Objectif Initial:**"); st.text_area("Raw Objective Display", value=plan.get('raw_objective', 'N/A'), height=75, disabled=True, key=f"raw_obj_display_col2_v2_{plan.get('global_plan_id')}")
            st.markdown(f"**État Actuel Superviseur:** `{plan.get('current_supervisor_state', 'N/A')}`")
            st.markdown(f"**Type Tâche (LLM):** `{plan.get('task_type_estimation', 'N/A')}`")
            st.markdown(f"**Tentatives Clarification:** `{plan.get('clarification_attempts', 0)}`")

            if plan.get("clarified_objective"):
                st.markdown(f"**Objectif Clarifié Final:**"); st.text_area("Final Clarified Objective Display", value=plan.get('clarified_objective'), height=100, disabled=True, key=f"final_clar_obj_display_col2_{plan.get('global_plan_id')}")
            
            # --- Section Dialogue pour la Clarification (MODIFIÉE) ---
            if plan.get("current_supervisor_state") == GlobalPlanState.CLARIFICATION_PENDING_USER_INPUT:
                st.markdown("---")
                st.subheader("❓ Clarification et Enrichissement par l'Agent")

                agent_artifact = plan.get("last_agent_response_artifact", {})
                tentative_obj = agent_artifact.get("tentatively_enriched_objective", "")
                proposed_elements = agent_artifact.get("proposed_elements", {})
                agent_question = plan.get("last_question_to_user", "") # Ou agent_artifact.get("question_for_user", "")

                if tentative_obj:
                    st.markdown("**Objectif Enrichi Proposé par l'Agent (vous pouvez le modifier ci-dessous) :**")
                    # L'état de ce text_area est géré par st.session_state.editable_enriched_objective_text
                    # Il est pré-rempli par refresh_active_global_plan_details
                    st.text_area("Objectif Enrichi/Modifiable:", 
                                 value=st.session_state.editable_enriched_objective_text, 
                                 height=150, 
                                 key="editable_enriched_objective_text")
                
                if proposed_elements:
                    st.markdown("**Éléments Proposés/Assumés par l'Agent :**")
                    st.json(proposed_elements)

                if agent_question:
                    st.info(f"**Agent demande aussi :** {agent_question}")
                
                st.text_area( "Votre réponse/commentaires additionnels à la question et aux propositions :", height=100, key="clarification_response_input_key" )
                
                col_btn1, col_btn2 = st.columns(2)
                with col_btn1:
                    st.button( "Soumettre Réponse pour Continuer Clarification", key="submit_clarification_cb_key_v2", on_click=handle_submit_clarification_response )
                with col_btn2:
                    st.button( "✅ Valider Objectif Actuel & Lancer TEAM 1", key="accept_and_plan_button_key", on_click=handle_accept_and_plan )
            
            # ... (Affichage des autres états : OBJECTIVE_CLARIFIED, FAILED_MAX_..., etc. - identique) ...
            elif plan.get("current_supervisor_state") == GlobalPlanState.OBJECTIVE_CLARIFIED:
                st.success("🎉 Objectif clarifié par l'agent ! Prêt pour TEAM 1.")
            elif plan.get("current_supervisor_state") == GlobalPlanState.TEAM1_PLANNING_INITIATED:
                st.success(f"🚀 Planification TEAM 1 (ID: {plan.get('team1_plan_id')}) initiée !")
            elif plan.get("current_supervisor_state") == GlobalPlanState.TEAM1_PLANNING_COMPLETED:
                st.balloons()
                st.success(f"✅ Planification TEAM 1 (ID: {plan.get('team1_plan_id')}) terminée avec succès !")
            elif plan.get("current_supervisor_state") == GlobalPlanState.TEAM1_PLANNING_FAILED:
                st.error(f"❌ Échec de la planification TEAM 1 (ID: {plan.get('team1_plan_id')}). Détails: {plan.get('team1_status', '')}")

            # ... (Affichage Historique Conversation - identique) ...
            if plan.get("conversation_history"):
                with st.expander("Voir l'historique de la conversation", expanded=False): # expanded=False par défaut
                    for i, turn in enumerate(plan.get("conversation_history", [])):
                        st.markdown(f"**Tour {i+1}**"); st.text_area(f"Agent ({i+1}):", value=turn.get("agent_question", ""), disabled=True, height=75, key=f"hist_q_col2_v2_{plan.get('global_plan_id')}_{i}"); st.text_area(f"Vous ({i+1}):", value=turn.get("user_answer", ""), disabled=True, height=75, key=f"hist_a_col2_v2_{plan.get('global_plan_id')}_{i}"); st.markdown("---")
            
            # --- Affichage du Graphe TEAM 1 ---
            # (identique à ma proposition précédente)
            if plan.get("team1_plan_id"):
                # ... (code d'affichage du graphe) ...
                 team1_id = plan.get("team1_plan_id"); st.markdown("---"); st.subheader(f"Graphe de Tâches (Plan TEAM 1: `{team1_id}`)")
                 if st.session_state.current_task_graph_id_loaded != team1_id:
                    with st.spinner(f"Chargement du graphe pour {team1_id}..."):
                        st.session_state.current_task_graph_details = asyncio.run(get_task_graph_details_from_api(team1_id))
                        st.session_state.current_task_graph_id_loaded = team1_id
                 if st.session_state.current_task_graph_details:
                    task_graph_data = st.session_state.current_task_graph_details
                    try:
                        dot = graphviz.Digraph(comment=f'Task Graph for {team1_id}'); dot.attr(rankdir='TB')
                        nodes_data = task_graph_data.get("nodes", {});
                        if not nodes_data: st.info("Aucun nœud pour le graphe.")
                        for node_id, node_info in nodes_data.items():
                            label_lines = [ f"ID: {node_id}", f"Obj: {node_info.get('objective', 'N/A')[:35]}{'...' if len(node_info.get('objective', 'N/A')) > 35 else ''}", f"Agent: {node_info.get('assigned_agent', 'N/A')}", f"État: {node_info.get('state', 'N/A')}"]; label = "\\n".join(label_lines)
                            color = "grey"; node_state = node_info.get('state')
                            if node_state == "completed": color = "lightgreen"
                            elif node_state == "failed": color = "lightcoral"
                            elif node_state == "working": color = "lightblue"
                            elif node_state == "submitted": color = "yellow"
                            dot.node(node_id, label=label, shape="box", style="filled", fillcolor=color)
                            parent_id = node_info.get("parent")
                            if parent_id and parent_id in nodes_data: dot.edge(parent_id, node_id)
                        st.graphviz_chart(dot, use_container_width=True)
                    except Exception as e: st.error(f"Erreur génération graphe: {e}"); st.json(task_graph_data)
                 elif st.session_state.current_task_graph_id_loaded == team1_id : st.info(f"Aucun détail de graphe pour TEAM 1 '{team1_id}'.")


            with st.expander("Données brutes du plan global (JSON)", expanded=False):
                st.json(plan)
