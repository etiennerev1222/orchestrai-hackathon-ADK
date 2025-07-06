// react_frontend_modern/src/components/TaskGraphEditor.tsx

import React, { useEffect, useCallback, useState, useMemo } from 'react';
import ReactFlow, {
  MiniMap,
  Controls,
  Background,
  Panel,
  useNodesState,
  useEdgesState,
  addEdge,
  MarkerType,
  type Connection,
  type Edge,
  type Node,
  type NodeProps, // Type pour les props des nœuds personnalisés
  Handle, // Composant Handle pour les connexions
  Position, // Énumération pour les positions des Handles
  useReactFlow, // Hook pour accéder à l'instance de ReactFlow (fitView, etc.)
} from 'reactflow';
import 'reactflow/dist/style.css'; // Styles par défaut de ReactFlow
import api from '../api'; // Ton client API (maintenant le vrai, pas le mock)
import { v4 as uuidv4 } from 'uuid'; // Pour générer des IDs uniques
import * as dagre from 'dagre'; // <-- CHANGER ICI : Utiliser un import d'alias

// --- Constantes de couleurs et utilitaires (définies ici ou importées d'un fichier partagé) ---
const TYPE_COLORS = {
  executable: '#007bff',
  exploratory: '#ff9800',
  container: '#888888',
  decomposition: '#9c27b0'
};

const toPastel = (hex: string) => {
  if (!hex || hex[0] !== '#') return hex;
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  const mix = (c: number) => Math.round((c + 255) / 2);
  return `rgb(${mix(r)}, ${mix(g)}, ${mix(b)})`;
};

// --- Composant de Nœud Personnalisé (CustomTaskNode) ---
// Déplacé en dehors du composant principal pour optimisation (éviter React Flow warning #002)
const CustomTaskNode = ({ id, data, selected }: NodeProps<any>) => {
  const taskType = data.task_type;
  const objective = data.objective;
  const color = TYPE_COLORS[taskType as keyof typeof TYPE_COLORS] || '#6c757d'; // Fallback grey
  const bgColor = toPastel(color);

  let borderWidth = '2px';
  let borderStyle = 'solid';
  let borderColor = color;
  let boxShadow = '0 2px 4px rgba(0,0,0,0.2)';

  if (selected) {
    borderColor = 'var(--primary)';
    boxShadow = '0 0 0 2px var(--primary-hover)';
  }

  return (
    <div
      style={{
        background: bgColor,
        borderWidth: borderWidth,
        borderStyle: borderStyle,
        borderColor: borderColor,
        borderRadius: '6px',
        padding: '10px 15px',
        textAlign: 'center',
        fontWeight: 'bold',
        color: 'var(--text)',
        boxShadow: boxShadow,
        maxWidth: '180px',
        whiteSpace: 'pre-wrap',
        wordBreak: 'break-word',
      }}
    >
      {/* Handles de connexion - indispensables pour créer des liens */}
      <Handle type="target" position={Position.Top} style={{ background: 'var(--primary)', borderColor: 'var(--border)' }} />
      <Handle type="source" position={Position.Bottom} style={{ background: 'var(--primary)', borderColor: 'var(--border)' }} />

      <div style={{ fontSize: '0.8em', color: 'var(--sidebar-bg)' }}>[{taskType}]</div>
      <div style={{ fontSize: '1em', color: 'var(--text)' }}>{objective}</div>
    </div>
  );
};

// --- Définition des Types de Nœuds pour ReactFlow ---
// Cet objet est défini une seule fois au niveau du module
const NODE_TYPES_MAP = {
  customTaskNode: CustomTaskNode,
};

// --- Fonction de Layouting du Graphe avec Dagre ---
// Déplacée en dehors du composant principal pour optimisation
const getLayoutedElements = (nodesToLayout: Node[], edgesToLayout: Edge[], direction = 'TB') => {
  const dagreGraph = new dagre.graphlib.Graph();
  dagreGraph.setDefaultEdgeLabel(() => ({}));

  dagreGraph.setGraph({ rankdir: direction });

  nodesToLayout.forEach((node) => {
    // Les dimensions doivent être cohérentes avec le style de CustomTaskNode
    dagreGraph.setNode(node.id, { width: 180, height: 80 }); // Assurez-vous que ces valeurs sont appropriées
  });

  edgesToLayout.forEach((edge) => {
    dagreGraph.setEdge(edge.source, edge.target);
  });

  dagre.layout(dagreGraph);

  const layoutedNodes = nodesToLayout.map((node) => {
    const nodeWithPosition = dagreGraph.node(node.id);
    // Ajuster la position pour que le centre du nœud soit la position calculée
    node.position = {
      x: nodeWithPosition.x - nodeWithPosition.width / 2,
      y: nodeWithPosition.y - nodeWithPosition.height / 2,
    };
    return node;
  });

  return { nodes: layoutedNodes, edges: edgesToLayout };
};


// --- Composant Principal de l'Éditeur de Graphe ---
const TaskGraphEditor = ({ executionPlanId }: { executionPlanId: string }) => {
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);

  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const selectedNode = nodes.find((n) => n.id === selectedNodeId);

  // nodesMap pour un accès facile aux détails des nœuds par ID
  const nodesMap = useMemo(() => {
    return nodes.reduce((acc, node) => {
      acc[node.id] = node;
      return acc;
    }, {} as { [key: string]: Node });
  }, [nodes]);

  const { fitView } = useReactFlow();

  // --- Chargement Initial du Graphe ---
  useEffect(() => {
    console.log("useEffect for initial graph load is running. Plan ID:", executionPlanId);

    api.get(`/v1/execution_task_graphs/${executionPlanId}`).then((response: any) => {
      const graphData = response; // La réponse est directement l'objet graphe

      const rfNodes: Node[] = Object.values(graphData.nodes).map((node: any) => ({
        id: node.id,
        data: {
          objective: node.objective,
          task_type: node.task_type,
          rawDependencies: node.dependencies || [], // 'dependencies' du backend
        },
        position: { x: 0, y: 0 }, // Position temporaire, sera calculée par Dagre
        type: 'customTaskNode', // Utilise le type de nœud personnalisé
      }));

      const rfEdges: Edge[] = [];
      Object.values(graphData.nodes).forEach((node: any) => {
        node.dependencies?.forEach((depId: string) => {
          rfEdges.push({
            id: `e-${depId}-${node.id}`, // ID unique pour l'arête
            source: depId,
            target: node.id,
            type: 'default',
            animated: false,
            style: { stroke: 'var(--border)', strokeWidth: 2 },
            markerEnd: { type: MarkerType.ArrowClosed, color: 'var(--border)' },
          });
        });
      });

      // Appliquer le layout Dagre
      const { nodes: layoutedNodes, edges: layoutedEdges } = getLayoutedElements(rfNodes, rfEdges, 'TB'); // 'TB' = Top-Bottom

      setNodes(layoutedNodes);
      setEdges(layoutedEdges);

      // Ajuster la vue après un court délai pour s'assurer que le rendu est complet
      setTimeout(() => {
        fitView({ padding: 0.2 });
      }, 150);

    }).catch(error => {
      console.error("Error fetching graph data from real backend:", error);
      alert("Erreur lors du chargement du graphe. Vérifiez la console.");
    });
  }, [executionPlanId, setNodes, setEdges, fitView, getLayoutedElements]); // getLayoutedElements est une dépendance

  // --- Fonction de Détection de Cycle ---
  const detectCycle = useCallback((sourceId: string, targetId: string): boolean => {
    if (sourceId === targetId) {
        console.warn(`Attempted to connect node ${sourceId} to itself. This creates a cycle.`);
        return true;
    }
    // Créer une liste d'adjacence basée sur les dépendances (parents) pour le parcours direct
    const graphAdj: { [key: string]: string[] } = {};
    nodes.forEach(node => {
        graphAdj[node.id] = [];
    });
    edges.forEach(edge => {
        graphAdj[edge.source]?.push(edge.target); // source -> target
    });

    const visited = new Set<string>();
    const recursionStack = new Set<string>();

    const dfs = (nodeId: string): boolean => {
      visited.add(nodeId);
      recursionStack.add(nodeId);

      for (const neighborId of graphAdj[nodeId] || []) {
        if (!visited.has(neighborId)) {
          if (dfs(neighborId)) {
            return true;
          }
        } else if (recursionStack.has(neighborId)) {
          // Cycle détecté
          return true;
        }
      }
      recursionStack.delete(nodeId);
      return false;
    };

    // Pour une nouvelle arête sourceId -> targetId
    // Simuler l'ajout de l'arête pour la détection
    if (!graphAdj[sourceId]) graphAdj[sourceId] = [];
    graphAdj[sourceId].push(targetId);

    // Lancer le DFS pour détecter un cycle à partir de n'importe quel nœud après l'ajout simulé
    // C'est un peu "brute force", on peut optimiser en ne partant que des nœuds affectés.
    // Cependant, pour le moment, c'est robuste.
    for (const nodeId of Object.keys(graphAdj)) {
        if (!visited.has(nodeId)) {
            if (dfs(nodeId)) {
                // Rétablir l'état du graphe avant de retourner true
                graphAdj[sourceId].pop(); // Supprimer l'arête simulée
                return true;
            }
        }
    }
    // Rétablir l'état du graphe (s'il y a eu ajout simulé)
    graphAdj[sourceId].pop(); // Supprimer l'arête simulée

    return false;
  }, [nodes, edges]); // Dépend de l'état actuel des nœuds et arêtes


  // --- Fonction `onConnect` (Création de lien) ---
  const onConnect = useCallback(
    async (connection: Connection) => {
      if (!connection.source || !connection.target) {
        console.error('Connection source or target is null. Connection aborted.');
        return;
      }

      // 1. Détection de cycle AVANT toute modification de l'état local ou appel API
      if (detectCycle(connection.source, connection.target)) {
        alert('Impossible de créer cette dépendance : cela créerait une boucle dans le graphe.');
        console.warn('Cycle detected! Connection prevented:', connection.source, '->', connection.target);
        return;
      }

      // 2. Si pas de cycle, procéder à la création du lien
      const newEdgeId = `e-${connection.source}-${connection.target}`;
      const newEdge: Edge = {
        id: newEdgeId,
        source: connection.source,
        target: connection.target,
        type: 'default', animated: true,
        style: { stroke: 'var(--primary)', strokeWidth: 3 },
        markerEnd: { type: MarkerType.ArrowClosed, color: 'var(--primary)' },
      };
      try {
        // Appel API: POST /v1/execution_task_graphs/{executionPlanId}/dependencies
        await api.post(`/v1/execution_task_graphs/${executionPlanId}/dependencies`, {
            source_node_id: connection.source,
            target_node_id: connection.target
        });
        // Si l'API réussit, mettre à jour le frontend
        setEdges((eds) => addEdge(newEdge, eds));
        // Mise à jour des rawDependencies du nœud cible (important pour le panneau et detectCycle)
        setNodes(nds => nds.map(node => {
          if (node.id === connection.target) {
            return {
              ...node,
              data: {
                ...node.data,
                rawDependencies: [...(node.data.rawDependencies || []), connection.source]
              }
            };
          }
          return node;
        }));
      } catch (error: any) {
        console.error("Failed to add edge/dependency to backend:", error);
        alert(`Erreur lors de l'ajout de la dépendance: ${error.detail || error.message || 'Erreur inconnue'}. Vérifiez la console.`);
      }
    },
    [setEdges, setNodes, executionPlanId, detectCycle]
  );

  // --- Fonction `addTaskNode` ---
  const addTaskNode = useCallback(async () => {
    const newId = uuidv4();
    const newNode: Node = {
      id: newId,
      data: { objective: 'Nouvelle tâche', task_type: 'executable', rawDependencies: [] },
      // Les positions initiales seront ajustées par le layouting, mais donnent un point de départ
      position: { x: Math.random() * 400, y: Math.random() * 300 },
      type: 'customTaskNode',
    };
    try {
      // Appel API: POST /v1/execution_task_graphs/{executionPlanId}/nodes
      await api.post(`/v1/execution_task_graphs/${executionPlanId}/nodes`, {
          id: newId,
          objective: newNode.data.objective,
          task_type: newNode.data.task_type,
          dependencies: newNode.data.rawDependencies
      });
      // Si l'API réussit, ajouter au frontend
      setNodes((nds) => {
        const updatedNodes = [...nds, newNode];
        // Relancer le layout pour intégrer le nouveau nœud
        const { nodes: layoutedNodes, edges: layoutedEdges } = getLayoutedElements(updatedNodes, edges, 'TB');
        setEdges(layoutedEdges); // Peut-être pas nécessaire si les arêtes n'ont pas bougé
        return layoutedNodes;
      });
      // Après ajout et layout, ajuster la vue
      setTimeout(() => fitView({ padding: 0.2 }), 150);

    } catch (error: any) {
      console.error("Failed to add node to backend:", error);
      alert(`Erreur lors de l'ajout de la tâche: ${error.detail || error.message || 'Erreur inconnue'}. Vérifiez la console.`);
    }
  }, [setNodes, setEdges, executionPlanId, getLayoutedElements, edges, fitView]); // Ajouter edges et fitView, getLayoutedElements comme dépendances


  // --- Fonction `deleteNode` ---
  const deleteNode = useCallback(async (id: string) => {
    if (window.confirm(`Voulez-vous supprimer la tâche ${id} ?`)) {
      try {
        // Appel API: DELETE /v1/execution_task_graphs/{executionPlanId}/nodes/{nodeId}
        await api.delete(`/v1/execution_task_graphs/${executionPlanId}/nodes/${id}`);
        
        // Filtrer les nœuds et les arêtes localement après succès API
        setNodes((nds) => nds.filter((n) => n.id !== id));
        setEdges((eds) => eds.filter((e) => e.source !== id && e.target !== id));
        setSelectedNodeId(null);

        // Relancer le layout après suppression pour réorganiser le graphe
        // Puisque setNodes et setEdges sont asynchrones, le layout se fera au prochain rendu
        // setTimeout(() => fitView({ padding: 0.2 }), 150); // Optionally fitView after deletion
      } catch (error: any) {
        console.error("Failed to delete node from backend:", error);
        alert(`Erreur lors de la suppression de la tâche: ${error.detail || error.message || 'Erreur inconnue'}. Vérifiez la console.`);
      }
    }
  }, [setNodes, setEdges, setSelectedNodeId, executionPlanId]);

  // --- Fonction `onEdgeClick` (Suppression de lien via clic sur l'arête) ---
  const onEdgeClick = useCallback(async (event: React.MouseEvent, edge: Edge) => {
    event.stopPropagation();
    if (window.confirm(`Voulez-vous supprimer le lien de ${edge.source} vers ${edge.target} ?`)) {
      try {
        // Appel API: DELETE /v1/execution_task_graphs/{executionPlanId}/dependencies/{sourceId}/{targetId}
        await api.delete(`/v1/execution_task_graphs/${executionPlanId}/dependencies/${edge.source}/${edge.target}`);
        
        // Mettre à jour l'état local après succès API
        setEdges((eds) => eds.filter((e) => e.id !== edge.id));
        setNodes(nds => nds.map(node => {
          if (node.id === edge.target) {
            return {
              ...node,
              data: {
                ...node.data,
                rawDependencies: (node.data.rawDependencies || []).filter((depId: string) => depId !== edge.source)
              }
            };
          }
          return node;
        }));
      } catch (err: any) {
        console.error("Failed to delete edge/dependency from backend:", err);
        alert(`Erreur lors de la suppression du lien: ${err.detail || err.message || 'Erreur inconnue'}. Vérifiez la console.`);
      }
    }
  }, [setEdges, setNodes, executionPlanId]);

  // --- Fonction `removeDependency` (Suppression de lien via panneau) ---
  const removeDependency = useCallback(async (nodeId: string, depIdToRemove: string) => {
    const edgeToDelete = edges.find(e => e.source === depIdToRemove && e.target === nodeId);
    if (!edgeToDelete) {
        console.warn("Edge not found for removal:", depIdToRemove, "->", nodeId);
        return;
    }

    if (window.confirm(`Voulez-vous supprimer la dépendance de ${depIdToRemove} vers ${nodeId} ?`)) {
        try {
            // Appel API: DELETE /v1/execution_task_graphs/{executionPlanId}/dependencies/{sourceId}/{targetId}
            await api.delete(`/v1/execution_task_graphs/${executionPlanId}/dependencies/${depIdToRemove}/${nodeId}`);
            
            // Mettre à jour l'état local après succès API
            setNodes(nds => nds.map(node => {
              if (node.id === nodeId) {
                return { ...node, data: { ...node.data, rawDependencies: (node.data.rawDependencies || []).filter((depId: string) => depId !== depIdToRemove) } };
              }
              return node;
            }));
            setEdges(eds => eds.filter(edge => !(edge.source === depIdToRemove && edge.target === nodeId)));
        } catch (error: any) {
            console.error("Failed to remove dependency from backend:", error);
            alert(`Erreur lors de la suppression de la dépendance: ${error.detail || error.message || 'Erreur inconnue'}. Vérifiez la console.`);
        }
    }
  }, [setNodes, setEdges, executionPlanId, edges]); // Ajout de 'edges' comme dépendance

  // --- Fonctions `handleChange` pour Objectif et Type ---
  const handleObjectiveChange = useCallback(async (nodeId: string, newObjective: string) => {
    setNodes((nds) => {
      const updatedNodes = nds.map((n) =>
        n.id === nodeId
          ? { ...n, data: { ...n.data, objective: newObjective } }
          : n
      );
      const nodeToUpdate = updatedNodes.find(n => n.id === nodeId);
      if (nodeToUpdate) {
        api.put(`/v1/execution_task_graphs/${executionPlanId}/nodes/${nodeId}`, {
            objective: newObjective,
            task_type: nodeToUpdate.data.task_type,
            dependencies: nodeToUpdate.data.rawDependencies
        }).catch((err: any) => {
          console.error("Failed to update node objective on backend:", err);
          alert(`Erreur lors de la mise à jour de l'objectif: ${err.detail || err.message || 'Erreur inconnue'}. Vérifiez la console.`);
        });
      }
      return updatedNodes;
    });
  }, [setNodes, executionPlanId]);

  const handleTypeChange = useCallback(async (nodeId: string, newType: string) => {
    setNodes((nds) => {
      const updatedNodes = nds.map((n) =>
        n.id === nodeId
          ? { ...n, data: { ...n.data, task_type: newType } }
          : n
      );
      const nodeToUpdate = updatedNodes.find(n => n.id === nodeId);
      if (nodeToUpdate) {
        api.put(`/v1/execution_task_graphs/${executionPlanId}/nodes/${nodeId}`, {
            objective: nodeToUpdate.data.objective,
            task_type: newType,
            dependencies: nodeToUpdate.data.rawDependencies
        }).catch((err: any) => {
          console.error("Failed to update node type on backend:", err);
          alert(`Erreur lors de la mise à jour du type: ${err.detail || err.message || 'Erreur inconnue'}. Vérifiez la console.`);
        });
      }
      return updatedNodes;
    });
  }, [setNodes, executionPlanId]);


  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      onNodesChange={onNodesChange}
      onEdgesChange={onEdgesChange}
      onConnect={onConnect}
      onNodeClick={(_, node) => setSelectedNodeId(node.id)}
      onEdgeClick={onEdgeClick}
      // Suppression de la prop fitView ici car elle est appelée manuellement
      nodeTypes={NODE_TYPES_MAP} // Utilise la constante globale NODE_TYPES_MAP
    >
      <MiniMap />
      <Controls />
      <Background />
      <Panel position="top-right">
        <button onClick={addTaskNode}>➕ Ajouter une tâche</button>
      </Panel>
      {selectedNode && (
        <Panel position="top-left">
          <h4>Tâche {selectedNode.id}</h4>
          <label>Objectif:</label>
          <input
            value={selectedNode.data.objective}
            onChange={(e) => handleObjectiveChange(selectedNode.id, e.target.value)}
          />
          <label>Type:</label>
          <select
            value={selectedNode.data.task_type}
            onChange={(e) => handleTypeChange(selectedNode.id, e.target.value)}
          >
            {Object.keys(TYPE_COLORS).map(type => (
              <option key={type} value={type}>{type}</option>
            ))}
          </select>

          {/* --- Section Affichage des Dépendances --- */}
          <div style={{ marginTop: '15px', borderTop: '1px solid var(--border)', paddingTop: '10px' }}>
            <label>Dépendances:</label>
            {selectedNode.data.rawDependencies && selectedNode.data.rawDependencies.length > 0 ? (
              <ul>
                {selectedNode.data.rawDependencies.map((depId: string) => (
                  <li key={depId} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    {depId} (task: {nodesMap[depId]?.data.objective || 'N/A'})
                    <button
                      onClick={() => removeDependency(selectedNode.id, depId)}
                      style={{ background: 'transparent', color: 'var(--error-text)', border: 'none', padding: '0.2rem', marginLeft: '5px', width: 'auto', marginTop: '0' }}
                      title={`Supprimer la dépendance de ${depId}`}
                    >
                      ×
                    </button>
                  </li>
                ))}
              </ul>
            ) : (
              <p style={{ fontSize: '0.85em', color: 'var(--primary-hover)' }}>Aucune dépendance directe.</p>
            )}

            {/* Pourrait ajouter ici un champ pour ajouter une dépendance existante par ID */}
            {/* Ou des boutons pour ajouter/supprimer des arêtes directement sur le graphe */}
          </div>

          {/* --- Section Affichage des Dépendants (Tâches qui dépendent de celle-ci) --- */}
          <div style={{ marginTop: '15px', borderTop: '1px solid var(--border)', paddingTop: '10px' }}>
            <label>Dépendants:</label>
            {edges.filter(edge => edge.source === selectedNode.id).length > 0 ? (
              <ul>
                {edges.filter(edge => edge.source === selectedNode.id).map(edge => (
                  <li key={edge.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    {edge.target} (task: {nodesMap[edge.target]?.data.objective || 'N/A'})
                    <button
                      onClick={(event) => onEdgeClick(event, edge)} // Utiliser l'événement React MouseEvent
                      style={{ background: 'transparent', color: 'var(--error-text)', border: 'none', padding: '0.2rem', marginLeft: '5px', width: 'auto', marginTop: '0' }}
                      title={`Supprimer la dépendance vers ${edge.target}`}
                    >
                      ×
                    </button>
                  </li>
                ))}
              </ul>
            ) : (
              <p style={{ fontSize: '0.85em', color: 'var(--primary-hover)' }}>Aucune tâche ne dépend de celle-ci.</p>
            )}
          </div>

          <button onClick={() => deleteNode(selectedNode.id)}>🗑️ Supprimer la tâche</button>
        </Panel>
      )}
    </ReactFlow>
  );
};

export default TaskGraphEditor;