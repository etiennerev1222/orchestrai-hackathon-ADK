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

            try:
                llm_response_tcg_str = await call_llm(prompt_tcg, system_prompt_tcg, json_mode=True)
                parsed_llm_response = json.loads(llm_response_tcg_str)
                if "generated_test_cases" not in parsed_llm_response or not isinstance(parsed_llm_response["generated_test_cases"], list):
                    self.logger.error(f"TestingAgent (test_case_generation): Réponse LLM malformée - {llm_response_tcg_str}")
                    raise ValueError("Réponse LLM pour la génération de cas de test malformée.")
                self.logger.info(f"TestingAgent (test_case_generation) - Cas de test générés (JSON): {llm_response_tcg_str}")
                return llm_response_tcg_str 
            except Exception as e:
                self.logger.error(f"TestingAgent (test_case_generation) - Échec: {e}", exc_info=True)
                return json.dumps({"error": f"Erreur LLM lors de la génération des cas de test: {str(e)}", "generated_test_cases": [] })
        
        elif assigned_skill == AGENT_SKILL_SOFTWARE_TESTING:
            self.logger.info(f"TestingAgent: Mode '{AGENT_SKILL_SOFTWARE_TESTING}' pour l'objectif: '{objective}'")
            
            deliverable_code = input_artifacts_content.get("code_to_test") 
            test_cases_str_or_list = input_artifacts_content.get("test_cases_file") 
            if not deliverable_code:
                deliverable_code = input_artifacts_content.get("deliverable")
                
            self.logger.info(f"TestingAgent (software_testing) code_to_test: {'Présent' if deliverable_code else 'MANQUANT OU VIDE'}")
            self.logger.info(f"TestingAgent (software_testing) test_cases_file: {'Présent' if test_cases_str_or_list else 'MANQUANT OU VIDE'}")
            if isinstance(deliverable_code, str) and deliverable_code.strip():
                 self.logger.debug(f"TestingAgent (software_testing) deliverable_code (début): {deliverable_code[:200]}...")
            if isinstance(test_cases_str_or_list, str) and test_cases_str_or_list.strip():
                 self.logger.debug(f"TestingAgent (software_testing) test_cases_str_or_list (début): {test_cases_str_or_list[:200]}...")


            if not deliverable_code or (isinstance(deliverable_code, str) and (deliverable_code.startswith("// ERREUR:") or deliverable_code.startswith("// ATTENTION:"))):
                self.logger.warning(f"TestingAgent (software_testing): Livrable 'code_to_test' non valide ou manquant dans input_artifacts_content. Contenu: '{deliverable_code}'")
                return json.dumps({
                    "test_status": "error", 
                    "summary": "Livrable 'code_to_test' (attendu dans input_artifacts_content) non valide ou manquant pour l'exécution des tests.",
                    "passed_criteria": [], "failed_criteria": acceptance_criteria,
                    "identified_issues_or_bugs": [f"Le contenu du code à tester (attendu via 'code_to_test' dans input_artifacts_content) n'a pas été fourni correctement. Reçu: {deliverable_code}"]
                })
            
            formatted_test_cases = ""
            if test_cases_str_or_list and isinstance(test_cases_str_or_list, str):
                try:
                    parsed_tc_artifact = json.loads(test_cases_str_or_list)
                    if "generated_test_cases" in parsed_tc_artifact and isinstance(parsed_tc_artifact["generated_test_cases"], list):
                        formatted_test_cases = "\n- ".join(parsed_tc_artifact["generated_test_cases"])
                        if formatted_test_cases: formatted_test_cases = "- " + formatted_test_cases
                    else:
                        self.logger.warning(f"TestingAgent (software_testing): 'generated_test_cases' non trouvé ou pas une liste dans test_cases_file. Utilisation brute: {test_cases_str_or_list[:100]}")
                        formatted_test_cases = test_cases_str_or_list 
                except json.JSONDecodeError:
                    self.logger.warning(f"TestingAgent (software_testing): test_cases_file n'est pas un JSON valide. Utilisation brute: {test_cases_str_or_list[:100]}")
                    formatted_test_cases = test_cases_str_or_list
            elif isinstance(test_cases_str_or_list, list):
                 formatted_test_cases = "\n- ".join(test_cases_str_or_list)
                 if formatted_test_cases: formatted_test_cases = "- " + formatted_test_cases
            
            self.logger.info(f"TestingAgent (software_testing) - Cas de test formatés pour prompt (début): {formatted_test_cases[:300] if formatted_test_cases else 'Aucun cas de test spécifique fourni.'}")

            test_cases_prompt_section = ""
            if formatted_test_cases:
                test_cases_prompt_section = (
                    "Cas de test spécifiques à exécuter/vérifier (en plus des critères d'acceptation généraux) :\n"
                    f"'''\n{formatted_test_cases}\n'''\n\n"
                )
            
            system_prompt_st = (
                "Tu es un ingénieur QA expert et un testeur logiciel rigoureux. "
                "Ta mission est d'analyser un livrable de code fourni, ainsi qu'une liste de cas de test (si fournie), "
                "par rapport à son objectif, ses instructions de développement et ses critères d'acceptation. "
                "Tu dois déterminer si le livrable est conforme. Identifie les points de succès et les échecs ou bugs potentiels. "
                "Fournis un rapport de test concis au format JSON."

            )
            return json.dumps({"status": "error", "action": "llm_error", "message": f"LLM returned invalid JSON: {e}. Raw: {llm_response_str}"})
        except Exception as e:
            self.logger.error(
                f"TestingAgentLogic - Échec lors de la décision de l'action par le LLM: {e}",
                exc_info=True,
            )
            return json.dumps({"status": "error", "action": "internal_error", "message": f"Internal error during LLM action decision: {str(e)}"})
