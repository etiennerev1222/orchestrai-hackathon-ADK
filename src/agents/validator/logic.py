# src/agents/validator/logic.py
import logging
import json
from typing import Dict, Any
from src.shared.base_agent_logic import BaseAgentLogic
from src.shared.llm_client import call_llm

logger = logging.getLogger(__name__)

class ValidatorAgentLogic(BaseAgentLogic):
    def __init__(self):
        super().__init__()
        logger.info("Logique du ValidatorAgent initialisée (mode LLM).")

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

        # La seule et unique instruction système pour le validateur.
        system_prompt = (
            "Tu es un directeur de projet senior. Ton rôle est de prendre une décision finale (Approuvé ou Rejeté) "
            "sur un projet en te basant sur l'analyse fournie par ton équipe. "
            "Tu dois justifier ta décision et retourner le résultat au format JSON uniquement."
        )
        
        evaluation_str = json.dumps(evaluation_result, indent=2, ensure_ascii=False)

        prompt = (
            "Voici l'évaluation d'un plan de projet :\n"
            f"'''{evaluation_str}'''\n\n"
            "En te basant sur cette analyse, et en particulier sur le score de faisabilité et les faiblesses identifiées, "
            "décide si le plan doit être 'approved' ou 'rejected'. "
            "Si le score est inférieur à 5 ou si des faiblesses critiques sont mentionnées, tu devrais probablement le rejeter. "
            "Justifie ta décision et precises le point d'amélioration dans 'validation_comments'.\n"
            "Retourne ta décision exclusivement sous la forme d'un objet JSON avec les clés : "
            "'validation_status' ('approved' ou 'rejected') et 'validation_comments' (ta justification)."
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