import logging
import json
from typing import Dict, Any
from src.shared.base_agent_logic import BaseAgentLogic
from src.shared.llm_client import call_llm
from src.shared.prompts import get_base_prompt
from src.shared.prompt_utils import build_generic_system_prompt

logger = logging.getLogger(__name__)

class ValidatorAgentLogic(BaseAgentLogic):
    def __init__(self):
        super().__init__()
        logger.info("Logique du ValidatorAgent initialisée (mode LLM).")

    def get_active_tools(self) -> dict:
        """Retourne les outils disponibles pour le validateur."""
        return self.tool_registry.get_tools()

    async def process(self, input_data: Dict[str, Any], context_id: str | None = None) -> Dict[str, Any]:
        """
        Valide un plan basé sur son évaluation, en utilisant un LLM pour la décision finale.
        Retourne maintenant toujours le plan évalué, même en cas de rejet.
        """
        evaluation_result = input_data
        logger.info(f"ValidatorAgentLogic - Réception de l'évaluation (contexte: {context_id}): '{evaluation_result}'")

        if "error" in evaluation_result:
            return {
                "validation_status": "rejected",
                "validation_comments": f"Validation rejetée en raison d'une erreur en amont: {evaluation_result['error']}",
                "evaluated_plan": evaluation_result.get("evaluated_plan")
            }

        base_prompt = get_base_prompt("validator_agent")
        system_prompt = build_generic_system_prompt(
            base_prompt,
            self.tool_registry.get_metadata_for_tools(self.get_active_tools().keys())
        )
        
        evaluation_str = json.dumps(evaluation_result, indent=2, ensure_ascii=False)

        prompt = (
            "Voici l'évaluation d'un plan produit par la TEAM 1. Analyse-la en gardant à l'esprit que tu dois décider si ce plan est 'assez bon pour commencer l'exécution'.\n\n"
            f"'''{evaluation_str}'''\n\n"
            "Prends ta décision en suivant ces règles :\n"
            "- **SI** le `feasibility_score` est de 6 ou plus ET que les `weaknesses` sont des points de vigilance ou des détails à affiner plutôt que des bloqueurs fondamentaux, **ALORS** approuve le plan (`validation_status`: 'approved'). Tes `validation_comments` peuvent inclure des recommandations pour l'équipe d'exécution.\n"
            "- **SI** le `feasibility_score` est de 5 ou moins OU si une faiblesse majeure empêche toute forme de démarrage (ex: 'objectif incompréhensible', 'budget 10x trop faible'), **ALORS** rejette le plan (`validation_status`: 'rejected'). Tes `validation_comments` doivent expliquer clairement et de manière concise le ou les bloqueurs à corriger pour la TEAM 1.\n\n"
            "Retourne ta décision exclusivement sous la forme d'un objet JSON avec les clés : "
            "'validation_status' ('approved' ou 'rejected'), "
            "'validation_comments' (ta justification constructive), "
            "et 'final_plan' (le texte de 'evaluated_plan' si tu l'approuves, sinon `null`)."
        )
        
        try:
            json_response_str = await call_llm(prompt, system_prompt, json_mode=True)
            validation_decision = json.loads(json_response_str)

            evaluated_plan_text = evaluation_result.get("evaluated_plan")
            validation_decision["evaluated_plan"] = evaluated_plan_text

            if validation_decision.get("validation_status") == "approved":
                 validation_decision["final_plan"] = evaluated_plan_text
            else:
                 validation_decision["final_plan"] = None

            logger.info(f"ValidatorAgentLogic - Décision de validation finale: {validation_decision}")
            return validation_decision

        except Exception as e:
            logger.error(f"Échec de la validation par le LLM: {e}", exc_info=True)
            return {
                "validation_status": "rejected", 
                "validation_comments": f"LLM processing failed during validation: {e}",
                "evaluated_plan": evaluation_result.get("evaluated_plan")
            }