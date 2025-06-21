from src.shared.firebase_init import get_firestore_client
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def parse_date(date_str):
    try:
        return datetime.fromisoformat(date_str)
    except Exception:
        return datetime.min

def cleanup_duplicate_plans():
    db = get_firestore_client()
    if not db:
        logger.error("Firestore client non disponible.")
        return

    plans_ref = db.collection("global_plans")
    all_docs = list(plans_ref.stream())

    grouped = {}
    for doc in all_docs:
        data = doc.to_dict()
        key = (data.get("raw_objective"), data.get("current_supervisor_state"))
        if key not in grouped:
            grouped[key] = []
        grouped[key].append({
            "id": doc.id,
            "created_at": data.get("created_at"),
            "team1_plan_id": data.get("team1_plan_id"),
            "team2_execution_plan_id": data.get("team2_execution_plan_id")
        })

    for key, plans in grouped.items():
        if len(plans) <= 1:
            continue
        # Garder le plus récent
        plans.sort(key=lambda p: parse_date(p["created_at"]), reverse=True)
        to_delete = plans[1:]
        for plan in to_delete:
            logger.info(f"Suppression du plan doublon : {plan['id']} (objectif={key[0]})")
            plans_ref.document(plan['id']).delete()
            if plan["team1_plan_id"]:
                db.collection("task_graphs").document(plan["team1_plan_id"]).delete()
            if plan["team2_execution_plan_id"]:
                db.collection("execution_task_graphs").document(plan["team2_execution_plan_id"]).delete()

if __name__ == "__main__":
    cleanup_duplicate_plans()
