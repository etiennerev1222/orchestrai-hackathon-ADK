# React Frontend (Vite + TypeScript)

This folder contains the modern React dashboard used by OrchestrAI.
It replaces the legacy `react_frontend` project and is powered by
[Vite](https://vitejs.dev/) and TypeScript.

## Development

```bash
cd react_frontend_modern
npm install
npm run dev
```

The dev server runs on <http://localhost:5173> and expects a
`public/config.js` file setting `window.CONFIG.BACKEND_API_URL` to the
GRA endpoint.

## Build & Deploy

```bash
npm run build
```

The generated files under `dist/` are deployed to Firebase Hosting by
running `./deployment.sh deploy_frontend` from the repository root.

## TaskGraphEditor

The dashboard embeds a `TaskGraphEditor` component based on React Flow.
It uses the GRA's CRUD API to create, update and delete nodes and
dependencies of an execution plan.

