import logging
from src.shared.base_agent_logic import BaseAgentLogic
from src.shared.llm_client import call_llm

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
            "plus spécifique et directement exploitable par une equipe d'agent LLM aux capacité étendue. Si l'objectif est vague, enrichis-le avec des "
            "hypothèses raisonnables. Ne pose pas de questions, fournis directement une version améliorée."
        )
        
        prompt = (
            f"Voici l'objectif brut à reformuler : '{objective_text}'.\n\n"
            "Reformule-le en un objectif clair et détaillé, orienté vers une réalisation concrète par une équipe d'agents LLM. "
            "Par exemple, transforme 'analyser les données de ventes' en "
            "'Analyser les données de ventes en utilisant des modèles prédictifs pour identifier les tendances clés, "
            "les opportunités de croissance et les segments de clientèle prioritaires, en fournissant un rapport structuré "
            "\n\n"
        )

        try:
            reformulated_text = await call_llm(prompt, system_prompt)
            logger.info(f"ReformulatorAgentLogic - Objectif reformulé par LLM: '{reformulated_text}'")
            return reformulated_text
        except Exception as e:
            logger.error(f"Échec de la reformulation par le LLM: {e}")
            return f"[ERREUR DE REFORMULATION] L'objectif initial était: '{objective_text}'"
        
