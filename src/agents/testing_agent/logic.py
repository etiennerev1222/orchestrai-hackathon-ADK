import logging
import json

from src.shared.base_agent_logic import BaseAgentLogic
from src.shared.llm_client import call_llm

logger = logging.getLogger(__name__)
if not logger.hasHandlers():
    logging.basicConfig(level=logging.INFO)

AGENT_SKILL_SOFTWARE_TESTING = "software_testing"
AGENT_SKILL_TEST_CASE_GENERATION = "test_case_generation"


class TestingAgentLogic(BaseAgentLogic):
    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(f"{__name__}.TestingAgentLogic")
        self.logger.info("Logique du TestingAgent initialisée.")

    async def process(self, input_data_str: str, context_id: str | None = None) -> str:
        """Détermine la prochaine action de test à entreprendre."""
        try:
            input_payload = json.loads(input_data_str)
            objective = input_payload.get("objective", "Objectif de test non spécifié.")
            local_instructions = input_payload.get("local_instructions", [])
            acceptance_criteria = input_payload.get("acceptance_criteria", [])
            environment_id = input_payload.get("environment_id")
            current_environment_state = input_payload.get(
                "current_state",
                "L'environnement est vide ou inconnu. Aucune information préalable sur l'état."
            )
            last_action_result = input_payload.get("last_action_result", {})
        except json.JSONDecodeError:
            self.logger.error(f"TestingAgent: Input JSON invalide: {input_data_str}")
            return json.dumps({"status": "error", "message": f"Input JSON invalide: {input_data_str}"})

        if not environment_id:
            self.logger.error("TestingAgent: 'environment_id' manquant dans l'input.")
            return json.dumps({"status": "error", "message": "Environment ID is required for testing actions."})

        self.logger.info(
            f"TestingAgent - Décision d'action pour l'objectif: '{objective}' (environnement: {environment_id})"
        )
        self.logger.debug(f"Instructions locales: {local_instructions}")
        self.logger.debug(f"Critères d'acceptation: {acceptance_criteria}")
        self.logger.debug(f"État actuel de l'environnement: {current_environment_state}")
        self.logger.debug(f"Résultat de la dernière action: {json.dumps(last_action_result, indent=2)}")

        system_prompt = (
            "Tu es un ingénieur QA expert en tests automatisés et en planification d'actions atomiques. "
            "Ton rôle est d'analyser un objectif de test, des instructions et des critères d'acceptation, "
            "ainsi que l'état actuel de l'environnement de travail et le résultat de la dernière action exécutée. "
            "Décide ensuite de la **prochaine action unique et la plus pertinente** pour avancer vers la validation de l'objectif."
            "\n\nRéponds TOUJOURS UNIQUEMENT avec un objet JSON décrivant cette action. "
            "Si plusieurs actions semblent possibles, choisis la plus logique et atomique."
            "\n\n**Actions/Outils disponibles :**"
            "\n1. **Générer et écrire un fichier de test :**"
            "\n   `{ \"action\": \"generate_test_code_and_write_file\", \"file_path\": \"/app/tests/test_something.py\", \"objective\": \"description des tests\", \"local_instructions\": [], \"acceptance_criteria\": [] }`"
            "\n2. **Exécuter une commande shell :**"
            "\n   `{ \"action\": \"execute_command\", \"command\": \"votre commande\", \"workdir\": \"/app\" }`"
            "\n3. **Lire le contenu d'un fichier :**"
            "\n   `{ \"action\": \"read_file\", \"file_path\": \"/app/chemin/fichier\" }`"
            "\n4. **Lister le contenu d'un répertoire :**"
            "\n   `{ \"action\": \"list_directory\", \"path\": \"/app/chemin/dossier\" }`"
            "\n5. **Terminer la tâche de test :**"
            "\n   `{ \"action\": \"complete_task\", \"summary\": \"Résumé des tests effectués et résultats.\" }`"
            "\n\nTon processus de raisonnement devrait être itératif : écris des tests, exécute-les, analyse les sorties, répète si nécessaire."
            "\n\nContexte actuel :"
            f"\nÉtat de l'environnement : {current_environment_state}"
            f"\nDernier résultat d'action : {json.dumps(last_action_result, indent=2)}"
            "\n\nN'oublie pas : réponds UNIQUEMENT avec l'objet JSON de la prochaine action."
        )

        prompt = (
            f"**Objectif de test global pour cette session :** {objective}\n\n"
            f"**Instructions spécifiques pour cette tâche :**\n"
            f"{'- ' + chr(10) + '- '.join(local_instructions) if local_instructions else 'Aucune instruction spécifique.'}\n\n"
            f"**Critères d'acceptation de la tâche de test :**\n"
            f"{'- ' + chr(10) + '- '.join(acceptance_criteria) if acceptance_criteria else 'Non spécifiés.'}\n\n"
            "En te basant sur l'objectif, les instructions, les critères et le contexte, quelle est la **PROCHAINE action unique** à entreprendre ?"
            "Réponds UNIQUEMENT avec l'objet JSON correspondant à l'action choisie."
        )

        try:
            llm_response_str = await call_llm(prompt, system_prompt, json_mode=True)
            self.logger.info(f"TestingAgentLogic - Réponse LLM (action JSON): {llm_response_str[:500]}...")
            json.loads(llm_response_str)
            return llm_response_str
        except json.JSONDecodeError as e:
            self.logger.error(
                f"TestingAgentLogic - La réponse LLM n'est pas un JSON valide: {e}. Réponse brute: {llm_response_str}",
                exc_info=True,
            )
            return json.dumps({"status": "error", "action": "llm_error", "message": f"LLM returned invalid JSON: {e}. Raw: {llm_response_str}"})
        except Exception as e:
            self.logger.error(
                f"TestingAgentLogic - Échec lors de la décision de l'action par le LLM: {e}",
                exc_info=True,
            )
            return json.dumps({"status": "error", "action": "internal_error", "message": f"Internal error during LLM action decision: {str(e)}"})
