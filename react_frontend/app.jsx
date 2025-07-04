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

function AgentStatusBar({ agents, graHealth, stats, onViewLogs, onRestart }) {
    // Ce composant ne gère plus son propre état, il reçoit tout via les props.
    // C'est une meilleure pratique dans React.

    const statsMap = React.useMemo(() => {
        const map = {};
        (stats || []).forEach(s => {
            map[s.agent_name] = s;
        });
        return map;
    }, [stats]);

    const getStatusInfo = (healthStatus) => {
        const state = healthStatus?.state || 'Offline';
        switch (state.toUpperCase()) {
            case 'IDLE': return { className: 'status-idle', icon: '🔵' };
            case 'BUSY': return { className: 'status-busy', icon: '⚙️' };
            case 'SLEEPING': return { className: 'status-sleeping', icon: '💤' };
            case 'STARTING': return { className: 'status-starting', icon: '🚀' };
            case 'ONLINE': case 'ONLINE (LEGACY)': return { className: 'status-online', icon: '✅' };
            case 'ERROR': return { className: 'status-error', icon: '🔥' };
            default: return { className: 'status-offline', icon: '⚠️' };
        }
    };

  const agentList = Array.isArray(agents) ? agents : [];
  if (!agentList.length && !graHealth) return null;

  // La carte pour le GRA reste inchangée
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
      <div className="agent-actions">
        <button
          className="icon-btn"
          title="View logs"
          onClick={() => onViewLogs && onViewLogs('gra')}
        >
          <i className="fa-solid fa-file-lines"></i>
        </button>
      </div>
    </div>
  );
  const supervisorsNames = ['GlobalSupervisorLogic', 'ExecutionSupervisorLogic'];
  const supervisors = agentList.filter(a => supervisorsNames.includes(a.name));
  const otherAgents = agentList.filter(a => !supervisorsNames.includes(a.name));

  const renderCard = a => {
          const { className, icon } = getStatusInfo(a.health_status);
          const stateText = a.health_status?.state || 'Offline';
          const tooltip = `Skills: ${(a.skills || []).join(', ')}\n` +
                          `Internal: ${a.internal_url}\n` +
                          (a.public_url ? `URL: ${a.public_url}\n` : '') +
                          (a.health_status?.current_task_id ? `Task: ${a.health_status.current_task_id}` : 'No active task');

          return (
            <div key={a.name} className="agent-card" title={tooltip}>
              <div className="agent-header">
                <div className="agent-name">{a.name.replace('AgentServer', '')}</div>
                <div className={className}>{icon} {stateText}</div>
              </div>
              <div className="agent-timestamp">{a.timestamp ? new Date(a.timestamp).toLocaleString() : '–'}</div>
              <div className="agent-metrics">
                {(() => {
                  const statKey = a.name;
                  const altKey = a.name.replace('AgentServer', 'AgentExecutor');
                  const stat = statsMap[statKey] || statsMap[altKey];
                  return (
                    <>
                      <div className="metric-tile success">
                        {stat?.tasks_completed ?? 0}
                      </div>
                      <div className="metric-tile fail">
                        {stat?.tasks_failed ?? 0}
                      </div>
                    </>
                  );
                })()}
              </div>
              <div className="agent-actions">
                {a.public_url && (
                  <button
                    className="icon-btn"
                    title="View logs"
                    onClick={() => onViewLogs && onViewLogs(a)}
                  >
                    <i className="fa-solid fa-file-lines"></i>
                  </button>
                )}
                <button
                  className="icon-btn"
                  title="Restart agent"
                  onClick={() => onRestart && onRestart(a)}
                >
                  <i className="fa-solid fa-rotate-right"></i>
                </button>
              </div>
            </div>
          );
        };

  return (
      <div className="agents-container">
        <div className="agents-group">
          {graCard}
          {supervisors.map(renderCard)}
        </div>
        <div className="agents-group">
          {otherAgents.map(renderCard)}
        </div>
      </div>
    );
}

function PlanInfo({ plan, flowRunning, hasFailures, team1Counts, team2Counts, onDeleteEnvironment }) {
  if (!plan) return null;

  const renderStatSection = (title, counts) => {
    if (!counts) return null;
    return (
      <div className="stat-section">
        <div className="card-header">{title}</div>
        <div className="card-content">
          {Object.entries(counts).map(([state, count]) => {
            const failed = state === 'failed' || state === 'unable_to_complete';
            return (
              <span key={state} className={`stat-pill ${failed ? 'failed' : ''}`}>{state}: {count}</span>
            );
          })}
        </div>
      </div>
    );
  };

  return (
    <div className="plan-cards">
      <details className="plan-meta" open>
        <summary>Plan details</summary>
        <div className="plan-cards">
          <div className="plan-card grouped-info">
            <div className="info-row">
              <div className="card-header">Plan ID</div>
              <div className="card-content">{plan.global_plan_id}</div>
            </div>
            {plan.environment_id && (
              <div className="info-row">
                <div className="card-header">Environment ID</div>
                <div className="card-content">
                  {plan.environment_id}
                  {onDeleteEnvironment && (
                    <button
                      style={{ marginLeft: '0.5rem' }}
                      onClick={() => onDeleteEnvironment(plan.environment_id)}
                      title="Delete this environment"
                    >
                      🗑
                    </button>
                  )}
                </div>
              </div>
            )}
            <div className="info-row">
              <div className="card-header">Raw Objective</div>
              <div className="card-content">{plan.raw_objective}</div>
            </div>
          </div>
          {plan.clarified_objective && (
            <div className="plan-card">
              <div className="card-header">Clarified Objective</div>
              <div className="card-content">{plan.clarified_objective}</div>
            </div>
          )}
        </div>
      </details>
      <div className="plan-card important">
        <div className="card-header">Current State</div>
        <div className="card-content">
          {plan.current_supervisor_state} – {flowRunning ? '🟢 Flow running' : '🏁 Finished'}
        </div>
      </div>
      {(team1Counts || team2Counts) && (
        <div className="plan-card stat-card combined-stats">
          {renderStatSection('TEAM 1 Stats', team1Counts)}
          {renderStatSection('TEAM 2 Stats', team2Counts)}
        </div>
      )}
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
  const [preview, setPreview] = React.useState(null); // {name, content}
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

  const handleDownload = async name => {
    const filePath = currentPath === '.' ? name : `${currentPath}/${name}`;
    const url = `${BACKEND_API_URL}/api/environments/${environmentId}/files/download?path=${encodeURIComponent(
      filePath
    )}`;
    try {
      const response = await fetch(url);
      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || 'Download failed');
      }
      const blob = await response.blob();
      const downloadUrl = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = downloadUrl;
      a.download = name;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(downloadUrl);
    } catch (err) {
      console.error('Download error:', err);
      setError(err.message);
    }
  };

  const handlePreview = async name => {
    const filePath = currentPath === '.' ? name : `${currentPath}/${name}`;
    const url = `${BACKEND_API_URL}/api/environments/${environmentId}/files/download?path=${encodeURIComponent(filePath)}`;
    try {
      const response = await fetch(url);
      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || 'Unable to load file');
      }
      const text = await response.text();
      setPreview({ name, content: text });
    } catch (err) {
      console.error('Preview error:', err);
      setError(err.message);
    }
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
        <span>Path: /app/{currentPath}</span>
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
                {file.type === 'file' && (
                  <button
                    onClick={e => {
                      e.stopPropagation();
                      handlePreview(file.name);
                    }}
                    style={{ marginLeft: '0.5rem' }}
                  >
                    View
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {preview && (
        <div className="file-preview-overlay" onClick={() => setPreview(null)}>
          <div className="file-preview" onClick={e => e.stopPropagation()}>
            <span className="file-preview-close" onClick={() => setPreview(null)}>×</span>
            <h4>{preview.name}</h4>
            <pre>{preview.content}</pre>
          </div>
        </div>
      )}
    </div>
  );
}

function App() {

   // --- 1. GESTION DE L'ÉTAT ---
  const [initialLoading, setInitialLoading] = React.useState(true);
  const [agents, setAgents] = React.useState([]);
  const [plans, setPlans] = React.useState([]);
  const [stats, setStats] = React.useState([]);
  const [graHealth, setGraHealth] = React.useState('offline');
  
  const [selectedPlanId, setSelectedPlanId] = React.useState('');
  const [planDetails, setPlanDetails] = React.useState(null);
  const [team1Graph, setTeam1Graph] = React.useState(null);
  const [team2Graph, setTeam2Graph] = React.useState(null);
  const [team1NodesMap, setTeam1NodesMap] = React.useState({});
  const [team2NodesMap, setTeam2NodesMap] = React.useState({});
  const [popup, setPopup] = React.useState(null);
  const [newObjective, setNewObjective] = React.useState('');
  const [autoRefresh, setAutoRefresh] = React.useState(true);
  const [planSubmitting, setPlanSubmitting] = React.useState(false);
  const [statusFilter, setStatusFilter] = React.useState('all');
  const [stateFilter, setStateFilter] = React.useState('');
  const [activeEnvironmentId, setActiveEnvironmentId] = React.useState(null);
  const [showFileBrowser, setShowFileBrowser] = React.useState(false);
  const [team1Counts, setTeam1Counts] = React.useState(null);
  const [team2Counts, setTeam2Counts] = React.useState(null);
  const [highlightFailed, setHighlightFailed] = React.useState(false);
  const [highlightWorking, setHighlightWorking] = React.useState(false);
  const [highlightCompleted, setHighlightCompleted] = React.useState(false);
  const [logModal, setLogModal] = React.useState(null); // {agentName, logs}
  const [envModal, setEnvModal] = React.useState(null); // environment id to delete

  
  // --- 2. EFFETS (Hooks pour le cycle de vie) ---
  
  // Effet pour les WebSockets (temps réel)
  React.useEffect(() => {
    const wsUrl = `${BACKEND_API_URL.replace(/^http/, 'ws')}/ws/status`;
    const socket = new WebSocket(wsUrl);
    socket.onopen = () => console.log("WebSocket connection established.");
    socket.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        if (Array.isArray(payload)) {
          setAgents(payload);
        } else {
          if (payload.agents) {
            const list = Array.isArray(payload.agents)
              ? payload.agents
              : Object.values(payload.agents);
            setAgents(list);
          }
          if (payload.gra_status)
            setGraHealth(
              payload.gra_status.state?.toLowerCase() === "running"
                ? "online"
                : "offline"
            );
        }
      } catch (err) {
        console.error("Error parsing WebSocket payload", err);
      }
    };
    socket.onerror = (error) => console.error("WebSocket Error:", error);
    socket.onclose = () => console.log("WebSocket connection closed.");
    return () => socket.close();
  }, []);

  // Effet pour le chargement initial et le polling
  React.useEffect(() => {
    const fetchPolledData = async () => {
      try {
        const [plansRes, statsRes, healthRes] = await Promise.all([
          fetch(`${BACKEND_API_URL}/v1/global_plans_summary`),
          fetch(`${BACKEND_API_URL}/v1/stats/agents`),
          fetch(`${BACKEND_API_URL}/health`),
        ]);
        setPlans(await plansRes.json());
        const statsData = await statsRes.json();
        setStats(statsData.stats || []);
        setGraHealth(healthRes.ok ? 'online' : 'offline');
      } catch (err) {
        console.error('Error fetching polled data:', err);
      } finally {
        if (initialLoading) setInitialLoading(false);
      }
    };
    fetchPolledData();
    const intervalId = setInterval(fetchPolledData, 30000); // Toutes les 30s
    return () => clearInterval(intervalId);
  }, [initialLoading]);

  // Effet pour rafraîchir les détails du plan sélectionné
  const refreshPlanDetails = React.useCallback((planId) => {
    if (!planId) return;
    fetch(`${BACKEND_API_URL}/v1/global_plans/${planId}`).then(res => res.json()).then(plan => {
        setPlanDetails(plan);
        if (plan.team1_plan_id) {
          fetch(`${BACKEND_API_URL}/plans/${plan.team1_plan_id}`).then(r => r.json()).then(d => {
            setTeam1NodesMap(d.nodes || {}); setTeam1Graph(parseTaskGraph(d.nodes, true)); setTeam1Counts(computeStateCounts(d.nodes));
          });
        }
        if (plan.team2_execution_plan_id) {
          fetch(`${BACKEND_API_URL}/v1/execution_task_graphs/${plan.team2_execution_plan_id}`).then(r => r.json()).then(d => {
            setTeam2NodesMap(d.nodes || {});
            setTeam2Counts(computeStateCounts(d.nodes));
          });
        }
    }).catch(err => console.error('Error loading plan details', err));
  }, []);

  React.useEffect(() => {
    if (selectedPlanId) refreshPlanDetails(selectedPlanId);
  }, [selectedPlanId, refreshPlanDetails]);

  React.useEffect(() => {
    if (autoRefresh && selectedPlanId) {
      const intervalId = setInterval(() => refreshPlanDetails(selectedPlanId), 5000);
      return () => clearInterval(intervalId);
    }
  }, [autoRefresh, selectedPlanId, refreshPlanDetails]);
  
  React.useEffect(() => {
    if (planDetails) {
      const envId = planDetails.environment_id ||
        (planDetails.global_plan_id ? `exec-${planDetails.global_plan_id}` : null);
      if (envId) setActiveEnvironmentId(envId);
      else setActiveEnvironmentId(null);
    } else {
      setActiveEnvironmentId(null);
    }
  }, [planDetails]);

  React.useEffect(() => {
    const states = [];
    if (highlightFailed) states.push('failed');
    if (highlightWorking) states.push('working');
    if (highlightCompleted) states.push('completed');
    if (team2NodesMap && Object.keys(team2NodesMap).length > 0) {
      setTeam2Graph(parseTaskGraph(team2NodesMap, false, states));
    } else {
      setTeam2Graph(null);
    }
  }, [team2NodesMap, highlightFailed, highlightWorking, highlightCompleted]);

  // --- 3. FONCTIONS MEMOIZED et HANDLERS ---
  const uniqueStates = React.useMemo(() => Array.from(new Set(plans.map(p => p.current_supervisor_state))).sort(), [plans]);
  const filteredPlans = React.useMemo(() => {
    let list = plans;
    if (statusFilter === 'inprogress') list = list.filter(p => !FINISHED_STATES.includes(p.current_supervisor_state));
    else if (statusFilter === 'finished') list = list.filter(p => FINISHED_STATES.includes(p.current_supervisor_state));
    if (stateFilter) list = list.filter(p => p.current_supervisor_state === stateFilter);
    return list;
  }, [plans, statusFilter, stateFilter]);

  const hasFailures = React.useMemo(() => {
    const countFail = counts => (counts?.failed || 0) + (counts?.unable_to_complete || 0);
    return countFail(team1Counts) + countFail(team2Counts) > 0;
  }, [team1Counts, team2Counts]);

  const onNodeClick = (info, isTeam1) => showArtifactForNode(info.id, isTeam1, { x: info.x, y: info.y });
  const onEdgeClick = (info, isTeam1) => { if (info.edge?.from) showArtifactForNode(info.edge.from, isTeam1, { x: info.x, y: info.y }); };

  // Toutes vos autres fonctions doivent être déclarées ici...) showArtifactForNode(info.edge.from, isTeam1, { x: info.x, y: info.y }); };
  
 
  function parseTaskGraph(nodesObj, isTeam1, highlightStates = []) {
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
        let size = 25;
        if (highlightStates.length) {
          if (highlightStates.includes(state)) {
            size = 40;
          } else {
            nodeData.color = { background: '#EFEFEF', border: '#C0C0C0' };
            size = 15;
          }
        }
        nodeData.size = size;
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

  async function openLogs(target) {
    const name = typeof target === 'string' ? target : target?.name;
    if (!name) return;
    const url =
      name === 'gra'
        ? `${BACKEND_API_URL}/v1/gra/logs`
        : `${BACKEND_API_URL}/v1/agents/${encodeURIComponent(name)}/logs`;
    try {
      const res = await fetch(url);
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || `HTTP ${res.status}`);
      }
      const data = await res.json();
      const logs = Array.isArray(data) ? data : [JSON.stringify(data)];
      const displayName = name === 'gra' ? 'GRA Server' : name;
      setLogModal({ agentName: displayName, logs });
    } catch (err) {
      const displayName = name === 'gra' ? 'GRA Server' : name;
      setLogModal({ agentName: displayName, logs: [`Error: ${err.message}`] });
    }
  }

  function restartAgent(agent) {
    if (!agent?.name) return;
    fetch(`${BACKEND_API_URL}/v1/agents/${encodeURIComponent(agent.name)}/restart`, {
      method: 'POST'
    })
      .catch(err => console.error('Error restarting agent', err));
  }

  function confirmDeleteEnvironment(envId) {
    if (!envId) return;
    fetch(`${BACKEND_API_URL}/api/environments/${envId}`, { method: 'DELETE' })
      .then(res => {
        if (!res.ok) return res.json().then(d => Promise.reject(d));
        return res.json();
      })
      .then(() => {
        setEnvModal(null);
        if (selectedPlanId) refreshPlanDetails(selectedPlanId);
      })
      .catch(err => {
        console.error('Error deleting environment', err);
        setEnvModal(null);
      });
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
      const initialRequest = nodeInfo.objective;
      if (artifact) {
        fetch(`${BACKEND_API_URL}/artifacts/${artifact}`)
          .then(r => r.json())
          .then(d => {
            const artContent = parseMaybeJson(d.content);
            if (nodeInfo.state === 'failed') {
              display({ initial_request: initialRequest, artifact: artContent });
            } else {
              display(artContent);
            }
          })
          .catch(() => {
            if (nodeInfo.state === 'failed')
              display({
                initial_request: initialRequest,
                summary: nodeInfo.result_summary || 'Failure without details'
              });
          });
      } else if (nodeInfo.state === 'failed') {
        display({
          initial_request: initialRequest,
          summary: nodeInfo.result_summary || 'Failure without details'
        });
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



  // --- 4. RENDU DU COMPOSANT ---
  if (initialLoading) {
    return <div className="loading-overlay"><div className="spinner"></div></div>;
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
        {/* On passe les états en props aux composants enfants */}
        <AgentStatusBar agents={agents} graHealth={graHealth} stats={stats} onViewLogs={openLogs} onRestart={restartAgent} />
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
          <label style={{ marginLeft: '1rem' }} title="Toggle the file explorer">
            <input
              type="checkbox"
              checked={showFileBrowser}
              onChange={e => setShowFileBrowser(e.target.checked)}
            />
            Show file explorer
          </label>
        </div>
        
        <PlanInfo
          plan={planDetails}
          flowRunning={planDetails && !FINISHED_STATES.includes(planDetails.current_supervisor_state)}
          hasFailures={hasFailures}
          team1Counts={team1Counts}
          team2Counts={team2Counts}
          onDeleteEnvironment={envId => setEnvModal(envId)}
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
            <div style={{ marginBottom: '0.5rem' }}>
              Highlight states:
              <label style={{ marginLeft: '0.5rem' }}>
                <input
                  type="checkbox"
                  checked={highlightFailed}
                  onChange={e => setHighlightFailed(e.target.checked)}
                />
                failed
              </label>
              <label style={{ marginLeft: '0.5rem' }}>
                <input
                  type="checkbox"
                  checked={highlightWorking}
                  onChange={e => setHighlightWorking(e.target.checked)}
                />
                working
              </label>
              <label style={{ marginLeft: '0.5rem' }}>
                <input
                  type="checkbox"
                  checked={highlightCompleted}
                  onChange={e => setHighlightCompleted(e.target.checked)}
                />
                completed
              </label>
            </div>
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
        {team2NodesMap && Object.keys(team2NodesMap).length > 0 && (
          <FinalArtifactsHistory nodes={team2NodesMap} />
        )}
        {activeEnvironmentId && showFileBrowser && (
          <FileBrowser
            key={selectedPlanId}
            planId={selectedPlanId}
            environmentId={activeEnvironmentId}
          />
        )}
        {logModal && (
          <div className="log-modal-overlay" onClick={() => setLogModal(null)}>
            <div className="log-modal" onClick={e => e.stopPropagation()}>
              <span className="log-modal-close" onClick={() => setLogModal(null)}>×</span>
              <h4>Logs – {logModal.agentName}</h4>
              <pre>{logModal.logs.join('\n')}</pre>
            </div>
          </div>
        )}
        {envModal && (
          <div className="log-modal-overlay" onClick={() => setEnvModal(null)}>
            <div className="log-modal" onClick={e => e.stopPropagation()}>
              <span className="log-modal-close" onClick={() => setEnvModal(null)}>×</span>
              <h4>Delete environment {envModal}?</h4>
              <div style={{ marginTop: '0.5rem' }}>
                <button
                  onClick={() => confirmDeleteEnvironment(envModal)}
                  style={{ marginRight: '1rem' }}
                >
                  Delete
                </button>
                <button onClick={() => setEnvModal(null)}>Cancel</button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(<App />);
