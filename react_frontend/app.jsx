// react_frontend/app.jsx

// La constante lit maintenant la variable globale définie dans config.js
const BACKEND_API_URL = window.CONFIG.BACKEND_API_URL || 'https://gra-server-o3o3chxieq-ew.a.run.app';
const FINISHED_STATES = [
  'TEAM2_EXECUTION_COMPLETED',
  'TEAM2_EXECUTION_FAILED',
  'TEAM1_PLANNING_FAILED',
  'FAILED_MAX_CLARIFICATION_ATTEMPTS',
  'FAILED_AGENT_ERROR'
];

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

function Graph({
  nodes,
  edges,
  onNodeClick,
  onEdgeClick,
  allowFullscreen,
  popup,
  closePopup,
  id
}) {
  const wrapperRef = React.useRef(null);
  const containerRef = React.useRef(null);
  const networkRef = React.useRef(null);
  const [isFullscreen, setIsFullscreen] = React.useState(false);

  const toggleFullscreen = () => {
    const wrapper = wrapperRef.current;
    if (!wrapper) return;
    if (!isFullscreen) {
      if (wrapper.requestFullscreen) {
        wrapper.requestFullscreen();
        setIsFullscreen(true);
      }
    } else {
      if (document.exitFullscreen) {
        document.exitFullscreen();
        setIsFullscreen(false);
      }
    }
  };

  React.useEffect(() => {
    const handler = () => {
      const elem = document.fullscreenElement;
      setIsFullscreen(elem === wrapperRef.current);
    };
    document.addEventListener('fullscreenchange', handler);
    return () => document.removeEventListener('fullscreenchange', handler);
  }, []);

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
      const rect = wrapperRef.current.getBoundingClientRect();
      const coords = {
        x: (ev.pageX || 0) - rect.left,
        y: (ev.pageY || 0) - rect.top
      };
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
    <div className="graph-wrapper" ref={wrapperRef}>
      <div
        ref={containerRef}
        style={{
          height: isFullscreen ? '100vh' : '600px',
          width: '100%',
          border: '1px solid #ccc',
          marginBottom: isFullscreen ? 0 : '1rem'
        }}
      />
      {allowFullscreen && (
        <button className="fullscreen-button" onClick={toggleFullscreen}>
          {isFullscreen ? 'Quitter plein écran' : 'Plein écran'}
        </button>
      )}
      <button className="fit-button" onClick={() => networkRef.current?.fit()}>
        Recentrer
      </button>
      {popup && popup.target === id && (
        <div
          className="artifact-popup"
          style={{ left: popup.x, top: popup.y, position: 'absolute' }}
          onClick={closePopup}
        >
          <span className="artifact-popup-close">&times;</span>
          <pre>{popup.content}</pre>
        </div>
      )}
    </div>
  );
}

function AgentStatusBar({ agents }) {
  if (!agents?.length) return null;
  return (
    <table className="agents-table">
      <thead>
        <tr>
          <th>Agent</th>
          <th>Statut</th>
          <th>Dernière mise à jour</th>
          <th>Public URL</th>
        </tr>
      </thead>
      <tbody>
        {agents.map(a => (
          <tr key={a.name} title={`Skills: ${(a.skills || []).join(', ')}\nInternal: ${a.internal_url}`}>
            <td>{a.name.replace('AgentServer', '')}</td>
            <td className={a.health_status?.includes('Online') ? 'status-online' : 'status-offline'}>
              {a.health_status || ''}
            </td>
            <td>{new Date(a.timestamp).toLocaleString()}</td>
            <td>
              <a href={a.public_url} target="_blank" rel="noopener noreferrer">
                {a.public_url}
              </a>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function PlanInfo({ plan, flowRunning, hasFailures }) {
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
      {hasFailures && (
        <div className="plan-info-failure">❌ Certaines tâches sont en échec</div>
      )}
    </div>
  );
}

function PlanStats({ team1Counts, team2Counts }) {
  if (!team1Counts && !team2Counts) return null;

  const renderTable = counts => (
    <table className="plan-stats-table">
      <tbody>
        {Object.entries(counts).map(([state, count]) => {
          const isFailed = state === 'failed' || state === 'unable_to_complete';
          return (
            <tr key={state} className={isFailed ? 'failed-state' : ''}>
              <td>{state}</td>
              <td>{count}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );

  return (
    <details className="plan-stats">
      <summary>📊 Statistiques du plan</summary>
      {team1Counts && (
        <div>
          <strong>TEAM 1</strong>
          {renderTable(team1Counts)}
        </div>
      )}
      {team2Counts && (
        <div>
          <strong>TEAM 2</strong>
          {renderTable(team2Counts)}
        </div>
      )}
    </details>
  );
}

function FinalArtifactsHistory({ nodes }) {
  const [items, setItems] = React.useState([]);

  React.useEffect(() => {
    if (!nodes || Object.keys(nodes).length === 0) {
      setItems([]);
      return;
    }
    const finals = Object.values(nodes).filter(n =>
      (n.state === 'completed' || n.state === 'failed' || n.state === 'unable_to_complete') &&
      (!n.sub_task_ids || n.sub_task_ids.length === 0) &&
      n.output_artifact_ref
    );
    Promise.all(
      finals.map(n =>
        fetch(`${BACKEND_API_URL}/artifacts/${n.output_artifact_ref}`)
          .then(r => r.json())
          .then(d => ({
            task: n.objective || n.id,
            content: formatArtifact(d.content),
            updated: n.updated_at || ''
          }))
          .catch(() => null)
      )
    ).then(list => {
      const arr = list.filter(Boolean).sort((a, b) => new Date(a.updated) - new Date(b.updated));
      setItems(arr);
    });
  }, [nodes]);

  if (!items.length) return null;

  return (
    <div className="messages-history">
      <h4>Historique des livrables finaux</h4>
      {items.map((it, idx) => (
        <div key={idx} className="message-item">
          <div><strong>Tâche:</strong> {it.task}</div>
          {it.updated && (
            <div className="msg-date">{new Date(it.updated).toLocaleString()}</div>
          )}
          <pre>{it.content}</pre>
        </div>
      ))}
    </div>
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
  const [statusFilter, setStatusFilter] = React.useState('all');
  const [stateFilter, setStateFilter] = React.useState('');

  const uniqueStates = React.useMemo(
    () => Array.from(new Set(plans.map(p => p.current_supervisor_state))).sort(),
    [plans]
  );

  const filteredPlans = React.useMemo(() => {
    let list = plans;
    if (statusFilter === 'inprogress') {
      list = list.filter(
        p => !FINISHED_STATES.includes(p.current_supervisor_state)
      );
    } else if (statusFilter === 'finished') {
      list = list.filter(p =>
        FINISHED_STATES.includes(p.current_supervisor_state)
      );
    }
    if (stateFilter) {
      list = list.filter(p => p.current_supervisor_state === stateFilter);
    }
    return list;
  }, [plans, statusFilter, stateFilter]);

  const hasFailures = React.useMemo(() => {
    const countFail = counts => (counts?.failed || 0) + (counts?.unable_to_complete || 0);
    return countFail(team1Counts) + countFail(team2Counts) > 0;
  }, [team1Counts, team2Counts]);

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

    const typeBorderColors = {
      executable: '#007bff',
      exploratory: '#ff9800',
      container: '#888888',
      decomposition: '#9c27b0'
    };

    Object.entries(nodesObj).forEach(([id, info]) => {
      let bgColor = '#d3d3d3';
      const state = info.state;
      if (state === 'completed') bgColor = '#d4edda';
      else if (state === 'failed' || state === 'unable_to_complete') bgColor = '#f8d7da';
      else if (state === 'working') bgColor = '#fff3cd';

      const nodeData = { id, label: (info.objective || id).slice(0, 35) };
      if (isTeam1) {
        nodeData.color = bgColor;
      } else {
        const borderColor = typeBorderColors[info.task_type] || '#000000';
        nodeData.color = { background: bgColor, border: borderColor };
        nodeData.borderWidth = info.sub_task_ids && info.sub_task_ids.length > 0 ? 3 : 1;
      }
      nodes.push(nodeData);

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

  function resumeExecution(planId) {
    if (!planId) return;
    fetch(`${BACKEND_API_URL}/v1/global_plans/${planId}/resume_execution`, {
      method: 'POST'
    })
      .then(r => r.json())
      .then(() => refreshPlanDetails(planId))
      .catch(err => console.error('Erreur reprise execution', err));
  }


  function showArtifactForNode(nodeId, isTeam1, coords) {
    const nodeInfo = (isTeam1 ? team1NodesMap : team2NodesMap)?.[nodeId];
    if (!nodeInfo) return;

    const display = content =>
      setPopup({ x: coords.x, y: coords.y, content, target: isTeam1 ? 'team1' : 'team2' });

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
        <div style={{ marginBottom: '0.5rem' }}>
          <label>
            Filtrer&nbsp;
            <select
              value={statusFilter}
              onChange={e => setStatusFilter(e.target.value)}
            >
              <option value="all">Tous</option>
              <option value="inprogress">En cours</option>
              <option value="finished">Terminés</option>
            </select>
          </label>
          <select
            style={{ marginLeft: '0.5rem' }}
            value={stateFilter}
            onChange={e => setStateFilter(e.target.value)}
          >
            <option value="">État: Tous</option>
            {uniqueStates.map(s => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </div>
        <select size="10" style={{ width: '100%' }} value={selectedPlanId} onChange={e => setSelectedPlanId(e.target.value)}>
          <option value="">-- Sélectionnez --</option>
          {filteredPlans.map(p => (
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
        <PlanInfo
          plan={planDetails}
          flowRunning={planDetails && !FINISHED_STATES.includes(planDetails.current_supervisor_state)}
          hasFailures={hasFailures}
        />
        {planDetails?.team2_execution_plan_id &&
          planDetails.current_supervisor_state !== 'TEAM2_EXECUTION_COMPLETED' && (
            <div style={{ marginBottom: '0.5rem' }}>
              <button onClick={() => resumeExecution(planDetails.global_plan_id)}>
                Reprendre l'exécution TEAM 2
              </button>
            </div>
          )}
        <PlanStats team1Counts={team1Counts} team2Counts={team2Counts} />
        {planDetails?.current_supervisor_state === 'CLARIFICATION_PENDING_USER_INPUT' && (
          <ClarificationSection plan={planDetails} />
        )}
        {team1Graph && (
          <div>
            <h4>Graphe Team 1</h4>
            <Graph
              id="team1"
              nodes={team1Graph.nodes}
              edges={team1Graph.edges}
              onNodeClick={info => onNodeClick(info, true)}
              onEdgeClick={info => onEdgeClick(info, true)}
              popup={popup}
              closePopup={() => setPopup(null)}
            />
          </div>
        )}
        {team2Graph && (
          <div>
            <h4>Graphe Exécution Team 2</h4>
            <Graph
              id="team2"
              nodes={team2Graph.nodes}
              edges={team2Graph.edges}
              onNodeClick={info => onNodeClick(info, false)}
              onEdgeClick={info => onEdgeClick(info, false)}
              allowFullscreen
              popup={popup}
              closePopup={() => setPopup(null)}
            />
          </div>
        )}
        {team2NodesMap && <FinalArtifactsHistory nodes={team2NodesMap} />}
      </div>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(<App />);
