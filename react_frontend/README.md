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
- `style.css` – simple styling for the dashboard.
