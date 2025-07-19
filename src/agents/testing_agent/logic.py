import logging
import json
from typing import Dict, Any, Tuple

from src.shared.base_agent_logic import BaseAgentLogic
from src.shared.llm_client import call_llm
from src.shared.prompts import get_base_prompt
from src.shared.prompt_utils import build_generic_system_prompt

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
        try:
            input_payload = json.loads(input_data_str)
            objective = input_payload.get("objective", "Objectif de test non spécifié.")
            local_instructions = input_payload.get("local_instructions", [])
            acceptance_criteria = input_payload.get("acceptance_criteria", [])
            assigned_skill = input_payload.get("assigned_skill")
            
            input_artifacts_content = input_payload.get("input_artifacts_content", {})

        except json.JSONDecodeError as e:
            self.logger.error(f"TestingAgent: Input JSON invalide: {input_data_str}. Erreur: {e}")
            return json.dumps({
                "test_status": "error", "summary": "Input JSON invalide pour TestingAgent", 
                "details": input_data_str, "generated_test_cases": [], 
                "passed_criteria": [], "failed_criteria": [], "identified_issues_or_bugs": []
            })

        self.logger.info(f"TestingAgent - Tâche (Objectif: '{objective}', Compétence: {assigned_skill}) reçue (contexte: {context_id})")
        self.logger.debug(f"TestingAgent - Payload d'input complet reçu: {json.dumps(input_payload, indent=2)}")


        if assigned_skill == AGENT_SKILL_TEST_CASE_GENERATION:
            self.logger.info(f"TestingAgent: Mode '{AGENT_SKILL_TEST_CASE_GENERATION}' pour l'objectif: '{objective}'")
            feature_spec_content = input_artifacts_content.get("feature_spec_id", "")
            
            base_prompt = get_base_prompt("testing_agent_tcg")
            system_prompt_tcg = build_generic_system_prompt(
                base_prompt,
                self.tool_registry.get_metadata_for_tools(self.tool_registry.tools.keys())
            )
            prompt_tcg = (
                f"Objectif de la fonctionnalité pour laquelle générer des cas de test : {objective}\n\n"
                f"Instructions spécifiques pour la fonctionnalité (si fournies dans l'objectif) :\n"
                f"{'- ' + chr(10) + '- '.join(local_instructions) if local_instructions else 'Basé sur l objectif général.'}\n\n"
                f"Critères d'acceptation de la fonctionnalité (que les tests devront vérifier) :\n"
                f"{'- ' + chr(10) + '- '.join(acceptance_criteria) if acceptance_criteria else 'Basé sur l objectif général.'}\n\n"
            )
            if feature_spec_content:
                prompt_tcg += f"Spécifications/Code de la fonctionnalité à considérer pour la génération des tests:\n```\n{feature_spec_content}\n```\n\n"

            prompt_tcg += (
                "Génère une liste de cas de test. Chaque cas de test doit être une description actionnable. "
                "Retourne ta réponse UNIQUEMENT sous la forme d'un objet JSON avec une seule clé : "
                "'generated_test_cases' (une liste de strings)."
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
            
            base_prompt = get_base_prompt("testing_agent_st")
            system_prompt_st = build_generic_system_prompt(
                base_prompt,
                self.tool_registry.get_metadata_for_tools(self.tool_registry.tools.keys())
            )
            prompt_st = (
                f"Objectif du développement qui a produit ce livrable : {objective}\n\n"
                f"Critères d'acceptation généraux de la tâche de test actuelle :\n"
                f"{'- ' + chr(10) + '- '.join(acceptance_criteria) if acceptance_criteria else 'Non spécifiés.'}\n\n"
                f"{test_cases_prompt_section}"
                f"Livrable de code à tester :\n"
                f"```python\n{deliverable_code}\n```\n\n"
                "Ta mission est d'analyser rigoureusement le 'Livrable de code à tester'.\n"
                "1. Évalue si le code respecte les 'Critères d'acceptation généraux'.\n"
                "2. Si des 'Cas de test spécifiques' sont fournis, évalue le code par rapport à CHACUN d'eux. Indique clairement pour chaque cas de test spécifique s'il passe ou échoue, et pourquoi.\n"
                "3. Identifie les bugs ou les non-conformités.\n"
                "Retourne ton évaluation UNIQUEMENT sous forme d'un objet JSON avec les clés suivantes : "
                "'test_status' ('passed', 'failed', ou 'partial_success' - basé sur l'ensemble), "
                "'summary' (un résumé global), "
                "'acceptance_criteria_status': {{'passed': [liste des critères généraux passés], 'failed': [liste des critères généraux échoués]}}, "
                "'specific_test_cases_results': [{{'test_case': 'description du cas de test fourni', 'status': 'passed'/'failed', 'details': 'explication si failed'}}] (une liste, vide si aucun cas de test spécifique n'a été fourni), "
                "et 'identified_issues_or_bugs' (liste de descriptions des problèmes ou bugs)."
            )

            try:
                llm_response_str = await call_llm(prompt_st, system_prompt_st, json_mode=True) 
                test_report = json.loads(llm_response_str)
                if not all(k in test_report for k in ["test_status", "summary"]):
                    self.logger.error(f"Rapport de test LLM malformé: {test_report}")
                    raise ValueError("Le rapport de test du LLM n'a pas la structure attendue.")
                self.logger.info(f"TestingAgent (software_testing) - Rapport de test généré: {test_report.get('test_status')}, Summary: {test_report.get('summary')}")
                return json.dumps(test_report, ensure_ascii=False)

            except Exception as e:
                self.logger.error(f"TestingAgent (software_testing) - Échec: {e}", exc_info=True)
                return json.dumps({
                    "test_status": "error", "summary": f"Erreur lors de la génération du rapport de test: {str(e)}",
                    "passed_criteria": [], "failed_criteria": acceptance_criteria,
                    "identified_issues_or_bugs": [f"Erreur interne de l'agent de test: {str(e)}"]
                })
        else:
            self.logger.warning(f"TestingAgent: Compétence assignée '{assigned_skill}' non reconnue ou non gérée explicitement pour l'objectif: '{objective}'")
            return json.dumps({
                "test_status": "error", "summary": f"Compétence '{assigned_skill}' non gérée par TestingAgent.",
                "generated_test_cases": [], 
                "passed_criteria": [], "failed_criteria": acceptance_criteria, "identified_issues_or_bugs": []
            })
