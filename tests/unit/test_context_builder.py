import asyncio
from unittest.mock import patch
import pytest

from src.shared.context_builder import build_context_summary

class DummyTask:
    def __init__(self, id, objective, parent_id=None, dependencies=None, result_summary=None, sub_task_ids=None):
        self.id = id
        self.objective = objective
        self.parent_id = parent_id
        self.dependencies = dependencies or []
        self.result_summary = result_summary
        self.sub_task_ids = sub_task_ids or []

class DummyGraph:
    def __init__(self, execution_plan_id):
        self.tasks = {}
    def get_task(self, task_id):
        return self.tasks.get(task_id)

def setup_dummy_graph():
    g = DummyGraph("plan1")
    # parent task
    parent = DummyTask("p1", "Analyser le document", result_summary="Analyse du texte OK", sub_task_ids=["t1", "s1"])
    target = DummyTask("t1", "Extraire les noms", parent_id="p1", dependencies=["d1"])
    sibling = DummyTask("s1", "Nettoyer le texte", parent_id="p1", result_summary="Résumé du nettoyage du texte")
    dep = DummyTask("d1", "Reco entités", result_summary="Résultat de reconnaissance des entités")
    g.tasks = {"p1": parent, "t1": target, "s1": sibling, "d1": dep}
    return g

@patch("src.shared.context_builder.ExecutionTaskGraph", autospec=True)
def test_build_context_summary(mock_graph_cls):
    g = setup_dummy_graph()
    mock_graph_cls.return_value = g
    summary = asyncio.run(build_context_summary("t1", "plan1"))
    assert "Objectif actuel" in summary
    assert "Analyser le document" in summary
    assert "Analyse du texte OK" in summary
    assert "Reco entités" not in summary  # objective not included
    assert "reconnaissance" in summary.lower()
    assert "Nettoyer le texte" not in summary
