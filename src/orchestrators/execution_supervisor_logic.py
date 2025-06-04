# src/orchestrators/execution_supervisor_logic.py
import logging
import uuid
import asyncio
from typing import Optional, Dict, Any, List
import httpx
import json

from src.shared.execution_task_graph_management import (
    ExecutionTaskGraph,
    ExecutionTaskNode,
    ExecutionTaskState,
    ExecutionTaskType
)
from src.shared.service_discovery import get_gra_base_url
from src.clients.a2a_api_client import call_a2a_agent
from a2a.types import Artifact as A2ATypeArtifact 

from src.agents.testing_agent.logic import AGENT_SKILL_SOFTWARE_TESTING
from src.agents.development_agent.logic import AGENT_SKILL_CODING_PYTHON
from src.agents.decomposition_agent.logic import AGENT_SKILL_DECOMPOSE_EXECUTION_PLAN

logger = logging.getLogger(__name__) # Logger au niveau du module

class ExecutionSupervisorLogic:
    def __init__(self, global_plan_id: str, team1_plan_final_text: str):
        self.global_plan_id = global_plan_id
        self.team1_plan_final_text = team1_plan_final_text
        self._local_to_global_id_map_for_plan: Dict[str, str] = {}
        
        self.execution_plan_id = f"exec_{self.global_plan_id}_{uuid.uuid4().hex[:8]}"
        self.task_graph = ExecutionTaskGraph(execution_plan_id=self.execution_plan_id)
        
        self._gra_base_url: Optional[str] = None
        self.logger = logging.getLogger(f"{__name__}.ExecutionSupervisorLogic.{self.execution_plan_id}")
        if not self.logger.hasHandlers() and not self.logger.propagate:
            if not logging.getLogger().hasHandlers():
                logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        self.logger.info(f"ExecutionSupervisorLogic initialisé pour global_plan '{global_plan_id}'. Execution plan ID: '{self.execution_plan_id}'")

    async def initialize_and_decompose_plan(self):
        """
        Tâche initiale : faire décomposer le plan textuel de TEAM 1 en ExecutionTaskGraph.
        """
        self.logger.info(f"[{self.execution_plan_id}] Initialisation et décomposition du plan de TEAM 1.")
        self.task_graph.set_overall_status("INITIALIZING")
        self._local_to_global_id_map_for_plan.clear() 

        decomposition_task_id = f"decompose_{self.execution_plan_id}"
        decomposition_task = ExecutionTaskNode(
            task_id=decomposition_task_id,
            objective="Décomposer le plan textuel de TEAM 1 en tâches d'exécution structurées.",
            task_type=ExecutionTaskType.DECOMPOSITION,
            assigned_agent_type=AGENT_SKILL_DECOMPOSE_EXECUTION_PLAN
        )
        self.task_graph.add_task(decomposition_task, is_root=True)
        self.task_graph.update_task_state(decomposition_task_id, ExecutionTaskState.READY, "Prêt pour décomposition initiale.")
        
        self.logger.info(f"[{self.execution_plan_id}] Tâche de décomposition '{decomposition_task_id}' créée et marquée READY.")
        self.task_graph.set_overall_status("PENDING_DECOMPOSITION")

    async def _ensure_gra_url(self):
        if not self._gra_base_url:
            self._gra_base_url = await get_gra_base_url()
            if not self._gra_base_url:
                msg = f"[{self.execution_plan_id}] Impossible de découvrir l'URL du GRA."
                self.logger.error(msg)
                raise ConnectionError(msg)
        return self._gra_base_url

    async def _get_agent_details_from_gra(self, skill: str) -> Optional[Dict[str, str]]:
        gra_url = await self._ensure_gra_url()
        agent_details = None
        try:
            async with httpx.AsyncClient() as client:
                self.logger.info(f"[{self.execution_plan_id}] Demande au GRA ({gra_url}) un agent avec la compétence: '{skill}'")
                response = await client.get(f"{gra_url}/agents", params={"skill": skill}, timeout=10.0)
                response.raise_for_status()
                data = response.json()
                if data.get("url") and data.get("name"):
                    agent_details = {"url": data["url"], "name": data["name"]}
                    self.logger.info(f"[{self.execution_plan_id}] Détails pour '{skill}' obtenus du GRA: {agent_details}")
                else:
                    self.logger.error(f"[{self.execution_plan_id}] Données incomplètes du GRA pour '{skill}'. Réponse: {data}")
        except httpx.HTTPStatusError as e:
            self.logger.error(f"[{self.execution_plan_id}] Erreur HTTP ({e.response.status_code}) en contactant le GRA pour '{skill}' à {e.request.url}: {e.response.text}")
        except httpx.RequestError as e:
            self.logger.error(f"[{self.execution_plan_id}] Erreur de requête en contactant le GRA pour '{skill}': {e}")
        except Exception as e:
            self.logger.error(f"[{self.execution_plan_id}] Erreur inattendue en contactant le GRA pour '{skill}': {e}", exc_info=True)
        return agent_details

    async def _store_a2a_artifact_in_gra(self, 
                                          a2a_artifact_to_store: A2ATypeArtifact, 
                                          a2a_task_id: str, 
                                          a2a_context_id: str, 
                                          producing_agent_name: str) -> Optional[str]:
        gra_url = await self._ensure_gra_url()
        if not gra_url:
            return None

        content_for_gra: Optional[str | Dict[str, Any]] = None
        if a2a_artifact_to_store.parts:
            first_part = a2a_artifact_to_store.parts[0]
            if hasattr(first_part, 'root') and hasattr(first_part.root, 'text'):
                 content_for_gra = first_part.root.text
            elif hasattr(first_part, 'text'):
                 content_for_gra = first_part.text

        if content_for_gra is None:
            self.logger.warning(f"[{self.execution_plan_id}] L'artefact A2A (ID local: {a2a_artifact_to_store.artifactId}) n'a pas de contenu textuel extractible pour le stockage GRA.")
            return None

        gra_artifact_payload = {
            "task_id": a2a_task_id,
            "context_id": a2a_context_id,
            "agent_name": producing_agent_name,
            "content": content_for_gra 
        }
        
        try:
            async with httpx.AsyncClient() as client:
                self.logger.info(f"[{self.execution_plan_id}] Stockage de l'artefact (produit par {producing_agent_name} pour tâche {a2a_task_id}) via GRA: {gra_url}/artifacts")
                self.logger.debug(f"Payload pour GRA /artifacts: {json.dumps(gra_artifact_payload, indent=2)}")
                response = await client.post(f"{gra_url}/artifacts", json=gra_artifact_payload, timeout=10.0)
                response.raise_for_status()
                response_data = response.json()
                gra_artifact_id = response_data.get("artifact_id")
                if gra_artifact_id:
                    self.logger.info(f"[{self.execution_plan_id}] Artefact stocké avec succès dans GRA. ID GRA: {gra_artifact_id} (ID A2A local était: {a2a_artifact_to_store.artifactId})")
                    return gra_artifact_id
                else:
                    self.logger.error(f"[{self.execution_plan_id}] Le GRA n'a pas retourné d'artifact_id après stockage. Réponse: {response_data}")
                    return None
        except Exception as e:
            self.logger.error(f"[{self.execution_plan_id}] Erreur lors du stockage de l'artefact via GRA: {e}", exc_info=True)
            return None

    async def _fetch_artifact_content(self, gra_artifact_id: str) -> Optional[str]:
        if not gra_artifact_id:
            self.logger.warning(f"[{self.execution_plan_id}] ID d'artefact GRA vide fourni pour récupération.")
            return None
        try:
            gra_url = await self._ensure_gra_url()
            async with httpx.AsyncClient() as client:
                self.logger.info(f"[{self.execution_plan_id}] Récupération de l'artefact GRA ID '{gra_artifact_id}'.")
                response = await client.get(f"{gra_url}/artifacts/{gra_artifact_id}", timeout=10.0)
                response.raise_for_status()
                artifact_data_from_gra = response.json()
                
                content = artifact_data_from_gra.get("content")
                if isinstance(content, str):
                    return content
                elif isinstance(content, dict):
                    return json.dumps(content, ensure_ascii=False)
                else:
                    self.logger.warning(f"[{self.execution_plan_id}] Artefact GRA ID '{gra_artifact_id}' a un contenu de type inattendu: {type(content)}.")
                    return str(content)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.logger.error(f"[{self.execution_plan_id}] Artefact GRA ID '{gra_artifact_id}' non trouvé dans le GRA (404).")
            else:
                self.logger.error(f"[{self.execution_plan_id}] Erreur HTTP lors de la récupération de l'artefact GRA ID '{gra_artifact_id}': {e}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"[{self.execution_plan_id}] Erreur lors de la récupération du contenu de l'artefact GRA ID '{gra_artifact_id}': {e}", exc_info=True)
            return None

    async def _prepare_input_for_execution_agent(self, task_node: ExecutionTaskNode) -> str:
        input_payload = {
            "objective": task_node.objective,
            "local_instructions": task_node.meta.get("local_instructions", []),
            "acceptance_criteria": task_node.meta.get("acceptance_criteria", []),
            "task_id": task_node.id,
            "execution_plan_id": self.execution_plan_id,
            "task_type": task_node.task_type.value,
             "assigned_skill": task_node.assigned_agent_type 
        }

        if task_node.task_type == ExecutionTaskType.EXPLORATORY:
            available_skills = await self._get_all_available_execution_skills_from_gra()
            input_payload["available_execution_skills"] = available_skills
            self.logger.debug(f"[{self.execution_plan_id}] Ajout de {len(available_skills)} compétences disponibles à l'input pour la tâche exploratoire {task_node.id}")

        if task_node.assigned_agent_type == AGENT_SKILL_SOFTWARE_TESTING and task_node.dependencies:
            self.logger.debug(f"[{self.execution_plan_id}] Tâche de test {task_node.id}. Recherche du livrable parmi les dépendances: {task_node.dependencies}")
            found_deliverable = False
            for dep_id in task_node.dependencies:
                dep_task_node = self.task_graph.get_task(dep_id)
                if dep_task_node and dep_task_node.assigned_agent_type == AGENT_SKILL_CODING_PYTHON: 
                    if dep_task_node.output_artifact_ref: 
                        self.logger.info(f"[{self.execution_plan_id}] Tâche de test {task_node.id} dépend de {dep_id} (code). Récupération de l'artefact GRA ID: {dep_task_node.output_artifact_ref}.")
                        deliverable_content = await self._fetch_artifact_content(dep_task_node.output_artifact_ref)
                        if deliverable_content:
                            input_payload["deliverable"] = deliverable_content
                            self.logger.info(f"[{self.execution_plan_id}] Livrable (code) de {dep_id} (artefact GRA {dep_task_node.output_artifact_ref}) injecté pour test {task_node.id}.")
                            found_deliverable = True
                        else:
                            self.logger.warning(f"[{self.execution_plan_id}] Contenu du livrable de {dep_id} (artefact GRA {dep_task_node.output_artifact_ref}) non récupérable pour test {task_node.id}.")
                            input_payload["deliverable"] = f"// ERREUR: Contenu du livrable (artefact GRA {dep_task_node.output_artifact_ref}) non récupérable."
                        break 
            if not found_deliverable:
                 self.logger.warning(f"[{self.execution_plan_id}] Aucun livrable de code trouvé via dépendances pour tâche de test {task_node.id}.")
                 input_payload["deliverable"] = "// ATTENTION: Aucun livrable de code trouvé dans les dépendances directes."
        
        if task_node.input_data_refs:
            input_payload["input_artifacts_content"] = {} 
            self.logger.debug(f"[{self.execution_plan_id}] Traitement input_data_refs pour tâche {task_node.id}: {task_node.input_data_refs}")
            for ref_name, gra_artifact_id_to_load in task_node.input_data_refs.items():
                self.logger.info(f"[{self.execution_plan_id}] Tâche {task_node.id} a input_data_ref '{ref_name}' pointant vers GRA artifact ID: {gra_artifact_id_to_load}.")
                artifact_content = await self._fetch_artifact_content(gra_artifact_id_to_load)
                if artifact_content:
                    input_payload["input_artifacts_content"][ref_name] = artifact_content
                else:
                    input_payload["input_artifacts_content"][ref_name] = f"// ERREUR: Contenu de l'artefact GRA ID {gra_artifact_id_to_load} non récupérable pour input '{ref_name}'."
            if not input_payload["input_artifacts_content"]: 
                del input_payload["input_artifacts_content"]
        
        return json.dumps(input_payload, ensure_ascii=False, indent=2)

    async def process_plan_execution(self):
        self.logger.info(f"[{self.execution_plan_id}] Début du cycle de traitement d'exécution.")
        current_graph_snapshot_before_ready = self.task_graph.as_dict()
        ready_tasks_nodes = self.task_graph.get_ready_tasks()

        if not ready_tasks_nodes:
            self.logger.info(f"[{self.execution_plan_id}] Aucune tâche d'exécution prête pour ce cycle.")
            overall_status = current_graph_snapshot_before_ready.get("overall_status", "UNKNOWN")
            if overall_status.startswith("COMPLETED") or overall_status.startswith("FAILED") or overall_status.startswith("TIMEOUT") or overall_status == "PLAN_DECOMPOSED_EMPTY":
                 self.logger.info(f"[{self.execution_plan_id}] Plan d'exécution déjà dans un état terminal ou sans tâches enfants: {overall_status}")
                 return
            
            all_nodes_data = current_graph_snapshot_before_ready.get("nodes", {})
            if not all_nodes_data and overall_status == "PENDING_DECOMPOSITION":
                 self.logger.info(f"[{self.execution_plan_id}] En attente de la tâche de décomposition initiale (graph vide).")
                 return

            non_terminal_tasks_count = 0
            has_failures_in_graph = False
            if all_nodes_data:
                for _, node_data in all_nodes_data.items():
                    state = ExecutionTaskState(node_data.get("state", ExecutionTaskState.PENDING))
                    if state not in [ExecutionTaskState.COMPLETED, ExecutionTaskState.FAILED, ExecutionTaskState.CANCELLED]:
                        non_terminal_tasks_count += 1
                    if state == ExecutionTaskState.FAILED:
                        has_failures_in_graph = True
                
                if non_terminal_tasks_count == 0: 
                    final_status = "EXECUTION_COMPLETED_WITH_FAILURES" if has_failures_in_graph else "EXECUTION_COMPLETED_SUCCESSFULLY"
                    self.logger.info(f"[{self.execution_plan_id}] Toutes les tâches d'exécution sont terminales. Statut: {final_status}")
                    self.task_graph.set_overall_status(final_status)
            return

        for task_node_from_ready in ready_tasks_nodes:
            task_node = self.task_graph.get_task(task_node_from_ready.id)
            if not task_node:
                self.logger.warning(f"[{self.execution_plan_id}] Tâche {task_node_from_ready.id} retournée par get_ready_tasks mais non trouvée ensuite. Skipping.")
                continue
            
            self.logger.debug(f"[{self.execution_plan_id}] Tâche {task_node.id} rechargée, état actuel en DB: {task_node.state.value}")
            if task_node.state != ExecutionTaskState.READY:
                self.logger.info(f"[{self.execution_plan_id}] Tâche {task_node.id} récupérée avec état '{task_node.state.value}' au lieu de READY. Skipping.")
                continue

            current_overall_status = self.task_graph.as_dict().get("overall_status")
            if task_node.task_type == ExecutionTaskType.DECOMPOSITION and \
               current_overall_status not in ["INITIALIZING", "PENDING_DECOMPOSITION"]:
                self.logger.info(f"[{self.execution_plan_id}] Tâche de décomposition {task_node.id} READY, mais statut global ('{current_overall_status}') indique traitement déjà fait. Forcing COMPLETED.")
                self.task_graph.update_task_state(task_node.id, ExecutionTaskState.COMPLETED, "Forçage COMPLETED (décomposition déjà faite).")
                continue

            self.logger.info(f"[{self.execution_plan_id}] Prise en charge tâche prête: {task_node.id} ('{task_node.objective}'), Type: {task_node.task_type.value}, État: {task_node.state.value}")
            self.task_graph.update_task_state(task_node.id, ExecutionTaskState.ASSIGNED, "Assignation en cours...")
            
            agent_skill_needed = task_node.assigned_agent_type
            if not agent_skill_needed:
                self.logger.error(f"[{self.execution_plan_id}] Tâche {task_node.id} sans assigned_agent_type. Passage FAILED.")
                self.task_graph.update_task_state(task_node.id, ExecutionTaskState.FAILED, "Type d'agent requis non spécifié.")
                continue

            agent_details = await self._get_agent_details_from_gra(agent_skill_needed)
            if not agent_details or not agent_details.get("url"):
                self.logger.error(f"[{self.execution_plan_id}] Aucun agent pour '{agent_skill_needed}' (tâche {task_node.id}). Remise à READY.")
                self.task_graph.update_task_state(task_node.id, ExecutionTaskState.READY, f"Agent pour '{agent_skill_needed}' non trouvé, en attente.")
                continue
            
            agent_url = agent_details["url"]
            agent_name_from_gra = agent_details.get("name", agent_skill_needed) 

            self.task_graph.update_task_state(task_node.id, ExecutionTaskState.WORKING, f"Appel agent {agent_name_from_gra} ({agent_skill_needed}) à {agent_url}.")
            
            input_for_agent_text = ""
            if task_node.task_type == ExecutionTaskType.DECOMPOSITION:
                all_registered_agents_skills = await self._get_all_available_execution_skills_from_gra()
                input_payload_for_decomposition = {
                    "team1_plan_text": self.team1_plan_final_text,
                    "available_execution_skills": all_registered_agents_skills
                }
                input_for_agent_text = json.dumps(input_payload_for_decomposition, ensure_ascii=False)
            else:
                input_for_agent_text = await self._prepare_input_for_execution_agent(task_node)

            a2a_task_result = await call_a2a_agent(agent_url, input_for_agent_text, self.execution_plan_id)

            if a2a_task_result and a2a_task_result.status:
                a2a_state_val = a2a_task_result.status.state.value
                gra_persisted_artifact_id: Optional[str] = None 
                artifact_text_content = None 

                if a2a_task_result.artifacts and len(a2a_task_result.artifacts) > 0:
                    first_a2a_artifact = a2a_task_result.artifacts[0]
                    gra_persisted_artifact_id = await self._store_a2a_artifact_in_gra(
                        first_a2a_artifact,
                        a2a_task_result.id, 
                        a2a_task_result.contextId, 
                        agent_name_from_gra 
                    )
                    if first_a2a_artifact.parts:
                        part_cont = first_a2a_artifact.parts[0]
                        if hasattr(part_cont, 'root') and hasattr(part_cont.root, 'text'): artifact_text_content = part_cont.root.text
                        elif hasattr(part_cont, 'text'): artifact_text_content = part_cont.text
                
                if a2a_state_val == "completed":
                    if task_node.task_type == ExecutionTaskType.DECOMPOSITION:
                        if artifact_text_content: 
                            try:
                                decomposed_plan_structure = json.loads(artifact_text_content)
                                tasks_to_create = decomposed_plan_structure.get("tasks", [])
                                if isinstance(tasks_to_create, list):
                                    if not tasks_to_create:
                                        self.task_graph.update_task_state(task_node.id, ExecutionTaskState.COMPLETED, "Décomposition OK, aucune tâche enfant produite.")
                                        self.task_graph.update_task_output(task_node.id, artifact_ref=gra_persisted_artifact_id) 
                                        self.task_graph.set_overall_status("PLAN_DECOMPOSED_EMPTY") 
                                    else:
                                        self.task_graph.update_task_output(task_node.id, artifact_ref=gra_persisted_artifact_id, summary="Plan décomposé.")
                                        await self._add_and_resolve_decomposed_tasks(tasks_to_create, task_node.id)
                                        self.task_graph.update_task_state(task_node.id, ExecutionTaskState.COMPLETED, "Décomposition OK, tâches enfants ajoutées.")
                                        self.task_graph.set_overall_status("PLAN_DECOMPOSED")
                                else:
                                    self.task_graph.update_task_state(task_node.id, ExecutionTaskState.FAILED, "Format 'tasks' incorrect dans décomposition.")
                                    self.task_graph.update_task_output(task_node.id, artifact_ref=gra_persisted_artifact_id) 
                            except json.JSONDecodeError:
                                self.task_graph.update_task_state(task_node.id, ExecutionTaskState.FAILED, "Artefact décomposition JSON invalide.")
                                self.task_graph.update_task_output(task_node.id, artifact_ref=gra_persisted_artifact_id)
                        else:
                            self.task_graph.update_task_state(task_node.id, ExecutionTaskState.FAILED, "Agent décomposition n'a pas retourné d'artefact textuel.")
                    
                    elif task_node.task_type == ExecutionTaskType.EXPLORATORY:
                        self.task_graph.update_task_output(task_node.id, artifact_ref=gra_persisted_artifact_id, summary="Exploration terminée (pré-traitement).")
                        await self._process_completed_exploratory_task(task_node, artifact_text_content)
                    
                    elif task_node.task_type == ExecutionTaskType.EXECUTABLE:
                        summary = f"Livrable par {agent_name_from_gra}."
                        if artifact_text_content and len(artifact_text_content) < 100: summary += f" Aperçu: {artifact_text_content[:50]}..."
                        self.task_graph.update_task_output(task_node.id, artifact_ref=gra_persisted_artifact_id, summary=summary)
                        self.task_graph.update_task_state(task_node.id, ExecutionTaskState.COMPLETED, "Exécution OK.")
                                                # <<< AJOUT D'UN LOG DE DÉBOGAGE ICI >>>
                        self.logger.info(f"[{self.execution_plan_id}] APPEL update_task_output pour TÂCHE EXECUTABLE {task_node.id}: artifact_ref='{gra_persisted_artifact_id}', summary='{summary}'")


                    
                    else: 
                        self.task_graph.update_task_output(task_node.id, artifact_ref=gra_persisted_artifact_id)
                        self.task_graph.update_task_state(task_node.id, ExecutionTaskState.COMPLETED, "Tâche traitée.")
                
                elif a2a_state_val == "failed":
                    error_summary = f"Échec tâche A2A {a2a_task_result.id} pour {task_node.id} (agent {agent_name_from_gra})."
                    if artifact_text_content: error_summary += f" Détail: {artifact_text_content[:100]}"
                    self.task_graph.update_task_output(task_node.id, artifact_ref=gra_persisted_artifact_id, summary=error_summary) 
                    self.task_graph.update_task_state(task_node.id, ExecutionTaskState.FAILED, error_summary)

                else: 
                    unexpected_state_summary = f"État A2A inattendu: {a2a_state_val} pour {task_node.id}."
                    if artifact_text_content: unexpected_state_summary += f" Artefact: {artifact_text_content[:100]}"
                    self.task_graph.update_task_output(task_node.id, artifact_ref=gra_persisted_artifact_id, summary=unexpected_state_summary)
                    self.task_graph.update_task_state(task_node.id, ExecutionTaskState.FAILED, f"État A2A inattendu: {a2a_state_val}")
            else:
                self.task_graph.update_task_state(task_node.id, ExecutionTaskState.FAILED, "Réponse agent A2A invalide/absente.")
        
        self.logger.info(f"[{self.execution_plan_id}] Fin du cycle de traitement d'exécution.")

    async def run_full_execution(self):
        await self.initialize_and_decompose_plan()
        
        max_cycles = 10 
        for i in range(max_cycles):
            self.logger.info(f"\n--- CYCLE D'EXÉCUTION TEAM 2 N°{i+1}/{max_cycles} pour le plan {self.execution_plan_id} ---")
            await self.process_plan_execution()

            current_graph_data = self.task_graph.as_dict()
            all_nodes = current_graph_data.get("nodes", {})
            overall_status = current_graph_data.get("overall_status", "UNKNOWN")

            if overall_status == "EXECUTION_COMPLETED_SUCCESSFULLY" or \
               overall_status == "EXECUTION_COMPLETED_WITH_FAILURES" or \
               overall_status.startswith("FAILED") or \
               overall_status == "TIMEOUT_EXECUTION":
                self.logger.info(f"[{self.execution_plan_id}] Statut global du plan d'exécution est terminal ({overall_status}). Arrêt de run_full_execution.")
                break 

            if not all_nodes and overall_status == "PENDING_DECOMPOSITION":
                self.logger.info(f"[{self.execution_plan_id}] En attente de la décomposition initiale. Cycle {i+1}.")
                await asyncio.sleep(5) 
                continue

            non_terminal_tasks = [
                nid for nid, ndata in all_nodes.items() 
                if ExecutionTaskState(ndata.get("state", ExecutionTaskState.PENDING)) not in [
                    ExecutionTaskState.COMPLETED, ExecutionTaskState.FAILED, ExecutionTaskState.CANCELLED
                ]
            ]

            if (overall_status.startswith("PLAN_DECOMPOSED") or overall_status == "PLAN_DECOMPOSED_EMPTY") and not non_terminal_tasks:
                has_failed_tasks_in_graph = any(ExecutionTaskState(ndata.get("state")) == ExecutionTaskState.FAILED for ndata in all_nodes.values())
                final_plan_status = "EXECUTION_COMPLETED_WITH_FAILURES" if has_failed_tasks_in_graph else "EXECUTION_COMPLETED_SUCCESSFULLY"
                self.logger.info(f"[{self.execution_plan_id}] Toutes les tâches d'exécution sont terminales. Fin de l'exécution. Statut: {final_plan_status}")
                self.task_graph.set_overall_status(final_plan_status)
                break 

            if i == max_cycles - 1:
                self.logger.warning(f"[{self.execution_plan_id}] Nombre maximum de cycles d'exécution ({max_cycles}) atteint.")
                if overall_status not in ["EXECUTION_COMPLETED_SUCCESSFULLY", "EXECUTION_COMPLETED_WITH_FAILURES"]:
                    self.task_graph.set_overall_status("TIMEOUT_EXECUTION")
                break 
            await asyncio.sleep(5)         
        
        final_status = self.task_graph.as_dict().get("overall_status", "UNKNOWN")
        self.logger.info(f"[{self.execution_plan_id}] Exécution terminée avec le statut: {final_status}")

    async def _get_all_available_execution_skills_from_gra(self) -> List[str]:
        self.logger.info(f"[{self.execution_plan_id}] Récupération des compétences d'exécution disponibles depuis le GRA.")
        gra_url = await self._ensure_gra_url()
        all_skills = set()
        execution_related_skills_keywords = [
            "coding", "python", "javascript", "java", 
            "research", "analysis", "synthesis",      
            "testing", "test_case", 
            "database_design", "api_design",         
            "documentation", "document_synthesis",                       
             "execution_plan_decomposition" 
        ]
        excluded_skills_for_decomposition_assignment = [
            "clarify_objective", "reformulation", "evaluation", "validation", 
            "execution_plan_decomposition" 
        ]
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{gra_url}/agents_status", timeout=10.0)
                response.raise_for_status()
                agents_list = response.json()
                if isinstance(agents_list, list):
                    for agent_info in agents_list:
                        agent_skills = agent_info.get("skills", [])
                        if isinstance(agent_skills, list):
                            for skill in agent_skills:
                                if isinstance(skill, str) and skill not in excluded_skills_for_decomposition_assignment:
                                    if any(keyword in skill.lower() for keyword in execution_related_skills_keywords):
                                        all_skills.add(skill)
                        else:
                            self.logger.warning(f"[{self.execution_plan_id}] Champ 'skills' mal formaté pour l'agent: {agent_info.get('name', 'Inconnu')}")
                else:
                    self.logger.error(f"[{self.execution_plan_id}] Réponse de /agents_status du GRA n'est pas une liste: {agents_list}")
            if not all_skills:
                 default_exec_skills = ["coding_python", "web_research", "software_testing", "document_synthesis", "general_analysis", "database_design"]
                 self.logger.warning(f"[{self.execution_plan_id}] Aucune compétence d'exécution spécifique trouvée/filtrée via GRA, utilisation liste défaut: {default_exec_skills}")
                 return default_exec_skills
            self.logger.info(f"[{self.execution_plan_id}] Compétences d'exécution disponibles filtrées: {list(all_skills)}")
            return list(all_skills)
        except Exception as e:
            self.logger.error(f"[{self.execution_plan_id}] Erreur récupération compétences via GRA: {e}", exc_info=True)
            default_exec_skills = ["coding_python", "web_research", "software_testing", "document_synthesis", "general_analysis", "database_design"]
            self.logger.warning(f"[{self.execution_plan_id}] Utilisation liste compétences défaut due à erreur GRA: {default_exec_skills}")
            return default_exec_skills

    async def _add_and_resolve_decomposed_tasks(self, tasks_json_list: List[Dict], initial_dependency_id: str, existing_local_id_map: Optional[Dict[str,str]] = None):
        local_id_to_global_id_map = existing_local_id_map if existing_local_id_map is not None else {}
        if not existing_local_id_map: # Si c'est le premier appel pour ce plan, initialiser la map partagée
            self._local_to_global_id_map_for_plan.clear()
            local_id_to_global_id_map = self._local_to_global_id_map_for_plan


        nodes_to_add_to_graph = {} 
        def first_pass_create_nodes_recursive(task_list_json: List[Dict], current_parent_global_id: Optional[str]):
            for task_json in task_list_json:
                node_obj, _ = self._create_node_from_json_data(task_json, current_parent_global_id, local_id_to_global_id_map)
                nodes_to_add_to_graph[node_obj.id] = (node_obj, task_json)
                json_sub_tasks = task_json.get("sous_taches", [])
                if json_sub_tasks:
                    first_pass_create_nodes_recursive(json_sub_tasks, node_obj.id)
        
        first_pass_create_nodes_recursive(tasks_json_list, None) # Le parent est initial_dependency_id pour les tâches de premier niveau de ce lot

        for global_id, (node_obj, task_json_original) in nodes_to_add_to_graph.items():
            if node_obj.parent_id is None: # Tâche de premier niveau de ce lot
                 node_obj.dependencies.append(initial_dependency_id)

            local_deps = task_json_original.get("dependances", [])
            for local_dep_id in local_deps:
                if local_dep_id in local_id_to_global_id_map: 
                    global_dep_id = local_id_to_global_id_map[local_dep_id]
                    if global_dep_id != node_obj.id:
                        node_obj.dependencies.append(global_dep_id)
                    else:
                        self.logger.warning(f"[{self.execution_plan_id}] Tentative d'auto-dépendance (lot) pour {global_id}. Ignorée.")
                else:
                    # Tenter de résoudre la dépendance par rapport à des tâches déjà existantes dans le graphe global
                    # Ceci est une heuristique simple ; une résolution de dépendance plus complexe pourrait être nécessaire
                    # si les ID locaux ne sont pas uniques ou si les dépendances croisent des lots de décomposition.
                    # Pour l'instant, on logue si non trouvé dans la map locale du lot.
                    self.logger.warning(f"[{self.execution_plan_id}] Dépendance locale (lot) '{local_dep_id}' pour '{task_json_original.get('id')}' non trouvée dans la map actuelle. Si elle réfère à une tâche hors de ce lot, elle doit être déjà dans le graphe avec un ID global connu.")
            
            node_obj.dependencies = list(set(node_obj.dependencies)) # Dédoublonnage
            self.task_graph.add_task(node_obj)
            self.logger.info(f"[{self.execution_plan_id}] Tâche (lot) '{node_obj.objective}' (ID: {node_obj.id}) ajoutée/résolue avec parent '{node_obj.parent_id}' et dépendances: {node_obj.dependencies}.")

    def _create_node_from_json_data(self, task_data_dict: Dict[str, Any], assigned_parent_id: Optional[str], local_id_map: Dict[str,str]) -> tuple[ExecutionTaskNode, Dict[str,Any]]:
        local_id = task_data_dict.get("id")
        if not local_id:
            local_id = f"generated_local_id_{uuid.uuid4().hex[:6]}"
            self.logger.warning(f"[{self.execution_plan_id}] Tâche JSON sans 'id' local, génération d'un ID local: {local_id}")
        
        # Générer un ID global unique, préfixé pour éviter collisions et faciliter le débogage.
        # Remplacer les points par des underscores pour éviter problèmes potentiels avec certains systèmes/DB.
        clean_local_id = local_id.replace(' ', '_').replace('.', '_')
        global_task_id = f"exec_task_{clean_local_id}_{uuid.uuid4().hex[:6]}"
        
        if local_id in local_id_map:
            # Si l'ID local a déjà été mappé, cela signifie que l'agent de décomposition
            # a potentiellement utilisé des ID locaux non uniques. On logue un avertissement
            # mais on continue avec le nouvel ID global généré pour éviter les conflits d'ID globaux.
            # Les dépendances qui référençaient l'ancien mapping de cet ID local pourraient être incorrectes.
            self.logger.warning(f"[{self.execution_plan_id}] L'ID local '{local_id}' a déjà été mappé à '{local_id_map[local_id]}'. Il est maintenant ré-mappé à '{global_task_id}'. Vérifiez l'unicité des ID locaux fournis par l'agent de décomposition.")
        local_id_map[local_id] = global_task_id # Mettre à jour/ajouter le mapping

        node_meta = {
            "local_id_from_agent": local_id,
            "local_instructions": task_data_dict.get("instructions_locales", []),
            "acceptance_criteria": task_data_dict.get("acceptance_criteria", [])
        }
        if task_data_dict.get("nom"): # 'nom' est optionnel mais utile
            node_meta["local_nom_from_agent"] = task_data_dict.get("nom")
        
        task_type_str = task_data_dict.get("type", "exploratory").lower()
        try:
            task_type_enum = ExecutionTaskType(task_type_str)
        except ValueError:
            self.logger.warning(f"[{self.execution_plan_id}] Type de tâche invalide '{task_type_str}' pour ID local '{local_id}'. Utilisation de 'exploratory' par défaut.")
            task_type_enum = ExecutionTaskType.EXPLORATORY

        new_node = ExecutionTaskNode(
            task_id=global_task_id,
            objective=task_data_dict.get("description", task_data_dict.get("nom", "Objectif non défini par l'agent")),
            task_type=task_type_enum,
            assigned_agent_type=task_data_dict.get("assigned_agent_type"),
            dependencies=[], # Sera rempli plus tard par _add_and_resolve_decomposed_tasks
            parent_id=assigned_parent_id, 
            meta=node_meta,
            input_data_refs=task_data_dict.get("input_data_refs", {}) # Transférer si fourni
        )
        return new_node, task_data_dict

    async def _process_completed_exploratory_task(self, completed_task_node: ExecutionTaskNode, artifact_content_text: Optional[str]):
        self.logger.info(f"[{self.execution_plan_id}] Traitement du résultat de la tâche exploratoire: {completed_task_node.id}")
        if not artifact_content_text:
            self.logger.warning(f"[{self.execution_plan_id}] Tâche exploratoire {completed_task_node.id} complétée sans artefact textuel pour de nouvelles tâches.")
            self.task_graph.update_task_state(completed_task_node.id, ExecutionTaskState.COMPLETED, "Exploration terminée, pas de nouvelles tâches spécifiées.")
            return

        try:
            exploration_result = json.loads(artifact_content_text)
            new_sub_tasks_dicts = exploration_result.get("new_sub_tasks", [])
            summary_from_artifact = exploration_result.get("summary", f"Exploration par {completed_task_node.id} terminée.")

            # L'artifact_ref de completed_task_node (l'ID GRA) a déjà été mis à jour.
            # On met à jour le résumé de la tâche sur la base du contenu de l'artefact.
            self.task_graph.update_task_output(task_id=completed_task_node.id, summary=summary_from_artifact)

            if not isinstance(new_sub_tasks_dicts, list):
                self.logger.error(f"[{self.execution_plan_id}] La clé 'new_sub_tasks' de {completed_task_node.id} n'est pas une liste.")
                self.task_graph.update_task_state(completed_task_node.id, ExecutionTaskState.FAILED, "Format incorrect de l'artefact (new_sub_tasks).")
                return

            if not new_sub_tasks_dicts:
                self.logger.info(f"[{self.execution_plan_id}] Tâche exploratoire {completed_task_node.id} n'a pas défini de nouvelles sous-tâches.")
                self.task_graph.update_task_state(completed_task_node.id, ExecutionTaskState.COMPLETED, summary_from_artifact)
                return

            self.logger.info(f"[{self.execution_plan_id}] Tâche exploratoire {completed_task_node.id} a défini {len(new_sub_tasks_dicts)} nouvelle(s) sous-tâche(s).")
            
            # Les nouvelles sous-tâches dépendront de la tâche exploratoire qui les a générées (initial_dependency_id).
            # Le parent_id des tâches de premier niveau de ce lot sera completed_task_node.id.
            await self._add_and_resolve_decomposed_tasks(
                tasks_json_list=new_sub_tasks_dicts, 
                initial_dependency_id=completed_task_node.id, # Les nouvelles tâches dépendent de la tâche exploratoire mère
                existing_local_id_map=self._local_to_global_id_map_for_plan # Utiliser la map du plan global
            )
            
            self.task_graph.update_task_state(completed_task_node.id, ExecutionTaskState.COMPLETED, f"{summary_from_artifact} {len(new_sub_tasks_dicts)} nouvelles sous-tâches ajoutées.")

        except json.JSONDecodeError:
            self.logger.error(f"[{self.execution_plan_id}] Artefact de la tâche exploratoire {completed_task_node.id} JSON invalide: {artifact_content_text}")
            self.task_graph.update_task_state(completed_task_node.id, ExecutionTaskState.FAILED, "Artefact d'exploration JSON invalide.")
        except Exception as e:
            self.logger.error(f"[{self.execution_plan_id}] Erreur traitement résultat tâche exploratoire {completed_task_node.id}: {e}", exc_info=True)
            self.task_graph.update_task_state(completed_task_node.id, ExecutionTaskState.FAILED, f"Erreur traitement résultat exploration: {str(e)}")