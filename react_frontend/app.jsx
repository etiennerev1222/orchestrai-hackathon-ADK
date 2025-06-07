const BACKEND_API_URL = window.BACKEND_API_URL || 'http://localhost:8000';

function Graph({ nodes, edges, onNodeClick, onEdgeClick }) {
  const containerRef = React.useRef(null);

  React.useEffect(() => {
    if (!containerRef.current) return;
    const data = {
      nodes: new vis.DataSet(nodes || []),
      edges: new vis.DataSet(edges || [])
    };
    const edgeDS = data.edges;
    const options = {
      layout: {
        hierarchical: {
          enabled: true,
          direction: 'UD',
          sortMethod: 'directed',
          levelSeparation: 250,
          nodeSpacing: 200
        }
      },
      physics: false
    };
    const network = new vis.Network(containerRef.current, data, options);
    network.on('click', params => {
      if (params.nodes.length && onNodeClick) {
        onNodeClick(params.nodes[0]);
      } else if (params.edges.length && onEdgeClick) {
        const edgeId = params.edges[0];
        const edgeData = edgeDS.get(edgeId);
        if (edgeData) onEdgeClick(edgeData);
      }
    });
    return () => network.destroy();
  }, [nodes, edges]);

  return <div ref={containerRef} style={{height: '600px', border: '1px solid #ccc', marginBottom:'1rem'}} />;
}

function App() {
  const [plans, setPlans] = React.useState([]);
  const [selectedPlanId, setSelectedPlanId] = React.useState('');
  const [planDetails, setPlanDetails] = React.useState(null);
  const [team1Graph, setTeam1Graph] = React.useState(null);
  const [team2Graph, setTeam2Graph] = React.useState(null);
  const [artifactContent, setArtifactContent] = React.useState('');
  const [newObjective, setNewObjective] = React.useState('');

  React.useEffect(() => {
    fetch(`${BACKEND_API_URL}/v1/global_plans_summary`)
      .then(res => res.json())
      .then(data => setPlans(data))
      .catch(err => console.error('Erreur chargement plans', err));
  }, []);

  React.useEffect(() => {
    if (!selectedPlanId) return;
    fetch(`${BACKEND_API_URL}/v1/global_plans/${selectedPlanId}`)
      .then(res => res.json())
      .then(plan => {
        setPlanDetails(plan);
        if (plan.team1_plan_id) {
          fetch(`${BACKEND_API_URL}/plans/${plan.team1_plan_id}`)
            .then(r => r.json())
            .then(d => setTeam1Graph(parseTaskGraph(d.nodes, true)));
        }
        if (plan.team2_execution_plan_id) {
          fetch(`${BACKEND_API_URL}/v1/execution_task_graphs/${plan.team2_execution_plan_id}`)
            .then(r => r.json())
            .then(d => setTeam2Graph(parseTaskGraph(d.nodes, false)));
        }
      })
      .catch(err => console.error('Erreur chargement details plan', err));
  }, [selectedPlanId]);

  function parseTaskGraph(nodesObj, isTeam1) {
    const nodes = [];
    const edges = [];
    if (!nodesObj) return { nodes, edges };
    Object.entries(nodesObj).forEach(([id, info]) => {
      let color = '#d3d3d3';
      const state = info.state;
      if (state === 'completed') color = '#d4edda';
      else if (state === 'failed' || state === 'unable_to_complete') color = '#f8d7da';
      else if (state === 'working') color = '#fff3cd';

      nodes.push({ id, label: (info.objective || id).slice(0,35), color });
      const links = isTeam1 ? info.children : info.dependencies;
      (links || []).forEach(childId => {
        if (nodesObj[childId]) {
          if (isTeam1) edges.push({ id: `${id}->${childId}`, from: id, to: childId });
          else edges.push({ id: `${childId}->${id}`, from: childId, to: id });
        }
      });
    });
    return { nodes, edges };
  }

  function submitNewPlan() {
    if (!newObjective) return;
    fetch(`${BACKEND_API_URL}/v1/global_plans`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ objective: newObjective, user_id: 'react_frontend' })
    })
      .then(r => r.json())
      .then(() => {
        setNewObjective('');
        return fetch(`${BACKEND_API_URL}/v1/global_plans_summary`)
          .then(res => res.json())
          .then(data => setPlans(data));
      })
      .catch(err => console.error('Erreur soumission plan', err));
  }

  function formatArtifact(data) {
    if (!data) return '';
    if (typeof data === 'string') {
      try {
        const obj = JSON.parse(data);
        return JSON.stringify(obj, null, 2);
      } catch {
        return data;
      }
    }
    if (typeof data === 'object') return JSON.stringify(data, null, 2);
    return String(data);
  }

  function showArtifactForNode(nodeId, isTeam1) {
    if (!planDetails) return;
    const nodeInfo = (isTeam1 ? planDetails.team1_details?.nodes : planDetails.team2_details?.nodes)?.[nodeId];
    if (!nodeInfo) return;

    if (isTeam1) {
      setArtifactContent(formatArtifact(nodeInfo.artifact_ref));
    } else {
      const artifact = nodeInfo.output_artifact_ref;
      if (artifact) {
        fetch(`${BACKEND_API_URL}/artifacts/${artifact}`)
          .then(r => r.json())
          .then(d => setArtifactContent(formatArtifact(d.content)));
      } else {
        setArtifactContent('');
      }
    }
  }

  function onNodeClick(nodeId, isTeam1) {
    showArtifactForNode(nodeId, isTeam1);
  }

  function onEdgeClick(edgeData, isTeam1) {
    if (edgeData?.from) {
      showArtifactForNode(edgeData.from, isTeam1);
    }
  }

  return (
    <div className="app">
      <div className="sidebar">
        <h3>Nouveau Plan</h3>
        <textarea value={newObjective} onChange={e => setNewObjective(e.target.value)} rows="4" style={{ width: '100%' }} />
        <button onClick={submitNewPlan} style={{ width: '100%', marginTop: '0.5rem' }}>Lancer Planification</button>
        <hr />
        <h3>Plans Existants</h3>
        <select size="10" style={{ width: '100%' }} value={selectedPlanId} onChange={e => setSelectedPlanId(e.target.value)}>
          <option value="">-- Sélectionnez --</option>
          {plans.map(p => (
            <option key={p.global_plan_id} value={p.global_plan_id}>
              {p.global_plan_id} | {p.raw_objective.slice(0, 30)}...
            </option>
          ))}
        </select>
      </div>
      <div className="content">
        {team1Graph && (
          <div>
            <h4>Graphe Team 1</h4>
            <Graph
              nodes={team1Graph.nodes}
              edges={team1Graph.edges}
              onNodeClick={id => onNodeClick(id, true)}
              onEdgeClick={edge => onEdgeClick(edge, true)}
            />
          </div>
        )}
        {team2Graph && (
          <div>
            <h4>Graphe Exécution Team 2</h4>
            <Graph
              nodes={team2Graph.nodes}
              edges={team2Graph.edges}
              onNodeClick={id => onNodeClick(id, false)}
              onEdgeClick={edge => onEdgeClick(edge, false)}
            />
          </div>
        )}
        {artifactContent && (
          <div>
            <h4>Artefact</h4>
            <pre style={{ whiteSpace: 'pre-wrap', background: '#f9f9f9', padding: '10px' }}>{artifactContent}</pre>
          </div>
        )}
      </div>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(<App />);
