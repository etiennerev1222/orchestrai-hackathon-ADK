
import streamlit as st
import httpx
import asyncio
import json 
from typing import Dict, Any, Optional, List
import os
from streamlit_agraph import agraph, Node, Edge, Config
import sys
import pathlib

sys.path.append(str(pathlib.Path(__file__).parent.parent))
from src.shared.execution_task_graph_management import ExecutionTaskState
from src.shared.task_graph_management import TaskState

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
    if not global_plan_id: return None
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{BACKEND_API_URL}/v1/global_plans/{global_plan_id}", timeout=10.0)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404: st.warning(f"Plan global '{global_plan_id}' non trouvé.")
            else: st.error(f"Erreur HTTP récupération détails plan {global_plan_id}: {e}")
            return None
        except Exception as e:
            st.error(f"Erreur récupération détails plan {global_plan_id}: {e}")
            return None

async def get_task_graph_details_from_api(task_graph_plan_id: str):
    if not task_graph_plan_id: return None
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{BACKEND_API_URL}/plans/{task_graph_plan_id}", timeout=10.0) 
            response.raise_for_status()
            return response.json() 
        except Exception as e:
            st.error(f"Erreur lors de la récupération du TaskGraph (TEAM 1) {task_graph_plan_id}: {e}")
            return None

async def get_execution_task_graph_details_from_api(execution_plan_id: str):
    if not execution_plan_id: return None
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{BACKEND_API_URL}/v1/execution_task_graphs/{execution_plan_id}", timeout=10.0)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            st.error(f"Erreur lors de la récupération du graphe d'exécution (TEAM 2) {execution_plan_id}: {e}")
            return None

async def get_agents_status_with_health_from_api():
    async with httpx.AsyncClient() as client:
        try:
            response_agents = await client.get(f"{BACKEND_API_URL}/agents_status", timeout=10.0)
            response_agents.raise_for_status()
            agents_list = response_agents.json()

            async def fetch_health_and_card(agent: Dict[str, Any]):
                url = agent.get("public_url")
                is_healthy = False
                card_data = None
                if url:
                    card_url = url.rstrip("/") + "/.well-known/agent.json"
                    try:
                        res = await client.get(card_url, timeout=5.0)
                        is_healthy = res.status_code == 200
                        if res.status_code == 200:
                            card_data = res.json()
                    except Exception:
                        is_healthy = False
                return is_healthy, card_data

            tasks = [fetch_health_and_card(agent) for agent in agents_list]
            results = await asyncio.gather(*tasks)

            for agent, (is_healthy, card) in zip(agents_list, results):
                agent["health_status"] = "✅ Online" if is_healthy else "⚠️ Offline"
                agent["health_color"] = "green" if is_healthy else "orange"
                if card:
                    agent["card"] = card
            return agents_list
        except Exception as e:
            st.error(f"Erreur récupération statut enrichi agents: {e}")
            return []

async def get_all_agent_task_stats_from_api():
    """Récupère les statistiques globales de tâches traitées par les agents."""
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{BACKEND_API_URL}/v1/stats/agent_tasks", timeout=10.0)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            st.error(f"Erreur récupération statistiques agents: {e}")
            return None

async def get_agent_stats_from_api():
    """Récupère les statistiques de traitement des tâches pour chaque agent."""
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{BACKEND_API_URL}/v1/stats/agents", timeout=10.0)
            response.raise_for_status()
            data = response.json()
            return data.get("stats", [])
        except Exception as e:
            st.error(f"Erreur récupération statistiques individuelles agents: {e}")
            return []

async def accept_and_start_planning_api(global_plan_id: str, user_final_objective: Optional[str] = None):
    async with httpx.AsyncClient() as client:
        try:
            payload = {"user_final_objective": user_final_objective} if user_final_objective else {}
            response = await client.post(f"{BACKEND_API_URL}/v1/global_plans/{global_plan_id}/accept_and_plan", json=payload, timeout=30.0)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            st.error(f"Erreur acceptation objectif / lancement TEAM 1: {e}")
            return None

async def get_artifact_content_from_api(gra_artifact_id: str):
    if not gra_artifact_id: return None
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{BACKEND_API_URL}/artifacts/{gra_artifact_id}", timeout=10.0)
            response.raise_for_status()
            artifact_data = response.json()
            return artifact_data.get("content")
        except Exception as e:
            st.error(f"Erreur récupération contenu artefact {gra_artifact_id}: {e}")
            return f"Erreur: Impossible de récupérer l'artefact {gra_artifact_id}. {e}"


def initialize_session_state():
    """Initialise toutes les clés nécessaires au premier lancement."""
    keys_to_init = {
        'active_global_plan_id': None, 'active_global_plan_details': None, 
        'global_plans_summary_list': [], 'agents_status': [],
        'agents_stats': [],
        'current_task_graph_details': None, 'current_task_graph_id_loaded': None,
        'current_execution_graph_details': None, 'current_execution_graph_id_loaded': None,
        'selected_artifact_content': None, 'selected_artifact_task_id': None,
        'new_objective_sidebar_key': "", 'clarification_response_input_key': "",
        'editable_enriched_objective_text': "",
        'show_artifact_modal': False
    }
    for key, default_value in keys_to_init.items():
        if key not in st.session_state:
            st.session_state[key] = default_value

def handle_node_click(node_id: str, is_team1: bool):
    """Callback unique pour gérer le clic sur un noeud de graphe."""
    if not node_id: return

    st.session_state.selected_artifact_task_id = node_id
    st.session_state.selected_artifact_content = "Chargement de l'artefact..."

    graph_data = st.session_state.current_task_graph_details if is_team1 else st.session_state.current_execution_graph_details
    node_data = graph_data.get("nodes", {}).get(node_id) if graph_data else None

    if not node_data:
        st.session_state.selected_artifact_content = f"Détails du noeud {node_id} non trouvés."
        return

    artifact_ref_key = "artifact_ref" if is_team1 else "output_artifact_ref"
    artifact_ref = node_data.get(artifact_ref_key)

    if not artifact_ref:
        st.session_state.selected_artifact_content = "Ce noeud n'a pas d'artefact de sortie associé."
        return

    if is_team1:
        st.session_state.selected_artifact_content = json.dumps(artifact_ref, indent=2, ensure_ascii=False) if isinstance(artifact_ref, dict) else str(artifact_ref)
    else:
        content = asyncio.run(get_artifact_content_from_api(artifact_ref))
        st.session_state.selected_artifact_content = content or "Contenu de l'artefact non trouvé ou vide."

    st.session_state.show_artifact_modal = True


def render_artifact_content(content: Any, display_key: str):
    """Affiche le contenu d'un artefact dans le bon format."""
    if content == "Chargement...":
        st.info(content)
    elif content:
        try:
            parsed_json = json.loads(content)
            st.json(parsed_json, key=f"{display_key}_json")
        except (json.JSONDecodeError, TypeError):
            if "```python" in content or "import " in content:
                st.code(content, language="python", line_numbers=True, key=f"{display_key}_code")
            else:
                st.text_area("Contenu :", value=str(content), height=600, disabled=True, key=f"{display_key}_textarea")
    else:
        st.info("Aucun contenu d'artefact à afficher.")
def display_agent_status_bar(agents_status: List[Dict[str, Any]], agent_stats: Optional[List[Dict[str, Any]]] = None):
    """Affiche les agents dans des containers avec nom, statut, date et stats."""
    st.subheader("📡 Statut des Agents")
    if not agents_status:
        st.info("Aucun agent n'a été découvert. Vérifiez que le GRA et les serveurs d'agents sont lancés.")
        return

    stats_map = {s.get("agent_name"): s for s in (agent_stats or [])}

    cols = st.columns(len(agents_status))
    for i, agent in enumerate(agents_status):
        with cols[i]:
            name = agent.get("name", "Inconnu").replace("AgentServer", "")
            status_text = agent.get("health_status", "Offline")
            ts = agent.get("timestamp")
            ts_str = str(ts)
            public_url = agent.get("public_url")
            card = agent.get("card")
            skills = ", ".join(agent.get("skills", []))

            with st.container(border=True):
                st.markdown(f"**{name}**")
                st.markdown(status_text)
                st.caption(f"Maj : {ts_str}")
                if public_url:
                    st.markdown(f"[URL Publique]({public_url})")
                if card:
                    with st.expander("Agent Card"):
                        st.json(card)
                agent_stat = stats_map.get(agent.get("name"))
                if agent_stat:
                    cols_metrics = st.columns(2)
                    cols_metrics[0].metric("Succès", agent_stat.get("tasks_completed", 0))
                    cols_metrics[1].metric("Échecs", agent_stat.get("tasks_failed", 0))

def compute_state_counts(nodes: Dict[str, Dict[str, Any]]) -> Dict[str, int]:
    """Calcule le nombre de tâches par état."""
    counts: Dict[str, int] = {}
    for n in nodes.values():
        state = n.get("state", "unknown")
        counts[state] = counts.get(state, 0) + 1
    return counts



st.set_page_config(layout="wide", page_title="OrchestrAI Dashboard")
initialize_session_state()

st.title("🤖 OrchestrAI - Tableau de Bord")

agents_status_list = asyncio.run(get_agents_status_with_health_from_api())
agents_stats_list = asyncio.run(get_agent_stats_from_api())
display_agent_status_bar(agents_status_list, agents_stats_list)
st.markdown("---")

main_col, artifact_col = st.columns([0.65, 0.35])

initialize_session_state()

with st.sidebar:
    st.header("🚀 Nouveau Plan Global")
    st.text_area("Objectif initial:", height=100, key="new_objective_sidebar_key")
    if st.button("Lancer Planification", key="launch_global_plan_button"):
        if st.session_state.new_objective_sidebar_key:
            asyncio.run(submit_new_global_plan_to_api(st.session_state.new_objective_sidebar_key))
            st.session_state.new_objective_sidebar_key = ""
        else:
            st.warning("Veuillez entrer un objectif.")

    st.markdown("---")
    st.header("📋 Plans Globaux Existants")
    if st.button("Rafraîchir la liste des plans", key="refresh_plans_list"):
        st.session_state.global_plans_summary_list = asyncio.run(get_global_plans_summary_from_api())

    if not st.session_state.global_plans_summary_list:
        st.session_state.global_plans_summary_list = asyncio.run(get_global_plans_summary_from_api())
    
    if not st.session_state.global_plans_summary_list:
        st.info("Aucun plan global trouvé.")
    else:
        sorted_plans = sorted(st.session_state.global_plans_summary_list, key=lambda p: p.get('updated_at', ''), reverse=True)
        plan_options = {plan['global_plan_id']: f"ID: {plan['global_plan_id']} | {plan['raw_objective'][:30]}..." for plan in sorted_plans}
        
        selected_id = st.selectbox(
            "Sélectionnez un Plan :",
            options=list(plan_options.keys()),
            format_func=lambda pid: plan_options.get(pid, pid),
            key="global_plan_selector"
        )
        st.session_state.active_global_plan_id = selected_id

main_col, artifact_col = st.columns([0.65, 0.35])

with main_col:
    if st.session_state.agents_status:
        agents_status_list = asyncio.run(get_agents_status_with_health_from_api())
        agents_stats_list = asyncio.run(get_agent_stats_from_api())
        display_agent_status_bar(agents_status_list, agents_stats_list)
        st.markdown("---")
    st.header("🔍 Plan Actif & Graphes")
    if st.session_state.active_global_plan_id:
        if not st.session_state.active_global_plan_details or st.session_state.active_global_plan_details.get("global_plan_id") != st.session_state.active_global_plan_id:
             with st.spinner("Chargement des détails du plan..."):
                st.session_state.active_global_plan_details = asyncio.run(get_global_plan_details_from_api(st.session_state.active_global_plan_id))
        
        plan = st.session_state.active_global_plan_details
        if plan:
            st.markdown(
                f"**Plan ID** : `{plan.get('global_plan_id')}`\n\n"
                f"**Objectif brut** : {plan.get('raw_objective')}\n\n"
                + (f"**Objectif clarifié** : {plan.get('clarified_objective')}\n\n" if plan.get('clarified_objective') else "")
                + f"**État actuel** : `{plan.get('current_supervisor_state')}`"
            )

            finished_states = [
                GlobalPlanState.TEAM2_EXECUTION_COMPLETED,
                GlobalPlanState.TEAM2_EXECUTION_FAILED,
                GlobalPlanState.TEAM1_PLANNING_FAILED,
                GlobalPlanState.FAILED_MAX_CLARIFICATION_ATTEMPTS,
                GlobalPlanState.FAILED_AGENT_ERROR,
            ]
            flow_running = plan.get("current_supervisor_state") not in finished_states
            st.markdown(f"**Flux en cours** : {'🟢 Oui' if flow_running else '🏁 Terminé'}")

            team1_counts = None
            team2_counts = None



            team1_plan_id = plan.get("team1_plan_id")
            if team1_plan_id:
                st.subheader(f"📊 Graphe de Planification (TEAM 1 : `{team1_plan_id}`)")

                if st.session_state.current_task_graph_id_loaded != team1_plan_id:
                    st.session_state.current_task_graph_details = asyncio.run(get_task_graph_details_from_api(team1_plan_id))
                    st.session_state.current_task_graph_id_loaded = team1_plan_id

                if st.session_state.current_task_graph_details:
                    nodes_t1 = st.session_state.current_task_graph_details.get("nodes", {})
                    if nodes_t1:
                        team1_counts = compute_state_counts(nodes_t1)
                        a_nodes, a_edges = [], []
                        for node_id, node_info in nodes_t1.items():
                            node_state_val = node_info.get("state")
                            color = {"background": "#D3D3D3", "border": "#808080"}
                            if node_state_val == TaskState.COMPLETED.value:
                                color = {"background": "#D4EDDA", "border": "#155724"}
                            elif node_state_val in [TaskState.FAILED.value, TaskState.UNABLE.value]:
                                color = {"background": "#F8D7DA", "border": "#721C24"}
                            elif node_state_val == TaskState.WORKING.value:
                                color = {"background": "#FFF3CD", "border": "#856404"}

                            label = node_info.get("objective", node_id)[:35]
                            title = (
                                f"ID: {node_id}\nAgent: {node_info.get('assigned_agent', 'N/A')}"
                                f"\nÉtat: {node_state_val}\nObjectif: {node_info.get('objective', 'N/A')}"
                            )
                            a_nodes.append(
                                Node(id=node_id, label=label, title=title, shape="box", color=color, font={"color": "black"})
                            )

                        for node_id, node_info in nodes_t1.items():
                            for child_id in node_info.get("children", []):
                                if child_id in nodes_t1:
                                    a_edges.append(Edge(source=node_id, target=child_id, color="gray"))

                        config = Config(
                            width=1200,
                            height=900,
                            directed=True,
                            physics=False,
                            layout={
                                "hierarchical": {
                                    "enabled": True,
                                    "direction": "UD",
                                    "sortMethod": "directed",
                                    "levelSeparation": 250,
                                    "nodeSpacing": 200,
                                }
                            },
                        )

                        clicked_node_id = agraph(nodes=a_nodes, edges=a_edges, config=config)

                        if clicked_node_id and clicked_node_id != st.session_state.selected_artifact_task_id:
                            handle_node_click(clicked_node_id, is_team1=True)
                            st.rerun()
                    else:
                        st.info("Le graphe de planification est vide.")
                else:
                    st.info("Le graphe de planification est introuvable.")


            team2_exec_id = plan.get("team2_execution_plan_id")
            if team2_exec_id:
                st.subheader(f"📈 Graphe d'Exécution (TEAM 2 : `{team2_exec_id}`)")
                if st.session_state.current_execution_graph_id_loaded != team2_exec_id:
                    st.session_state.current_execution_graph_details = asyncio.run(get_execution_task_graph_details_from_api(team2_exec_id))
                    st.session_state.current_execution_graph_id_loaded = team2_exec_id

                if st.session_state.current_execution_graph_details:
                    nodes_data_t2 = st.session_state.current_execution_graph_details.get("nodes", {})
                    if nodes_data_t2:
                        team2_counts = compute_state_counts(nodes_data_t2)
                        a_nodes, a_edges = [], []
                        for node_id, node_info in nodes_data_t2.items():
                            node_state_val = node_info.get("state")
                            color = {"background": "#D3D3D3", "border": "#808080"}
                            if node_state_val == ExecutionTaskState.COMPLETED.value: color = {"background": "#D4EDDA", "border": "#155724"}
                            elif node_state_val == ExecutionTaskState.FAILED.value: color = {"background": "#F8D7DA", "border": "#721C24"}
                            elif node_state_val == ExecutionTaskState.WORKING.value: color = {"background": "#FFF3CD", "border": "#856404"}
                            
                            label = node_info.get("objective", node_id)[:35]
                            title = f"ID: {node_id}\nÉtat: {node_state_val}\nObjectif: {node_info.get('objective', 'N/A')}"
                            a_nodes.append(Node(id=node_id, label=label, title=title, shape="box", color=color, font={"color": "black"}))

                            for dep_id in node_info.get("dependencies", []):
                                if dep_id in nodes_data_t2:
                                    a_edges.append(Edge(source=dep_id, target=node_id, color="gray"))
                        
                        config = Config(width=1200, height=900, directed=True, physics=False, layout={"hierarchical": {"enabled": True, "direction": "UD", "sortMethod": "directed", "levelSeparation": 250, "nodeSpacing": 200}})
                        
                        clicked_node_id = agraph(nodes=a_nodes, edges=a_edges, config=config)
                        
                        if clicked_node_id and clicked_node_id != st.session_state.selected_artifact_task_id:
                            handle_node_click(clicked_node_id, is_team1=False)
                            st.rerun()
                    else:
                        st.info("Le graphe d'exécution est en attente de décomposition.")

            if team1_counts or team2_counts:
                with st.expander("📊 Statistiques du plan"):
                    if team1_counts:
                        st.markdown("**TEAM 1**")
                        st.json(team1_counts)
                    if team2_counts:
                        st.markdown("**TEAM 2**")
                        st.json(team2_counts)
    else:
        st.info("Sélectionnez un plan dans la barre latérale pour commencer.")

    if st.session_state.get('show_artifact_modal'):
        with st.modal("Artefact"):
            st.markdown(f"**Tâche :** `{st.session_state.selected_artifact_task_id}`")
            modal_display_key = f"modal_art_display_{st.session_state.selected_artifact_task_id}"
            render_artifact_content(st.session_state.get('selected_artifact_content'), modal_display_key)
        st.session_state.show_artifact_modal = False

with artifact_col:
    st.header("📄 Artefact Sélectionné")
    if st.session_state.get('selected_artifact_task_id'):
        st.markdown(f"**Tâche :** `{st.session_state.selected_artifact_task_id}`")

        content = st.session_state.get('selected_artifact_content')
        display_key = f"art_display_{st.session_state.selected_artifact_task_id}"
        render_artifact_content(content, display_key)
    else:
        st.info("Cliquez sur un nœud dans un graphe pour voir son artefact.")
