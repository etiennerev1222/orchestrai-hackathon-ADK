# src/agents/development_agent/logic.py

import logging
import json
from typing import Dict, Any

from src.shared.base_agent_logic import BaseAgentLogic
from src.shared.llm_client import call_llm

logger = logging.getLogger(__name__)

AGENT_SKILL_CODING_PYTHON = "coding_python"


class DevelopmentAgentLogic(BaseAgentLogic):
    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(f"{__name__}.DevelopmentAgentLogic")
        self.logger.info("Logique du DevelopmentAgent initialisée.")

    def _get_system_prompt(self) -> str:
        return (
            "Tu es un développeur IA expert et un planificateur d'actions. Ton rôle est d'analyser un objectif de développement, des instructions, "
            "l'état de l'environnement, et le résultat de la dernière action pour décider de la **prochaine action unique et la plus pertinente**."
            "\n\nTu dois toujours répondre **UNIQUEMENT** avec un objet JSON qui spécifie cette action. "
            "Ne fournis AUCUN autre texte ou explication en dehors de cet objet JSON."
            "\n\n**Actions/Outils disponibles et leur format JSON :**"
            "\n1. **generate_code_and_write_file**: Pour créer ou écraser un fichier avec du code."
            "\n   `{ \"action\": \"generate_code_and_write_file\", \"file_path\": \"/app/main.py\", \"objective\": \"...\", \"local_instructions\": [], \"acceptance_criteria\": [] }`"
            "\n2. **execute_command**: Pour exécuter une commande shell (ex: `pip install`, `python main.py`, `ls -l`)."
            "\n   `{ \"action\": \"execute_command\", \"command\": \"votre commande shell\", \"workdir\": \"/app\" }`"
            "\n3. **read_file**: Pour lire le contenu d'un fichier existant."
            "\n   `{ \"action\": \"read_file\", \"file_path\": \"/app/main.py\" }`"
            "\n4. **list_directory**: Pour lister le contenu d'un répertoire."
            "\n   `{ \"action\": \"list_directory\", \"path\": \"/app\" }`"
            "\n- Si une erreur se produit, lis le fichier de code, corrige-le (en le ré-écrivant), et ré-exécute."
            "\n5. **complete_task**: Quand tu estimes que l'objectif est entièrement atteint et vérifié."
            "\n   `{ \"action\": \"complete_task\", \"summary\": \"Le code a été écrit, installé et testé avec succès. Le livrable est prêt.\","
            " \"details\": { \"fichiers_generes\": [\"/app/main.py\"], \"commandes_executees\": [\"pip install ...\"], \"résultats_des_tests\": \"Tous les tests ont réussi\", \"log_final\": \"...\" } }`"
            "\n\n**Ton processus de raisonnement est itératif :**"
            "\n- Écris le code initial."
            "\n- Exécute-le."
            "\n- Lis la sortie (stdout/stderr)."
        )

    async def process(self, input_data_str: str, context_id: str | None = None) -> str:
        """Génère la prochaine action JSON que l'agent de développement devrait entreprendre."""

        try:
            input_payload = json.loads(input_data_str)
            objective = input_payload.get("objective", "Objectif non spécifié.")
            last_action_result = input_payload.get("last_action_result", {})
        except json.JSONDecodeError:
            self.logger.error(f"DevelopmentAgentLogic: Input JSON invalide: {input_data_str}")
            return json.dumps({"action": "complete_task", "summary": "Erreur: L'input de la tâche était mal formaté."})

        self.logger.info(f"DevelopmentAgentLogic - Décision d'action pour l'objectif: '{objective}'")
        if last_action_result:
            self.logger.info(f"Résultat de la dernière action pour informer la décision: {last_action_result}")

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
            return json.dumps({"action": "complete_task", "summary": f"Erreur interne lors de l'appel au LLM: {e}"})
