# src/agents/decomposition_agent/logic.py
import logging
import json
from typing import Dict, Any, List # Retrait de Tuple qui n'est plus utilisé ici

from src.shared.base_agent_logic import BaseAgentLogic
from src.shared.llm_client import call_llm
import uuid # Ajouté pour les ID locaux si l'agent en génère

logger = logging.getLogger(__name__)
if not logger.hasHandlers(): # S'assurer que le logger de module a un handler
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

AGENT_SKILL_DECOMPOSE_EXECUTION_PLAN = "execution_plan_decomposition"

class DecompositionAgentLogic(BaseAgentLogic):
    def __init__(self):
        super().__init__()
        # Utiliser self.logger pour les logs d'instance pour une meilleure traçabilité
        self.logger = logging.getLogger(f"{__name__}.DecompositionAgentLogic")
        self.logger.info("Logique du DecompositionAgent initialisée.")


    async def process(self, input_data_str: str, context_id: str | None = None) -> Dict[str, Any]:
        # ... (parsing de input_data_str pour obtenir team1_plan_text et available_skills_list comme avant) ...
        self.logger.info(f"DecompositionAgent - Reçu input_data_str (contexte: {context_id}): '{input_data_str[:300]}...'")

        try:
            input_payload = json.loads(input_data_str)
            team1_plan_text = input_payload.get("team1_plan_text") or input_payload.get("plan_text")
            available_skills_list = input_payload.get("available_execution_skills", [])
        except (json.JSONDecodeError, TypeError) as e:
            # Autoriser un mode plus simple où input_data_str est directement le plan texte
            self.logger.warning(
                "DecompositionAgent: input_data_str n'est pas un JSON valide, traitement comme texte brut"
            )
            team1_plan_text = input_data_str if isinstance(input_data_str, str) else str(input_data_str)
            available_skills_list = []


        if not team1_plan_text:
            # ... (gestion plan vide existante) ...
            self.logger.warning("Texte du plan de TEAM 1 vide, aucune décomposition possible.")
            return {
                "global_context": "Plan de TEAM 1 vide fourni à l'agent de décomposition.",
                "instructions": ["Aucune instruction car plan vide."],
                "tasks": []
            }
        
        if available_skills_list and all(isinstance(s, str) for s in available_skills_list):
            skills_string = ", ".join([f"'{s}'" for s in available_skills_list])
        else:
            self.logger.warning(f"Liste des compétences disponibles non fournie ou mal formatée, utilisation d'une liste par défaut pour le prompt. Reçu: {available_skills_list}")
            default_skills = ["coding_python", "web_research", "software_testing", "document_synthesis", "general_analysis", "database_design", "test_case_generation"] # Ajout de test_case_generation
            skills_string = ", ".join([f"'{s}'" for s in default_skills])
            available_skills_list = default_skills # S'assurer que la liste utilisée plus bas est à jour


        system_prompt = (
            "Tu es un chef de projet expert en décomposition de plans en tâches granulaires et structurées. "
            "Ton rôle est de prendre un plan de projet détaillé et de le transformer en un objet JSON structuré. "
            "Cet objet JSON DOIT avoir les clés racine suivantes et uniquement celles-ci : 'global_context' (string), 'instructions' (array of string), et 'tasks' (array of task objects).\n"
            "Pour chaque tâche dans la liste 'tasks' (et pour chaque tâche dans 'sous_taches'), tu dois fournir EXACTEMENT les clés suivantes :\n"
            "- 'id': un identifiant textuel local unique et court (ex: 'T01', 'T02.1').\n"
            "- 'nom': un nom court et descriptif.\n"
            "- 'description': une description détaillée.\n"
            "- 'type': 'executable', 'exploratory', ou 'container'.\n"
            "- 'dependances': une liste d'IDs locaux des tâches dont cette tâche dépend directement. Si une tâche d'exécution de tests (ex: avec compétence 'software_testing') dépend de code ET de cas de tests, elle doit lister les IDs des tâches ayant produit ces deux éléments.\n"
            "- 'instructions_locales': liste de strings.\n"
            "- 'acceptance_criteria': liste de strings.\n"
            f"- 'assigned_agent_type': une chaîne de caractères choisie EXACTEMENT parmi la liste suivante de compétences disponibles : [{skills_string}]. Choisis la plus pertinente. Si aucune ne correspond parfaitement, choisis 'general_analysis'.\n"
            "- 'input_data_refs': un dictionnaire optionnel (peut être omis ou vide {}). Si une tâche a besoin de l'artefact d'une tâche précédente comme input nommé, utilise ce champ. Par exemple, pour une tâche qui exécute des tests, tu pourrais avoir : `\"input_data_refs\": {\"code_to_test\": \"ID_TACHE_CODE\", \"test_cases_file\": \"ID_TACHE_GEN_TESTS\"}`. Les valeurs sont les 'id' locaux d'autres tâches.\n"
            "- 'sous_taches': une liste vide [] ou une liste d'objets tâche imbriqués, suivant la même structure.\n"
            "Assure-toi que la réponse est UNIQUEMENT l'objet JSON global."
        )
        
        prompt = (
            f"Voici le plan détaillé à décomposer :\n\n"
            f"'''{team1_plan_text}'''\n\n"
            f"Les compétences d'agent que tu DOIS utiliser pour 'assigned_agent_type' sont : [{skills_string}].\n"
            "Pour les tâches d'exécution de tests (généralement assignées à 'software_testing'), si elles nécessitent à la fois du code et des cas de test, assure-toi que leurs 'dependances' incluent les IDs locaux des tâches qui produisent le code et celles qui produisent les cas de test. "
            "De plus, pour de telles tâches, utilise 'input_data_refs' pour spécifier comment les artefacts des dépendances doivent être nommés en entrée. L'entrée contenant le code à tester DOIT s'appeler 'code_to_test'. Par exemple : `\"input_data_refs\": {\"code_to_test\": \"ID_TACHE_DEV\", \"test_specifications\": \"ID_TACHE_GEN_CAS_TEST\"}`. Adapte les autres noms de clés si besoin.\n"
            "Génère l'objet JSON structuré comme décrit. Sois rigoureux sur le format JSON et les types de données.\n"
            "L'objet JSON global doit avoir les clés 'global_context', 'instructions', et 'tasks'."
        )

        try:
            # ... (logique d'appel LLM et de parsing JSON existante) ...
            self.logger.debug(f"DecompositionAgentLogic - Prompt Système LLM:\n{system_prompt}")
            self.logger.debug(f"DecompositionAgentLogic - Prompt Utilisateur LLM:\n{prompt}")
            llm_response_str = await call_llm(prompt, system_prompt, json_mode=True)
            self.logger.debug(f"DecompositionAgentLogic - Réponse brute du LLM: {llm_response_str}")
            
            decomposed_plan_json = json.loads(llm_response_str)
            
            if not isinstance(decomposed_plan_json, dict) or \
               not all(k in decomposed_plan_json for k in ["global_context", "instructions", "tasks"]) or \
               not isinstance(decomposed_plan_json.get("tasks"), list):
                self.logger.error(f"La réponse du LLM n'a pas la structure principale attendue. Réponse: {decomposed_plan_json}")
                return {
                    "global_context": "Erreur de décomposition.", 
                    "instructions": ["Le LLM n'a pas retourné la structure JSON attendue."],
                    "tasks": [{"id": "error_task", "nom": "Erreur LLM", "description": f"Réponse LLM incorrecte: {llm_response_str}", "type": "exploratory", "dependances": [], "instructions_locales": [], "acceptance_criteria": [], "assigned_agent_type": "general_analysis", "sous_taches": [], "input_data_refs": {}}],
                    "error": "LLM response structure incorrect."
                }

            self.logger.info(f"DecompositionAgent - Plan décomposé reçu du LLM. Nombre de tâches principales: {len(decomposed_plan_json.get('tasks', []))}")
            return decomposed_plan_json

        except json.JSONDecodeError as e:
            self.logger.error(f"Impossible de parser la réponse JSON du LLM pour la décomposition: {e}. Réponse brute: '{llm_response_str}'")
            return {
                "global_context": "Erreur de décomposition.", 
                "instructions": ["La réponse du LLM n'était pas un JSON valide."],
                "tasks": [{"id": "error_task_json", "nom": "Erreur JSON LLM", "description": f"JSON Invalide: {llm_response_str}", "type": "exploratory", "dependances": [], "instructions_locales": [], "acceptance_criteria": [], "assigned_agent_type": "general_analysis", "sous_taches": [], "input_data_refs": {}}],
                "error": "Invalid JSON response from LLM", 
                "raw_response": llm_response_str
            }
        except Exception as e:
            self.logger.error(f"Échec de la décomposition par le LLM: {e}", exc_info=True)
            return {
                "global_context": "Erreur de décomposition.", 
                "instructions": [f"Erreur interne lors de l'appel LLM: {str(e)}"],
                "tasks": [{"id": "error_task_llm_call", "nom": "Erreur Appel LLM", "description": f"Échec appel LLM: {str(e)}", "type": "exploratory", "dependances": [], "instructions_locales": [], "acceptance_criteria": [], "assigned_agent_type": "general_analysis", "sous_taches": [], "input_data_refs": {}}],
                "error": f"LLM processing failed: {e}"
            }
