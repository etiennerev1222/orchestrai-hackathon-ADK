# gra

**Français :**
- Implémente le Gestionnaire de Ressources et d'Agents (GRA).
- Permet l'enregistrement et la découverte des agents via REST.
- Sert de point d'entrée unique pour le front-end et les orchestrateurs.

**English:**
- Implements the Resource and Agent Manager (GRA).
- Allows agent registration and discovery through REST endpoints.
- Serves as a single entry point for the front-end and supervisors.

Recent additions expose CRUD routes to edit execution graphs:

- `POST   /v1/execution_task_graphs/{plan_id}/nodes`
- `PUT    /v1/execution_task_graphs/{plan_id}/nodes/{node_id}`
- `DELETE /v1/execution_task_graphs/{plan_id}/nodes/{node_id}`
- `POST   /v1/execution_task_graphs/{plan_id}/dependencies`
- `DELETE /v1/execution_task_graphs/{plan_id}/dependencies/{source}/{target}`

These power the `TaskGraphEditor` component in the React front end.
