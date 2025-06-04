# src/agents/research_agent/logic.py
import logging
import json
from typing import Dict, Any, List 
import uuid # Assurez-vous qu'il est importé si vous générez des ID locaux

from src.shared.base_agent_logic import BaseAgentLogic
from src.shared.llm_client import call_llm

logger = logging.getLogger(__name__)
if not logger.hasHandlers():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

AGENT_SKILL_GENERAL_ANALYSIS = "general_analysis"
AGENT_SKILL_WEB_RESEARCH = "web_research"
AGENT_SKILL_DOCUMENT_SYNTHESIS = "document_synthesis"

class ResearchAgentLogic(BaseAgentLogic):
    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(f"{__name__}.ResearchAgentLogic")
        self.logger.info("Logique du ResearchAgent initialisée.")

    async def process(self, input_data_str: str, context_id: str | None = None) -> str:
        try:
            input_payload = json.loads(input_data_str)
            objective = input_payload.get("objective", "Objectif de recherche non spécifié.")
            local_instructions = input_payload.get("local_instructions", [])
            acceptance_criteria = input_payload.get("acceptance_criteria", [])
            # Récupérer les compétences disponibles si elles sont passées
            available_skills_list = input_payload.get("available_execution_skills", []) 
            task_type_for_agent = input_payload.get("task_type", "exploratory") # Le type de la tâche actuelle
            
        except json.JSONDecodeError as e:
            self.logger.error(f"ResearchAgent: Input JSON invalide: {input_data_str}. Erreur: {e}")
            return json.dumps({"error": "Input JSON invalide pour ResearchAgent", "details": input_data_str})
        except AttributeError:
            self.logger.error(f"ResearchAgent: input_data_str n'est pas une chaîne JSON. Reçu type: {type(input_data_str)}")
            return json.dumps({"error": "Format d'input incorrect, attendu une chaîne JSON."})


        self.logger.info(f"ResearchAgent - Tâche ({task_type_for_agent}) à traiter (contexte: {context_id}): '{objective}'")
        self.logger.debug(f"Instructions locales: {local_instructions}")
        self.logger.debug(f"Critères d'acceptation: {acceptance_criteria}")
        self.logger.debug(f"Compétences d'exécution disponibles pour suggestion de sous-tâches: {available_skills_list}")

        skills_string_for_prompt = ", ".join([f"'{s}'" for s in available_skills_list]) if available_skills_list else "la liste fournie par le superviseur"
        if not available_skills_list: # Fallback si la liste est vide
            default_skills = ["coding_python", "web_research", "software_testing", "document_synthesis", "general_analysis", "database_design"]
            skills_string_for_prompt = ", ".join([f"'{s}'" for s in default_skills])


        system_prompt = (
            "Tu es un assistant de recherche et d'analyse IA expert. Ta mission est d'exécuter des tâches exploratoires ou d'analyse. "
            "Tu dois fournir un résumé de tes découvertes ou de ton analyse. "
            "Si la nature de la tâche exploratoire ('exploratory') implique la définition de nouvelles sous-tâches pour atteindre l'objectif initial, "
            "tu DOIS les proposer. Pour les tâches non exploratoires, tu ne génères généralement pas de nouvelles sous-tâches.\n"
            "Ta réponse DOIT être un objet JSON unique avec DEUX clés racine OBLIGATOIRES : 'summary' (string) et 'new_sub_tasks' (array of task objects).\n"
            "La clé 'new_sub_tasks' doit être une liste vide [] si aucune nouvelle sous-tâche n'est nécessaire ou si la tâche n'est pas de type 'exploratory' et ne justifie pas de décomposition.\n"
            "Si tu génères des 'new_sub_tasks', chaque objet tâche dans la liste DOIT avoir EXACTEMENT les clés suivantes:\n"
            "- 'id': un identifiant textuel local unique et court pour la sous-tâche (ex: 'sub_T01', 'sub_T02a').\n"
            "- 'nom': un nom court et descriptif.\n"
            "- 'description': une description détaillée.\n"
            "- 'type': 'executable', 'exploratory', ou 'container'.\n"
            "- 'dependances': une liste vide [], car ces sous-tâches dépendront implicitement de la tâche exploratoire parente (gérée par le superviseur).\n"
            "- 'instructions_locales': liste de strings.\n"
            "- 'acceptance_criteria': liste de strings.\n"
            f"- 'assigned_agent_type': une chaîne de caractères choisie EXACTEMENT parmi la liste suivante de compétences disponibles : [{skills_string_for_prompt}]. Choisis la plus pertinente. Si aucune ne correspond parfaitement, choisis 'general_analysis'.\n"
            "- 'sous_taches': une liste vide [], car la décomposition s'arrête à ce niveau pour les tâches que tu génères.\n"
            "Fournis UNIQUEMENT l'objet JSON, sans texte ou explication en dehors."
        )
        
        prompt = (
            f"Objectif de la tâche actuelle ({task_type_for_agent}) : {objective}\n\n"
            f"Instructions spécifiques pour cette tâche : {', '.join(local_instructions) if local_instructions else 'Aucune'}\n\n"
            f"Critères d'acceptation pour cette tâche : {', '.join(acceptance_criteria) if acceptance_criteria else 'Non spécifiés'}\n\n"
            f"Si cette tâche est de type 'exploratory' et que ton analyse révèle des étapes concrètes supplémentaires nécessaires, "
            f"décris-les dans 'new_sub_tasks' en utilisant les compétences disponibles pour 'assigned_agent_type': [{skills_string_for_prompt}]. "
            "Sinon, ou si la tâche n'est pas de type 'exploratory' et ne nécessite pas de décomposition, laisse 'new_sub_tasks' comme une liste vide [].\n"
            "Dans tous les cas, fournis un 'summary' de ton travail pour la tâche actuelle.\n"
            "Réponds UNIQUEMENT avec l'objet JSON spécifié."
        )

        try:
            self.logger.debug(f"ResearchAgentLogic - Prompt Système LLM:\n{system_prompt}")
            self.logger.debug(f"ResearchAgentLogic - Prompt Utilisateur LLM:\n{prompt}")
            llm_response_str = await call_llm(prompt, system_prompt, json_mode=True)
            self.logger.debug(f"ResearchAgentLogic - Réponse brute du LLM: {llm_response_str}")

            # Valider la structure de la réponse JSON du LLM
            try:
                llm_json_output = json.loads(llm_response_str)
                if not isinstance(llm_json_output, dict) or \
                   "summary" not in llm_json_output or \
                   "new_sub_tasks" not in llm_json_output or \
                   not isinstance(llm_json_output["new_sub_tasks"], list):
                    self.logger.error(f"Réponse LLM pour ResearchAgent n'a pas la structure attendue (summary, new_sub_tasks): {llm_json_output}")
                    # Retourner une erreur structurée
                    return json.dumps({
                        "summary": "Erreur: La réponse du LLM n'a pas la structure JSON attendue.",
                        "new_sub_tasks": [],
                        "error": "LLM response structure incorrect."
                    })
                # Ici, la structure est correcte, on peut la retourner directement (sérialisée en string)
                self.logger.info(f"ResearchAgent - Résultat traité. Summary: '{llm_json_output.get('summary')[:100]}...'. Nombre de nouvelles sous-tâches: {len(llm_json_output.get('new_sub_tasks',[]))}")
                return json.dumps(llm_json_output, ensure_ascii=False)

            except json.JSONDecodeError as e:
                self.logger.error(f"Impossible de parser JSON du LLM pour ResearchAgent: {e}. Réponse: '{llm_response_str}'")
                return json.dumps({
                    "summary": "Erreur: La réponse du LLM n'était pas un JSON valide.",
                    "new_sub_tasks": [],
                    "error": "Invalid JSON response from LLM", 
                    "raw_response": llm_response_str
                })

        except Exception as e:
            self.logger.error(f"ResearchAgent - Échec du traitement: {e}", exc_info=True)
            return json.dumps({
                "summary": f"Erreur interne lors du traitement par ResearchAgent: {str(e)}",
                "new_sub_tasks": [],
                "error": f"LLM processing or internal error: {str(e)}"
            })