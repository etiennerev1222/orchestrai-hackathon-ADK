// react_frontend/app.jsx

// This constant now reads the global variable defined in config.js
const BACKEND_API_URL = window.CONFIG.BACKEND_API_URL || 'http://localhost:8080';
const FINISHED_STATES = [
  'TEAM2_EXECUTION_COMPLETED',
  'TEAM2_EXECUTION_FAILED',
  'TEAM1_PLANNING_FAILED',
  'FAILED_MAX_CLARIFICATION_ATTEMPTS',
  'FAILED_AGENT_ERROR'
];

const TYPE_COLORS = {
  executable: '#007bff',
  exploratory: '#ff9800',
  container: '#888888',
  decomposition: '#9c27b0'
};

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

function toPastel(hex) {
  if (!hex || hex[0] !== '#') return hex;
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  const mix = (c) => Math.round((c + 255) / 2);
  return `rgb(${mix(r)}, ${mix(g)}, ${mix(b)})`;
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
          {isFullscreen ? 'Exit full screen' : 'Full screen'}
        </button>
      )}
      <button className="fit-button" onClick={() => networkRef.current?.fit()}>
        Recenter
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
  const statsMap = React.useMemo(() => {
    const map = {};
    (stats || []).forEach(s => {
      map[s.agent_name] = s;
    });
    return map;
  }, [stats]);
  if (!agents?.length && !graHealth) return null;
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
        <div className="card-header">Raw Objective</div>
        <div className="card-content">{plan.raw_objective}</div>
      </div>
      {plan.clarified_objective && (
        <div className="plan-card">
          <div className="card-header">Clarified Objective</div>
          <div className="card-content">{plan.clarified_objective}</div>
        </div>
      )}
      <div className="plan-card important">
        <div className="card-header">Current State</div>
        <div className="card-content">{plan.current_supervisor_state}</div>
      </div>
      <div className="plan-card important">
        <div className="card-header">Flow Running</div>
        <div className="card-content">{flowRunning ? '🟢 Yes' : '🏁 Finished'}</div>
      </div>
      {renderStats('TEAM 1 Stats', team1Counts)}
      {renderStats('TEAM 2 Stats', team2Counts)}
      {hasFailures && (
        <div className="plan-info-failure">❌ Some tasks have failed</div>
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
      <summary>📊 Plan statistics</summary>
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

  function detectArtifactType(content) {
    const obj = typeof content === 'string' ? parseMaybeJson(content) : content;
    if (obj && typeof obj === 'object') {
      if (obj.global_context && Array.isArray(obj.tasks)) return 'task_def';
      if (obj.evaluated_plan || obj.evaluation_notes) return 'plan';
      if (obj.summary || obj.test_status !== undefined) return 'result';
    }
    return 'other';
  }

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
      const arr = list
        .filter(Boolean)
        .sort((a, b) => new Date(a.updated) - new Date(b.updated))
        .map(it => ({ ...it, type: detectArtifactType(it.content) }));
      setItems(arr);
    });
  }, [nodes]);

  const grouped = React.useMemo(() => {
    const sections = { task_def: [], plan: [], result: [], other: [] };
    items.forEach(it => {
      sections[it.type].push(it);
    });
    return sections;
  }, [items]);

  if (!items.length) return null;

  const typeLabels = {
    task_def: 'Task definitions',
    plan: 'Plan',
    result: 'Results',
    other: 'Others'
  };

  return (
    <div className="messages-history">
      <h4>Final artifacts history</h4>
      {Object.entries(grouped).map(([type, list]) => (
        list.length ? (
          <div key={type} className="artifact-section">
            <h5>{typeLabels[type]}</h5>
            {list.map((it, idx) => (
              <div key={idx} className="message-item">
                <div><strong>Task:</strong> {it.task}</div>
                {it.updated && (
                  <div className="msg-date">{new Date(it.updated).toLocaleString()}</div>
                )}
                <FormattedContent data={it.content} open />
              </div>
            ))}
          </div>
        ) : null
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
        throw new Error(errData.detail || `Error ${response.status}`);
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
      console.error('Error fetching files:', err);
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
        throw new Error(errData.detail || 'Upload failed');
      }
      fetchFiles(currentPath);
    } catch (err) {
      console.error('Upload error:', err);
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
            <h3>File Explorer</h3>
            <p>Select a plan to view its files.</p>
        </div>
      )
  }
  return (
    <div className="file-browser">
      <h3>File Explorer (ID: {environmentId})</h3>
      <div className="path-bar">
        <span>Path: /workspace/{currentPath}</span>
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
            Upload file
          </button>
          <button
            onClick={() => fetchFiles(currentPath)}
            disabled={isLoading}
            title="Reload the file list"
          >
            Refresh
          </button>
        </div>
      </div>

      {isLoading && <p>Loading...</p>}
      {error && <p className="error-message">Error: {error}</p>}

      <table>
        <thead>
          <tr>
            <th>Type</th>
            <th>Name</th>
            <th>Size</th>
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
                    Download
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
        console.error('Initial load error', err);
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
    if (!autoRefresh) return;
    const id = setInterval(() => refreshAgentStats(), 5000);
    return () => clearInterval(id);
  }, [autoRefresh]);

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
      .catch(err => console.error('Error loading plan details', err));
  }

  function refreshAgentStats() {
    fetch(`${BACKEND_API_URL}/v1/stats/agents`)
      .then(r => r.json())
      .then(d => setAgentsStats(d.stats || d || []))
      .catch(err => console.error('Error refreshing agent stats', err));
  }

  function parseTaskGraph(nodesObj, isTeam1) {
    const nodes = [];
    const edges = [];
    if (!nodesObj) return { nodes, edges };

    Object.entries(nodesObj).forEach(([id, info]) => {
      const typeColor = TYPE_COLORS[info.task_type] || '#000000';
      const bgColor = toPastel(typeColor);
      let borderColor = '#cccccc';
      const state = info.state;
      if (state === 'completed') borderColor = '#28a745';
      else if (state === 'failed' || state === 'unable_to_complete') borderColor = '#dc3545';

      const nodeData = { id, label: (info.objective || id).slice(0, 35) };
      if (isTeam1) {
        let team1Color = '#d3d3d3';
        if (state === 'completed') team1Color = '#d4edda';
        else if (state === 'failed' || state === 'unable_to_complete') team1Color = '#f8d7da';
        else if (state === 'working') team1Color = '#fff3cd';
        nodeData.color = team1Color;
      } else {
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

  function Team2Legend() {
    const typeEntries = Object.entries(TYPE_COLORS);
    return (
      <div className="graph-legend">
        {typeEntries.map(([type, color]) => (
          <div key={type} className="legend-item">
            <span className="legend-color" style={{ background: toPastel(color) }}></span>
            {type}
          </div>
        ))}
        <div className="legend-item">
          <span className="legend-border" style={{ borderColor: '#28a745' }}></span>
          completed
        </div>
        <div className="legend-item">
          <span className="legend-border" style={{ borderColor: '#dc3545' }}></span>
          failed
        </div>
      </div>
    );
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
      .then(data => {
        const newId = data.global_plan_id;
        setNewObjective('');
        return fetch(`${BACKEND_API_URL}/v1/global_plans_summary`)
          .then(res => res.json())
          .then(plansData => {
            setPlans(plansData);
            if (newId) setSelectedPlanId(newId);
          });
      })
      .catch(err => console.error('Plan submission error', err))
      .finally(() => setPlanSubmitting(false));
  }

  function resumeExecution(planId) {
    if (!planId) return;
    fetch(`${BACKEND_API_URL}/v1/global_plans/${planId}/resume_execution`, {
      method: 'POST'
    })
      .then(r => r.json())
      .then(() => refreshPlanDetails(planId))
      .catch(err => console.error('Error resuming execution', err));
  }

  function retryFailedTasks(planId) {
    if (!planId) return;
    fetch(`${BACKEND_API_URL}/v1/global_plans/${planId}/retry_failed_tasks`, {
      method: 'POST'
    })
      .then(r => r.json())
      .then(() => refreshPlanDetails(planId))
      .catch(err => console.error('Error retrying failed tasks', err));
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
          .then(d => display(parseMaybeJson(d.content)))
          .catch(() => {
            if (nodeInfo.state === 'failed')
              display(nodeInfo.result_summary || 'Failure without details');
          });
      } else if (nodeInfo.state === 'failed') {
        display(nodeInfo.result_summary || 'Failure without details');
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
        .catch(err => console.error('Error sending clarification', err));
    };

    const forceTeam1 = () => {
      fetch(`${BACKEND_API_URL}/v1/global_plans/${plan.global_plan_id}/accept_and_plan`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_final_objective: enrichedObjective || plan.raw_objective })
      })
        .then(r => r.json())
        .then(() => refreshPlanDetails(plan.global_plan_id))
        .catch(err => console.error('Error accepting objective', err));
    };

    return (
      <div className="clarification-block">
        <h4>Clarification in progress</h4>
        <div className="chat-history">
          {history.map((h, idx) => (
            <div key={idx} className="chat-item">
              <div><strong>Agent:</strong> {h.agent_question}</div>
              <div><strong>You:</strong> {h.user_answer}</div>
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
            <div>Suggested objective&nbsp;:</div>
            <textarea value={enrichedObjective} readOnly rows="3" style={{ width: '100%' }} />
          </div>
        )}
        <textarea
          value={answer}
          onChange={e => setAnswer(e.target.value)}
          rows="3"
          placeholder="Your answer..."
          style={{ width: '100%' }}
        />
        <div style={{ marginTop: '0.5rem' }}>
          <button onClick={submitAnswer}>Send</button>
          <button onClick={forceTeam1} style={{ marginLeft: '0.5rem' }}>Force TEAM 1</button>
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
      <header className="app-header">
        <h1>OrchestrAI Dashboard</h1>
      </header>
      {(initialLoading || planSubmitting) && (
        <div className="loading-overlay">
          <div className="spinner"></div>
        </div>
      )}
      <div className="sidebar">
        <h3 title="Enter a new objective to create a plan">New Plan</h3>
        <textarea
          value={newObjective}
          onChange={e => setNewObjective(e.target.value)}
          rows="4"
          style={{ width: '100%' }}
        />
        <button
          onClick={submitNewPlan}
          disabled={planSubmitting}
          style={{ width: '100%', marginTop: '0.5rem' }}
          title="Start planning for the entered objective"
        >
          Launch planning
        </button>
        <hr />
        <details className="existing-plans">
          <summary>Existing Plans</summary>
          <div style={{ marginBottom: '0.5rem' }}>
            <label>
              Filter&nbsp;
              <select
                value={statusFilter}
                onChange={e => setStatusFilter(e.target.value)}
              >
                <option value="all">All</option>
                <option value="inprogress">In progress</option>
                <option value="finished">Finished</option>
              </select>
            </label>
            <select
              style={{ marginLeft: '0.5rem' }}
              value={stateFilter}
              onChange={e => setStateFilter(e.target.value)}
            >
              <option value="">State: All</option>
              {uniqueStates.map(s => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </div>
          <select size="10" style={{ width: '100%' }} value={selectedPlanId} onChange={e => setSelectedPlanId(e.target.value)}>
            <option value="">-- Select --</option>
            {filteredPlans.map(p => (
              <option key={p.global_plan_id} value={p.global_plan_id}>
                {p.global_plan_id} | {p.raw_objective.slice(0, 30)}...
              </option>
            ))}
          </select>
        </details>
        <hr />
      </div>
      <div className="content">
        <AgentStatusBar agents={agentsStatus} graHealth={graHealth} stats={agentsStats} />
        <div style={{ marginBottom: '0.5rem' }}>
          <button
            onClick={() => selectedPlanId && refreshPlanDetails(selectedPlanId)}
            disabled={!selectedPlanId}
            title="Reload details of the selected plan"
          >
            Refresh plan
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
                Resume TEAM 2 execution
              </button>
              {hasFailures && (
                <button style={{ marginLeft: '1rem' }} onClick={() => retryFailedTasks(planDetails.global_plan_id)}>
                  Retry failed tasks
                </button>
              )}
            </div>
          )}
        {planDetails?.current_supervisor_state === 'CLARIFICATION_PENDING_USER_INPUT' && (
          <ClarificationSection plan={planDetails} />
        )}
        {team1Graph && (
          <details className="graph-section" open>
            <summary>Team 1 graph</summary>
            <Graph
              id="team1"
              nodes={team1Graph.nodes}
              edges={team1Graph.edges}
              onNodeClick={info => onNodeClick(info, true)}
              onEdgeClick={info => onEdgeClick(info, true)}
              popup={popup}
              closePopup={() => setPopup(null)}
            />
          </details>
        )}
        {team2Graph && (
          <div>
            <h4>Team 2 execution graph</h4>
            <Team2Legend />
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
