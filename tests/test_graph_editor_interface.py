import types
import sys
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

class DummyTaskNode:
    def __init__(self, task_id, objective, task_type, parent_id=None, dependencies=None, assigned_agent_type=None, meta=None):
        self.id = task_id
        self.objective = objective
        self.task_type = task_type
        self.parent_id = parent_id
        self.state = 'pending'
        self.dependencies = dependencies or []
        self.assigned_agent_type = assigned_agent_type
        self.meta = meta or {}

    def to_dict(self):
        return {
            'id': self.id,
            'objective': self.objective,
            'task_type': self.task_type,
            'parent_id': self.parent_id,
            'state': self.state,
            'dependencies': self.dependencies,
            'assigned_agent_type': self.assigned_agent_type,
            'meta': self.meta,
        }

    @staticmethod
    def from_dict(data):
        n = DummyTaskNode(
            data['id'],
            data['objective'],
            data['task_type'],
            parent_id=data.get('parent_id'),
            dependencies=data.get('dependencies', []),
            assigned_agent_type=data.get('assigned_agent_type'),
            meta=data.get('meta', {}),
        )
        n.state = data.get('state', 'pending')
        return n

class DummyGraph:
    _store: dict = {}

    def __new__(cls, execution_plan_id):
        if execution_plan_id in cls._store:
            return cls._store[execution_plan_id]
        inst = super().__new__(cls)
        cls._store[execution_plan_id] = inst
        return inst

    def __init__(self, execution_plan_id):
        if hasattr(self, 'initialized'):
            return
        self.execution_plan_id = execution_plan_id
        self.nodes = {}
        self.edit = False
        self.initialized = True

    def as_dict(self):
        return {'id': self.execution_plan_id, 'nodes': self.nodes}

    def add_task(self, node, is_root=False):
        self.nodes[node.id] = node.to_dict()

    def edit_task(self, task_id, updates):
        n = self.nodes[task_id]
        n.update(updates)
        return DummyTaskNode.from_dict(n)

    def delete_task(self, task_id):
        self.nodes.pop(task_id, None)

    def link_tasks(self, f, t):
        self.nodes.setdefault(t, {'dependencies': []})['dependencies'].append(f)

    def unlink_tasks(self, f, t):
        deps = self.nodes.get(t, {}).get('dependencies', [])
        if f in deps:
            deps.remove(f)

    def validate_graph(self):
        return True

    def set_edit_mode(self, enabled, user_id=None):
        self.edit = enabled

    def get_edit_mode(self):
        return self.edit

@pytest.fixture()
def client(monkeypatch):
    dummy_module = types.ModuleType('src.shared.execution_task_graph_management')
    dummy_module.ExecutionTaskGraph = DummyGraph
    dummy_module.ExecutionTaskNode = DummyTaskNode
    dummy_module.ExecutionTaskType = str
    sys.modules['src.shared.execution_task_graph_management'] = dummy_module
    import importlib
    gei = importlib.import_module('src.interfaces.graph_editor_interface')
    app = FastAPI()
    app.include_router(gei.router)
    return TestClient(app)

def test_add_and_edit_task(client):
    r = client.post('/execution_graph/p1/add_task', json={'id': 't1', 'objective': 'obj', 'task_type': 'executable'})
    assert r.status_code == 200
    r = client.patch('/execution_graph/p1/edit_task/t1', json={'objective': 'new'})
    assert r.status_code == 200
    assert r.json()['objective'] == 'new'

def test_toggle_edit_mode(client):
    r = client.post('/execution_graph/p1/toggle_edit_mode', json={'enabled': True})
    assert r.json()['edit_mode'] is True
    r = client.get('/execution_graph/p1/edit_mode')
    assert r.json()['edit_mode'] is True
