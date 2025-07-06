// react_frontend_modern/src/editor_test_entry.tsx

import React from 'react';
import ReactDOM from 'react-dom/client';
import TaskGraphEditor from './components/TaskGraphEditor';
import { ReactFlowProvider } from 'reactflow'; // <-- IMPORTER ReactFlowProvider ICI

const params = new URLSearchParams(window.location.search);
const planId = 'exec_gplan_6d5c0b83c98b_425f7c1d'; // Ton ID de plan

const root = ReactDOM.createRoot(document.getElementById('root-editor')!);

root.render(
  <React.StrictMode>
    {/* Envelopper TaskGraphEditor avec ReactFlowProvider */}
    <ReactFlowProvider>
      <TaskGraphEditor executionPlanId={planId} />
    </ReactFlowProvider>
  </React.StrictMode>
);