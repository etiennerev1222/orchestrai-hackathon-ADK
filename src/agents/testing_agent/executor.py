import logging
import json

from src.shared.base_agent_executor import BaseAgentExecutor
from .logic import TestingAgentLogic
from a2a.types import (
    Artifact, Task, Message, TaskState, TaskStatus,
    TaskStatusUpdateEvent, TaskArtifactUpdateEvent
)
from a2a.utils import new_text_artifact, new_agent_text_message, new_task
from a2a.server.agent_execution import RequestContext
from a2a.server.events.event_queue import EventQueue
import json
from src.services.environment_manager.environment_manager import EnvironmentManager
from typing_extensions import override

logger = logging.getLogger(__name__)

class TestingAgentExecutor(BaseAgentExecutor):
    def __init__(self, environment_manager=None):
        specific_agent_logic = TestingAgentLogic()
        super().__init__(
            agent_logic=specific_agent_logic,
            default_artifact_name="test_report",
            default_artifact_description="Rapport de test généré pour un livrable."
        )
        self.logger = logging.getLogger(f"{__name__}.TestingAgentExecutor")
        self.logger.info("TestingAgentExecutor initialisé.")

        self.environment_manager = EnvironmentManager()
        self.agent_logic.set_environment_manager(self.environment_manager)

    def _create_artifact_from_result(self, result_data: str, task: Task) -> Artifact:
        """
        Crée un Artifact A2A à partir du rapport de test (chaîne JSON) retourné par la logique.
        """
        self.logger.info(f"Création de l'artefact du rapport de test pour la tâche {task.id}.")
        return new_text_artifact(
            name=self.default_artifact_name,
            description=self.default_artifact_description,
            text=result_data 
        )

    @override
    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        current_task_id = context.current_task.id if context.current_task else "N/A"
        current_context_id = context.context_id or (context.message.contextId if context.message else "N/A")
        self.logger.info(f"TestingAgentExecutor.execute appelé pour la tâche {current_task_id}, contexte {current_context_id}")

        message = context.message
        task = context.current_task

        if not message:
            self.logger.error("Aucun message fourni dans le contexte.")
            return

        if not task:
            task = new_task(request=message)
            self.logger.info(f"Nouvelle tâche créée: ID={task.id}, ContextID={task.contextId}")
            await event_queue.enqueue_event(task)

        input_json_str = self._extract_input_from_message(message)

        if input_json_str is None:
            await event_queue.enqueue_event(TaskStatusUpdateEvent(
                status=TaskStatus(state=TaskState.failed, message=new_agent_text_message(
                    text="Entrée utilisateur invalide ou manquante.",
                    context_id=current_context_id, task_id=current_task_id)),
                final=True, contextId=current_context_id, taskId=current_task_id
            ))
            return

        try:
            input_payload = json.loads(input_json_str)
            environment_id = input_payload.get("environment_id")

            if not environment_id:
                raise ValueError("Environment ID missing in task input.")



            llm_action_str = await self.agent_logic.process(input_json_str, current_context_id)
            llm_action = json.loads(llm_action_str)
            action_type = llm_action.get("action")

            final_state = TaskState.working
            is_final = False
            action_summary = ""

            if action_type == "generate_test_code_and_write_file":
                file_path = llm_action.get("file_path", "/app/test.py")
                objective = llm_action.get("objective", "")
                instructions = llm_action.get("local_instructions", [])
                criteria = llm_action.get("acceptance_criteria", [])

                from src.shared.llm_client import call_llm
                system_prompt = (
                    "Tu es un ingénieur QA expert en Python. Génère un fichier de test Python fonctionnel, "
                    "clair et directement exécutable, basé sur les spécifications fournies. "
                    "Retourne UNIQUEMENT le code Python."
                )
                prompt = (
                    f"Objectif des tests : {objective}\n"
                    f"Instructions : {', '.join(instructions) if instructions else 'Aucune'}\n"
                    f"Critères d'acceptation : {', '.join(criteria) if criteria else 'Non spécifiés'}\n"
                )

                code = await call_llm(prompt, system_prompt, json_mode=False)
                await self.environment_manager.write_file_to_environment(environment_id, file_path, code)
                action_summary = f"Code de test généré et écrit dans {file_path}."

            elif action_type == "execute_command":
                command = llm_action.get("command")
                workdir = llm_action.get("workdir", "/app")
                result = await self.environment_manager.execute_command_in_environment(environment_id, command, workdir)
                action_summary = f"Commande '{command}' exécutée. Exit: {result['exit_code']}. Stdout: {result['stdout'][:100]}... Stderr: {result['stderr'][:100]}..."
                if result['exit_code'] != 0:
                    final_state = TaskState.failed
                    is_final = True

            elif action_type == "read_file":
                file_path = llm_action.get("file_path")
                try:
                    content = await self.environment_manager.read_file_from_environment(environment_id, file_path)
                    action_summary = f"Fichier '{file_path}' lu. Contenu (début): {content[:100]}..."
                except FileNotFoundError:
                    action_summary = f"Erreur: Fichier '{file_path}' non trouvé."
                    final_state = TaskState.failed
                    is_final = True
                except Exception as e:
                    action_summary = f"Erreur lecture fichier '{file_path}': {str(e)}"
                    final_state = TaskState.failed
                    is_final = True

            elif action_type == "list_directory":
                path = llm_action.get("path", "/app")
                result = await self.environment_manager.execute_command_in_environment(environment_id, f"ls -F {path}")
                action_summary = f"Contenu de '{path}': {result['stdout']}. Exit code: {result['exit_code']}"
                if result['exit_code'] != 0:
                    final_state = TaskState.failed
                    is_final = True

            elif action_type == "complete_task":
                action_summary = llm_action.get("summary", "Tâche de test complétée.")
                final_state = TaskState.completed
                is_final = True

            else:
                action_summary = f"Action inconnue: {action_type}"
                final_state = TaskState.failed
                is_final = True

            artifact = self._create_artifact_from_result(json.dumps({
                "action_taken": action_type,
                "summary": action_summary,
                "details": llm_action
            }), task)

            await event_queue.enqueue_event(TaskArtifactUpdateEvent(
                append=False, contextId=current_context_id, taskId=current_task_id,
                artifact=artifact, lastChunk=True
            ))

            await event_queue.enqueue_event(TaskStatusUpdateEvent(
                status=TaskStatus(state=final_state, message=new_agent_text_message(
                    text=action_summary,
                    context_id=current_context_id, task_id=current_task_id
                )),
                final=is_final, contextId=current_context_id, taskId=current_task_id
            ))

        except Exception as e:
            self.logger.error(f"Erreur lors de l'exécution : {e}", exc_info=True)
            await event_queue.enqueue_event(TaskStatusUpdateEvent(
                status=TaskStatus(state=TaskState.failed, message=new_agent_text_message(
                    text=f"Erreur interne : {str(e)}",
                    context_id=current_context_id, task_id=current_task_id
                )),
                final=True, contextId=current_context_id, taskId=current_task_id
            ))
    