# Supervisor Class Diagrams

This document presents the main classes coordinating OrchestrAI. The Mermaid diagram shows how the supervisors interact with each other and with the `EnvironmentManager`.

```mermaid
classDiagram
    class GlobalSupervisorLogic {
        +start_new_global_plan(raw_objective)
        +get_status()
    }
    class PlanningSupervisorLogic {
        +create_new_plan(raw_objective, plan_id)
        +_handle_task_completion()
    }
    class ExecutionSupervisorLogic {
        +execute_plan()
    }
    class EnvironmentManager {
        +create_isolated_environment(environment_id)
        +execute_command(environment_id, command)
    }

    GlobalSupervisorLogic --> PlanningSupervisorLogic : orchestrates
    GlobalSupervisorLogic --> ExecutionSupervisorLogic : launches
    GlobalSupervisorLogic --> EnvironmentManager : uses
    PlanningSupervisorLogic --> ExecutionSupervisorLogic : produces plan for
```
