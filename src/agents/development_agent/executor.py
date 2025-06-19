import logging
import json

from src.shared.base_agent_executor import BaseAgentExecutor
from .logic import DevelopmentAgentLogic

from a2a.types import (
    Artifact, Task, Message, TaskState, TaskStatus,
    TaskStatusUpdateEvent, TaskArtifactUpdateEvent
)
from a2a.utils import new_text_artifact, new_agent_text_message, new_task
from src.services.environment_manager.environment_manager import EnvironmentManager
from typing_extensions import override
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events.event_queue import EventQueue

logger = logging.getLogger(__name__)

class DevelopmentAgentExecutor(BaseAgentExecutor):
    def __init__(self):
        specific_agent_logic = DevelopmentAgentLogic()
        super().__init__(
            agent_logic=specific_agent_logic,
            default_artifact_name="development_action_result",
            default_artifact_description="Résultat de l'action de développement (écriture/exécution/lecture)."
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
            text=result_data 
        )
    
    def _reconstruct_environment_id(self):
        if self.current_environment_id:
            return self.current_environment_id
        return EnvironmentManager.normalize_environment_id(self.execution_plan_id)

    @override
    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        task_context_id_for_log = context.context_id if context.context_id else (context.message.contextId if context.message and context.message.contextId else "N/A")
        self.logger.info(f"{self.__class__.__name__}.execute appelé pour le contexte: {task_context_id_for_log}")
        
        message = context.message
        task = context.current_task
        if context.message and hasattr(context.message, "input") and isinstance(context.message.input, dict):
            self.execution_plan_id = context.message.input.get("execution_plan_id", "N/A")
        else:
            logger.warning(f"{context.message}: Aucune entrée JSON valide trouvée dans le message, utilisation de 'N/A'.")
            self.execution_plan_id = "exec_default"
        if not message:
            self.logger.error("Aucun message fourni dans le contexte.")
            return

        if not task:
            task = new_task(request=message)
            self.logger.info(f"Nouvelle tâche créée: ID={task.id}, ContextID={task.contextId}")
            await event_queue.enqueue_event(task)

        current_task_id = task.id
        current_context_id = task.contextId 

        user_input_json_str = self._extract_input_from_message(message)
        
        if user_input_json_str is None:
            self.logger.warning(f"Aucune entrée utilisateur valide extraite du message pour la tâche {current_task_id}.")
            await event_queue.enqueue_event(TaskStatusUpdateEvent(
                status=TaskStatus(state=TaskState.failed, message=new_agent_text_message(
                    text="Aucune entrée utilisateur valide fournie ou format de partie incorrect.",
                    context_id=current_context_id, task_id=current_task_id)),
                final=True, contextId=current_context_id, taskId=current_task_id))
            self._update_stats(success=False)
            return
        
        try:
            input_payload_from_supervisor = json.loads(user_input_json_str)
            provided_env = input_payload_from_supervisor.get("environment_id")

            if not provided_env:
                self.logger.warning(
                    f"Environment ID missing in task input for task {current_task_id}. Attempting reconstruction.")
            self.current_environment_id = EnvironmentManager.normalize_environment_id(
                provided_env or self.execution_plan_id
            )
            await self.environment_manager.create_isolated_environment(self.current_environment_id)

            last_action_result: dict | None = None
            continue_loop = True
            while continue_loop:
                payload_for_logic = dict(input_payload_from_supervisor)
                if last_action_result is not None:
                    payload_for_logic["last_action_result"] = last_action_result

                self.logger.info(
                    f"Appel de la logique de l'agent pour décider de la prochaine action (env: {self.current_environment_id}).")
                llm_action_json_str = await self.agent_logic.process(json.dumps(payload_for_logic), current_context_id)

                llm_action_payload = json.loads(llm_action_json_str)
                action_type = llm_action_payload.get("action")

                final_status_state = TaskState.working
                is_final_event = False
                action_result_summary = "Action exécutée par l'agent de développement."

                if action_type == "generate_code_and_write_file":
                    file_path = llm_action_payload.get("file_path", "/app/main.py")
                    code_objective = llm_action_payload.get("objective", "")
                    code_instructions = llm_action_payload.get("local_instructions", [])
                    code_acceptance_criteria = llm_action_payload.get("acceptance_criteria", [])
                
                self.logger.info(f"Développement : Action 'generate_code_and_write_file' décidée par LLM pour '{file_path}'.")
                
                from src.shared.llm_client import call_llm 

                code_system_prompt = (
                    "Tu es un développeur IA expert en Python. Ta mission est de générer du code Python propre, "
                    "fonctionnel et bien commenté, basé sur les spécifications fournies. "
                    "Le code doit être directement utilisable. N'inclus que le code dans ta réponse, "
                    "sauf si des commentaires dans le code sont nécessaires pour l'expliquer."
                    "Assure-toi de respecter les instructions spécifiques et les critères d'acceptation."
                )
                code_generation_prompt = (
                    f"Objectif du code : {code_objective}\n\n"
                    f"Instructions spécifiques : {', '.join(code_instructions) if code_instructions else 'Aucune.'}\n\n"
                    f"Critères d'acceptation : {', '.join(code_acceptance_criteria) if code_acceptance_criteria else 'Non spécifiés.'}\n\n"
                    "Génère UNIQUEMENT le code Python correspondant."
                )
                
                generated_code = await call_llm(code_generation_prompt, code_system_prompt, json_mode=False)
                await self.environment_manager.write_file_to_environment(self._reconstruct_environment_id(), file_path, generated_code)
                
                    action_result_summary = f"Code généré et écrit dans {file_path}. Aperçu: {generated_code[:100]}..."

                elif action_type == "execute_command":
                    command = llm_action_payload.get("command")
                    workdir = llm_action_payload.get("workdir", "/app")
                    env_id = self._reconstruct_environment_id()
                    self.logger.info(f"Développement : Exécution de commande '{command}' dans '{env_id}'.")

                cmd_result = await self.environment_manager.execute_command_in_environment(
                    env_id, command, workdir
                )
                action_result_summary = (
                    f"Commande '{command}' exécutée. Exit code: {cmd_result['exit_code']}. "
                    f"Stdout: {cmd_result['stdout'][:100]}... Stderr: {cmd_result['stderr'][:100]}..."
                )

                if cmd_result["exit_code"] != 0:
                    # Ne pas échouer immédiatement la tâche. On renvoie le résultat
                    # de la commande à l'agent appelant pour qu'il décide de la suite
                    self.logger.warning(
                        "La commande '%s' a retourné un code non nul dans l'environnement %s."
                        " Stdout: %s, Stderr: %s",
                        command,
                        env_id,
                        cmd_result["stdout"],
                        cmd_result["stderr"],
                    )
                elif action_type == "read_file":
                    file_path = llm_action_payload.get("file_path")
                    env_id = self._reconstruct_environment_id()
                    self.logger.info(f"Développement : Lecture de fichier '{file_path}' depuis '{env_id}'.")
                try:
                    content = await self.environment_manager.read_file_from_environment(env_id, file_path)
                    action_result_summary = f"Fichier '{file_path}' lu. Contenu (début): {content[:100]}..."
                except Exception as e:
                    # Ne pas échouer immédiatement la tâche. On renvoie le résultat
                    # de la commande à l'agent appelant pour qu'il décide de la suite
                    self.logger.warning(
                        "La commande '%s' a retourné une erreur de fichier l'environnement %s."
                        " Stdout: %s, Stderr: %s",
                        command,
                        env_id,
                        cmd_result["stdout"],
                        cmd_result["stderr"],
                    )


                elif action_type == "list_directory":
                    path = llm_action_payload.get("path", "/app")
                    env_id = self._reconstruct_environment_id()
                    self.logger.info(f"Développement : Listing du répertoire '{path}' dans '{env_id}'.")
                cmd_result = await self.environment_manager.execute_command_in_environment(env_id, f"ls -F {path}")
                action_result_summary = f"Contenu de '{path}': {cmd_result['stdout']}. Exit code: {cmd_result['exit_code']}"
                if cmd_result['exit_code'] != 0:
                    final_status_state = TaskState.failed
                    is_final_event = True

                elif action_type == "complete_task":
                    action_result_summary = llm_action_payload.get("summary", "Tâche complétée par l'agent de développement.")
                    final_status_state = TaskState.completed
                    is_final_event = True

                else:
                    action_result_summary = f"Action LLM inconnue: '{action_type}'."
                    final_status_state = TaskState.failed
                    is_final_event = True

                artifact_content = {"action_taken": action_type, "summary": action_result_summary, "details": llm_action_payload}
                result_artifact = self._create_artifact_from_result(json.dumps(artifact_content), task)

                await event_queue.enqueue_event(TaskArtifactUpdateEvent(
                    append=False, contextId=current_context_id, taskId=current_task_id, lastChunk=True,
                    artifact=result_artifact
                ))

                status_message_text = f"Action '{action_type}' exécutée. {action_result_summary}"
                if final_status_state == TaskState.failed:
                    status_message_text = f"Action '{action_type}' a échoué. {action_result_summary}"

                await event_queue.enqueue_event(TaskStatusUpdateEvent(
                    status=TaskStatus(state=final_status_state, message=new_agent_text_message(
                        text=status_message_text,
                        context_id=current_context_id, task_id=current_task_id)),
                    final=is_final_event, contextId=current_context_id, taskId=current_task_id))

                if is_final_event:
                    self._update_stats(success=final_status_state != TaskState.failed)
                    continue_loop = False
                else:
                    last_action_result = artifact_content

        except json.JSONDecodeError as e:
            self.logger.error(f"Erreur de décodage JSON de l'input ou de la réponse LLM pour la tâche {current_task_id}: {e}", exc_info=True)
            await event_queue.enqueue_event(TaskStatusUpdateEvent(
                status=TaskStatus(state=TaskState.failed, message=new_agent_text_message(
                    text=f"JSON invalide en entrée ou de la logique de l'agent: {str(e)}",
                    context_id=current_context_id, task_id=current_task_id)),
                final=True, contextId=current_context_id, taskId=current_task_id))
            self._update_stats(success=False)
        except Exception as e:
            self.logger.error(f"Erreur pendant l'exécution de la tâche {current_task_id}: {e}", exc_info=True)
            await event_queue.enqueue_event(TaskStatusUpdateEvent(
                status=TaskStatus(state=TaskState.failed, message=new_agent_text_message(
                    text=f"Erreur interne de l'agent: {str(e)}",
                    context_id=current_context_id, task_id=current_task_id)),
                final=True, contextId=current_context_id, taskId=current_task_id))
            self._update_stats(success=False)