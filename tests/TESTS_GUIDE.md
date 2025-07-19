# TESTS_GUIDE

This document lists the available test scripts and explains how to run them.
It complements the short `README.md` and helps understand the prerequisites
for each test.

## Integration tests

- **check_health.py**
  - Checks that every agent registered in Firestore responds to `/health`.
  - Requires Google Cloud credentials with access to the Firestore project.
  - Run: `python tests/check_health.py`.

- **create_cube_test_env_for_dev.py**
  - Creates a Kubernetes execution environment through the `EnvironmentManager`.
  - Needs `kubectl` configured for your cluster and the service account
    used by the manager.
  - Run: `python tests/create_cube_test_env_for_dev.py`.

- **run_test_environment_manager.sh**
  - End-to-end test of the Environment Manager REST API.
  - Requires a running `environment-manager` pod and `kubectl` access.
  - Run: `bash tests/run_test_environment_manager.sh`.

- **port_forward_environment_mamager.sh**
  - Convenience script to port‑forward the Environment Manager to `localhost:8080`.
  - Run: `bash tests/port_forward_environment_mamager.sh`.

- **run_test_development_agent.sh**
  - Sends requests to the Development agent running in Kubernetes.
  - Requires `kubectl` and valid gcloud credentials.
  - Run: `bash tests/run_test_development_agent.sh`.

- **test_decoposeur.py**
  - Client for the `DecompositionAgentServer` listening on `localhost:8005`.
  - Run: `python tests/test_decoposeur.py` (agent must be started first).

- **test_evaluator_client.py**
  - Client for the `EvaluatorAgentServer` expected on `localhost:8002`.
  - Run: `python tests/test_evaluator_client.py`.

- **test_reformulator_client.py**
  - Client for the `ReformulatorAgentServer` expected on `localhost:8001`.
  - Run: `python tests/test_reformulator_client.py`.

- **test_llm_client.py**
  - Simple check of the internal LLM client against Vertex AI.
  - Requires valid Google Cloud credentials.
  - Run: `python tests/test_llm_client.py`.

- **test_graph_editor_interface.py**
  - Uses FastAPI's `TestClient` to validate the graph editor endpoints.
  - Run via `pytest tests/test_graph_editor_interface.py`.
- **dev_tools_tests.py**
  - Runs Development agent tools against a running Environment Manager.
  - Requires access to the service defined by `$ENVIRONMENT_MANAGER_INTERNAL_URL`.
- **test_development_agent.py**
  - Sends a complete task to a deployed Development agent and polls for results.
  - Requires Firestore access and the agent URL stored in the service registry.
- **test_environment_manager.py**
  - Python variant of the end‑to‑end Environment Manager test.
  - Assumes the service is reachable on `localhost:8000`.
- **test_palier_6_tool_invoke.py**
  - Validates that `capability_check` invocations are tracked in Firestore.
  - Needs valid Google Cloud credentials.
- **k8s_iam_test_server.py**
  - Lightweight FastAPI server for testing IAM calls to the GKE API.
  - Run with `python tests/k8s_iam_test_server.py` or build using `tests/Dockerfile`.
- **deploy_dns_test.sh**
  - Example Cloud Run Job for verifying internal DNS resolution.
- **simule_UserInteractionAgentLogic.py**
  - Demonstrates `UserInteractionAgentLogic` clarification flow locally.

## Unit tests (`tests/unit/`)

Run all unit tests with:

```bash
pytest tests/unit
```

Individual files include:

- `test_collaboration_logging.py`
- `test_context_builder.py`
- `test_decomposition_logic.py`
- `test_dev_executor_artifact.py`
- `test_dev_agent_executor_tool_call.py`
- `test_environment_manager_upload.py`
- `test_interaction_logger.py`
- `test_retry_failed_tasks.py`
- `test_tool_capability_check.py`
- `test_evaluator_capability_check.py`
- `test_global_prompts.py`

Each unit test has no external dependencies and can be run independently
with `pytest tests/unit/<file>`.
