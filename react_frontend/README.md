# React Frontend

This folder contains a minimal React interface to visualize and interact with the OrchestrAI backend.

## Usage

1. Make sure the backend API is running (see project README).
2. Start a simple HTTP server in this directory:
   ```bash
   cd react_frontend
   python -m http.server 8080
   ```
3. Open [http://localhost:8080/index.html](http://localhost:8080/index.html) in your browser.

The interface fetches data from `http://localhost:8000` by default (backend API). You can override this URL by setting `BACKEND_API_URL` as a global variable before loading the scripts:

```html
<script>
  window.BACKEND_API_URL = 'http://your-backend:8000';
</script>
```

## Files

- `index.html` – entry point including CDN imports for React and Vis Network.
- `app.jsx` – main React application (loaded via Babel in the browser).
- `style.css` – styling for the dashboard (now with a dark theme by default).

The interface adopts a modern look inspired by Streamlit with the `Inter` font and dark colours.

The dashboard now exposes a **Reprendre l'exécution** button when a plan TEAM 2 is incomplete. Clicking it calls the `/v1/global_plans/<id>/resume_execution` API to continue pending tasks.
When failures occur, a **Relancer les tâches échouées** button appears to reset failed tasks via `/v1/global_plans/<id>/retry_failed_tasks`.

## Node Colours

In the Team&nbsp;2 execution graph, nodes now show additional visual cues:

- the node border colour reflects the task type (`executable`, `exploratory`, `container`, `decomposition`),
- nodes that have spawned sub-tasks have a thicker border.

## Secure Serving

For demo deployments you may want to protect the dashboard with a simple password.
Run the provided `secure_server.py` script instead of `python -m http.server`:

```bash
cd react_frontend
BASIC_AUTH_USERNAME=myuser BASIC_AUTH_PASSWORD=mypass python secure_server.py
```

The server exposes the files on port `8080` (modifiable via `PORT` environment
variable) and requires HTTP Basic authentication with the credentials specified
via `BASIC_AUTH_USERNAME` and `BASIC_AUTH_PASSWORD`.
