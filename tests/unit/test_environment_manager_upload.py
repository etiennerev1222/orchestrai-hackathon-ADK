import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.environment_manager.logic import EnvironmentManager

@pytest.mark.asyncio
async def test_upload_to_cloud_and_index():
    manager = EnvironmentManager()
    manager.read_file_from_environment = AsyncMock(return_value="data")
    storage_client = MagicMock()
    bucket = MagicMock()
    blob = MagicMock()
    storage_client.bucket.return_value = bucket
    bucket.blob.return_value = blob

    doc_ref = MagicMock()
    doc_ref.id = "artifact123"
    db_mock = MagicMock()
    db_mock.collection.return_value.document.return_value = doc_ref

    graph_instance = MagicMock()

    with patch("src.services.environment_manager.logic.storage.Client", return_value=storage_client), \
         patch("src.services.environment_manager.logic.db", db_mock), \
         patch("src.services.environment_manager.logic.ExecutionTaskGraph", return_value=graph_instance) as graph_cls:
        result = await manager.upload_to_cloud_and_index(
            "env1", "foo.txt", "bucket", "dest.txt", "plan1", "task1"
        )

        blob.upload_from_string.assert_called_once()
        doc_ref.set.assert_called_once()
        artifact = doc_ref.set.call_args.args[0]
        assert artifact["environment_id"] == "env1"
        assert artifact["gcs_uri"] == "gs://bucket/dest.txt"
        assert "agent_name" in artifact
        graph_cls.assert_called_once_with("plan1")
        graph_instance.update_task_output.assert_called_once_with("task1", artifact_ref="artifact123")
        assert result["artifact_id"] == "artifact123"
        assert result["gcs_uri"] == "gs://bucket/dest.txt"
