import pytest
from src.agents.development_agent.executor import DevelopmentAgentExecutor
from src.shared.execution_task_graph_management import ExecutionTaskGraph
from src.shared.firebase_init import get_firestore_client

@pytest.mark.asyncio
async def test_trace_and_artifact_tool_invoke():
    context_id = "test-context-palier6-1"
    executor = DevelopmentAgentExecutor()

    payload = {
        "sender_agent": "DevelopmentAgent",
        "action": "invoke_tool",
        "tool": "capability_check",
        "input": {"deliverable_description": "Créer une API FastAPI"}
    }

    result = await executor.agent_logic.tool_registry.handle_llm_response(payload, context_id=context_id)
    print("🧪 Résultat outil:", result)
    assert isinstance(result, dict), "❌ Résultat outil invalide"

    # ✅ Vérification du graphe d'exécution
    graph = ExecutionTaskGraph(context_id)
    graph_data = graph._get_graph_data()
    nodes = graph_data.get("nodes", {})
    assert nodes, "❌ Le graphe est vide"

    print("📊 Nœuds du graphe:")
    for n_id, n_data in nodes.items():
        print(f"  - {n_id}: {n_data.get('objective')}")

    found_node = any("Invoke capability_check" in n["objective"] for n in nodes.values())
    assert found_node, "❌ Nœud 'Invoke capability_check' non trouvé dans le graphe"

    firestore_client = get_firestore_client()
    assert firestore_client is not None, "❌ Firestore client non initialisé"

    collection = firestore_client.collection("threads").document(context_id).collection("interactions")
    docs = list(collection.stream())

    print(f"📁 Artefacts trouvés: {len(docs)}")
    for doc in docs:
        data = doc.to_dict()
        print("📄", data)
        if data.get("tool_invoked", {}).get("name") == "capability_check":
            break
    else:
        assert False, "❌ L’artefact capability_check n’a pas été enregistré"

    assert any("sender_agent" in d.to_dict() for d in docs), "❌ sender_agent absent"
