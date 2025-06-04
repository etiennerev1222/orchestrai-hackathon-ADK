# src/agents/testing_agent/logic.py
import logging
import json
from typing import Dict, Any, Tuple # Ajout de Tuple

from src.shared.base_agent_logic import BaseAgentLogic
from src.shared.llm_client import call_llm

logger = logging.getLogger(__name__)
if not logger.hasHandlers():
    logging.basicConfig(level=logging.INFO)

# Compétences que cet agent fournira
AGENT_SKILL_SOFTWARE_TESTING = "software_testing"
AGENT_SKILL_TEST_CASE_GENERATION = "test_case_generation" # Pourrait être une compétence séparée


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
            assigned_skill = input_payload.get("assigned_skill") # Récupérer la compétence assignée

        except json.JSONDecodeError as e: # Garder la gestion d'erreur pour l'input initial
            self.logger.error(f"TestingAgent: Input JSON invalide: {input_data_str}. Erreur: {e}")
            return json.dumps({"test_status": "error", "summary": "Input JSON invalide pour TestingAgent", "details": input_data_str})

        self.logger.info(f"TestingAgent - Tâche (Objectif: '{objective}', Compétence: {assigned_skill}) reçue (contexte: {context_id})")

        if assigned_skill == AGENT_SKILL_TEST_CASE_GENERATION:
            self.logger.info(f"TestingAgent: Mode 'test_case_generation' pour l'objectif: '{objective}'")
            # Pour la génération de cas de test, le "deliverable" est l'objectif/specs de la fonctionnalité à tester
            # Ce contenu devrait être dans 'objective', 'local_instructions', 'acceptance_criteria'
            system_prompt_tcg = (
                "Tu es un ingénieur QA expert en création de cas de test. "
                "Ta mission est de générer une suite de cas de test pertinents et exhaustifs (mais concis) "
                "basée sur un objectif, des instructions et des critères d'acceptation d'une fonctionnalité ou d'un module. "
                "Retourne les cas de test sous forme d'une liste de descriptions textuelles dans un objet JSON."
            )
            prompt_tcg = (
                f"Objectif de la fonctionnalité pour laquelle générer des cas de test : {objective}\n\n"
                f"Instructions spécifiques pour la fonctionnalité :\n"
                f"{'- ' + chr(10) + '- '.join(local_instructions) if local_instructions else 'Aucune instruction spécifique.'}\n\n"
                f"Critères d'acceptation de la fonctionnalité (que les tests devront vérifier) :\n"
                f"{'- ' + chr(10) + '- '.join(acceptance_criteria) if acceptance_criteria else 'Non spécifiés.'}\n\n"
                "Génère une liste de cas de test. Pour chaque cas de test, fournis une brève description de ce qu'il vérifie. "
                "Retourne ta réponse UNIQUEMENT sous la forme d'un objet JSON avec une seule clé : "
                "'generated_test_cases' (une liste de strings, chaque string étant un cas de test détaillé et actionnable)."
            )
            try:
                llm_response_tcg_str = await call_llm(prompt_tcg, system_prompt_tcg, json_mode=True)
                self.logger.info(f"TestingAgent (test_case_generation) - Cas de test générés (brut): {llm_response_tcg_str}")
                # Valider que la réponse est bien un JSON avec la clé attendue
                json.loads(llm_response_tcg_str) # Juste pour valider le JSON
                return llm_response_tcg_str 
            except Exception as e:
                self.logger.error(f"TestingAgent (test_case_generation) - Échec: {e}", exc_info=True)
                return json.dumps({
                    "error": f"Erreur LLM lors de la génération des cas de test: {str(e)}",
                    "generated_test_cases": []
                })
        
        elif assigned_skill == AGENT_SKILL_SOFTWARE_TESTING:
            
            self.logger.info(f"TestingAgent: Mode '{AGENT_SKILL_SOFTWARE_TESTING}' pour l'objectif: '{objective}'")
            
            # Utiliser les clés définies dans input_data_refs par le DecompositionAgent
            deliverable_code = input_payload.get("code_input") # ou "deliverable", selon ce que DecompositionAgent a mis
            test_cases_to_execute_str = input_payload.get("test_specifications") # ou "test_cases"

            if not deliverable_code:
                self.logger.warning(f"TestingAgent (software_testing): Livrable 'code_input' manquant pour l'objectif '{objective}'.")
                # ... (retourner une erreur structurée)
                return json.dumps({
                    "test_status": "error", 
                    "summary": "Livrable 'code_input' manquant pour l'exécution des tests.",
                    "passed_criteria": [], "failed_criteria": acceptance_criteria,
                    "identified_issues_or_bugs": ["Le contenu du code à tester n'a pas été fourni."]
                })

            system_prompt_st = (
                "Tu es un ingénieur QA expert et un testeur logiciel rigoureux. "
                "Ta mission est d'analyser un livrable de code fourni, ainsi qu'une liste de cas de test (si fournie), "
                "par rapport à son objectif, ses instructions de développement et ses critères d'acceptation. "
                "Tu dois déterminer si le livrable est conforme. Identifie les points de succès et les échecs ou bugs potentiels. "
                "Fournis un rapport de test concis au format JSON."
            )
            
            test_cases_prompt_section = ""

            if test_cases_to_execute_str :
                # S'assurer que c'est une chaîne pour le prompt, même si c'est une liste de cas de test
                formatted_test_cases = ""
                if isinstance(test_cases_to_execute_str , list):
                    formatted_test_cases = "\n- ".join(test_cases_to_execute_str)
                    if formatted_test_cases: formatted_test_cases = "- " + formatted_test_cases
                elif isinstance(test_cases_to_execute_str, str):
                     # Si c'est déjà une chaîne (par exemple, un JSON de cas de test de l'étape précédente)
                    try: # Essayons de le parser pour le formater joliment si c'est un JSON de la tâche TCG
                        parsed_tc_artifact = json.loads(test_cases_to_execute_str)
                        if "generated_test_cases" in parsed_tc_artifact and isinstance(parsed_tc_artifact["generated_test_cases"], list):
                            formatted_test_cases = "\n- ".join(parsed_tc_artifact["generated_test_cases"])
                            if formatted_test_cases: formatted_test_cases = "- " + formatted_test_cases
                        else: # Pas le format attendu, on le prend tel quel
                            formatted_test_cases = test_cases_to_execute_str
                    except json.JSONDecodeError: # Ce n'est pas un JSON, on le prend tel quel
                        formatted_test_cases = test_cases_to_execute_str
                
                if formatted_test_cases:
                    test_cases_prompt_section = (
                        "Cas de test à exécuter/vérifier (en plus des critères d'acceptation) :\n"
                        f"'''\n{formatted_test_cases}\n'''\n\n"
                    )


            if test_cases_to_execute_str:
                test_cases_prompt_section = (
                    "Cas de test à exécuter/vérifier (en plus des critères d'acceptation) :\n"
                    f"'''\n{test_cases_to_execute_str}\n'''\n\n" # S'assurer que c'est bien une string
                )

            prompt_st = (
                f"Objectif du développement qui a produit ce livrable : {objective}\n\n"
                f"Instructions qui ont guidé le développement :\n"
                f"{'- ' + chr(10) + '- '.join(local_instructions) if local_instructions else 'Aucune instruction spécifique.'}\n\n"
                f"Critères d'acceptation à vérifier :\n"
                f"{'- ' + chr(10) + '- '.join(acceptance_criteria) if acceptance_criteria else 'Non spécifiés.'}\n\n"
                f"{test_cases_prompt_section}"
                f"Livrable de code à tester :\n"
                f"```python\n{deliverable_code}\n```\n\n" # Supposer que c'est du Python, ou rendre plus générique
                "Analyse ce code. Détermine si les critères d'acceptation et les cas de test (si fournis) sont remplis. "
                "Identifie les bugs ou les non-conformités. "
                "Retourne ton évaluation UNIQUEMENT sous forme d'un objet JSON avec les clés suivantes : "
                "'test_status' ('passed', 'failed', ou 'partial_success'), "
                "'summary' (un résumé global de tes découvertes), "
                "'passed_criteria' (liste des critères d'acceptation qui sont validés), "
                "'failed_criteria' (liste des critères non validés), "
                "et 'identified_issues_or_bugs' (liste de descriptions des problèmes ou bugs trouvés, avec des suggestions de correction si possible)."
            )
            try:
                llm_response_str = await call_llm(prompt_st, system_prompt_st, json_mode=True) 
                # ... (validation et retour du rapport JSON comme avant) ...
                test_report = json.loads(llm_response_str)
                if not all(k in test_report for k in ["test_status", "summary"]):
                    self.logger.error(f"Rapport de test LLM malformé: {test_report}")
                    raise ValueError("Le rapport de test du LLM n'a pas la structure attendue.")
                self.logger.info(f"TestingAgent (software_testing) - Rapport de test généré: {test_report.get('test_status')}, Summary: {test_report.get('summary')}")
                return json.dumps(test_report, ensure_ascii=False)

            except Exception as e:
                # ... (gestion d'erreur comme avant) ...
                self.logger.error(f"TestingAgent (software_testing) - Échec: {e}", exc_info=True)
                return json.dumps({
                    "test_status": "error",
                    "summary": f"Erreur lors de la génération du rapport de test: {str(e)}",
                    "passed_criteria": [],
                    "failed_criteria": acceptance_criteria,
                    "identified_issues_or_bugs": [f"Erreur interne de l'agent de test: {str(e)}"]
                })
        else:
            self.logger.warning(f"TestingAgent: Compétence assignée '{assigned_skill}' non reconnue ou non gérée explicitement. Objectif: '{objective}'")
            return json.dumps({
                "test_status": "error",
                "summary": f"Compétence '{assigned_skill}' non gérée par le TestingAgent.",
                "passed_criteria": [], "failed_criteria": acceptance_criteria, "identified_issues_or_bugs": []
            })
