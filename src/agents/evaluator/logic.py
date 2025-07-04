import logging
import json
from typing import Dict, Any
from src.shared.base_agent_logic import BaseAgentLogic
from src.shared.llm_client import call_llm

logger = logging.getLogger(__name__)

class EvaluatorAgentLogic(BaseAgentLogic):
    def __init__(self):
        super().__init__()
        logger.info("Logique de l'EvaluatorAgent initialisée (mode LLM).")

    async def process(self, input_data: str, context_id: str | None = None) -> Dict[str, Any]:
        """
        Évalue un plan/objectif donné en utilisant un LLM et retourne une analyse structurée en JSON.
        """
        plan_to_evaluate = input_data
        logger.info(f"EvaluatorAgentLogic - Plan à évaluer (contexte: {context_id}): '{plan_to_evaluate}'")

        system_prompt = (
            "Tu es un analyste stratégique chargé d'évaluer la qualité et la faisabilité d'un objectif de projet. "
            "Tu dois fournir une évaluation structurée au format JSON. Ne fournis aucun texte en dehors de l'objet JSON."
        )

        prompt = (
            "Évalue l'objectif de projet suivant :\n"
            f"'''{plan_to_evaluate}'''\n\n"
            "Analyse ses forces, ses faiblesses, les risques potentiels et donne une note de faisabilité sur 10. "
            "Retourne ton analyse exclusivement sous la forme d'un objet JSON avec les clés suivantes : "
            "'evaluation_notes' (un résumé de ton analyse), 'strengths' (une liste de points forts), "
            "'weaknesses' (une liste de points faibles), 'feasibility_score' (un nombre de 1 à 10), "
            "et 'evaluated_plan' (le texte du plan que tu as évalué)."
        )

        try:
            json_response_str = await call_llm(prompt, system_prompt, json_mode=True)
            
            evaluation_result = json.loads(json_response_str)
            logger.info(f"EvaluatorAgentLogic - Évaluation JSON reçue du LLM: {evaluation_result}")
            return evaluation_result

        except json.JSONDecodeError as e:
            logger.error(f"Impossible de parser la réponse JSON du LLM: {e}. Réponse brute: '{json_response_str}'")
            return {"error": "Invalid JSON response from LLM", "raw_response": json_response_str}
        except Exception as e:
            logger.error(f"Échec de l'évaluation par le LLM: {e}")
            return {"error": f"LLM processing failed: {e}", "evaluated_plan": plan_to_evaluate}
        











