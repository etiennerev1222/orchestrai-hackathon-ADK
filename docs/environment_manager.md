# Environment Manager

Internal service that creates isolated execution environments. In production it targets Kubernetes, but a lightweight Docker backend can be used when running locally. It is mainly used by the development agent to write files, run commands and clean up environments once execution is finished.

The manager stores environment metadata in the `kubernetes_environments` Firestore collection. When no dedicated environment is found for a plan, a fallback environment identified by `exec_default` can be used. A helper script `scripts/create_fallback_environment.py` is provided to create this fallback pod.

Generated code is executed inside a working directory mounted at `/app` in each pod.

The GRA exposes `/api/environments/{env_id}` (DELETE) to remove a pod and its persistent volume claim. The React dashboard uses this endpoint to let you clean up environments.

## Local Docker mode

When no Kubernetes cluster is available you can still run the Environment Manager locally. Set `ENV_MANAGER_BACKEND=docker` before launching the service:

```bash
ENV_MANAGER_BACKEND=docker python -m src.services.environment_manager.server
```

In this mode a single Docker container is created on demand (default image `python:3.11-slim-buster`). All file operations and command executions happen inside this container.
