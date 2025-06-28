import asyncio
import logging
from google.cloud import storage
from datetime import datetime
from typing import Optional

from src.shared.firebase_init import db
from src.shared.execution_task_graph_management import ExecutionTaskGraph

from .k8s_environment_manager import KubernetesEnvironmentManager as BaseEnvironmentManager
import os
logger = logging.getLogger(__name__)

class EnvironmentManager(BaseEnvironmentManager):
    """Extension of the legacy EnvironmentManager with artifact publishing."""

    async def upload_to_cloud_and_index(
        self,
        environment_id: str,
        path: str,
        bucket_name: str,
        destination_blob: str,
        execution_plan_id: Optional[str] = None,
        task_id: Optional[str] = None,
    ) -> dict:
        """Read a file from an environment, upload it to Cloud Storage and index in Firestore."""
        content = await self.read_file_from_environment(environment_id, path)
        storage_client = storage.Client()
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(destination_blob)
        artifact["agent_name"] = os.environ.get("AGENT_NAME", "EnvironmentManagerGKEv2")
        await asyncio.to_thread(blob.upload_from_string, content.encode("utf-8"))
        artifact = {
            "environment_id": environment_id,
            "path": path,
            "gcs_uri": f"gs://{bucket_name}/{destination_blob}",
            "created_at": datetime.utcnow().isoformat(),
        }
        doc_ref = db.collection("artifacts").document()
        await asyncio.to_thread(doc_ref.set, artifact)
        artifact_id = doc_ref.id
        if execution_plan_id and task_id:
            ExecutionTaskGraph(execution_plan_id).update_task_output(task_id, artifact_ref=artifact_id)
        logger.info(f"Artifact {artifact_id} stored for env {environment_id}")
        return {"artifact_id": artifact_id, "gcs_uri": artifact["gcs_uri"]}
