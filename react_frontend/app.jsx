const BACKEND_API_URL = window.BACKEND_API_URL || 'http://localhost:8000';
const FINISHED_STATES = [
  'TEAM2_EXECUTION_COMPLETED',
  'TEAM2_EXECUTION_FAILED',
  'TEAM1_PLANNING_FAILED',
  'FAILED_MAX_CLARIFICATION_ATTEMPTS',
  'FAILED_AGENT_ERROR'
];

function Graph({ nodes, edges, onNodeClick, onEdgeClick }) {
  const containerRef = React.useRef(null);
  const networkRef = React.useRef(null);

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
    networkRef.current = network;
    network.on('click', params => {
      const ev = params.event?.srcEvent || {};
      const coords = { x: ev.pageX || 0, y: ev.pageY || 0 };
      if (params.nodes.length && onNodeClick) {
        onNodeClick({ id: params.nodes[0], x: coords.x, y: coords.y });
      } else if (params.edges.length && onEdgeClick) {
        const edgeId = params.edges[0];
        const edgeData = edgeDS.get(edgeId);
        if (edgeData) onEdgeClick({ edge: edgeData, x: coords.x, y: coords.y });
      }
    });
    network.fit();
    return () => network.destroy();
  }, [nodes, edges]);

  return (
    <div className="graph-wrapper">
      <div
        ref={containerRef}
        style={{ height: '600px', border: '1px solid #ccc', marginBottom: '1rem' }}
      />
      <button className="fit-button" onClick={() => networkRef.current?.fit()}>
        Recentrer
      </button>
    </div>
  );
}

function AgentStatusBar({ agents }) {
  if (!agents?.length) return null;
  return (
    <div className="agent-status-bar">
      {agents.map(a => (
        <div
          key={a.name}
          className="agent-status"
          title={(a.skills || []).join(', ')}
        >
          <span>{a.health_status || ''}</span>
          {a.name.replace('AgentServer', '')}
        </div>
      ))}
    </div>
  );
}

function PlanInfo({ plan, flowRunning }) {
  if (!plan) return null;
  return (
    <div className="plan-info">
      <div><strong>Plan ID:</strong> {plan.global_plan_id}</div>
      <div><strong>Objectif brut:</strong> {plan.raw_objective}</div>
      {plan.clarified_objective && (
        <div><strong>Objectif clarifié:</strong> {plan.clarified_objective}</div>
      )}
      <div><strong>État actuel:</strong> {plan.current_supervisor_state}</div>
      <div><strong>Flux en cours:</strong> {flowRunning ? '🟢 Oui' : '🏁 Terminé'}</div>
    </div>
  );
}

function PlanStats({ team1Counts, team2Counts }) {
  if (!team1Counts && !team2Counts) return null;
  return (
    <details className="plan-stats">
      <summary>📊 Statistiques du plan</summary>
      {team1Counts && (
        <div>
          <strong>TEAM 1</strong>
          <pre>{JSON.stringify(team1Counts, null, 2)}</pre>
        </div>
      )}
      {team2Counts && (
        <div>
          <strong>TEAM 2</strong>
          <pre>{JSON.stringify(team2Counts, null, 2)}</pre>
        </div>
      )}
    </details>
  );
}

function App() {
  const [plans, setPlans] = React.useState([]);
  const [selectedPlanId, setSelectedPlanId] = React.useState('');
  const [planDetails, setPlanDetails] = React.useState(null);
  const [team1Graph, setTeam1Graph] = React.useState(null);
  const [team1NodesMap, setTeam1NodesMap] = React.useState({});
  const [team2Graph, setTeam2Graph] = React.useState(null);
  const [team2NodesMap, setTeam2NodesMap] = React.useState({});
  const [popup, setPopup] = React.useState(null);
  const [agentsStatus, setAgentsStatus] = React.useState([]);
  const [newObjective, setNewObjective] = React.useState('');
  const [autoRefresh, setAutoRefresh] = React.useState(false);
  const [team1Counts, setTeam1Counts] = React.useState(null);
  const [team2Counts, setTeam2Counts] = React.useState(null);

  React.useEffect(() => {
    fetch(`${BACKEND_API_URL}/v1/global_plans_summary`)
      .then(res => res.json())
      .then(data => setPlans(data))
      .catch(err => console.error('Erreur chargement plans', err));
  }, []);

  React.useEffect(() => {
    fetch(`${BACKEND_API_URL}/agents_status`)
      .then(res => res.json())
      .then(list => setAgentsStatus(list))
      .catch(err => console.error('Erreur chargement statut agents', err));
  }, []);

  React.useEffect(() => {
    if (!selectedPlanId) return;
    refreshPlanDetails(selectedPlanId);
  }, [selectedPlanId]);

  React.useEffect(() => {
    if (!autoRefresh || !selectedPlanId) return;
    const id = setInterval(() => refreshPlanDetails(selectedPlanId), 5000);
    return () => clearInterval(id);
  }, [autoRefresh, selectedPlanId]);

  function refreshPlanDetails(planId) {
    fetch(`${BACKEND_API_URL}/v1/global_plans/${planId}`)
      .then(res => res.json())
      .then(plan => {
        setPlanDetails(plan);
        if (plan.team1_plan_id) {
          fetch(`${BACKEND_API_URL}/plans/${plan.team1_plan_id}`)
            .then(r => r.json())
            .then(d => {
              setTeam1NodesMap(d.nodes || {});
              setTeam1Graph(parseTaskGraph(d.nodes, true));
              setTeam1Counts(computeStateCounts(d.nodes));
            });
        } else {
          setTeam1Counts(null);
        }
        if (plan.team2_execution_plan_id) {
          fetch(`${BACKEND_API_URL}/v1/execution_task_graphs/${plan.team2_execution_plan_id}`)
            .then(r => r.json())
            .then(d => {
              setTeam2NodesMap(d.nodes || {});
              setTeam2Graph(parseTaskGraph(d.nodes, false));
              setTeam2Counts(computeStateCounts(d.nodes));
            });
        } else {
          setTeam2Graph(null);
          setTeam2NodesMap({});
          setTeam2Counts(null);
        }
      })
      .catch(err => console.error('Erreur chargement details plan', err));
  }

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

  function computeStateCounts(nodesObj) {
    if (!nodesObj) return null;
    const counts = {};
    Object.values(nodesObj).forEach(n => {
      const state = n.state || 'unknown';
      counts[state] = (counts[state] || 0) + 1;
    });
    return counts;
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

  function showArtifactForNode(nodeId, isTeam1, coords) {
    const nodeInfo = (isTeam1 ? team1NodesMap : team2NodesMap)?.[nodeId];
    if (!nodeInfo) return;

    const display = content => setPopup({ x: coords.x, y: coords.y, content });

    if (isTeam1) {
      display(formatArtifact(nodeInfo.artifact_ref));
    } else {
      const artifact = nodeInfo.output_artifact_ref;
      if (artifact) {
        fetch(`${BACKEND_API_URL}/artifacts/${artifact}`)
          .then(r => r.json())
          .then(d => display(formatArtifact(d.content)));
      }
    }
  }

  function ClarificationSection({ plan }) {
    const [answer, setAnswer] = React.useState('');
    if (!plan) return null;
    const history = plan.conversation_history || [];
    const artifact = plan.last_agent_response_artifact || {};
    const lastQuestion = plan.last_question_to_user || artifact.question_for_user;
    const enrichedObjective = plan.tentatively_enriched_objective_from_agent || artifact.tentatively_enriched_objective;

    const submitAnswer = () => {
      if (!answer) return;
      fetch(`${BACKEND_API_URL}/v1/global_plans/${plan.global_plan_id}/respond`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_response: answer })
      })
        .then(r => r.json())
        .then(() => {
          setAnswer('');
          refreshPlanDetails(plan.global_plan_id);
        })
        .catch(err => console.error('Erreur envoi clarification', err));
    };

    const forceTeam1 = () => {
      fetch(`${BACKEND_API_URL}/v1/global_plans/${plan.global_plan_id}/accept_and_plan`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_final_objective: enrichedObjective || plan.raw_objective })
      })
        .then(r => r.json())
        .then(() => refreshPlanDetails(plan.global_plan_id))
        .catch(err => console.error('Erreur acceptation objectif', err));
    };

    return (
      <div className="clarification-block">
        <h4>Clarification en cours</h4>
        <div className="chat-history">
          {history.map((h, idx) => (
            <div key={idx} className="chat-item">
              <div><strong>Agent:</strong> {h.agent_question}</div>
              <div><strong>Vous:</strong> {h.user_answer}</div>
            </div>
          ))}
          {lastQuestion && (
            <div className="chat-item">
              <div><strong>Agent:</strong> {lastQuestion}</div>
            </div>
          )}
        </div>
        {enrichedObjective && (
          <div style={{ marginBottom: '0.5rem' }}>
            <div>Objectif proposé&nbsp;:</div>
            <textarea value={enrichedObjective} readOnly rows="3" style={{ width: '100%' }} />
          </div>
        )}
        <textarea
          value={answer}
          onChange={e => setAnswer(e.target.value)}
          rows="3"
          placeholder="Votre réponse..."
          style={{ width: '100%' }}
        />
        <div style={{ marginTop: '0.5rem' }}>
          <button onClick={submitAnswer}>Envoyer</button>
          <button onClick={forceTeam1} style={{ marginLeft: '0.5rem' }}>Forcer TEAM 1</button>
        </div>
      </div>
    );
  }

  function onNodeClick(info, isTeam1) {
    showArtifactForNode(info.id, isTeam1, { x: info.x, y: info.y });
  }

  function onEdgeClick(info, isTeam1) {
    if (info.edge?.from) {
      showArtifactForNode(info.edge.from, isTeam1, { x: info.x, y: info.y });
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
        <AgentStatusBar agents={agentsStatus} />
        <div style={{ marginBottom: '0.5rem' }}>
          <button onClick={() => selectedPlanId && refreshPlanDetails(selectedPlanId)} disabled={!selectedPlanId}>
            Rafraîchir le plan
          </button>
          <label style={{ marginLeft: '1rem' }}>
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={e => setAutoRefresh(e.target.checked)}
            />
            Auto-refresh
          </label>
        </div>
        <PlanInfo plan={planDetails} flowRunning={planDetails && !FINISHED_STATES.includes(planDetails.current_supervisor_state)} />
        <PlanStats team1Counts={team1Counts} team2Counts={team2Counts} />
        {planDetails?.current_supervisor_state === 'CLARIFICATION_PENDING_USER_INPUT' && (
          <ClarificationSection plan={planDetails} />
        )}
        {team1Graph && (
          <div>
            <h4>Graphe Team 1</h4>
            <Graph
              nodes={team1Graph.nodes}
              edges={team1Graph.edges}
              onNodeClick={info => onNodeClick(info, true)}
              onEdgeClick={info => onEdgeClick(info, true)}
            />
          </div>
        )}
        {team2Graph && (
          <div>
            <h4>Graphe Exécution Team 2</h4>
            <Graph
              nodes={team2Graph.nodes}
              edges={team2Graph.edges}
              onNodeClick={info => onNodeClick(info, false)}
              onEdgeClick={info => onEdgeClick(info, false)}
            />
          </div>
        )}
        {popup && (
          <div
            className="artifact-popup"
            style={{ left: popup.x, top: popup.y }}
            onClick={() => setPopup(null)}
          >
            <span className="artifact-popup-close">&times;</span>
            <pre>{popup.content}</pre>
          </div>
        )}
      </div>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(<App />);
