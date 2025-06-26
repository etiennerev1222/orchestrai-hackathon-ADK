import logging
from firebase_admin import firestore
from .firebase_init import db

logger = logging.getLogger(__name__)

def update_agent_stats(agent_name: str, success: bool):
    """Increment success or failure counters for the given agent."""
    if not db:
        logger.error(
            "Client Firestore (db) non initialisé, impossible de mettre à jour les stats."
        )
        return
    try:
        stats_ref = db.collection("agent_stats").document(agent_name)
        field_to_update = (
            {"tasks_completed": firestore.Increment(1)}
            if success
            else {"tasks_failed": firestore.Increment(1)}
        )
        stats_ref.set(field_to_update, merge=True)
        logger.info(
            f"Statistiques mises à jour pour {agent_name}: +1 tâche {'complétée' if success else 'échouée'}."
        )
    except Exception as e:
        logger.error(
            f"Impossible de mettre à jour les statistiques pour {agent_name}: {e}"
        )


def increment_agent_restart(agent_name: str):
    """Increment restart counter for the given agent."""
    if not db:
        logger.error(
            "Client Firestore (db) non initialisé, impossible de mettre à jour le compteur de redémarrages."
        )
        return
    try:
        stats_ref = db.collection("agent_stats").document(agent_name)
        stats_ref.set({"restarts": firestore.Increment(1)}, merge=True)
        logger.info(f"Redémarrage enregistré pour {agent_name}")
    except Exception as e:
        logger.error(f"Impossible de mettre à jour le compteur de redémarrages pour {agent_name}: {e}")
