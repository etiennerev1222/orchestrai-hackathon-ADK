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

    async def process(self, input_data_str: str, context_id: str | None = None) -> str: # Retourne un JSON string
        """
        Évalue un livrable (ex: code) par rapport à des spécifications ou critères.
        L'input_data_str est attendu comme un JSON string contenant:
        - "objective": Description de ce que le livrable est censé faire.
        - "deliverable": Le contenu du livrable (ex: le code source).
        - "local_instructions": Instructions qui ont guidé la création du livrable.
        - "acceptance_criteria": Les critères pour valider le livrable.
        Retourne un rapport de test structuré en JSON.
        """
        try:
            input_payload = json.loads(input_data_str)
            objective = input_payload.get("objective", "Objectif du test non spécifié.")
            deliverable_content = input_payload.get("deliverable", "") # Le code ou le document à tester
            local_instructions = input_payload.get("local_instructions", [])
            acceptance_criteria = input_payload.get("acceptance_criteria", [])
        except json.JSONDecodeError:
            self.logger.error(f"TestingAgent: Input JSON invalide: {input_data_str}")
            return json.dumps({
                "test_status": "error", 
                "summary": "Input JSON invalide pour TestingAgent",
                "details": input_data_str
            })

        self.logger.info(f"TestingAgent - Test pour l'objectif (contexte: {context_id}): '{objective}'")
        self.logger.debug(f"Livrable à tester (début): {deliverable_content[:200]}...")
        self.logger.debug(f"Critères d'acceptation pour le test: {acceptance_criteria}")

        system_prompt = (
            "Tu es un ingénieur QA expert et un testeur logiciel rigoureux. "
            "Ta mission est d'analyser un livrable (généralement du code source) "
            "par rapport à son objectif, ses instructions de développement et ses critères d'acceptation. "
            "Tu dois déterminer si le livrable est conforme. Identifie les points de succès et les échecs ou bugs potentiels. "
            "Fournis un rapport de test concis au format JSON."
        )
        
        prompt = (
            f"Objectif du développement qui a produit ce livrable : {objective}\n\n"
            f"Instructions qui ont guidé le développement :\n"
            f"{'- ' + chr(10) + '- '.join(local_instructions) if local_instructions else 'Aucune instruction spécifique.'}\n\n"
            f"Critères d'acceptation à vérifier :\n"
            f"{'- ' + chr(10) + '- '.join(acceptance_criteria) if acceptance_criteria else 'Non spécifiés.'}\n\n"
            f"Livrable à tester :\n"
            f"```\n{deliverable_content}\n```\n\n"
            "Analyse ce livrable. Détermine si les critères d'acceptation sont remplis. "
            "Identifie les bugs ou les non-conformités. "
            "Retourne ton évaluation sous forme d'un objet JSON avec les clés suivantes : "
            "'test_status' ('passed', 'failed', ou 'partial_success'), "
            "'summary' (un résumé global de tes découvertes), "
            "'passed_criteria' (liste des critères d'acceptation qui sont validés), "
            "'failed_criteria' (liste des critères non validés), "
            "et 'identified_issues_or_bugs' (liste de descriptions des problèmes ou bugs trouvés, avec des suggestions de correction si possible)."
        )

        try:
            # On attend un JSON structuré du LLM
            llm_response_str = await call_llm(prompt, system_prompt, json_mode=True) 
            test_report = json.loads(llm_response_str)
            
            # Validation basique du rapport de test
            if not all(k in test_report for k in ["test_status", "summary"]):
                self.logger.error(f"Rapport de test LLM malformé: {test_report}")
                raise ValueError("Le rapport de test du LLM n'a pas la structure attendue.")

            self.logger.info(f"TestingAgent - Rapport de test généré: {test_report.get('test_status')}, Summary: {test_report.get('summary')}")
            return json.dumps(test_report, ensure_ascii=False) # Retourner le rapport JSON comme une chaîne

        except Exception as e:
            self.logger.error(f"TestingAgent - Échec de la génération du rapport de test: {e}", exc_info=True)
            return json.dumps({
                "test_status": "error",
                "summary": f"Erreur lors de la génération du rapport de test: {str(e)}",
                "passed_criteria": [],
                "failed_criteria": acceptance_criteria, # Marquer tous comme échoués par défaut
                "identified_issues_or_bugs": [f"Erreur interne de l'agent de test: {str(e)}"]
            })