import asyncio
import logging
from src.services.environment_manager.environment_manager import EnvironmentManager

# Configuration du logger pour bien voir les messages
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

async def test_environment_manager():
    manager = EnvironmentManager()
    import uuid
    hex_id = uuid.uuid4().hex[:12]
    test_global_plan_id = f"gplan_{hex_id}"
    test_global_plan_id ='exec-gplan_baee972ca40f'
    env_id = EnvironmentManager.normalize_environment_id(test_global_plan_id)

    logging.info(f"🌱 Création de l'environnement : {env_id}")
    created_env = await manager.create_isolated_environment(test_global_plan_id)
    assert created_env is not None, "❌ L'environnement n'a pas pu être créé."
    logging.info("✅ Environnement créé avec succès.")

    pod_name = manager.environments[env_id]['pod_name']
    await manager._ensure_pod_running(pod_name)
    logging.info(f"✅ Pod {pod_name} est bien en état Running.")

    # Écriture d'un fichier
    test_content = "print('Hello test')"
    await manager.write_file_to_environment(test_global_plan_id, "/app/hello_test.py", test_content)
    logging.info("✅ Fichier écrit avec succès.")

    # Lecture du fichier
    content = await manager.read_file_from_environment(test_global_plan_id, "/app/hello_test.py")
    assert content.strip() == test_content.strip(), "❌ Le contenu lu ne correspond pas au contenu écrit."
    logging.info("✅ Fichier lu et contenu validé.")

    # Exécution d'une commande
    result = await manager.execute_command_in_environment(test_global_plan_id, "python /app/hello_test.py")
    assert "Hello test" in result['stdout'], f"❌ Résultat inattendu : {result}"
    logging.info("✅ Commande exécutée avec succès et output validé.")

    # Listing des fichiers
    files = await manager.list_files_in_environment(test_global_plan_id, "/app")
    assert any(
    f["name"].endswith("hello_test.py") or f["name"] == "hello_test.py"
    for f in files
), "❌ Le fichier écrit n'apparaît pas dans le listing."
    logging.info("✅ Listing des fichiers validé.")

    # Destruction de l'environnement
    #await manager.destroy_environment(test_global_plan_id)
    #logging.info("✅ Environnement détruit avec succès.")

if __name__ == "__main__":
    asyncio.run(test_environment_manager())
