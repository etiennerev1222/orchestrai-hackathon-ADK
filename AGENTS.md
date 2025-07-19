# AGENTS.md - Multi-agent quick start

This repository implements a complete multi-agent framework built on top of the **Google Agent Development Kit (ADK)**. Agents collaborate to clarify goals, generate a plan and execute tasks using skill-specific tools.

## Overview

1. **Clarification**: `UserInteractionAgent` interacts with the user to refine the objective.
2. **Planning (TEAM 1)**: `Reformulator`, `Evaluator` and `Validator` craft a detailed plan orchestrated by `PlanningSupervisorLogic`.
3. **Execution (TEAM 2)**: `DecompositionAgent` splits the validated plan. `Development`, `Research` and `Testing` agents perform concrete tasks under `ExecutionSupervisorLogic`.
4. **Tool-based agents**: All logics inherit from `BaseAgentLogic` which loads tools from a `ToolRegistry`. Tools live in `src/tools/` and include `generate_code_and_write_file`, `execute_command`, `workforce_information` and `capability_check`.
5. **Global supervision**: `GlobalSupervisorLogic` coordinates the phases and stores state in Firestore.
6. **GRA service**: FastAPI registry exposing agent discovery and status endpoints.
7. **Dashboard**: `src/app_frontend.py` offers a Streamlit UI to submit goals and follow progress.

Agents live under `src/agents/<agent>` and provide:
- `server.py` – A2A server exposing the API.
- `logic.py` – Business logic based on `BaseAgentLogic`.
- `executor.py` – Helper to run the logic.

Orchestrators are located in `src/orchestrators/` and rely on `src/shared/` for task graph management, Firestore access and LLM utilities.

## Quick Start

1. Install dependencies: `pip install -r requirements.txt`.
2. Start the GRA: `python -m src.services.gra.server`.
3. Run each agent: `python -m src.agents.<agent>.server`.
4. Launch the dashboard: `streamlit run src/app_frontend.py`.

Firestore collections `global_plans`, `task_graphs`, `execution_task_graphs` and `agents` store the orchestration state.

## References
- `README.md` for a full architecture overview.
- `src/run_orchestrator.py` for running a plan from the command line.
- `tests/` for automated tests.
