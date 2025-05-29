# src/agents/reformulator/logic.py
import logging
from src.shared.base_agent_logic import BaseAgentLogic
from src.shared.llm_client import call_llm # <-- Importer le client LLM

logger = logging.getLogger(__name__)

class ReformulatorAgentLogic(BaseAgentLogic):
    def __init__(self):
        super().__init__()
        logger.info("Logique du ReformulatorAgent initialisée (mode LLM).")

    async def process(self, input_data: str, context_id: str | None = None) -> str:
        """
        Reformule un objectif en utilisant un LLM pour le rendre plus clair et structuré.
        """
        objective_text = input_data
        logger.info(f"ReformulatorAgentLogic - Objectif à traiter (contexte: {context_id}): '{objective_text}'")

        if not objective_text:
            return "Objectif vide reçu, aucune reformulation possible."

        system_prompt = (
            "Tu es un assistant expert en gestion de projet. "
            "Ton rôle est de reformuler un objectif fourni par un utilisateur pour le rendre plus clair, "
            "plus spécifique et directement exploitable. Si l'objectif est vague, enrichis-le avec des "
            "hypothèses raisonnables. Ne pose pas de questions, fournis directement une version améliorée."
        )
        
        prompt = (
            f"Voici l'objectif brut à reformuler : '{objective_text}'.\n\n"
            "Reformule-le en un objectif clair et détaillé. Par exemple, transforme 'organiser une conférence' en "
            "'Organiser une conférence de A à Z sur un thème générique, incluant la recherche de lieu, "
            "le processus de sélection des intervenants, de la promotion de l'événement et de la gestion logistique le jour J, "
            "à livrer pour la date demandée par l'utilisateur ou première date raissonable'\n\n"
        )

        try:
            reformulated_text = await call_llm(prompt, system_prompt)
            logger.info(f"ReformulatorAgentLogic - Objectif reformulé par LLM: '{reformulated_text}'")
            return reformulated_text
        except Exception as e:
            logger.error(f"Échec de la reformulation par le LLM: {e}")
            return f"[ERREUR DE REFORMULATION] L'objectif initial était: '{objective_text}'"
        
# Le bloc if __name__ == "__main__": pour tester isolément peut rester,
# mais il faudra ajuster l'instanciation et l'appel de méthode si vous le décommentez.
# Exemple:
# if __name__ == "__main__":
#     import asyncio
#     async def test_reformulator_logic():
#         logic = ReformulatorAgentLogic()
#         test_objective = "tester cette nouvelle logique"
#         result = await logic.process(test_objective, "test-ctx-reformulator")
#         print(f"Test: Entrée='{test_objective}', Sortie='{result}'")
#     asyncio.run(test_reformulator_logic())