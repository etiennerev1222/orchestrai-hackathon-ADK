import React, { useEffect, useState } from 'react';
import ReactFlow, {
  Background,
  Controls,
  addEdge,
  MiniMap,
  Connection,
  Edge,
  Node,
} from 'reactflow';
import 'reactflow/dist/style.css';
import api from '../utils/api';

type TaskNode = {
  id: string;
  objective: string;
  task_type: string;
  assigned_agent_type?: string;
  state: string;
  dependencies: string[];
};

type GraphData = {
  nodes: Record<string, TaskNode>;
  root_task_ids: string[];
};

interface Props {
  executionPlanId: string;
}

export default function TaskGraphEditor({ executionPlanId }: Props) {
  const [graph, setGraph] = useState<GraphData | null>(null);
  const [rfNodes, setRfNodes] = useState<Node[]>([]);
  const [rfEdges, setRfEdges] = useState<Edge[]>([]);

  useEffect(() => {
    api.get(`/execution_task_graphs/${executionPlanId}`)
      .then(res => setGraph(res.data))
      .catch(() => {});
  }, [executionPlanId]);

  useEffect(() => {
    if (!graph) return;
    const nodes: Node[] = Object.values(graph.nodes).map(n => ({
      id: n.id,
      data: { label: `${n.objective} (${n.state})` },
      position: { x: Math.random() * 250, y: Math.random() * 250 },
    }));
    const edges: Edge[] = [];
    Object.values(graph.nodes).forEach(n => {
      n.dependencies.forEach(d => {
        edges.push({ id: `${d}-${n.id}`, source: d, target: n.id });
      });
    });
    setRfNodes(nodes);
    setRfEdges(edges);
  }, [graph]);

  const onConnect = (params: Edge | Connection) =>
    setRfEdges(eds => addEdge(params, eds));

  return (
    <div style={{ height: 600 }}>
      <ReactFlow nodes={rfNodes} edges={rfEdges} onConnect={onConnect}>
        <Background />
        <MiniMap />
        <Controls />
      </ReactFlow>
    </div>
  );
}
