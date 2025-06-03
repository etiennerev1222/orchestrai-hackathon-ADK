# src/agents/decomposition_agent/logic.py
import logging
import json
from typing import Dict, Any, List

from src.shared.base_agent_logic import BaseAgentLogic
from src.shared.llm_client import call_llm
# from src.shared.execution_task_graph_management import ExecutionTaskType # Moins pertinent ici car on attend le JSON

logger = logging.getLogger(__name__)

AGENT_SKILL_DECOMPOSE_EXECUTION_PLAN = "execution_plan_decomposition"

class DecompositionAgentLogic(BaseAgentLogic):
    def __init__(self):
        super().__init__()
        logger.info("Logique du DecompositionAgent initialisée.")

    async def process(self, team1_plan_text: str, context_id: str | None = None) -> Dict[str, Any]: # Changement : retourne un Dict (le JSON global)
        """
        Décompose un plan textuel de TEAM 1 en une structure JSON globale
        contenant un contexte, des instructions et une liste de tâches structurées.
        La sortie est un dictionnaire Python prêt à être sérialisé en JSON par l'executor.
        """
        logger.info(f"DecompositionAgent - Plan à décomposer (contexte: {context_id}): '{team1_plan_text[:200]}...'")

        # input_data_str pourrait maintenant être un JSON contenant team1_plan_text ET available_skills
        try:
            input_payload = json.loads(team1_plan_text) # Supposer que l'input est maintenant un JSON
            team1_plan_text = input_payload.get("team1_plan_text", "")
            available_skills_list = input_payload.get("available_execution_skills", [])
        except json.JSONDecodeError:
            # Gérer l'erreur si l'input n'est pas le JSON attendu
            logger.error("Input pour DecompositionAgentLogic n'est pas un JSON valide ou ne contient pas les clés attendues.")
            team1_plan_text = team1_plan_text # Ancien comportement par défaut
            available_skills_list = ["coding_python", "web_research", "software_testing", "document_synthesis", "general_analysis", "plan_decomposition_refinement"] # Fallback


        skills_string = ", ".join([f"'{s}'" for s in available_skills_list]) if available_skills_list else "la liste fournie par le superviseur"

        if not team1_plan_text:
            logger.warning("Texte du plan de TEAM 1 vide, aucune décomposition possible.")
            # Retourner une structure vide conforme au schéma attendu par le superviseur (ou une erreur)
            return {
                "global_context": "Plan de TEAM 1 vide.",
                "instructions": ["Aucune instruction car plan vide."],
                "tasks": []
            }

        system_prompt = (
            "Tu es un chef de projet expert en décomposition de plans en tâches granulaires et structurées. "
            "Ton rôle est de prendre un plan de projet détaillé (rédigé en langage naturel) et de le transformer en un objet JSON structuré. "
            "Cet objet JSON doit contenir un 'global_context' (résumé du plan original), des 'instructions' globales (si pertinentes, sinon une liste vide), "
            "et une liste de 'tasks'.\n"
            "Pour chaque tâche dans la liste 'tasks', tu dois fournir :\n"
            "- 'id': un identifiant textuel unique et court pour la tâche (ex: 'T01', 'T02a').\n"
            "- 'nom': un nom court et descriptif pour la tâche.\n"
            "- 'description': une description détaillée de ce que la tâche doit accomplir.\n"
            "- 'type': choisir entre 'executable' (produit un livrable) ou 'exploratory' (recherche/analyse pouvant mener à de nouvelles tâches). Le type 'container' peut aussi être utilisé pour des tâches qui regroupent logiquement d'autres tâches mais ne sont pas directement exécutables.\n"
            "- 'dependances': une liste d'IDs des tâches (que tu as définies dans la même liste) dont cette tâche dépend directement. Si aucune dépendance, fournir une liste vide [].\n"
            "- 'instructions_locales': une liste de chaînes de caractères détaillant les étapes ou consignes spécifiques pour réaliser cette tâche.\n"
            "- 'acceptance_criteria': une liste de chaînes de caractères décrivant les conditions pour considérer la tâche comme terminée avec succès.\n"
            f"- 'assigned_agent_type': une chaîne de caractères EXACTE choisie parmi la liste suivante de compétences disponibles : [{skills_string}]. Choisis la compétence la plus pertinente pour la tâche.\n"
            "- 'assigned_agent_type': une chaîne de caractères indiquant la compétence requise (ex: 'coding_python', 'web_research', 'software_testing', 'document_synthesis', 'general_analysis', 'plan_decomposition_refinement').\n"
            "- 'sous_taches': une liste (qui peut être vide) d'objets tâche imbriqués, suivant exactement la même structure que les tâches principales. Utilise cela pour décomposer une tâche complexe en étapes plus petites.\n"
            "Assure-toi que la réponse est UNIQUEMENT l'objet JSON global, sans aucun texte ou explication en dehors."
        )
        
        prompt = (
            f"Voici le plan détaillé (qui servira de 'global_context') à décomposer :\n\n"
            f"'''{team1_plan_text}'''\n\n"
            "Génère l'objet JSON structuré comme décrit dans les instructions système. "
            "Le 'global_context' doit être un résumé concis de ce plan. "
            f"Les compétences d'agent que tu PEUX assigner aux tâches sont : {skills_string}.\n"
            "Les 'instructions' globales peuvent être une liste vide si aucune instruction de haut niveau ne s'applique à toutes les tâches. "
            "Pour les 'dependances', utilise les 'id' des tâches que tu as définies précédemment dans la liste 'tasks'. "
            "Si une tâche n'a pas de dépendances, utilise une liste vide []. De même pour 'sous_taches' si applicable.\n"
            "Sois rigoureux sur le format JSON et les types de données.\n"
            "L'objet JSON global doit avoir les clés 'global_context', 'instructions', et 'tasks'."
        )

        try:
            llm_response_str = await call_llm(prompt, system_prompt, json_mode=True)
            # Le LLM est censé retourner directement une chaîne représentant l'objet JSON global
            decomposed_plan_json = json.loads(llm_response_str)
            
            # Validation basique de la structure principale attendue
            if not isinstance(decomposed_plan_json, dict) or \
               not all(k in decomposed_plan_json for k in ["global_context", "instructions", "tasks"]) or \
               not isinstance(decomposed_plan_json.get("tasks"), list):
                logger.error(f"La réponse du LLM n'est pas un objet JSON avec la structure attendue (global_context, instructions, tasks): {decomposed_plan_json}")
                raise ValueError("La réponse du LLM n'a pas la structure principale attendue.")

            logger.info(f"DecompositionAgent - Plan décomposé (structure JSON globale) reçu du LLM. Nombre de tâches principales: {len(decomposed_plan_json.get('tasks', []))}")
            return decomposed_plan_json # Retourner le dictionnaire Python complet

        except json.JSONDecodeError as e:
            logger.error(f"Impossible de parser la réponse JSON du LLM pour la décomposition: {e}. Réponse brute: '{llm_response_str}'")
            return {"error": "Invalid JSON response from LLM", "raw_response": llm_response_str}
        except Exception as e:
            logger.error(f"Échec de la décomposition par le LLM: {e}", exc_info=True)
            return {"error": f"LLM processing failed: {e}"}