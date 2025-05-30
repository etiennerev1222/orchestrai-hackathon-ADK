# run_orchestrator.py
import asyncio
import uuid
import logging
import json

from src.orchestrators.planning_supervisor_logic import PlanningSupervisorLogic, TaskState
from src.shared.task_graph_management import TaskGraph

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def main():
    objective = "Organiser une conférence sur l'IA éthique à Zurich pour Q4, avec un focus sur l'impact social. Budget : 5000 CHF."
    plan_id = f"plan_{uuid.uuid4().hex[:12]}"

    logger.info("--- DÉMARRAGE D'UN NOUVEAU PLAN ---")
    logger.info(f"Objectif: {objective}")
    logger.info(f"ID du Plan (Document Firestore): {plan_id}")

    supervisor = PlanningSupervisorLogic(max_revisions=2)
    supervisor.create_new_plan(raw_objective=objective, plan_id=plan_id)

    max_cycles = 20
    for i in range(max_cycles):
        logger.info(f"\n--- CYCLE DE TRAITEMENT N°{i+1} pour le plan {plan_id} ---")
        
        await supervisor.process_plan(plan_id=plan_id)

        # --- CORRECTION DE LA CONDITION D'ARRÊT ---
        # On vérifie si TOUTES les tâches sont terminées, pas seulement la tâche racine.
        graph_reader = TaskGraph(plan_id=plan_id)
        all_tasks_data = graph_reader.as_dict().get("nodes", {})
        
        if not all_tasks_data:
            logger.warning("Le graphe de tâches est vide, arrêt.")
            break

        non_terminal_tasks = [
            task_id for task_id, task in all_tasks_data.items() 
            if task.get("state") not in [TaskState.COMPLETED.value, TaskState.FAILED.value, TaskState.CANCELLED.value]
        ]

        if not non_terminal_tasks:
            logger.info("Toutes les tâches du plan ont atteint un état final. Arrêt du processus.")
            break
        
        logger.info(f"Tâches encore actives: {non_terminal_tasks}")

        if i == max_cycles - 1:
            logger.warning("Le nombre maximum de cycles a été atteint. Arrêt du traitement.")
            break

        await asyncio.sleep(5)

    logger.info(f"\n--- RÉSULTAT FINAL POUR LE PLAN '{plan_id}' ---")
    final_graph = TaskGraph(plan_id=plan_id).as_dict()
    final_root_status = final_graph.get("nodes", {}).get(plan_id, {}).get("state", "INCONNU")

    logger.info(f"État final de la tâche racine '{plan_id}': {final_root_status}")
    logger.info("Graphe final stocké dans Firestore.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Arrêt demandé par l'utilisateur.")