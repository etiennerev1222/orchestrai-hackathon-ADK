# src/agents/development_agent/logic.py

import logging
import json

from src.shared.base_agent_logic import BaseAgentLogic
from src.shared.llm_client import call_llm
from src.services.environment_manager.environment_manager import EnvironmentManager # Import for type hinting/static methods

logger = logging.getLogger(__name__)

AGENT_SKILL_CODING_PYTHON = "coding_python"

class DevelopmentAgentLogic(BaseAgentLogic):
    """Logic handling the reasoning of the development agent."""
    def __init__(self):
        super().__init__()
        import os
        self.agent_name = os.environ.get("AGENT_NAME", "DevelopmentAgentGKEv2")
        self.logger = logging.getLogger(f"{__name__}.{self.agent_name}.DevelopmentAgentLogic")
        self.logger.info("Logique du DevelopmentAgent initialisée.")
        self.environment_manager: EnvironmentManager | None = None # Add type hint

    def set_environment_manager(self, manager: EnvironmentManager):
        """Sets the EnvironmentManager instance for the logic to use."""
        self.environment_manager = manager
        self.logger.info("EnvironmentManager set for DevelopmentAgentLogic.")

    def _get_system_prompt(self) -> str:
        return (
            "Tu es un développeur IA expert et un planificateur d'actions. Ton rôle est d'analyser un objectif de développement, des instructions, "
            "l'état de l'environnement, et le résultat de la dernière action pour décider de la **prochaine action unique et la plus pertinente**."
            "\n\nTu dois toujours répondre **UNIQUEMENT** avec un objet JSON qui spécifie cette action. "
            "Ne fournis AUCUN autre texte ou explication en dehors de cet objet JSON."
            "\n\n**Actions/Outils disponibles et leur format JSON :**"
            "\n1. **generate_code_and_write_file**: Pour créer ou écraser un fichier avec du code."
            "\n   `{ \"action\": \"generate_code_and_write_file\", \"file_path\": \"/chemin/vers/fichier.py\", \"objective\": \"Description du code à générer\", \"local_instructions\": [\"Instruction 1\", \"Instruction 2\"], \"acceptance_criteria\": [\"Critère 1\", \"Critère 2\"] }`"
            "\n   - `file_path`: Chemin absolu du fichier à créer ou écraser (ex: `/app/main.py`)."
            "\n   - `objective`: Description claire de ce que le code doit faire."
            "\n   - `local_instructions`: (Optionnel) Liste d'instructions spécifiques pour la génération du code."
            "\n   - `acceptance_criteria`: (Optionnel) Liste de critères de test ou de validation pour le code."
            "\n\n2. **execute_command**: Pour exécuter une commande shell dans l'environnement."
            "\n   `{ \"action\": \"execute_command\", \"command\": \"commande à exécuter\", \"workdir\": \"/chemin/travail\" }`"
            "\n   - `command`: La commande shell à exécuter (ex: `python -m pytest`)."
            "\n   - `workdir`: (Optionnel) Répertoire de travail pour la commande (par défaut `/app`)."
            "\n\n3. **read_file**: Pour lire le contenu d'un fichier existant."
            "\n   `{ \"action\": \"read_file\", \"file_path\": \"/chemin/vers/fichier.txt\" }`"
            "\n   - `file_path`: Chemin absolu du fichier à lire."
            "\n\n4. **list_directory**: Pour lister le contenu d'un répertoire."
            "\n   `{ \"action\": \"list_directory\", \"path\": \"/chemin/du/repertoire\" }`"
            "\n   - `path`: (Optionnel) Chemin absolu du répertoire à lister (par défaut `/app`)."
            "\n\n5. **complete_task**: Pour indiquer que l'objectif global est atteint."
            "\n   `{ \"action\": \"complete_task\", \"summary\": \"Résumé des accomplissements et résultats clés.\" }`"
            "\n   - `summary`: Un résumé concis et structuré des tâches effectuées, des fichiers générés, des tests passés, etc."
            "\n\n**Contexte actuel de l'environnement (simulé ou réel) :**"
            "\n- L'environnement est un conteneur Linux avec Python 3.11."
            "\n- Le répertoire de travail par défaut est `/app`."
            "\n- Les outils `bash`, `jq`, `findutils`, `git`, `curl`, `wget`, `vim`, `build-essential` sont installés."
            "\n- Les dépendances Python listées dans `requirements.txt` sont installées."
            "\n\n**Ton processus de décision :**"
            "\n1. Évalue l'objectif global de développement."
            "\n2. Analyse le `last_action_result` pour comprendre l'état actuel et les éventuels problèmes."
            "\n3. Choisis l'action unique la plus logique pour progresser vers l'objectif."
            "\n4. Si un problème survient (indiqué par `last_action_result.details.error`), tente de le résoudre avec une action appropriée (ex: `read_file` pour inspecter un fichier, `execute_command` pour déboguer)."
            "\n5. Si l'objectif est clairement atteint et validé, utilise `complete_task`."
            "\n6. Ne génère pas de code tant que tu n'as pas une compréhension claire de l'environnement ou si une action précédente a échoué de manière inattendue."
            "\n\nRéponds UNIQUEMENT avec l'objet JSON de l'action choisie."
        )

    async def process(self, input_data_str: str, context_id: str) -> str:
        input_data = json.loads(input_data_str)
        objective = input_data.get("objective")
        last_action_result = input_data.get("last_action_result")

        if not objective:
            self.logger.error("DevelopmentAgentLogic - Objectif manquant dans l'input.")
            return json.dumps(
                {"action": "complete_task", "summary": "Tâche échouée: objectif non spécifié."}
            )

        self.logger.info(f"DevelopmentAgentLogic - Décision d'action pour l'objectif: '{objective}'")
        if last_action_result:
            self.logger.info(f"Résultat de la dernière action pour informer la décision: {json.dumps(last_action_result, indent=2)}")

        system_prompt = self._get_system_prompt()

        prompt = (
            f"Objectif de développement global : {objective}\n\n"
            f"Résultat de la dernière action exécutée : {json.dumps(last_action_result, indent=2)}\n\n"
            "En te basant sur l'objectif et le résultat de la dernière action, quelle est la **PROCHAINE action unique et atomique que tu dois planifier** ? "
            "Quand tu choisis `complete_task`, fournis un résumé structuré (avec fichiers générés, commandes exécutées, résultats des tests)."
            " Réponds UNIQUEMENT avec l'objet JSON correspondant à l'action choisie."
        )
        try:
            llm_response_str = await call_llm(prompt, system_prompt, json_mode=True)
            self.logger.info(f"DevelopmentAgentLogic - Réponse LLM (prochaine action): {llm_response_str}")
            logger.debug(f"Action LLM décidée: - Payload: {llm_response_str}")
            return llm_response_str
        except Exception as e:
            self.logger.error(f"DevelopmentAgentLogic - Échec lors de la décision de l'action par le LLM: {e}", exc_info=True)
            # Fallback to a failure message if LLM call fails
            return json.dumps({"action": "complete_task", "summary": f"Échec de la décision de l'action par le LLM: {str(e)}", "status": "failed"})

