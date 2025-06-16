// react_frontend/app.jsx

// La constante lit maintenant la variable globale définie dans config.js
const BACKEND_API_URL = window.CONFIG.BACKEND_API_URL || 'http://localhost:8080';
const FINISHED_STATES = [
  'TEAM2_EXECUTION_COMPLETED',
  'TEAM2_EXECUTION_FAILED',
  'TEAM1_PLANNING_FAILED',
  'FAILED_MAX_CLARIFICATION_ATTEMPTS',
  'FAILED_AGENT_ERROR'
];

function parseMaybeJson(data) {
  if (!data) return data;
  if (typeof data === 'string') {
    try {
      return JSON.parse(data);
    } catch {
      return data;
    }
  }
  return data;
}

function FormattedContent({ data, open }) {
  const value = parseMaybeJson(data);
  const ref = React.useRef(null);

  React.useEffect(() => {
    if (ref.current && window.hljs) {
      ref.current.querySelectorAll('pre code').forEach(block => {
        window.hljs.highlightElement(block);
      });
    }
  }, [value]);

  if (value === null || value === undefined) return <span>{String(value)}</span>;
  if (typeof value === 'string') {
    const html = window.DOMPurify.sanitize(window.marked.parse(value));
    return <div ref={ref} dangerouslySetInnerHTML={{ __html: html }} />;
  }
  if (typeof value === 'number' || typeof value === 'boolean') {
    return <span>{String(value)}</span>;
  }
  if (Array.isArray(value)) {
    return (
      <details className="json-viewer" open={open}>
        <summary>Array[{value.length}]</summary>
        <div style={{ paddingLeft: '1rem' }}>
          {value.map((v, i) => (
            <div key={i}>
              <FormattedContent data={v} />
            </div>
          ))}
        </div>
      </details>
    );
  }
  if (typeof value === 'object') {
    return (
      <details className="json-viewer" open={open}>
        <summary>Object</summary>
        <div style={{ paddingLeft: '1rem' }}>
          {Object.entries(value).map(([k, v]) => (
            <div key={k} style={{ marginBottom: '0.25rem' }}>
              <strong>{k}:</strong> <FormattedContent data={v} />
            </div>
          ))}
        </div>
      </details>
    );
  }
  return <span>{String(value)}</span>;
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
  const popupRef = React.useRef(null);
  const [popupPos, setPopupPos] = React.useState({ x: 0, y: 0 });
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
        x: (ev.clientX || 0) - rect.left,
        y: (ev.clientY || 0) - rect.top
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

  React.useLayoutEffect(() => {
    if (!popup || popup.target !== id) return;
    if (!popupRef.current || !wrapperRef.current) return;
    const wrapperRect = wrapperRef.current.getBoundingClientRect();
    const popupRect = popupRef.current.getBoundingClientRect();
    let x = popup.x + 10;
    let y = popup.y + 10;
    if (x + popupRect.width > wrapperRect.width) {
      x = wrapperRect.width - popupRect.width - 10;
    }
    if (y + popupRect.height > wrapperRect.height) {
      y = wrapperRect.height - popupRect.height - 10;
    }
    if (x < 0) x = 0;
    if (y < 0) y = 0;
    setPopupPos({ x, y });
  }, [popup, id]);

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
          ref={popupRef}
          className="artifact-popup"
          style={{ left: popupPos.x, top: popupPos.y, position: 'absolute' }}
          onClick={closePopup}
        >
          <span className="artifact-popup-close">&times;</span>
          <FormattedContent data={popup.content} open />
        </div>
      )}
    </div>
  );
}

function AgentStatusBar({ agents, graHealth, stats }) {
  if (!agents?.length && !graHealth) return null;
  const statsMap = React.useMemo(() => {
    const map = {};
    (stats || []).forEach(s => {
      map[s.agent_name] = s;
    });
    return map;
  }, [stats]);
  const graCard = (
    <div
      key="gra"
      className="agent-card gra-card"
      title={`URL: ${BACKEND_API_URL}`}
    >
      <div className="agent-header">
        <div className="agent-name">GRA Server</div>
        <div className={graHealth === 'online' ? 'status-online' : 'status-offline'}>
          {graHealth === 'online' ? '✅ Online' : '⚠️ Offline'}
        </div>
      </div>
    </div>
  );

  return (
    <div className="agents-container">
      {graCard}
      {agents.map(a => (
        <div
          key={a.name}
          className="agent-card"
          title={`Skills: ${(a.skills || []).join(', ')}\nInternal: ${a.internal_url}${a.public_url ? `\nURL: ${a.public_url}` : ''}`}
        >
          <div className="agent-header">
            <div className="agent-name">{a.name.replace('AgentServer', '')}</div>
            <div className={a.health_status?.includes('Online') ? 'status-online' : 'status-offline'}>
              {a.health_status || ''}
            </div>
          </div>
          <div className="agent-timestamp">{new Date(a.timestamp).toLocaleString()}</div>
          <div className="agent-metrics">
            <div className="metric-tile success">
              {statsMap[a.name.replace('AgentServer', 'AgentExecutor')]?.tasks_completed ?? 0}
            </div>
            <div className="metric-tile fail">
              {statsMap[a.name.replace('AgentServer', 'AgentExecutor')]?.tasks_failed ?? 0}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

function PlanInfo({ plan, flowRunning, hasFailures, team1Counts, team2Counts }) {
  if (!plan) return null;
  const renderStats = (title, counts) => {
    if (!counts) return null;
    return (
      <div className="plan-card stat-card">
        <div className="card-header">{title}</div>
        <div className="card-content">
          {Object.entries(counts).map(([state, count]) => {
            const failed = state === 'failed' || state === 'unable_to_complete';
            return (
              <span key={state} className={`stat-pill ${failed ? 'failed' : ''}`}>
                {state}: {count}
              </span>
            );
          })}
        </div>
      </div>
    );
  };
  return (
    <div className="plan-cards">
      <div className="plan-card">
        <div className="card-header">Plan ID</div>
        <div className="card-content">{plan.global_plan_id}</div>
      </div>
      <div className="plan-card">
        <div className="card-header">Objectif brut</div>
        <div className="card-content">{plan.raw_objective}</div>
      </div>
      {plan.clarified_objective && (
        <div className="plan-card">
          <div className="card-header">Objectif clarifié</div>
          <div className="card-content">{plan.clarified_objective}</div>
        </div>
      )}
      <div className="plan-card important">
        <div className="card-header">État actuel</div>
        <div className="card-content">{plan.current_supervisor_state}</div>
      </div>
      <div className="plan-card important">
        <div className="card-header">Flux en cours</div>
        <div className="card-content">{flowRunning ? '🟢 Oui' : '🏁 Terminé'}</div>
      </div>
      {renderStats('Statistiques TEAM 1', team1Counts)}
      {renderStats('Statistiques TEAM 2', team2Counts)}
      {hasFailures && (
        <div className="plan-info-failure">❌ Certaines tâches sont en échec</div>
      )}
    </div>
  );
}

function PlanStats({ team1Counts, team2Counts }) {
  if (!team1Counts && !team2Counts) return null;

  const renderTiles = counts => (
    <div className="stats-tiles">
      {Object.entries(counts).map(([state, count]) => {
        const failed = state === 'failed' || state === 'unable_to_complete';
        return (
          <div key={state} className={`stat-tile ${failed ? 'failed' : ''}`}>
            <div>{state}</div>
            <div>{count}</div>
          </div>
        );
      })}
    </div>
  );

  return (
    <details className="plan-stats">
      <summary>📊 Statistiques du plan</summary>
      {team1Counts && (
        <div>
          <strong>TEAM 1</strong>
          {renderTiles(team1Counts)}
        </div>
      )}
      {team2Counts && (
        <div>
          <strong>TEAM 2</strong>
          {renderTiles(team2Counts)}
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
            content: parseMaybeJson(d.content),
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
          <FormattedContent data={it.content} open />
        </div>
      ))}
    </div>
  );
}

function FileBrowser({ environmentId, planId }) {
  const [files, setFiles] = React.useState([]);
  const [currentPath, setCurrentPath] = React.useState('.');
  const [isLoading, setIsLoading] = React.useState(false);
  const [error, setError] = React.useState(null);
  const fileInputRef = React.useRef(null);

  const fetchFiles = React.useCallback(async path => {
    if (!environmentId) return;
    setIsLoading(true);
    setError(null);
    try {
      const response = await fetch(
        `${BACKEND_API_URL}/api/environments/${environmentId}/files?path=${encodeURIComponent(
          path
        )}`
      );
      if (!response.ok) {
        const errData = await response.json();
        throw new Error(errData.detail || `Erreur ${response.status}`);
      }
      const data = await response.json();
      data.sort((a, b) => {
        if (a.type === 'directory' && b.type !== 'directory') return -1;
        if (a.type !== 'directory' && b.type === 'directory') return 1;
        return a.name.localeCompare(b.name);
      });
      setFiles(data);
      setCurrentPath(path);
    } catch (err) {
      console.error('Erreur lors de la récupération des fichiers:', err);
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  }, [environmentId]);
  React.useEffect(() => {
    // Ce useEffect gère le changement d'environmentId.
    // Il réinitialise le chemin et lance le fetch.
    setCurrentPath('.');
    fetchFiles('.');
  }, [environmentId, planId]); // planId est gardé pour forcer le refresh si on resélectionne le même plan

  const handleDirectoryClick = name => {
    const newPath = currentPath === '.' ? name : `${currentPath}/${name}`;
    fetchFiles(newPath);
  };

  const handleBackClick = () => {
    if (currentPath === '.') return;
    const parentPath =
      currentPath.substring(0, currentPath.lastIndexOf('/')) || '.';
    fetchFiles(parentPath);
  };

  const handleDownload = name => {
    const filePath = currentPath === '.' ? name : `${currentPath}/${name}`;
    const url = `${BACKEND_API_URL}/api/environments/${environmentId}/files/download?path=${encodeURIComponent(
      filePath
    )}`;
    window.open(url, '_blank');
  };

  const handleUpload = async e => {
    const file = e.target.files[0];
    if (!file) return;
    const formData = new FormData();
    formData.append('file', file);
    formData.append('path', `${currentPath}/${file.name}`);
    setError(null);
    try {
      const response = await fetch(
        `${BACKEND_API_URL}/api/environments/${environmentId}/files/upload`,
        {
          method: 'POST',
          body: formData
        }
      );
      if (!response.ok) {
        const errData = await response.json();
        throw new Error(errData.detail || 'Échec du téléversement');
      }
      fetchFiles(currentPath);
    } catch (err) {
      console.error('Erreur de téléversement:', err);
      setError(err.message);
    } finally {
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const formatBytes = (bytes, decimals = 2) => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const dm = decimals < 0 ? 0 : decimals;
    const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
  };

  if (!environmentId) {
      return (
        <div className="file-browser">
            <h3>Explorateur de Fichiers</h3>
            <p>Sélectionnez un plan pour voir ses fichiers.</p>
        </div>
      )
  }
  return (
    <div className="file-browser">
      <h3>Explorateur de Fichiers (ID: {environmentId})</h3>
      <div className="path-bar">
        <span>Chemin: /workspace/{currentPath}</span>
        <div className="file-actions">
          <input
            type="file"
            ref={fileInputRef}
            onChange={handleUpload}
            style={{ display: 'none' }}
          />
          <button
            onClick={() =>
              fileInputRef.current && fileInputRef.current.click()
            }
          >
            Téléverser un fichier
          </button>
          <button onClick={() => fetchFiles(currentPath)} disabled={isLoading}>
            Rafraîchir
          </button>
        </div>
      </div>

      {isLoading && <p>Chargement...</p>}
      {error && <p className="error-message">Erreur: {error}</p>}

      <table>
        <thead>
          <tr>
            <th>Type</th>
            <th>Nom</th>
            <th>Taille</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {currentPath !== '.' && (
            <tr className="clickable-row" onClick={handleBackClick}>
              <td>📁</td>
              <td>..</td>
              <td></td>
              <td></td>
            </tr>
          )}
          {files.map(file => (
            <tr
              key={file.name}
              className={file.type === 'directory' ? 'clickable-row' : ''}
              onClick={() =>
                file.type === 'directory' && handleDirectoryClick(file.name)
              }
            >
              <td>{file.type === 'directory' ? '📁' : '📄'}</td>
              <td>{file.name}</td>
              <td>{file.type === 'file' ? formatBytes(file.size) : ''}</td>
              <td>
                {file.type === 'file' && (
                  <button
                    onClick={e => {
                      e.stopPropagation();
                      handleDownload(file.name);
                    }}
                  >
                    Télécharger
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
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
  const [agentsStats, setAgentsStats] = React.useState([]);
  const [newObjective, setNewObjective] = React.useState('');
  const [autoRefresh, setAutoRefresh] = React.useState(false);
  const [team1Counts, setTeam1Counts] = React.useState(null);
  const [team2Counts, setTeam2Counts] = React.useState(null);
  const [statusFilter, setStatusFilter] = React.useState('all');
  const [stateFilter, setStateFilter] = React.useState('');
  const [graHealth, setGraHealth] = React.useState(null);
  const [initialLoading, setInitialLoading] = React.useState(true);
  const [planSubmitting, setPlanSubmitting] = React.useState(false);
  const [activeEnvironmentId, setActiveEnvironmentId] = React.useState(null);

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
    async function fetchInitial() {
      try {
        const [plansRes, agentsRes, statsRes, healthRes] = await Promise.all([
          fetch(`${BACKEND_API_URL}/v1/global_plans_summary`),
          fetch(`${BACKEND_API_URL}/agents_status`),
          fetch(`${BACKEND_API_URL}/v1/stats/agents`),
          fetch(`${BACKEND_API_URL}/health`)
        ]);
        const plansData = await plansRes.json();
        setPlans(plansData);
        const agentsList = await agentsRes.json();
        setAgentsStatus(agentsList);
        const statsData = await statsRes.json();
        setAgentsStats(statsData.stats || statsData || []);
        setGraHealth(healthRes.ok ? 'online' : 'offline');
      } catch (err) {
        console.error('Erreur chargement initial', err);
      } finally {
        setInitialLoading(false);
      }
    }
    fetchInitial();
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

  React.useEffect(() => {
    // Met à jour automatiquement l'environmentId lorsque les détails du plan
    // sont chargés ou changent. Le FileBrowser utilise cet ID pour se
    // synchroniser avec l'environnement créé pour TEAM 2.
    if (planDetails && planDetails.team2_execution_plan_id) {
      setActiveEnvironmentId(planDetails.team2_execution_plan_id);
    } else {
      setActiveEnvironmentId(null);
    }
  }, [planDetails?.team2_execution_plan_id]);

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
    setPlanSubmitting(true);
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
      .catch(err => console.error('Erreur soumission plan', err))
      .finally(() => setPlanSubmitting(false));
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
      display(parseMaybeJson(nodeInfo.artifact_ref));
    } else {
      const artifact = nodeInfo.output_artifact_ref;
      if (artifact) {
        fetch(`${BACKEND_API_URL}/artifacts/${artifact}`)
          .then(r => r.json())
          .then(d => display(parseMaybeJson(d.content)));
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
      {(initialLoading || planSubmitting) && (
        <div className="loading-overlay">
          <div className="spinner"></div>
        </div>
      )}
      <div className="sidebar">
        <h3>Nouveau Plan</h3>
        <textarea value={newObjective} onChange={e => setNewObjective(e.target.value)} rows="4" style={{ width: '100%' }} />
        <button onClick={submitNewPlan} disabled={planSubmitting} style={{ width: '100%', marginTop: '0.5rem' }}>Lancer Planification</button>
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
        <hr />
        <h3>Environment ID</h3>
        <input
          type="text"
          value={activeEnvironmentId}
          onChange={e => setActiveEnvironmentId(e.target.value)}
          style={{ width: '100%' }}
        />
      </div>
      <div className="content">
        <AgentStatusBar agents={agentsStatus} graHealth={graHealth} stats={agentsStats} />
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
          team1Counts={team1Counts}
          team2Counts={team2Counts}
        />
        {planDetails?.team2_execution_plan_id &&
          planDetails.current_supervisor_state !== 'TEAM2_EXECUTION_COMPLETED' && (
            <div style={{ marginBottom: '0.5rem' }}>
              <button onClick={() => resumeExecution(planDetails.global_plan_id)}>
                Reprendre l'exécution TEAM 2
              </button>
            </div>
          )}
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
        {activeEnvironmentId && (
          <FileBrowser key={selectedPlanId} planId={selectedPlanId} environmentId={activeEnvironmentId} />
        )}
      </div>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(<App />);
