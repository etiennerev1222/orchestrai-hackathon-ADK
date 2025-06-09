# orchestrators

**Français :**
- Logiques de supervision du projet.
- `global_supervisor_logic.py` orchestre l'ensemble du flux.
- `planning_supervisor_logic.py` pilote TEAM&nbsp;1 et gère le `TaskGraph`.
- `execution_supervisor_logic.py` pilote TEAM&nbsp;2 et gère l'`ExecutionTaskGraph`.
- `continue_execution` permet de reprendre un plan TEAM 2 interrompu.

**English:**
- Supervisory logic for the project.
- `global_supervisor_logic.py` orchestrates the whole flow.
- `planning_supervisor_logic.py` drives TEAM&nbsp;1 and manages the `TaskGraph`.
- `execution_supervisor_logic.py` drives TEAM&nbsp;2 and manages the `ExecutionTaskGraph`.
- `continue_execution` allows resuming an interrupted TEAM 2 plan.
