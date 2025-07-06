// react_frontend_modern/src/editor_test_entry.tsx

import React from 'react';
import ReactDOM from 'react-dom/client';
import TaskGraphEditor from './components/TaskGraphEditor';
import { ReactFlowProvider } from 'reactflow'; // Importe ReactFlowProvider

// La variable 'params' n'est plus utilisée, nous l'avons supprimée pour les erreurs TS6133
// const params = new URLSearchParams(window.location.search);

// Utilise un ID de plan fixe pour le test
const planId = 'exec_gplan_6d5c0b83c98b_425f7c1d'; // Utilise un ID de plan existant pour le test

// Simuler la liste des compétences d'agent pour le test
const demoAvailableAgentSkills: string[] = [
  "executable", // Ces sont des types de tâches, mais peuvent être des compétences
  "exploratory",
  "container",
  "decomposition",
  "general_analysis",
  "web_research",
  "coding_python",
  "software_testing",
  "document_synthesis",
  "database_design",
  "execution_plan_decomposition"
];


const root = ReactDOM.createRoot(document.getElementById('root-editor')!);

root.render(
  <React.StrictMode>
    <ReactFlowProvider>
      {/* Passe la prop availableAgentSkills au TaskGraphEditor */}
      <TaskGraphEditor
        executionPlanId={planId}
        availableAgentSkills={demoAvailableAgentSkills} // <-- NOUVELLE PROP
      />
    </ReactFlowProvider>
  </React.StrictMode>
);