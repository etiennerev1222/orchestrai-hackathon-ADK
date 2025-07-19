from unittest.mock import MagicMock, patch

from src.shared.interaction_logger import log_collaboration_trace


def test_log_collaboration_trace_adds_edge():
    interaction = {
        "interaction_id": "abc",
        "msg_type": "CAPABILITY_CHECK",
        "sender_agent": "A",
        "receiver_agent": "B",
    }
    with patch("src.shared.interaction_logger.save_interaction_artifact") as save_mock, \
         patch("src.shared.interaction_logger.ExecutionTaskGraph") as graph_cls:
        graph_instance = MagicMock()
        graph_cls.return_value = graph_instance

        log_collaboration_trace(interaction, "ctx1")

        save_mock.assert_called_once_with("ctx1", interaction)
        graph_cls.assert_called_once_with("ctx1")
        graph_instance.add_collaborative_edge.assert_called_once_with(
            sender_agent="A",
            receiver_agent="B",
            msg_type="CAPABILITY_CHECK",
            interaction_id="abc",
        )
        assert "timestamp" in interaction
