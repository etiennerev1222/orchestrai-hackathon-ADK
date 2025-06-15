import asyncio
import os
import logging
import sys

def setup_test_environment():
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    sys.path.insert(0, project_root)

    os.environ["GCP_PROJECT_ID"] = "orchestrai-hackathon"
    os.environ["GCP_REGION"] = "europe-west1"
    
    if not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        credential_path = os.path.join(project_root, "credentials.json")
        if os.path.exists(credential_path):
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credential_path
        else:
            print("AVERTISSEMENT: Fichier credentials.json non trouvé. Le test pourrait échouer.")

    logging.basicConfig(
        level=logging.INFO, 
        format='%(asctime)s - %(levelname)s - %(name)s - %(message)s'
    )

async def main():
    logger = logging.getLogger(__name__)
    logger.info("--- Début du test du client LLM ---")
    
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
        logger.error(f"Erreur rencontrée : {e}", exc_info=False)

if __name__ == "__main__":
    setup_test_environment()
    asyncio.run(main())