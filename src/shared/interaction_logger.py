
import uuid
import logging
from datetime import datetime
from typing import Optional


logger = logging.getLogger(__name__)
from src.shared.firebase_init import get_firestore_client


def save_interaction_artifact(context_id: str, artifact: dict):
    if "sender_agent" not in artifact:
        logger.warning(f"⚠️ Artefact sans 'sender_agent': {artifact}")

    client = get_firestore_client()
    if not client:
        raise RuntimeError("Firestore client is not initialized.")

    interactions_collection = client.collection("threads").document(context_id).collection("interactions")

    interaction_id = artifact.get("interaction_id")
    if not interaction_id:
        raise ValueError("Artifact must contain an 'interaction_id'.")

    interactions_collection.document(interaction_id).set(artifact)


def build_collaboration_artifact(
    context_id: str,
    msg_type: str,
    sender_agent: str,
    receiver_agent: str,
    llm_prompt: Optional[str] = None,
    llm_output: Optional[dict] = None,
    result_summary: Optional[str] = None,
    tool_invoked: Optional[dict] = None
) -> dict:
    """
    Construit un artefact d’interaction collaborative prêt à être loggé.
    """
    return {
        "interaction_id": str(uuid.uuid4()),
        "msg_type": msg_type,
        "sender_agent": sender_agent,
        "receiver_agent": receiver_agent,
        "llm_prompt": llm_prompt,
        "llm_output": llm_output,
        "result_summary": result_summary,
        "tool_invoked": tool_invoked,
        "timestamp": datetime.utcnow().isoformat()
    }

from src.shared.execution_task_graph_management import ExecutionTaskGraph


def log_collaboration_trace(interaction: dict, context_id: str):
    from uuid import uuid4

    interaction_id = interaction.get("interaction_id") or str(uuid4())
    interaction["interaction_id"] = interaction_id
    interaction["timestamp"] = datetime.utcnow().isoformat()

    save_interaction_artifact(context_id, interaction)

    # 🔗 Ajout dans le graphe comme interaction collaborative
    if interaction.get("msg_type") in ["CAPABILITY_CHECK", "RESOURCE_REQUEST"]:
        ExecutionTaskGraph.add_collaborative_edge(
            context_id=context_id,
            sender_agent=interaction.get("sender_agent"),
            receiver_agent=interaction.get("receiver_agent"),
            msg_type=interaction.get("msg_type"),
            interaction_id=interaction_id
        )
