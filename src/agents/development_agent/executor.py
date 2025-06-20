import logging
import json

from src.shared.base_agent_executor import BaseAgentExecutor
from .logic import DevelopmentAgentLogic

from a2a.types import (
    Artifact,
    Task,
    Message,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
    TaskArtifactUpdateEvent,
)
from a2a.utils import new_text_artifact, new_agent_text_message, new_task
from src.services.environment_manager.environment_manager import EnvironmentManager
from typing_extensions import override
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events.event_queue import EventQueue
import time
from src.shared.agent_state import AgentOperationalState

logger = logging.getLogger(__name__)


class DevelopmentAgentExecutor(BaseAgentExecutor):
    def __init__(self):
        specific_agent_logic = DevelopmentAgentLogic()
        super().__init__(
            agent_logic=specific_agent_logic,
            default_artifact_name="development_action_result",
            default_artifact_description="Résultat de l'action de développement (écriture/exécution/lecture).",
        )
        self.logger = logging.getLogger(f"{__name__}.DevelopmentAgentExecutor")
        self.logger.info("DevelopmentAgentExecutor initialisé.")

        self.environment_manager = EnvironmentManager()
        self.agent_logic.set_environment_manager(self.environment_manager)
        self.current_environment_id: str | None = None

    def _create_artifact_from_result(self, result_data: str, task: Task) -> Artifact:
        """
        Crée un Artifact A2A à partir des données JSON de résultat de l'action.
        """
        self.logger.info(f"Création de l'artefact de résultat pour la tâche {task.id}.")
        return new_text_artifact(
            name=self.default_artifact_name,
            description=self.default_artifact_description,
            text=result_data,
        )

    def _reconstruct_environment_id(self):
        if self.current_environment_id:
            return self.current_environment_id
        return EnvironmentManager.normalize_environment_id(self.execution_plan_id)

    
    @override
    async def execute(
        self, context: RequestContext, event_queue: EventQueue
    ) -> None:  #

        self.state = AgentOperationalState.WORKING
        self.current_task_id = context.current_task.id if context.current_task else None
        self.last_activity_time = time.time()
        self.status_detail = "Préparation de la tâche"
        await self._notify_gra_of_status_change()  # Notifier le début

        # --- Initialisation de la tâche ---
        task_context_id_for_log = context.context_id or (
            context.message.contextId if context.message else "N/A"
        )  #
        self.logger.info(
            f"{self.__class__.__name__}.execute appelé pour le contexte: {task_context_id_for_log}"
        )  #

        message = context.message  #
        task = context.current_task  #
        if not task:  #
            task = new_task(request=message)  #
            await event_queue.enqueue_event(task)  #

        current_task_id = task.id  #
        current_context_id = task.contextId  #

        user_input_json_str = self._extract_input_from_message(message)  #

        if user_input_json_str is None:  #
            # Gestion d'erreur si l'input est invalide
            await event_queue.enqueue_event(
                TaskStatusUpdateEvent(  #
                    status=TaskStatus(
                        state=TaskState.failed,
                        message=new_agent_text_message(text="Input invalide."),
                    ),  #
                    final=True,
                    contextId=current_context_id,
                    taskId=current_task_id,
                )
            )  #
            self._update_stats(success=False)  #
            return
        try:
            # L'input initial du superviseur contient l'objectif.
            input_payload_from_supervisor = json.loads(user_input_json_str)  #

            # Récupération de l'ID de l'environnement

            provided_env = input_payload_from_supervisor.get("environment_id") #
            if not provided_env: #
                raise ValueError("Environment ID est manquant dans l'input de la tâche.")
            
            self.current_environment_id = EnvironmentManager.normalize_environment_id(provided_env) #
            self.status_detail = "Création de l'environnement"
            await self._notify_gra_of_status_change()
            await self.environment_manager.create_isolated_environment(self.current_environment_id) #

            self.status_detail = "Environnement prêt"
            await self._notify_gra_of_status_change()

            # --- Début de la boucle Pensée-Action ---
            last_action_result: dict | None = None  #
            continue_loop = True  #

            await event_queue.enqueue_event(
                TaskStatusUpdateEvent(  #
                    status=TaskStatus(
                        state=TaskState.working,
                        message=new_agent_text_message(
                            text="Début du cycle de développement."
                        ),
                    ),  #
                    final=False,
                    contextId=current_context_id,
                    taskId=current_task_id,  #
                )
            )

            while continue_loop:  #
                tool_result = (
                    None  # Réinitialiser le résultat de l'outil à chaque itération
                )
                # 1. Préparer l'input pour la logique (LLM)
                payload_for_logic = {  #
                    "objective": input_payload_from_supervisor.get("objective"),
                    "last_action_result": last_action_result,  #
                }

                self.logger.info(
                    f"Début itération: Appel de la logique pour décider de la prochaine action."
                )

                # 2. Appeler le LLM pour qu'il décide de la prochaine action
                llm_action_json_str = await self.agent_logic.process(
                    json.dumps(payload_for_logic), current_context_id
                )  #
                llm_action_payload = json.loads(llm_action_json_str)  #
                action_type = llm_action_payload.get("action")  #

                self.logger.info(f"Action décidée par le LLM: {action_type}")
                self.status_detail = f"Action décidée: {action_type}"
                await self._notify_gra_of_status_change()

                action_result_details = {}
                action_summary = f"Action '{action_type}' exécutée."  #

                # 3. Exécuter l'action demandée par le LLM
                if action_type == "generate_code_and_write_file":
                    file_path = llm_action_payload.get("file_path", "/app/main.py")

                    code_to_write = await self._generate_code_from_specs(llm_action_payload)

                    self.status_detail = f"Génération du fichier {file_path}"
                    await self._notify_gra_of_status_change()

                    tool_result = await self.environment_manager.safe_tool_call(
                        self.environment_manager.write_file_to_environment(
                            self.current_environment_id, file_path, code_to_write
                        ),
                        f"Écriture du fichier {file_path}",
                    )
                    if tool_result is None:
                        action_summary = (
                            f"L'appel à l'outil pour {action_type} n'a rien retourné."
                        )
                        action_result_details = {"error": action_summary}

                        self.failure_count = getattr(self, "failure_count", 0)
                        self.failure_count += 1
                        if self.failure_count >= 3:
                            action_summary = f"Abandon après {self.failure_count} échecs consécutifs sur {action_type}."
                            await event_queue.enqueue_event(TaskStatusUpdateEvent(
                                status=TaskStatus(
                                    state=TaskState.failed,
                                    message=new_agent_text_message(text=action_summary)
                                ),
                                final=True,
                                contextId=current_context_id,
                                taskId=current_task_id
                            ))
                            break  # Ou return                        
                    elif isinstance(tool_result, dict) and "error" in tool_result:
                        action_summary = tool_result["error"]
                        action_result_details = tool_result
                        self.failure_count = getattr(self, "failure_count", 0)
                        self.failure_count += 1
                        if self.failure_count >= 3:
                            action_summary = f"Abandon après {self.failure_count} échecs consécutifs sur {action_type}."
                            await event_queue.enqueue_event(TaskStatusUpdateEvent(
                                status=TaskStatus(
                                    state=TaskState.failed,
                                    message=new_agent_text_message(text=action_summary)
                                ),
                                final=True,
                                contextId=current_context_id,
                                taskId=current_task_id
                            ))
                            break  # Ou return                        

                    else:
                        action_summary = f"Code généré et écrit dans {file_path}."
                        action_result_details = {
                            "file_path": file_path,
                            "code_snippet": code_to_write[:150] + "...",
                        }

                elif action_type == "execute_command":
                    command = llm_action_payload.get("command")
                    workdir = llm_action_payload.get("workdir", "/app")
                    self.status_detail = f"Exécution de la commande: {command}"
                    await self._notify_gra_of_status_change()

                    self.status_detail = f"Exécution de la commande: {command}"
                    await self._notify_gra_of_status_change()

                    tool_result = await self.environment_manager.safe_tool_call(
                        self.environment_manager.execute_command_in_environment(
                            self.current_environment_id, command, workdir
                        ),
                        f"Commande '{command}'",
                    )
                    if tool_result is None:
                        action_summary = (
                            f"L'appel à l'outil pour {action_type} n'a rien retourné."
                        )
                        action_result_details = {"error": action_summary}
                    elif isinstance(tool_result, dict) and "error" in tool_result:
                        action_summary = tool_result["error"]
                        action_result_details = tool_result
                    else:
                        action_summary = f"Commande '{command}' exécutée."
                        action_result_details = tool_result

                elif action_type == "read_file":
                    file_path = llm_action_payload.get("file_path")
                    self.status_detail = f"Lecture du fichier {file_path}"
                    await self._notify_gra_of_status_change()

                    self.status_detail = f"Lecture du fichier {file_path}"
                    await self._notify_gra_of_status_change()

                    tool_result = await self.environment_manager.safe_tool_call(
                        self.environment_manager.read_file_from_environment(
                            self.current_environment_id, file_path
                        ),
                        f"Lecture du fichier {file_path}",
                    )
                    if tool_result is None:
                        action_summary = (
                            f"L'appel à l'outil pour {action_type} n'a rien retourné."
                        )
                        action_result_details = {"error": action_summary}
                    elif isinstance(tool_result, dict) and "error" in tool_result:
                        action_summary = tool_result["error"]
                        action_result_details = tool_result
                    else:
                        action_summary = f"Fichier '{file_path}' lu."
                        action_result_details = {
                            "file_path": file_path,
                            "content": tool_result,
                        }

                elif action_type == "list_directory":
                    path = llm_action_payload.get("path", "/app")
                    self.status_detail = f"Listing du répertoire {path}"
                    await self._notify_gra_of_status_change()

                    self.status_detail = f"Listing du répertoire {path}"
                    await self._notify_gra_of_status_change()

                    tool_result = await self.environment_manager.safe_tool_call(
                        self.environment_manager.list_files_in_environment(
                            self.current_environment_id, path
                        ),
                        f"Listing du répertoire {path}",
                    )

                    if tool_result is None:
                        action_summary = (
                            f"L'appel à l'outil pour {action_type} n'a rien retourné."
                        )
                        action_result_details = {"error": action_summary}
                    elif isinstance(tool_result, dict) and "error" in tool_result:
                        action_summary = tool_result["error"]
                        action_result_details = tool_result
                    else:
                        action_summary = f"Contenu de '{path}' listé."
                        action_result_details = {"path": path, "files": tool_result}

                elif action_type == "complete_task":
                    action_summary = llm_action_payload.get(
                        "summary", "Tâche de développement terminée."
                    )
                    final_artifact_content = {
                        "final_summary": action_summary,
                        "status": "completed",
                    }

                    self.status_detail = "Tâche de développement terminée"
                    await self._notify_gra_of_status_change()

                    continue_loop = False  # Stopper la boucle

                    final_artifact = self._create_artifact_from_result(
                        json.dumps(final_artifact_content), task
                    )
                    await event_queue.enqueue_event(
                        TaskArtifactUpdateEvent(
                            append=False,
                            contextId=current_context_id,
                            taskId=current_task_id,
                            lastChunk=True,
                            artifact=final_artifact,
                        )
                    )
                    await event_queue.enqueue_event(
                        TaskStatusUpdateEvent(
                            status=TaskStatus(
                                state=TaskState.completed,
                                message=new_agent_text_message(text=action_summary),
                            ),
                            final=True,
                            contextId=current_context_id,
                            taskId=current_task_id,
                        )
                    )

                    self._update_stats(success=True)

                else:
                    action_summary = (
                        f"Action LLM inconnue ou non gérée: '{action_type}'."
                    )
                    action_result_details = {"error": action_summary}
                    self.status_detail = action_summary
                    await self._notify_gra_of_status_change()

                # Préparer un retour intermédiaire si la boucle continue
                if continue_loop:
                    last_action_result = {
                        "action_taken": action_type,
                        "summary": action_summary,
                        "details": action_result_details,
                    }
                    self.status_detail = action_summary
                    await self._notify_gra_of_status_change()

                    await event_queue.enqueue_event(TaskStatusUpdateEvent(
                        status=TaskStatus(state=TaskState.working, message=new_agent_text_message(text=action_summary)),
                        final=False, contextId=current_context_id, taskId=current_task_id
                    ))

        except Exception as e: #
            self.logger.error(f"Erreur majeure dans l'exécuteur de développement pour la tâche {current_task_id}: {e}", exc_info=True) #
            await event_queue.enqueue_event(TaskStatusUpdateEvent( #
                status=TaskStatus(state=TaskState.failed, message=new_agent_text_message(text=f"Erreur interne de l'agent: {str(e)}")), #
                final=True, contextId=current_context_id, taskId=current_task_id)) #
            self.status_detail = f"Erreur: {e}"
            await self._notify_gra_of_status_change()
            self._update_stats(success=False) #
        finally: #

            self.state = AgentOperationalState.IDLE
            self.current_task_id = (
                context.current_task.id if context.current_task else None
            )
            self.last_activity_time = time.time()
            self.status_detail = None
            await self._notify_gra_of_status_change() # Notifier le début

    async def _generate_code_from_specs(self, specs: dict) -> str:
        """Méthode privée pour appeler le LLM spécifiquement pour la génération de code."""
        from src.shared.llm_client import call_llm  #

        code_system_prompt = (  #
            "Tu es un développeur IA expert en Python. Ta mission est de générer du code Python propre, "  #
            "fonctionnel et bien commenté, basé sur les spécifications fournies. "  #
            "Le code doit être directement utilisable. N'inclus que le code dans ta réponse, "  #
            "sauf si des commentaires dans le code sont nécessaires pour l'expliquer."  #
        )
        code_generation_prompt = (  #
            f"Objectif du code : {specs.get('objective', '')}\n\n"  #
            f"Instructions spécifiques : {specs.get('local_instructions', [])}\n\n"  #
            f"Critères d'acceptation : {specs.get('acceptance_criteria', [])}\n\n"  #
            "Génère UNIQUEMENT le code Python correspondant."  #
        )

        
        return await call_llm(code_generation_prompt, code_system_prompt, json_mode=False) #

