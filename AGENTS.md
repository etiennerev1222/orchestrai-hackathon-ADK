# AGENTS.md - point d'entrée pour moteurs multi-agents

Ce dépôt contient un système multi-agents complet basé sur l'**Agent Development Kit (ADK)**. Il permet de clarifier un objectif utilisateur, de générer un plan détaillé puis d'exécuter ce plan via plusieurs agents spécialisés.

## Vue d'ensemble

1. **Clarification** : `UserInteractionAgent` interagit avec l'utilisateur pour affiner l'objectif initial.
2. **Planification (TEAM 1)** : `Reformulator`, `Evaluator`, `Validator` génèrent et valident un plan détaillé orchestré par `PlanningSupervisorLogic`.
3. **Exécution (TEAM 2)** : `DecompositionAgent` découpe le plan validé. `Development`, `Research` et `Testing` réalisent concrètement les tâches orchestrées par `ExecutionSupervisorLogic`.
4. **Supervision Globale** : `GlobalSupervisorLogic` pilote les phases précédentes et gère les états dans Firestore.
5. **Gestionnaire de Ressources (GRA)** : service FastAPI centralisant l'enregistrement et la découverte des agents.
6. **Interface** : `src/app_frontend.py` expose un tableau de bord Streamlit pour soumettre et suivre les plans. Une interface React optionnelle permet des visualisations avancées.

Les agents sont implémentés sous `src/agents/` (un répertoire par agent). Chaque agent fournit :
- `server.py` : serveur A2A (ASGI) exposant son API.
- `logic.py` : logique métier s'appuyant sur un LLM (Gemini).
- `executor.py` : wrapper pour exécuter la logique.

Les orchestrateurs se trouvent sous `src/orchestrators/` et utilisent `src/shared/` pour la gestion des graphes de tâches, la connexion Firestore et l'accès LLM.

## Démarrage rapide

1. Installer les dépendances : `pip install -r requirements.txt`.
2. Lancer le GRA : `python -m src.services.gra.server`.
3. Démarrer chaque agent (`python -m src.agents.<agent>.server`).
4. Lancer l'interface : `streamlit run src/app_frontend.py`.

Les plans et graphes sont stockés dans Firestore (`global_plans`, `task_graphs`, `execution_task_graphs`, `agents`).

## Références utiles
- `README.md` : description détaillée de l'architecture et des phases du système.
- `src/run_orchestrator.py` : exemple de lancement de plan par script.
- `tests/` : exemples de tests automatisés.

