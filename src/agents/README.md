# agents

**Français :**
- Implémentations des différents agents du système.
- Catégories :
  - clarification (`user_interaction_agent`)
  - planification TEAM&nbsp;1 (`reformulator`, `evaluator`, `validator`)
  - exécution TEAM&nbsp;2 (`decomposition_agent`, `development_agent`, `research_agent`, `testing_agent`)
- Chaque sous-dossier possède un serveur FastAPI (`server.py`), une logique métier (`logic.py`) et un exécuteur (`executor.py`).

**English:**
- Implementations for the various system agents.
- Categories:
  - clarification (`user_interaction_agent`)
  - planning TEAM&nbsp;1 (`reformulator`, `evaluator`, `validator`)
  - execution TEAM&nbsp;2 (`decomposition_agent`, `development_agent`, `research_agent`, `testing_agent`)
- Each subdirectory exposes a FastAPI server (`server.py`), the business logic (`logic.py`) and an executor (`executor.py`).
