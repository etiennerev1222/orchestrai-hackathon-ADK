# Environment Manager

Internal service that creates isolated Kubernetes environments where generated code can run safely. It is mainly used by the development agent to write files, run commands and clean up pods once execution is finished.

The manager stores environment metadata in the `kubernetes_environments` Firestore collection. When no dedicated environment is found for a plan, a fallback environment identified by `exec_default` can be used. A helper script `scripts/create_fallback_environment.py` is provided to create this fallback pod.

Generated code is executed inside a working directory mounted at `/app` in each pod.

The GRA exposes `/api/environments/{env_id}` (DELETE) to remove a pod and its persistent volume claim. The React dashboard uses this endpoint to let you clean up environments.
