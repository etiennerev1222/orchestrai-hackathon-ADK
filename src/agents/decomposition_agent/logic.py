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
        """
        Décompose un plan textuel de TEAM 1 en une structure JSON globale.
        L'input_data_str est attendu comme un JSON string contenant :
        {
            "team1_plan_text": "Le plan à décomposer...",
            "available_execution_skills": ["skill1", "skill2", ...]
        }
        Retourne un dictionnaire Python prêt à être sérialisé en JSON.
        """
        self.logger.info(f"DecompositionAgent - Reçu input_data_str (contexte: {context_id}): '{input_data_str[:300]}...'")

        try:
            input_payload = json.loads(input_data_str)
            team1_plan_text = input_payload.get("team1_plan_text")
            available_skills_list = input_payload.get("available_execution_skills", [])
        except json.JSONDecodeError as e:
            self.logger.error(f"DecompositionAgent: Input JSON invalide: {input_data_str}. Erreur: {e}")
            return {"error": "Input JSON invalide pour DecompositionAgent", "details": input_data_str}
        except AttributeError: # Si input_data_str n'est pas un string (ex: déjà un dict par erreur)
            self.logger.error(f"DecompositionAgent: input_data_str n'est pas une chaîne JSON. Reçu type: {type(input_data_str)}")
            return {"error": "Format d'input incorrect, attendu une chaîne JSON."}


        if not team1_plan_text:
            self.logger.warning("Texte du plan de TEAM 1 vide, aucune décomposition possible.")
            return {
                "global_context": "Plan de TEAM 1 vide fourni à l'agent de décomposition.",
                "instructions": ["Aucune instruction car plan vide."],
                "tasks": []
            }
        
        # Préparer la chaîne des compétences pour le prompt
        if available_skills_list and all(isinstance(s, str) for s in available_skills_list):
            skills_string = ", ".join([f"'{s}'" for s in available_skills_list])
        else:
            self.logger.warning(f"Liste des compétences disponibles non fournie ou mal formatée, utilisation d'une liste par défaut pour le prompt. Reçu: {available_skills_list}")
            # Fallback si la liste de compétences n'est pas passée ou est malformée
            default_skills = ["coding_python", "web_research", "software_testing", "document_synthesis", "general_analysis", "database_design"]
            skills_string = ", ".join([f"'{s}'" for s in default_skills])


        system_prompt = (
            "Tu es un chef de projet senior expert en décomposition de plans complexes en tâches actionnables et granulaires. "
            "Ton rôle est de prendre un plan de projet détaillé (rédigé en langage naturel) et de le transformer en un objet JSON structuré. "
            "Cet objet JSON DOIT avoir les clés racine suivantes et uniquement celles-ci : 'global_context' (string), 'instructions' (array of string), et 'tasks' (array of task objects).\n"
            "Le 'global_context' doit être un résumé concis du plan original.\n"
            "Les 'instructions' globales peuvent être une liste vide [] si aucune instruction de haut niveau ne s'applique à toutes les tâches.\n"
            "La clé 'tasks' doit contenir une liste d'objets tâche.\n"
            "Pour chaque tâche dans la liste 'tasks' (et pour chaque tâche dans 'sous_taches'), tu dois fournir EXACTEMENT les clés suivantes :\n"
            "- 'id': un identifiant textuel unique et court pour la tâche (ex: 'T01', 'T02.1'). Utilise une numérotation logique.\n"
            "- 'nom': un nom court et descriptif pour la tâche (max 10 mots).\n"
            "- 'description': une description détaillée de ce que la tâche doit accomplir.\n"
            "- 'type': une chaîne de caractères choisie EXACTEMENT parmi 'executable', 'exploratory', ou 'container'.\n"
            "- 'dependances': une liste de chaînes de caractères (peut être vide []), contenant les 'id' des autres tâches (que tu as définies dans la même liste 'tasks' ou 'sous_taches' parente) dont cette tâche dépend directement.\n"
            "- 'instructions_locales': une liste de chaînes de caractères (peut être vide []) détaillant les étapes ou consignes spécifiques pour réaliser cette tâche.\n"
            "- 'acceptance_criteria': une liste de chaînes de caractères (peut être vide []) décrivant les conditions claires pour considérer la tâche comme terminée avec succès.\n"
            f"- 'assigned_agent_type': une chaîne de caractères choisie EXACTEMENT parmi la liste suivante de compétences disponibles : [{skills_string}]. Choisis la compétence la plus pertinente. Si aucune ne correspond parfaitement, choisis 'general_analysis'.\n"
            "- 'sous_taches': une liste (peut être vide []) d'objets tâche imbriqués, suivant EXACTEMENT la même structure que les tâches principales (incluant toutes les clés mentionnées ci-dessus).\n"
            "Assure-toi que la réponse est UNIQUEMENT l'objet JSON global structuré comme demandé, sans aucun texte, explication ou formatage en dehors de l'objet JSON lui-même."
        )
        
        prompt = (
            f"Voici le plan détaillé (qui servira de base pour le 'global_context') à décomposer :\n\n"
            f"'''{team1_plan_text}'''\n\n"
            f"Les compétences d'agent que tu DOIS utiliser pour le champ 'assigned_agent_type' sont : [{skills_string}].\n"
            "Génère l'objet JSON structuré comme décrit dans les instructions système. "
            "N'invente pas de nouvelles valeurs pour le champ 'type' ou 'assigned_agent_type' autres que celles explicitement autorisées."
        )

        try:
            self.logger.debug(f"DecompositionAgentLogic - Prompt Système LLM:\n{system_prompt}")
            self.logger.debug(f"DecompositionAgentLogic - Prompt Utilisateur LLM:\n{prompt}")
            llm_response_str = await call_llm(prompt, system_prompt, json_mode=True)
            self.logger.debug(f"DecompositionAgentLogic - Réponse brute du LLM: {llm_response_str}")
            
            decomposed_plan_json = json.loads(llm_response_str)
            
            if not isinstance(decomposed_plan_json, dict) or \
               not all(k in decomposed_plan_json for k in ["global_context", "instructions", "tasks"]) or \
               not isinstance(decomposed_plan_json.get("tasks"), list):
                self.logger.error(f"La réponse du LLM n'a pas la structure principale attendue. Réponse: {decomposed_plan_json}")
                # Essayer de retourner une structure d'erreur minimale conforme au format global attendu par le superviseur
                return {
                    "global_context": "Erreur de décomposition.", 
                    "instructions": ["Le LLM n'a pas retourné la structure JSON attendue."],
                    "tasks": [{"id": "error_task", "nom": "Erreur LLM", "description": f"Réponse LLM incorrecte: {llm_response_str}", "type": "exploratory", "dependances": [], "instructions_locales": [], "acceptance_criteria": [], "assigned_agent_type": "general_analysis", "sous_taches": [] }],
                    "error": "LLM response structure incorrect."
                }

            self.logger.info(f"DecompositionAgent - Plan décomposé reçu du LLM. Nombre de tâches principales: {len(decomposed_plan_json.get('tasks', []))}")
            return decomposed_plan_json

        except json.JSONDecodeError as e:
            self.logger.error(f"Impossible de parser la réponse JSON du LLM pour la décomposition: {e}. Réponse brute: '{llm_response_str}'")
            return {
                "global_context": "Erreur de décomposition.", 
                "instructions": ["La réponse du LLM n'était pas un JSON valide."],
                "tasks": [{"id": "error_task_json", "nom": "Erreur JSON LLM", "description": f"JSON Invalide: {llm_response_str}", "type": "exploratory", "dependances": [], "instructions_locales": [], "acceptance_criteria": [], "assigned_agent_type": "general_analysis", "sous_taches": [] }],
                "error": "Invalid JSON response from LLM", 
                "raw_response": llm_response_str
            }
        except Exception as e:
            self.logger.error(f"Échec de la décomposition par le LLM: {e}", exc_info=True)
            return {
                "global_context": "Erreur de décomposition.", 
                "instructions": [f"Erreur interne lors de l'appel LLM: {str(e)}"],
                "tasks": [{"id": "error_task_llm_call", "nom": "Erreur Appel LLM", "description": f"Échec appel LLM: {str(e)}", "type": "exploratory", "dependances": [], "instructions_locales": [], "acceptance_criteria": [], "assigned_agent_type": "general_analysis", "sous_taches": [] }],
                "error": f"LLM processing failed: {e}"
            }