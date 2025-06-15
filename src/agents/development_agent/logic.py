import logging
import json
from typing import Dict, Any, Tuple

from src.shared.base_agent_logic import BaseAgentLogic
from src.shared.llm_client import call_llm

logger = logging.getLogger(__name__)
if not logger.hasHandlers():
    logging.basicConfig(level=logging.INFO)

AGENT_SKILL_CODING_PYTHON = "coding_python"

class DevelopmentAgentLogic(BaseAgentLogic):
    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(f"{__name__}.DevelopmentAgentLogic")
        self.logger.info("Logique du DevelopmentAgent initialisée.")


    async def process(self, input_data_str: str, context_id: str | None = None) -> str:
        """
        Génère la prochaine action (JSON) que l'agent de développement devrait entreprendre,
        basée sur l'objectif et l'état actuel de l'environnement.
        La sortie est un JSON string décrivant l'action pour l'exécuteur.
        """
        try:
            input_payload = json.loads(input_data_str)
            objective = input_payload.get("objective", "Objectif de développement non spécifié.")
            local_instructions = input_payload.get("local_instructions", [])
            acceptance_criteria = input_payload.get("acceptance_criteria", [])
            environment_id = input_payload.get("environment_id")
            current_environment_state = input_payload.get("current_state", "L'environnement est vide ou inconnu. Aucune information préalable sur l'état.")
            last_action_result = input_payload.get("last_action_result", {})

        except json.JSONDecodeError:
            self.logger.error(f"DevelopmentAgent: Input JSON invalide: {input_data_str}")
            return json.dumps({"status": "error", "message": f"Input JSON invalide: {input_data_str}"})

        if not environment_id:
            self.logger.error("DevelopmentAgent: 'environment_id' manquant dans l'input.")
            return json.dumps({"status": "error", "message": "Environment ID is required for development actions."})

        self.logger.info(f"DevelopmentAgent - Décision d'action pour l'objectif: '{objective}' (environnement: {environment_id})")
        self.logger.debug(f"Instructions locales: {local_instructions}")
        self.logger.debug(f"Critères d'acceptation: {acceptance_criteria}")
        self.logger.debug(f"État actuel de l'environnement: {current_environment_state}")
        self.logger.debug(f"Résultat de la dernière action: {json.dumps(last_action_result, indent=2)}")

        system_prompt = (
            "Tu es un développeur IA expert en Python et un planificateur d'actions atomiques. "
            "Ton rôle est d'analyser un objectif de développement, des instructions, des critères d'acceptation, "
            "ainsi que l'état actuel de l'environnement de travail et le résultat de la dernière action exécutée. "
            "Tu dois ensuite décider de la **prochaine action unique et la plus pertinente** à entreprendre pour avancer vers l'objectif."
            "\n\nTu dois toujours répondre **UNIQUEMENT** avec un objet JSON qui spécifie cette action. "
            "Ne fournis AUCUN autre texte ou explication en dehors de cet objet JSON. "
            "Si plusieurs actions semblent possibles, choisis la plus logique et atomique qui vous rapproche de l'objectif final."
            "\n\n**Actions/Outils disponibles et leur structure JSON attendue :**"
            "\n1. **Pour générer et écrire du code :**"
            "\n   `{ \"action\": \"generate_code_and_write_file\", \"file_path\": \"/chemin/vers/fichier.py\", \"objective\": \"description du code\", \"local_instructions\": [], \"acceptance_criteria\": [] }`"
            "\n   - Utilise cette action pour créer ou mettre à jour un fichier de code (Python principalement). Le `file_path` DOIT commencer par `/app/`."
            "\n   - `objective` doit décrire ce que le CODE doit faire, pas la tâche globale."
            "\n   - `local_instructions` et `acceptance_criteria` sont spécifiques à la portion de code."

            "\n2. **Pour exécuter une commande shell (installation, exécution, exploration) :**"
            "\n   `{ \"action\": \"execute_command\", \"command\": \"votre commande shell\", \"workdir\": \"/repertoire/de/travail/optionnel\" }`"
            "\n   - Exemples de commandes : `'pip install flask'`, `'python /app/main.py'`, `'ls -l /app'`, `'pytest /app/tests/'`."
            "\n   - Utilise cette action pour installer des dépendances, lancer l'application, exécuter des tests, ou faire des vérifications du système de fichiers."

            "\n3. **Pour lire le contenu d'un fichier :**"
            "\n   `{ \"action\": \"read_file\", \"file_path\": \"/chemin/vers/fichier\" }`"
            "\n   - Utilise cette action pour inspecter du code, lire des logs, ou vérifier le contenu de fichiers générés."

            "\n4. **Pour lister le contenu d'un répertoire :**"
            "\n   `{ \"action\": \"list_directory\", \"path\": \"/chemin/vers/repertoire\" }`"
            "\n   - Utilise cette action pour comprendre la structure des fichiers ou confirmer la création de dossiers."

            "\n5. **Pour indiquer que la tâche globale de développement est terminée :**"
            "\n   `{ \"action\": \"complete_task\", \"summary\": \"Bref résumé du travail accompli et des livrables.\" }`"
            "\n   - Utilise cette action seulement lorsque tu es certain que l'objectif de développement global est atteint et que le code est fonctionnel et vérifié. C'est la dernière action que tu dois entreprendre pour une tâche."

            "\n\n**Ton processus de raisonnement devrait être itératif :**"
            "\n- Commence par créer des fichiers de code."
            "\n- Installe les dépendances nécessaires."
            "\n- Exécute le code ou les tests."
            "\n- Lis les sorties ou les logs pour comprendre le résultat."
            "\n- En fonction du résultat (succès, erreur), décide de la prochaine action (corriger le code, installer autre chose, marquer la tâche comme terminée)."
            "\n\n**Contexte et retour d'information :**"
            f"\nÉtat actuel de l'environnement (dernière observation connue) : {current_environment_state}"
            f"\nRésultat de la dernière action exécutée : {json.dumps(last_action_result, indent=2)}"
            "\n\nN'oublie pas : réponds UNIQUEMENT avec l'objet JSON de la prochaine action."
        )
        
        prompt = (
            f"**Objectif de développement global pour cette session :** {objective}\n\n"
            f"**Instructions spécifiques pour cette tâche :**\n"
            f"{'- ' + chr(10) + '- '.join(local_instructions) if local_instructions else 'Aucune instruction spécifique.'}\n\n"
            f"**Critères d'acceptation de la tâche de développement :**\n"
            f"{'- ' + chr(10) + '- '.join(acceptance_criteria) if acceptance_criteria else 'Non spécifiés.'}\n\n"
            f"En te basant sur l'objectif, les instructions, les critères, l'état de l'environnement et le résultat de la dernière action, "
            f"quelle est la **PROCHAINE action unique que tu dois planifier** ? "
            f"Réponds UNIQUEMENT avec l'objet JSON correspondant à l'action choisie."
        )

        try:
            llm_response_str = await call_llm(prompt, system_prompt, json_mode=True) 
            
            self.logger.info(f"DevelopmentAgentLogic - Réponse LLM (action JSON): {llm_response_str[:500]}...")
            
            json.loads(llm_response_str)
            return llm_response_str 

        except json.JSONDecodeError as e:
            self.logger.error(f"DevelopmentAgentLogic - La réponse LLM n'est pas un JSON valide: {e}. Réponse brute: {llm_response_str}", exc_info=True)
            return json.dumps({"status": "error", "action": "llm_error", "message": f"LLM returned invalid JSON: {e}. Raw: {llm_response_str}"})
        except Exception as e:
            self.logger.error(f"DevelopmentAgentLogic - Échec lors de la décision de l'action par le LLM: {e}", exc_info=True)
            return json.dumps({"status": "error", "action": "internal_error", "message": f"Internal error during LLM action decision: {str(e)}"})
        