import logging
from src.shared.base_agent_logic import BaseAgentLogic
from src.shared.llm_client import call_llm
from src.shared.prompts import get_base_prompt
from src.shared.prompt_utils import build_generic_system_prompt

logger = logging.getLogger(__name__)

class ReformulatorAgentLogic(BaseAgentLogic):
    def __init__(self):
        super().__init__()
        logger.info("Logique du ReformulatorAgent initialisée (mode LLM).")

    def get_active_tools(self) -> dict:
        """Expose les outils disponibles pour le LLM."""
        return {
            "workforce_information": self.tool_registry.get_tools().get(
                "workforce_information"
            )
        }

    async def process(self, input_data: str, context_id: str | None = None) -> str:
        """
        Reformule un objectif en utilisant un LLM pour le rendre plus clair et structuré.
        """
        objective_text = input_data
        logger.info(f"ReformulatorAgentLogic - Objectif à traiter (contexte: {context_id}): '{objective_text}'")

        if not objective_text:
            return "Objectif vide reçu, aucune reformulation possible."

        base_prompt = get_base_prompt("reformulator")
        system_prompt = build_generic_system_prompt(
            base_prompt,
            self.tool_registry.get_metadata_for_tools(self.get_active_tools().keys())
        )

        prompt = (
            f"Voici l'objectif brut à reformuler : '{objective_text}'.\n\n"
            "Reformule-le en un objectif clair et détaillé, orienté vers une réalisation concrète par une équipe d'agents LLM. "
            "Par exemple, transforme 'analyser les données de ventes' en "
            "'Analyser les données de ventes en utilisant des modèles prédictifs pour identifier les tendances clés, "
            "les opportunités de croissance et les segments de clientèle prioritaires, en fournissant un rapport structuré "
            "\n\n"
        )

        allowed_tools = list(self.get_active_tools().keys())

        try:
            result = await self.run_reasoning_loop_with_tools(
                objective=objective_text,
                context_id=context_id,
                allowed_tools=allowed_tools,
                initial_prompt=prompt,
                system_prompt=system_prompt,
            )
            final = self.extract_final_result_with_fallback(result)
            reformulated_text = final.get("clarified_objective") or final.get("summary") or str(final)
            logger.info(
                f"ReformulatorAgentLogic - Objectif reformulé par LLM: '{reformulated_text}'"
            )
            return reformulated_text
        except Exception as e:
            logger.error(f"Échec de la reformulation par le LLM: {e}")
            return f"[ERREUR DE REFORMULATION] L'objectif initial était: '{objective_text}'"
        
