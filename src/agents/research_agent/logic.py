import logging
import json
from typing import Dict, Any, List 
import uuid

from src.shared.base_agent_logic import BaseAgentLogic
from src.shared.llm_client import call_llm
from src.shared.prompts import get_base_prompt
from src.shared.prompt_utils import build_generic_system_prompt

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

    def get_active_tools(self) -> dict:
        """Expose les outils utilisables par l'agent de recherche."""
        return {
            "workforce_information": self.tool_registry.get_tools().get(
                "workforce_information"
            )
        }

    async def process(self, input_data_str: str, context_id: str | None = None) -> str:
        try:
            input_payload = json.loads(input_data_str)
            objective = input_payload.get("objective", "Objectif de recherche non spécifié.")
            local_instructions = input_payload.get("local_instructions", [])
            acceptance_criteria = input_payload.get("acceptance_criteria", [])
            available_skills_list = input_payload.get("available_execution_skills", []) 
            task_type_for_agent = input_payload.get("task_type", "exploratory")
            
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
        if not available_skills_list:
            default_skills = ["coding_python", "web_research", "software_testing", "document_synthesis", "general_analysis", "database_design"]
            skills_string_for_prompt = ", ".join([f"'{s}'" for s in default_skills])


        base_prompt = get_base_prompt("research_agent")
        system_prompt = build_generic_system_prompt(
            base_prompt,
            self.tool_registry.get_metadata_for_tools(self.get_active_tools().keys())
        )

        context_summary = self.get_context_summary(context_id)
        if context_summary:
            self.logger.info(f"[CTX] Résumé chargé pour {context_id}: {context_summary}")
            system_prompt = f"{system_prompt}\n\nContexte:\n{context_summary}"
        
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

        allowed_tools = list(self.get_active_tools().keys())

        try:
            self.logger.debug(
                f"ResearchAgentLogic - Prompt Système LLM:\n{system_prompt}"
            )
            self.logger.debug(
                f"ResearchAgentLogic - Prompt Utilisateur LLM:\n{prompt}"
            )
            loop_result = await self.run_reasoning_loop_with_tools(
                objective=objective,
                context_id=context_id,
                allowed_tools=allowed_tools,
                initial_prompt=prompt,
                system_prompt=system_prompt,
            )
            final = self.extract_final_result_with_fallback(loop_result)
            llm_json_output = final if isinstance(final, dict) else {}

            try:
                if not isinstance(llm_json_output, dict) or \
                   "summary" not in llm_json_output or \
                   "new_sub_tasks" not in llm_json_output or \
                   not isinstance(llm_json_output["new_sub_tasks"], list):
                    self.logger.error(
                        f"Réponse LLM pour ResearchAgent n'a pas la structure attendue (summary, new_sub_tasks): {llm_json_output}"
                    )
                    return json.dumps(
                        {
                            "summary": "Erreur: La réponse du LLM n'a pas la structure JSON attendue.",
                            "new_sub_tasks": [],
                            "error": "LLM response structure incorrect."
                        }
                    )
                self.logger.info(
                    f"ResearchAgent - Résultat traité. Summary: '{llm_json_output.get('summary', '')[:100]}...'. Nombre de nouvelles sous-tâches: {len(llm_json_output.get('new_sub_tasks',[]))}"
                )
                return json.dumps(llm_json_output, ensure_ascii=False)

            except Exception as e:
                self.logger.error(
                    f"Impossible de parser JSON du LLM pour ResearchAgent: {e}. Réponse: '{llm_json_output}'"
                )
                return json.dumps(
                    {
                        "summary": "Erreur: La réponse du LLM n'était pas un JSON valide.",
                        "new_sub_tasks": [],
                        "error": "Invalid JSON response from LLM",
                        "raw_response": str(llm_json_output)
                    }
                )

        except Exception as e:
            self.logger.error(f"ResearchAgent - Échec du traitement: {e}", exc_info=True)
            return json.dumps({
                "summary": f"Erreur interne lors du traitement par ResearchAgent: {str(e)}",
                "new_sub_tasks": [],
                "error": f"LLM processing or internal error: {str(e)}"
            })