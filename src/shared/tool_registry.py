# src/shared/tool_registry.py

import logging
from typing import Callable, Optional
from datetime import datetime
import uuid

from src.tools import development_tools, generic_tools
from src.shared.execution_task_graph_management import (
    ExecutionTaskGraph,
    ExecutionTaskNode,
    ExecutionTaskType,
)

logger = logging.getLogger(__name__)

class ToolRegistry:
    def __init__(self, agent_skill: str = "generic"):
        self.agent_skill = agent_skill
        self.tools = self._load_tools_for_skill(agent_skill)
        self.tool_metadata = self._load_tool_metadata(agent_skill)
        logger.info(f"ToolRegistry initialisé pour skill: {agent_skill}. Outils disponibles : {list(self.tools.keys())}")

    def load_all_tools(self):
        """
        Charge tous les outils associés à la compétence de l’agent.
        """
        self.tools = self._load_tools_for_skill(self.agent_skill)
        self.tool_metadata = self._load_tool_metadata(self.agent_skill)
        if self.agent_skill != "generic":
            self.tools.update(self._load_tools_for_skill("generic"))
            self.tool_metadata.update(self._load_tool_metadata("generic"))

    def _load_tools_for_skill(self, skill: str) -> dict:
        if skill == "coding_python":
            return {
                "generate_code_and_write_file": development_tools.generate_code_and_write_file,
                "execute_command": development_tools.execute_command,
                "read_file": development_tools.read_file,
                "list_directory": development_tools.list_directory,
                "complete_task": development_tools.complete_task,
                "workforce_information": generic_tools.workforce_information,
                "capability_check": generic_tools.capability_check
            }
        elif skill == "generic":
            return {
                "workforce_information": generic_tools.workforce_information,
                "capability_check": generic_tools.capability_check
            }
        else:
            logger.warning(f"Skill inconnu '{skill}', aucun outil chargé.")
            return {}

    def _load_tool_metadata(self, skill: str) -> dict:
        if skill == "coding_python":
            return {
                "generate_code_and_write_file": {"description": "Génère du code et l’écrit dans un fichier."},
                "execute_command": {"description": "Exécute une commande shell dans l’environnement."},
                "read_file": {"description": "Lit un fichier de l’environnement."},
                "list_directory": {"description": "Liste les fichiers dans un répertoire de l’environnement."},
                "complete_task": {"description": "Signale que la tâche est terminée."},
                "workforce_information": {"description": "Retourne les agents disponibles."},
                "capability_check": {"description": "Vérifie la capacité d’un agent à produire un livrable", "mandatory_on_first_turn": True}
            }
        elif skill == "generic":
            return {
                "workforce_information": {
                    "description": "Retourne les agents disponibles"
                },
                "capability_check": {
                    "description": "Vérifie la capacité d’un agent à produire un livrable",
                    "mandatory_on_first_turn": True
                }
            }
        else:
            return {}

    def get_metadata_for_tools(self, tool_names: Optional[list[str]]) -> dict:
        """
        Retourne un dictionnaire {tool_name: metadata} pour les outils listés.
        """
        return {name: self.tool_metadata.get(name, {}) for name in (tool_names or [])}

    async def handle_llm_response(self, llm_response: str | dict, context_id: Optional[str] = None) -> Optional[dict]:
        import json
        from src.shared.interaction_logger import save_interaction_artifact
        from src.shared.execution_task_graph_management import ExecutionTaskNode, ExecutionTaskGraph, ExecutionTaskType

        if isinstance(llm_response, str):
            try:
                data = json.loads(llm_response)
            except json.JSONDecodeError as e:
                raise ValueError(f"Erreur de parsing JSON : {e}")
        else:
            data = llm_response

        action = data.get("action")
        if not action:
            raise ValueError("Champ 'action' manquant dans la réponse.")
        sender_agent = data.get("sender_agent")
        if action == "invoke_tool" and not sender_agent:
            raise ValueError("Le champ 'sender_agent' est requis pour 'invoke_tool'")
        # 🔁 Cas spécial invoke_tool
        if action == "invoke_tool":
            tool_name = data.get("tool")
            if not tool_name:
                raise ValueError("Champ 'tool' requis pour action 'invoke_tool'.")

            handler = self.tools.get(tool_name)
            if not handler:
                raise ValueError(f"Outil '{tool_name}' non trouvé dans ToolRegistry.")

            task_id = f"tool-{uuid.uuid4()}"
            parent_task_id = context_id  # on assume que context_id est bien le parent logique ici

            # Créer et tracer la tâche dans le graphe
            task_node = ExecutionTaskNode(
                task_id=task_id,
                objective=f"Invoke {tool_name}",
                task_type=ExecutionTaskType.TOOL_CALL,
                parent_id=parent_task_id,
                meta={"sender_agent": sender_agent}
            )

            graph = ExecutionTaskGraph(context_id)

            # 👇 Ajout du noeud racine implicite si manquant
            if parent_task_id not in graph._get_graph_data().get("nodes", {}):
                root_task_node = ExecutionTaskNode(
                    task_id=parent_task_id,
                    objective="Root Task",
                    task_type=ExecutionTaskType.CONTAINER,
                    parent_id=None
                )
                graph.add_task(root_task_node, is_root=True)

            # Ajouter la tâche tool_call
            graph.add_task(task_node)
            graph.link_tasks(from_id=parent_task_id, to_id=task_id)

            # Appeler l'outil
            result = await handler(data.get("input", {}), context_id=context_id)
            sender_agent = data.get("sender_agent", "unknown")
            # 🔖 Enregistrer un artefact Firestore
            if isinstance(result, dict):
                interaction_id = str(uuid.uuid4())
                artifact = {
                    "interaction_id": interaction_id,
                    "sender_agent": sender_agent,
                    "msg_type": "TOOL_INVOKE",
                    "tool_invoked": {
                        "name": tool_name,
                        "input": data.get("input", {}),
                        "output": result
                    },
                    "result_summary": result.get("summary") or f"{tool_name} exécuté.",
                    "timestamp": datetime.utcnow().isoformat(),
                    "linked_task_id": task_id
                }
                save_interaction_artifact(context_id, artifact)

            return result

        # ✅ Cas standard : action == tool_name
        handler = self.tools.get(action)
        if not handler:
            logger.warning(f"Outil '{action}' non trouvé dans ToolRegistry.")
            return None

        return await handler(data, context_id=context_id)

    def get_tools(self) -> dict:
        return self.tools

    def get_tool_descriptions(self) -> dict:
        """
        Retourne une description textuelle (pour le prompt) de chaque outil.
        """
        from src.shared.prompt_utils import build_development_agent_system_prompt
        return {k: v.__doc__ or "Pas de description." for k, v in self.tools.items()}
