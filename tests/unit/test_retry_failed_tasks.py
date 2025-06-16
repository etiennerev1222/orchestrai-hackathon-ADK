import pytest
from unittest.mock import AsyncMock
import sys
import types


@pytest.mark.asyncio
async def test_retry_failed_tasks_resets_and_calls_continue(monkeypatch):
    fake_fb = types.ModuleType("firebase_admin")
    fake_fb.firestore = types.ModuleType("firestore")
    sys.modules['firebase_admin'] = fake_fb
    sys.modules['firebase_admin.firestore'] = fake_fb.firestore
    dummy_fb_init = types.ModuleType("src.shared.firebase_init")
    dummy_fb_init.db = None
    def get_firestore_client():
        return None
    dummy_fb_init.get_firestore_client = get_firestore_client
    sys.modules['src.shared.firebase_init'] = dummy_fb_init

    env_mgr_module = types.ModuleType('src.services.environment_manager.environment_manager')
    class DummyEnvMgr:
        async def create_isolated_environment(self, environment_id, base_image='python'):
            return environment_id
        def destroy_environment(self, environment_id):
            pass
    env_mgr_module.EnvironmentManager = DummyEnvMgr
    sys.modules['src.services.environment_manager.environment_manager'] = env_mgr_module

    from src.orchestrators.execution_supervisor_logic import (
        ExecutionSupervisorLogic,
        ExecutionTaskState,
    )

    class DummyGraph:
        def __init__(self, execution_plan_id):
            self.execution_plan_id = execution_plan_id
            self.nodes = {
                't1': {'state': ExecutionTaskState.FAILED.value},
                't2': {'state': ExecutionTaskState.COMPLETED.value},
            }
            self.overall_status = 'EXECUTION_COMPLETED_WITH_FAILURES'

        def as_dict(self):
            return {'nodes': self.nodes, 'overall_status': self.overall_status}

        def update_task_state(self, task_id, state, details=None):
            self.nodes[task_id]['state'] = state.value

        def set_overall_status(self, status):
            self.overall_status = status

    monkeypatch.setattr(
        'src.orchestrators.execution_supervisor_logic.EnvironmentManager',
        env_mgr_module.EnvironmentManager,
    )
    monkeypatch.setattr(
        'src.orchestrators.execution_supervisor_logic.ExecutionTaskGraph',
        DummyGraph,
    )

    logic = ExecutionSupervisorLogic('gp', 'plan', execution_plan_id='exec')
    dummy_continue = AsyncMock()
    monkeypatch.setattr(logic, 'continue_execution', dummy_continue)

    await logic.retry_failed_tasks()

    assert logic.task_graph.nodes['t1']['state'] == ExecutionTaskState.PENDING.value
    assert logic.task_graph.nodes['t2']['state'] == ExecutionTaskState.COMPLETED.value
    assert logic.task_graph.overall_status == 'RETRYING_FAILED_TASKS'
    dummy_continue.assert_awaited()
