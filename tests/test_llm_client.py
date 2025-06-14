# tests/test_llm_client.py
import asyncio
import os
import logging
import sys

# --- Configuration pour le test local ---
# Cette partie s'assure que le script trouve le dossier 'src'
# et que les variables d'environnement sont définies.
def setup_test_environment():
    # 1. Ajouter la racine du projet au chemin de Python
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    sys.path.insert(0, project_root)

    # 2. Définir les variables d'environnement nécessaires pour le test
    os.environ["GCP_PROJECT_ID"] = "orchestrai-hackathon"
    os.environ["GCP_REGION"] = "europe-west1" # Utiliser une région qui a fonctionné
    
    # 3. S'assurer que les credentials sont trouvés
    if not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        credential_path = os.path.join(project_root, "credentials.json")
        if os.path.exists(credential_path):
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credential_path
        else:
            print("AVERTISSEMENT: Fichier credentials.json non trouvé. Le test pourrait échouer.")

    # 4. Configurer le logging pour voir les messages
    logging.basicConfig(
        level=logging.INFO, 
        format='%(asctime)s - %(levelname)s - %(name)s - %(message)s'
    )

# --- Exécution du test ---
async def main():
    logger = logging.getLogger(__name__)
    logger.info("--- Début du test du client LLM ---")
    
    # On importe la fonction à tester APRÈS avoir configuré l'environnement
    from src.shared.llm_client import call_llm
    
    test_prompt = "Explique la gravité en une seule phrase simple et poétique."
    
    try:
        logger.info(f"Envoi du prompt : '{test_prompt}'")
        response = await call_llm(test_prompt)
        
        print("\n" + "="*25 + " RÉPONSE DU MODÈLE " + "="*25)
        print(response)
        print("="*70 + "\n")
        
        logger.info("--- Test réussi ! L'appel à Vertex AI a fonctionné. ---")
    
    except Exception as e:
        logger.error("--- Le test a échoué ---")
        logger.error(f"Erreur rencontrée : {e}", exc_info=False) # exc_info=False pour un log plus propre

if __name__ == "__main__":
    setup_test_environment()
    asyncio.run(main())