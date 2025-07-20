import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.shared.base_agent_logic import BaseAgentLogic

class DummyAgent(BaseAgentLogic):
    async def process(self, input_text: str, context_id: str | None = None):
        return ""

    def can_deliver(self, deliverable: str) -> bool:
        return True


@pytest.mark.asyncio
async def test_record_collaboration_builds_and_logs():
    artifact = {"interaction_id": "abc123"}
    with (
        patch(
            "src.shared.interaction_logger.build_collaboration_artifact",
            return_value=artifact,
        ) as build_mock,
        patch("src.shared.interaction_logger.log_collaboration_trace") as log_mock,
    ):
        interaction_id = BaseAgentLogic._record_collaboration(
            sender_agent="A",
            receiver_agent="B",
            msg_type="CAPABILITY_CHECK",
            context_id="ctx1",
            result_summary="done",
        )
        build_mock.assert_called_once_with(
            context_id="ctx1",
            msg_type="CAPABILITY_CHECK",
            sender_agent="A",
            receiver_agent="B",
            llm_prompt=None,
            llm_output=None,
            result_summary="done",
            tool_invoked=None,
        )
        log_mock.assert_called_once_with(artifact, context_id="ctx1")
        assert interaction_id == "abc123"


@pytest.mark.asyncio
async def test_send_collaborative_message_records_interaction():
    agent = DummyAgent()
    doc_mock = MagicMock()
    doc_mock.exists = True
    doc_mock.to_dict.return_value = {"internal_url": "http://agent-b"}
    coll_mock = MagicMock()
    coll_mock.document.return_value.get.return_value = doc_mock
    db_mock = MagicMock()
    db_mock.collection.return_value = coll_mock

    fake_task = MagicMock()
    fake_artifact = MagicMock()
    fake_artifact.parts = [MagicMock(root=MagicMock(text="{\"foo\": \"bar\"}"))]
    fake_task.artifacts = [fake_artifact]

    with (
        patch(
            "src.shared.base_agent_logic.get_firestore_client",
            return_value=db_mock,
        ),
        patch(
            "src.shared.base_agent_logic.call_a2a_agent",
            AsyncMock(return_value=fake_task),
        ) as call_mock,
        patch.object(BaseAgentLogic, "_record_collaboration") as record_mock,
    ):
        result = await agent.send_collaborative_message(
            "other",
            "CAPABILITY_CHECK",
            {"foo": "bar"},
            context_id="ctx1",
        )

        call_mock.assert_awaited_once()
        record_mock.assert_called_once()
        assert result == {"foo": "bar"}
