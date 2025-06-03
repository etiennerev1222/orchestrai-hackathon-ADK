# src/agents/development_agent/logic.py
import logging
import json
from typing import Dict, Any, Tuple # Ajout de Tuple

from src.shared.base_agent_logic import BaseAgentLogic
from src.shared.llm_client import call_llm

logger = logging.getLogger(__name__)
if not logger.hasHandlers():
    logging.basicConfig(level=logging.INFO)

# Compétences que cet agent fournira
AGENT_SKILL_CODING_PYTHON = "coding_python"
# Plus tard, on pourrait ajouter AGENT_SKILL_CODING_JAVASCRIPT, etc.

class DevelopmentAgentLogic(BaseAgentLogic):
    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(f"{__name__}.DevelopmentAgentLogic")
        self.logger.info("Logique du DevelopmentAgent initialisée.")

    async def process(self, input_data_str: str, context_id: str | None = None) -> str:
        """
        Génère du code basé sur un objectif, des instructions et des critères d'acceptation.
        L'input_data_str est attendu comme un JSON string.
        Retourne le code généré sous forme de chaîne (ou un message d'erreur).
        """
        try:
            input_payload = json.loads(input_data_str)
            objective = input_payload.get("objective", "Objectif de développement non spécifié.")
            local_instructions = input_payload.get("local_instructions", [])
            acceptance_criteria = input_payload.get("acceptance_criteria", [])
            # On pourrait aussi passer le langage/framework ici si l'agent est polyglotte
            # language = input_payload.get("language", "python") 
        except json.JSONDecodeError:
            self.logger.error(f"DevelopmentAgent: Input JSON invalide: {input_data_str}")
            return f"// Erreur: Input JSON invalide pour DevelopmentAgent\n// {input_data_str}"

        self.logger.info(f"DevelopmentAgent - Tâche à coder (contexte: {context_id}): '{objective}'")
        self.logger.debug(f"Instructions locales: {local_instructions}")
        self.logger.debug(f"Critères d'acceptation: {acceptance_criteria}")

        system_prompt = (
            "Tu es un développeur IA expert en Python. Ta mission est de générer du code Python propre, "
            "fonctionnel et bien commenté, basé sur les spécifications fournies. "
            "Le code doit être directement utilisable. N'inclus que le code dans ta réponse, "
            "sauf si des commentaires dans le code sont nécessaires pour l'expliquer."
            "Assure-toi de respecter les instructions spécifiques et les critères d'acceptation."
        )
        
        prompt = (
            f"Objectif de développement : {objective}\n\n"
            f"Instructions spécifiques pour l'implémentation :\n"
            f"{'- ' + chr(10) + '- '.join(local_instructions) if local_instructions else 'Aucune instruction spécifique.'}\n\n"
            f"Critères d'acceptation (le code doit permettre de les valider) :\n"
            f"{'- ' + chr(10) + '- '.join(acceptance_criteria) if acceptance_criteria else 'Non spécifiés.'}\n\n"
            "Génère UNIQUEMENT le code Python correspondant. Si tu dois expliquer quelque chose, fais-le sous forme de commentaires dans le code."
        )

        try:
            # json_mode=False car on attend du code brut, pas un JSON du LLM ici
            generated_code = await call_llm(prompt, system_prompt, json_mode=False) 
            
            self.logger.info(f"DevelopmentAgent - Code généré (début): {generated_code[:300]}...")
            # On pourrait ajouter une validation basique du code (ex: est-ce du Python valide?)
            return generated_code

        except Exception as e:
            self.logger.error(f"DevelopmentAgent - Échec de la génération de code: {e}", exc_info=True)
            return f"# Erreur lors de la génération de code pour '{objective}': {str(e)}"