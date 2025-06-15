#!/usr/bin/env python3
"""Nettoie les plans Firestore n'ayant pas démarré la phase TEAM 2.

Ce script supprime les documents des collections `global_plans` et
`task_graphs` lorsque le plan n'a pas progressé au-delà de TEAM 1.
"""

import logging
from typing import Dict, Any

from src.shared.firebase_init import get_firestore_client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TEAM2_PREFIX = "TEAM2_"


def _should_remove(plan_data: Dict[str, Any]) -> bool:
    """Détermine si le plan doit être supprimé."""
    state = plan_data.get("current_supervisor_state", "")
    team2_id = plan_data.get("team2_execution_plan_id")
    if team2_id:
        return False
    if isinstance(state, str) and state.startswith(TEAM2_PREFIX):
        return False
    return True


def cleanup_plans():
    db = get_firestore_client()
    if not db:
        logger.error("Client Firestore indisponible. Abandon du nettoyage.")
        return

    plans_ref = db.collection("global_plans")
    for doc in plans_ref.stream():
        data = doc.to_dict()
        if _should_remove(data):
            plan_id = doc.id
            logger.info("Suppression du plan %s", plan_id)
            plans_ref.document(plan_id).delete()

            team1_id = data.get("team1_plan_id")
            if team1_id:
                db.collection("task_graphs").document(team1_id).delete()

            exec_id = data.get("team2_execution_plan_id")
            if exec_id:
                db.collection("execution_task_graphs").document(exec_id).delete()


if __name__ == "__main__":
    cleanup_plans()
