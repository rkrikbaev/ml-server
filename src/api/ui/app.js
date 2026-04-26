import React, { useEffect, useMemo, useState } from "https://esm.sh/react@18.3.1";
import { createRoot } from "https://esm.sh/react-dom@18.3.1/client";
import htm from "https://esm.sh/htm@3.1.1";

const html = htm.bind(React.createElement);

const PAGE_SIZE = 20;
const TAB_ITEMS = ["Tasks", "Workers", "Queues", "Models"];
const STATE_CHIPS = [
  { key: "all", label: "All" },
  { key: "start", label: "start" },
  { key: "processing", label: "processing" },
  { key: "done_success", label: "done ✓" },
  { key: "done_error", label: "done ✗" },
      { key: "expired", label: "expired" },

];

    function formatClock(value) {
      if (!value) {
        return "--:--:--";
      }
      return new Date(value).toLocaleTimeString("ru-RU");
    }

    function formatDateTime(value) {
      if (!value) {
        return "--";
      }
      return new Date(value).toLocaleString("ru-RU");
    }

    function formatRelative(value) {
      if (!value) {
        return "--";
      }
      const diffSeconds = Math.max(Math.floor((Date.now() - new Date(value).getTime()) / 1000), 0);
      if (diffSeconds < 60) {
        return `${diffSeconds}s ago`;
      }
      const diffMinutes = Math.floor(diffSeconds / 60);
      if (diffMinutes < 60) {
        return `${diffMinutes}m ago`;
      }
      const diffHours = Math.floor(diffMinutes / 60);
      if (diffHours < 24) {
        return `${diffHours}h ago`;
      }
      return `${Math.floor(diffHours / 24)}d ago`;
    }

    function formatSeconds(value) {
      if (value === null || value === undefined || Number.isNaN(Number(value))) {
        return "--";
      }
      return `${Number(value).toFixed(1)}s`;
    }

    function truncateMiddle(value, head = 8, tail = 4) {
      if (!value || value.length <= head + tail + 1) {
        return value || "--";
      }
      return `${value.slice(0, head)}…${value.slice(-tail)}`;
    }

    function classForDisplayState(state) {
      if (state === "start") {
        return "state-start";
      }
      if (state === "processing") {
        return "state-processing";
      }
      if (state === "done 200") {
        return "state-done-success";
      }
      if (state.startsWith("done ")) {
        return "state-done-error";
      }
      if (state === "expired") {
        return "state-expired";
      }
      return "state-default";
    }

    function progressPercent(task, avgRuntime) {
      if (task.display_state !== "processing") {
        return 0;
      }
      const baseline = Math.max(avgRuntime || 90, 15);
      return Math.max(8, Math.min(96, ((task.runtime_s || 0) / baseline) * 100));
    }

    function formatUptime(totalSeconds) {
      const safe = Math.max(Number(totalSeconds) || 0, 0);
      const hours = Math.floor(safe / 3600);
      const minutes = Math.floor((safe % 3600) / 60);
      return `${hours}h ${minutes}m`;
    }

    function sourceLabel(source) {
      return source === "scada" ? "S" : source === "weather" ? "W" : "C";
    }

    function sourceName(source) {
      return source === "scada" ? "SCADA" : source === "weather" ? "Weather" : "CMMS";
    }

    function App() {
      const [activeTab, setActiveTab] = useState("Tasks");
      const [filters, setFilters] = useState({ state: "all", search: "", worker: "all", model: "all" });
      const [searchInput, setSearchInput] = useState("");
      const [page, setPage] = useState(1);
      const [autoRefresh, setAutoRefresh] = useState(true);
      const [tasksResponse, setTasksResponse] = useState({
        items: [],
        total: 0,
        counts: { total: 0, start: 0, processing: 0, done_success: 0, done_error: 0, expired: 0 },
        avg_runtime_s: 0,
        tasks_per_min: 0,
        updated_at: null,
        sidebar: { queues: [], workers: [], quick_filters: {}, broker: {} },
        available_models: [],
        available_workers: [],
      });
      const [tasksLoading, setTasksLoading] = useState(false);
      const [tasksError, setTasksError] = useState("");
      const [selectedTaskId, setSelectedTaskId] = useState("");
      const [selectedTask, setSelectedTask] = useState(null);
      const [detailLoading, setDetailLoading] = useState(false);
      const [runtimeStatus, setRuntimeStatus] = useState(null);
      const [liveOk, setLiveOk] = useState(true);
      const [registeredModels, setRegisteredModels] = useState([]);
      const [selectedModelId, setSelectedModelId] = useState("");
      const [selectedModelConfig, setSelectedModelConfig] = useState(null);
      const [modelsError, setModelsError] = useState("");
      const [isNewTaskOpen, setIsNewTaskOpen] = useState(false);
      const [newTaskForm, setNewTaskForm] = useState({
        object_reference: "/KAZ/AKMOLA/@models/P_WATT",
        model_id: "none",
        queue: "forecast.default",
        priority: "normal",
        kwargs: "{}",
        countdown: "0",
        expires: "",
      });
      const [submitError, setSubmitError] = useState("");
      const [copiedTaskId, setCopiedTaskId] = useState("");
      
      // Models tab state
      const [modelsTab, setModelsTab] = useState("catalog");
      const [modelsListSearch, setModelsListSearch] = useState("");
      const [modelsHealthFilter, setModelsHealthFilter] = useState("all");
      const [modelsViewMode, setModelsViewMode] = useState("list");
      const [modelsFilterSidebar, setModelsFilterSidebar] = useState({
        modelType: "all",
        horizon: "all",
        region: "all",
      });
      const [modelsData, setModelsData] = useState([]);
      const [modelsLoading, setModelsLoading] = useState(false);
      const [selectedModelDetail, setSelectedModelDetail] = useState(null);
      const [modelDetailLoading, setModelDetailLoading] = useState(false);
      const [modelRunsHistory, setModelRunsHistory] = useState([]);
      const [modelRunsLoading, setModelRunsLoading] = useState(false);
      const [modelDetailTab, setModelDetailTab] = useState("overview");

      useEffect(() => {
        const handle = window.setTimeout(() => {
          setFilters((current) => ({ ...current, search: searchInput.trim() }));
          setPage(1);
        }, 300);
        return () => window.clearTimeout(handle);
      }, [searchInput]);

      async function loadRuntimeStatus() {
        try {
          const response = await fetch("/ui/runtime-status");
          if (!response.ok) {
            throw new Error(`runtime-status ${response.status}`);
          }
          const data = await response.json();
          setRuntimeStatus(data);
          setLiveOk(true);
        } catch {
          setLiveOk(false);
        }
      }

      async function loadTasks({ silent = false } = {}) {
        if (!silent) {
          setTasksLoading(true);
        }
        try {
          const params = new URLSearchParams({
            state: filters.state,
            search: filters.search,
            worker: filters.worker,
            model: filters.model,
            page: String(page),
            page_size: String(PAGE_SIZE),
          });
          const response = await fetch(`/ui/tasks?${params.toString()}`);
          const data = await response.json();
          if (!response.ok) {
            throw new Error(data.message || `tasks ${response.status}`);
          }
          setTasksResponse(data);
          setTasksError("");
          setLiveOk(true);
        } catch (error) {
          setTasksError(String(error));
          setLiveOk(false);
        } finally {
          if (!silent) {
            setTasksLoading(false);
          }
        }
      }

      async function loadTaskDetail(taskId, { silent = false } = {}) {
        if (!taskId) {
          setSelectedTask(null);
          return;
        }
        if (!silent) {
          setDetailLoading(true);
        }
        try {
          const response = await fetch(`/ui/tasks/${encodeURIComponent(taskId)}`);
          const data = await response.json();
          if (!response.ok) {
            throw new Error(data.message || `task ${response.status}`);
          }
          setSelectedTask(data.task);
          setLiveOk(true);
        } catch {
          setSelectedTask(null);
        } finally {
          if (!silent) {
            setDetailLoading(false);
          }
        }
      }

      async function loadRegisteredModels() {
        try {
          const response = await fetch("/ui/models");
          const data = await response.json();
          if (!response.ok) {
            throw new Error(data.message || `models ${response.status}`);
          }
          const items = Array.isArray(data.models) ? data.models : [];
          setRegisteredModels(items);
          if (!selectedModelId && items.length) {
            setSelectedModelId(items[0].model_id);
          }
          if (!newTaskForm.model_id || newTaskForm.model_id === "none") {
            setNewTaskForm((current) => ({ ...current, model_id: items[0]?.model_id || "none" }));
          }
          setModelsError("");
        } catch (error) {
          setModelsError(String(error));
        }
      }

      async function openModelCard(modelId) {
        setSelectedModelId(modelId);
        setSelectedModelConfig(null);
        try {
          const response = await fetch(`/ui/model-config?model_id=${encodeURIComponent(modelId)}`);
          const data = await response.json();
          if (!response.ok) {
            throw new Error(data.message || `model-config ${response.status}`);
          }
          setSelectedModelConfig(data);
        } catch (error) {
          setModelsError(String(error));
        }
      }

      async function submitNewTask(retryRequest = null) {
        const payload = retryRequest || {
          object_reference: newTaskForm.object_reference,
          model_id: newTaskForm.model_id,
        };
        setSubmitError("");
        try {
          const response = await fetch("/predict", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
          });
          const data = await response.json();
          if (!response.ok && response.status !== 202) {
            throw new Error(data.message || `predict ${response.status}`);
          }
          setIsNewTaskOpen(false);
          setActiveTab("Tasks");
          setSelectedTaskId(data.task_id || "");
          await loadTasks();
          if (data.task_id) {
            await loadTaskDetail(data.task_id);
          }
        } catch (error) {
          setSubmitError(String(error));
        }
      }

      async function retryTask(task) {
        if (!task?.request) {
          return;
        }
        await submitNewTask(task.request);
      }

      async function copyTaskId(taskId) {
        if (!taskId) {
          return;
        }
        try {
          await navigator.clipboard.writeText(taskId);
          setCopiedTaskId(taskId);
          window.setTimeout(() => setCopiedTaskId((current) => (current === taskId ? "" : current)), 1500);
        } catch {
          setCopiedTaskId("");
        }
      }

      async function loadModelsList() {
        setModelsLoading(true);
        try {
          const response = await fetch("/ui/models");
          const data = await response.json();
          if (!response.ok) {
            throw new Error(data.message || `models ${response.status}`);
          }
          const items = Array.isArray(data.models) ? data.models : [];
          setModelsData(items);
          setModelsError("");
          setLiveOk(true);
        } catch (error) {
          setModelsError(String(error));
          setLiveOk(false);
        } finally {
          setModelsLoading(false);
        }
      }

      async function loadModelDetail(modelId) {
        if (!modelId) {
          setSelectedModelDetail(null);
          return;
        }
        setModelDetailLoading(true);
        try {
          const response = await fetch(`/ui/models/${encodeURIComponent(modelId)}`);
          const data = await response.json();
          if (!response.ok) {
            throw new Error(data.message || `model detail ${response.status}`);
          }
          setSelectedModelDetail(data);
          setLiveOk(true);
        } catch (error) {
          setSelectedModelDetail(null);
          setModelsError(String(error));
        } finally {
          setModelDetailLoading(false);
        }
      }

      async function loadModelRuns(modelId) {
        if (!modelId) {
          setModelRunsHistory([]);
          return;
        }
        setModelRunsLoading(true);
        try {
          const response = await fetch(`/ui/models/${encodeURIComponent(modelId)}/runs`);
          const data = await response.json();
          if (!response.ok) {
            throw new Error(data.message || `model runs ${response.status}`);
          }
          const runs = Array.isArray(data.runs) ? data.runs : [];
          setModelRunsHistory(runs);
          setLiveOk(true);
        } catch (error) {
          setModelRunsHistory([]);
          setModelsError(String(error));
        } finally {
          setModelRunsLoading(false);
        }
      }

      function getModelHealth(model) {
        if (!model) return "unknown";
        if (model.health === "error") return "error";
        if (model.health === "warning") return "warning";
        if (model.health === "ok") return "ok";
        return "unknown";
      }

      function getHealthColor(health) {
        if (health === "error") return "state-done-error";
        if (health === "warning") return "state-start";
        if (health === "ok") return "state-done-success";
        return "state-default";
      }

      useEffect(() => {
        if (activeTab === "Models") {
          loadModelsList();
        }
      }, [activeTab]);

      useEffect(() => {
        if (activeTab === "Tasks") {
          loadTasks();
        }
      }, [filters.state, filters.search, filters.worker, filters.model, page, activeTab]);

      useEffect(() => {
        if (activeTab === "Models" && selectedModelId) {
          loadModelDetail(selectedModelId);
          loadModelRuns(selectedModelId);
        }
      }, [selectedModelId, activeTab]);

      useEffect(() => {
        if (selectedTaskId) {
          loadTaskDetail(selectedTaskId, { silent: true });
        }
      }, [selectedTaskId]);

      useEffect(() => {
        if (!autoRefresh) {
          return undefined;
        }
        const interval = window.setInterval(() => {
          if (activeTab === "Tasks") {
            loadTasks({ silent: true });
            loadRuntimeStatus();
            if (selectedTaskId) {
              loadTaskDetail(selectedTaskId, { silent: true });
            }
          } else if (activeTab === "Models") {
            loadModelsList();
            if (selectedModelId) {
              loadModelDetail(selectedModelId);
              loadModelRuns(selectedModelId);
            }
          }
        }, 1500);
        return () => window.clearInterval(interval);
      }, [autoRefresh, filters.state, filters.search, filters.worker, filters.model, page, selectedTaskId, activeTab, selectedModelId]);

      const selectedTaskRequest = selectedTask?.request || null;
      const selectedTaskResult = selectedTask?.result || null;
      const pageCount = Math.max(1, Math.ceil((tasksResponse.total || 0) / PAGE_SIZE));
      const startRow = tasksResponse.total ? (page - 1) * PAGE_SIZE + 1 : 0;
      const endRow = Math.min(page * PAGE_SIZE, tasksResponse.total || 0);
      const queues = tasksResponse.sidebar?.queues || [];
      const workers = tasksResponse.sidebar?.workers || [];
      const quickFilters = tasksResponse.sidebar?.quick_filters || {};
      const brokerInfo = tasksResponse.sidebar?.broker || {};

      // Models filtering logic
      const filteredModels = useMemo(() => {
        return modelsData.filter((model) => {
          const matchesSearch = !modelsListSearch || model.model_id.toLowerCase().includes(modelsListSearch.toLowerCase());
          const health = getModelHealth(model);
          const matchesHealth = modelsHealthFilter === "all" || health === modelsHealthFilter;
          const matchesType = modelsFilterSidebar.modelType === "all" || model.model_type === modelsFilterSidebar.modelType;
          const matchesHorizon = modelsFilterSidebar.horizon === "all" || model.horizon === modelsFilterSidebar.horizon;
          const matchesRegion = modelsFilterSidebar.region === "all" || model.region === modelsFilterSidebar.region;
          return matchesSearch && matchesHealth && matchesType && matchesHorizon && matchesRegion;
        });
      }, [modelsData, modelsListSearch, modelsHealthFilter, modelsFilterSidebar]);

      const modelStats = useMemo(() => {
        const total = modelsData.length;
        const active = modelsData.filter((m) => getModelHealth(m) === "ok").length;
        const warnings = modelsData.filter((m) => getModelHealth(m) === "warning").length;
        const errors = modelsData.filter((m) => getModelHealth(m) === "error").length;
        const lastUpdated = modelsData.length ? Math.max(...modelsData.map((m) => m.updated_at || 0)) : null;
        return { total, active, warnings, errors, lastUpdated };
      }, [modelsData]);

      const content = useMemo(() => {
        if (activeTab === "Workers") {
          return html`
            <section className="monitor-card placeholder-card">
              <div className="section-head">
                <h2>Workers</h2>
                <p>Текущая сводка по пулу taskiq и runtime сервера.</p>
              </div>
              <div className="worker-grid">
                ${workers.map((worker) => html`
                  <article key=${worker.name} className="worker-card ${worker.status}">
                    <strong>${worker.name}</strong>
                    <span>${worker.status}</span>
                    <small>active tasks: ${worker.active_tasks}</small>
                  </article>
                `)}
                <article className="worker-card neutral">
                  <strong>Runtime</strong>
                  <span>CPU load 1m: ${runtimeStatus?.cpu_load?.load_1m ?? "--"}</span>
                  <small>RSS: ${runtimeStatus?.memory?.rss_mb ?? "--"} MB</small>
                </article>
              </div>
            </section>
          `;
        }

        if (activeTab === "Queues") {
          return html`
            <section className="monitor-card placeholder-card">
              <div className="section-head">
                <h2>Queues</h2>
                <p>Сводка очередей, агрегированная из monitor registry.</p>
              </div>
              <div className="queue-grid">
                ${queues.map((queue) => html`
                  <article key=${queue.name} className="queue-card ${queue.kind}">
                    <strong>${queue.name}</strong>
                    <span>${queue.count}</span>
                  </article>
                `)}
              </div>
            </section>
          `;
        }

        if (activeTab === "Models") {
          return html`
            <section className="models-layout">
              <aside className="models-sidebar">
                <div className="sidebar-section">
                  <h3>Model Type</h3>
                  <button type="button" className=${`sidebar-item ${modelsFilterSidebar.modelType === "all" ? "active" : ""}`} onClick=${() => setModelsFilterSidebar((current) => ({ ...current, modelType: "all" }))}>
                    <span className="sidebar-label">All types</span>
                  </button>
                  <button type="button" className=${`sidebar-item ${modelsFilterSidebar.modelType === "Prophet" ? "active" : ""}`} onClick=${() => setModelsFilterSidebar((current) => ({ ...current, modelType: "Prophet" }))}>
                    <span className="sidebar-label">Prophet</span>
                  </button>
                  <button type="button" className=${`sidebar-item ${modelsFilterSidebar.modelType === "ARIMA" ? "active" : ""}`} onClick=${() => setModelsFilterSidebar((current) => ({ ...current, modelType: "ARIMA" }))}>
                    <span className="sidebar-label">ARIMA</span>
                  </button>
                  <button type="button" className=${`sidebar-item ${modelsFilterSidebar.modelType === "XGBoost" ? "active" : ""}`} onClick=${() => setModelsFilterSidebar((current) => ({ ...current, modelType: "XGBoost" }))}>
                    <span className="sidebar-label">XGBoost</span>
                  </button>
                  <button type="button" className=${`sidebar-item ${modelsFilterSidebar.modelType === "ETS" ? "active" : ""}`} onClick=${() => setModelsFilterSidebar((current) => ({ ...current, modelType: "ETS" }))}>
                    <span className="sidebar-label">ETS</span>
                  </button>
                </div>
                <div className="sidebar-section">
                  <h3>Horizon</h3>
                  <button type="button" className=${`sidebar-item ${modelsFilterSidebar.horizon === "all" ? "active" : ""}`} onClick=${() => setModelsFilterSidebar((current) => ({ ...current, horizon: "all" }))}>
                    <span className="sidebar-label">All</span>
                  </button>
                  <button type="button" className=${`sidebar-item ${modelsFilterSidebar.horizon === "short" ? "active" : ""}`} onClick=${() => setModelsFilterSidebar((current) => ({ ...current, horizon: "short" }))}>
                    <span className="sidebar-label">Short</span>
                  </button>
                  <button type="button" className=${`sidebar-item ${modelsFilterSidebar.horizon === "medium" ? "active" : ""}`} onClick=${() => setModelsFilterSidebar((current) => ({ ...current, horizon: "medium" }))}>
                    <span className="sidebar-label">Medium</span>
                  </button>
                  <button type="button" className=${`sidebar-item ${modelsFilterSidebar.horizon === "long" ? "active" : ""}`} onClick=${() => setModelsFilterSidebar((current) => ({ ...current, horizon: "long" }))}>
                    <span className="sidebar-label">Long</span>
                  </button>
                </div>
                <div className="sidebar-section">
                  <h3>Region</h3>
                  <button type="button" className=${`sidebar-item ${modelsFilterSidebar.region === "all" ? "active" : ""}`} onClick=${() => setModelsFilterSidebar((current) => ({ ...current, region: "all" }))}>
                    <span className="sidebar-label">All regions</span>
                  </button>
                  <button type="button" className=${`sidebar-item ${modelsFilterSidebar.region === "AKMOLA" ? "active" : ""}`} onClick=${() => setModelsFilterSidebar((current) => ({ ...current, region: "AKMOLA" }))}>
                    <span className="sidebar-label">AKMOLA</span>
                  </button>
                  <button type="button" className=${`sidebar-item ${modelsFilterSidebar.region === "AKTOBE" ? "active" : ""}`} onClick=${() => setModelsFilterSidebar((current) => ({ ...current, region: "AKTOBE" }))}>
                    <span className="sidebar-label">AKTOBE</span>
                  </button>
                  <button type="button" className=${`sidebar-item ${modelsFilterSidebar.region === "ALMATY" ? "active" : ""}`} onClick=${() => setModelsFilterSidebar((current) => ({ ...current, region: "ALMATY" }))}>
                    <span className="sidebar-label">ALMATY</span>
                  </button>
                </div>
              </aside>

              <section className="models-main">
                <div className="toolbar-card">
                  <div className="section-head between compact">
                    <div>
                      <h2>Models</h2>
                      <p>Просмотр и управление моделями прогнозирования.</p>
                    </div>
                    <button type="button" className="ghost-btn" onClick=${() => loadModelsList()}>Обновить</button>
                  </div>
                  <div className="toolbar-row">
                    <input className="search-input" placeholder="Поиск по model_id..." value=${modelsListSearch} onInput=${(event) => setModelsListSearch(event.target.value)} />
                    <select value=${modelsHealthFilter} onChange=${(event) => setModelsHealthFilter(event.target.value)}>
                      <option value="all">All health</option>
                      <option value="ok">Активные</option>
                      <option value="warning">Предупреждение</option>
                      <option value="error">Ошибка</option>
                    </select>
                    <div className="view-toggle">
                      <button type="button" className=${`view-btn ${modelsViewMode === "list" ? "active" : ""}`} onClick=${() => setModelsViewMode("list")} title="List view">⊞</button>
                      <button type="button" className=${`view-btn ${modelsViewMode === "cards" ? "active" : ""}`} onClick=${() => setModelsViewMode("cards")} title="Cards view">▦</button>
                    </div>
                  </div>
                </div>

                <div className="stat-row monitor-card">
                  <span>Всего моделей: ${modelStats.total}</span>
                  <span>Активных: ${modelStats.active}</span>
                  <span>Предупреждений: ${modelStats.warnings}</span>
                  <span>Ошибок: ${modelStats.errors}</span>
                  <span>Последнее обновление: ${modelStats.lastUpdated ? formatRelative(modelStats.lastUpdated * 1000) : "--"}</span>
                </div>

                <div className=${`model-catalog ${selectedModelId ? "with-detail" : ""}`}>
                  ${modelsViewMode === "list"
                    ? html`
                        <div className="model-list-panel monitor-card">
                          <div className="table-wrap">
                            <table className="models-table">
                              <thead>
                                <tr>
                                  <th></th>
                                  <th>model_id</th>
                                  <th>Type</th>
                                  <th>Horizon</th>
                                  <th>MAPE</th>
                                  <th>Last run</th>
                                  <th>Runtime</th>
                                  <th>Runs</th>
                                  <th>Action</th>
                                </tr>
                              </thead>
                              <tbody>
                                ${modelsLoading
                                  ? html`<tr><td colSpan="9" className="empty-row">Loading models...</td></tr>`
                                  : !filteredModels.length
                                    ? html`<tr><td colSpan="9" className="empty-row">Модели не найдены</td></tr>`
                                    : filteredModels.map((model) => html`
                                        <tr key=${model.model_id} className=${`${selectedModelId === model.model_id ? "selected-row" : ""}`} onClick=${() => setSelectedModelId(model.model_id)}>
                                          <td className="center"><span className=${`health-dot ${getHealthColor(getModelHealth(model))}`}></span></td>
                                          <td className="clickable"><strong>${model.model_id}</strong></td>
                                          <td>${model.model_type || "--"}</td>
                                          <td>${model.horizon || "--"}</td>
                                          <td>${model.mape !== null && model.mape !== undefined ? `${Number(model.mape).toFixed(2)}%` : "--"}</td>
                                          <td>${formatRelative(model.last_run_at ? model.last_run_at * 1000 : null)}</td>
                                          <td className="mono">${formatSeconds(model.avg_runtime_s)}</td>
                                          <td>${model.run_count || 0}</td>
                                          <td><button type="button" className="table-action" onClick=${(event) => { event.stopPropagation(); setSelectedModelId(model.model_id); }}>Details</button></td>
                                        </tr>
                                      `)}
                              </tbody>
                            </table>
                          </div>
                        </div>
                      `
                    : html`
                        <div className="model-cards-panel">
                          ${modelsLoading
                            ? html`<p className="empty-state">Loading models...</p>`
                            : !filteredModels.length
                              ? html`<p className="empty-state">Модели не найдены</p>`
                              : filteredModels.map((model) => html`
                                  <article key=${model.model_id} className=${`model-card-item ${selectedModelId === model.model_id ? "selected" : ""}`} onClick=${() => setSelectedModelId(model.model_id)}>
                                    <div className="card-header">
                                      <span className=${`health-dot ${getHealthColor(getModelHealth(model))}`}></span>
                                      <h4>${model.model_id}</h4>
                                    </div>
                                    <div className="card-body">
                                      <div className="card-row"><span>Type:</span><strong>${model.model_type || "--"}</strong></div>
                                      <div className="card-row"><span>Horizon:</span><strong>${model.horizon || "--"}</strong></div>
                                      <div className="card-row"><span>MAPE:</span><strong>${model.mape !== null && model.mape !== undefined ? `${Number(model.mape).toFixed(2)}%` : "--"}</strong></div>
                                      <div className="card-row"><span>Last run:</span><strong>${formatRelative(model.last_run_at ? model.last_run_at * 1000 : null)}</strong></div>
                                      <div className="card-row"><span>Runs:</span><strong>${model.run_count || 0}</strong></div>
                                    </div>
                                  </article>
                                `)}
                        </div>
                      `}

                  ${selectedModelId && html`
                    <aside className="model-detail-panel monitor-card">
                      <div className="detail-head">
                        <div>
                          <h3>${selectedModelDetail?.model_id || selectedModelId}</h3>
                          <p>${selectedModelDetail?.model_type || "--"}</p>
                        </div>
                        <button type="button" className="close-btn" onClick=${() => { setSelectedModelId(""); setSelectedModelDetail(null); setModelRunsHistory([]); }}>✕</button>
                      </div>

                      <div className="detail-tabs">
                        <button type="button" className=${`tab-btn ${modelDetailTab === "overview" ? "active" : ""}`} onClick=${() => setModelDetailTab("overview")}>Обзор</button>
                        <button type="button" className=${`tab-btn ${modelDetailTab === "config" ? "active" : ""}`} onClick=${() => setModelDetailTab("config")}>Конфигурация</button>
                        <button type="button" className=${`tab-btn ${modelDetailTab === "history" ? "active" : ""}`} onClick=${() => setModelDetailTab("history")}>История</button>
                      </div>

                      ${modelDetailLoading && !selectedModelDetail
                        ? html`<p className="empty-state">Loading model details...</p>`
                        : modelDetailTab === "overview"
                          ? html`
                              <section className="detail-content">
                                ${selectedModelDetail && html`
                                  <section className="detail-section">
                                    <h4>STATE</h4>
                                    <div className="state-cards">
                                      <article className="state-card"><span>Health</span><strong className=${getHealthColor(getModelHealth(selectedModelDetail))}>${getModelHealth(selectedModelDetail)}</strong></article>
                                      <article className="state-card"><span>Type</span><strong>${selectedModelDetail.model_type || "--"}</strong></article>
                                      <article className="state-card"><span>Region</span><strong>${selectedModelDetail.region || "--"}</strong></article>
                                      <article className="state-card"><span>Horizon</span><strong>${selectedModelDetail.horizon || "--"}</strong></article>
                                    </div>
                                  </section>

                                  <section className="detail-section">
                                    <h4>KEY METRICS</h4>
                                    <div className="metrics-cards">
                                      <article className="metric-card"><span>MAPE</span><strong>${selectedModelDetail.mape !== null && selectedModelDetail.mape !== undefined ? `${Number(selectedModelDetail.mape).toFixed(2)}%` : "--"}</strong></article>
                                      <article className="metric-card"><span>Runs</span><strong>${selectedModelDetail.run_count || 0}</strong></article>
                                      <article className="metric-card"><span>Avg Runtime</span><strong>${formatSeconds(selectedModelDetail.avg_runtime_s)}</strong></article>
                                      <article className="metric-card"><span>Success Rate</span><strong>${selectedModelDetail.success_rate !== null && selectedModelDetail.success_rate !== undefined ? `${Number(selectedModelDetail.success_rate).toFixed(1)}%` : "--"}</strong></article>
                                    </div>
                                  </section>

                                  <section className="detail-section">
                                    <h4>ATTRIBUTES</h4>
                                    <dl>
                                      <div><dt>model_id</dt><dd className="mono">${selectedModelDetail.model_id}</dd></div>
                                      <div><dt>Last run</dt><dd>${formatDateTime(selectedModelDetail.last_run_at ? selectedModelDetail.last_run_at * 1000 : null)}</dd></div>
                                      <div><dt>Updated</dt><dd>${formatDateTime(selectedModelDetail.updated_at ? selectedModelDetail.updated_at * 1000 : null)}</dd></div>
                                    </dl>
                                  </section>

                                  <div className="detail-actions">
                                    <button type="button" className="primary-btn">Запустить прогноз</button>
                                    <button type="button" className="ghost-btn">MLflow</button>
                                  </div>
                                `}
                              </section>
                            `
                          : modelDetailTab === "config"
                            ? html`
                                <section className="detail-content">
                                  ${selectedModelDetail && html`
                                    <section className="detail-section">
                                      <h4>PARAMETERS</h4>
                                      <dl>
                                        <div><dt>seasonality_mode</dt><dd>${selectedModelDetail.seasonality_mode || "--"}</dd></div>
                                        <div><dt>yearly_seasonality</dt><dd>${selectedModelDetail.yearly_seasonality !== null ? String(selectedModelDetail.yearly_seasonality) : "--"}</dd></div>
                                        <div><dt>weekly_seasonality</dt><dd>${selectedModelDetail.weekly_seasonality !== null ? String(selectedModelDetail.weekly_seasonality) : "--"}</dd></div>
                                        <div><dt>daily_seasonality</dt><dd>${selectedModelDetail.daily_seasonality !== null ? String(selectedModelDetail.daily_seasonality) : "--"}</dd></div>
                                      </dl>
                                    </section>

                                    ${selectedModelDetail.scada_sources && html`
                                      <section className="detail-section">
                                        <h4>SCADA SOURCES</h4>
                                        <div className="sources-list">
                                          ${(Array.isArray(selectedModelDetail.scada_sources) ? selectedModelDetail.scada_sources : []).map((source) => html`<span key=${source} className="source-tag">${source}</span>`)}
                                        </div>
                                      </section>
                                    `}

                                    <section className="detail-section">
                                      <h4>RAW CONFIG</h4>
                                      <pre className="json-viewer">${JSON.stringify(selectedModelDetail.raw_config || {}, null, 2)}</pre>
                                    </section>

                                    <div className="detail-actions">
                                      <button type="button" className="ghost-btn">Export config</button>
                                    </div>
                                  `}
                                </section>
                              `
                            : html`
                                <section className="detail-content">
                                  ${modelRunsLoading
                                    ? html`<p className="empty-state">Loading run history...</p>`
                                    : !modelRunsHistory.length
                                      ? html`<p className="empty-state">No runs found</p>`
                                      : html`
                                          <div className="runs-table-wrap">
                                            <table className="runs-table">
                                              <thead>
                                                <tr>
                                                  <th>Started</th>
                                                  <th>Duration</th>
                                                  <th>Status</th>
                                                  <th>MAPE</th>
                                                  <th>Quality</th>
                                                </tr>
                                              </thead>
                                              <tbody>
                                                ${modelRunsHistory.map((run) => html`
                                                  <tr key=${run.run_id || run.started_at}>
                                                    <td>${formatDateTime(run.started_at ? run.started_at * 1000 : null)}</td>
                                                    <td className="mono">${formatSeconds(run.duration_s)}</td>
                                                    <td><span className=${`state-badge ${run.status === "success" ? "state-done-success" : "state-done-error"}`}>${run.status}</span></td>
                                                    <td>${run.mape !== null && run.mape !== undefined ? `${Number(run.mape).toFixed(2)}%` : "--"}</td>
                                                    <td>${run.quality || "--"}</td>
                                                  </tr>
                                                `)}
                                              </tbody>
                                            </table>
                                          </div>
                                          <div className="runs-stats">
                                            <span>Total runs: ${modelRunsHistory.length}</span>
                                            <span>Successful: ${modelRunsHistory.filter((r) => r.status === "success").length}</span>
                                            <span>Failed: ${modelRunsHistory.filter((r) => r.status === "failed").length}</span>
                                          </div>
                                        `}
                                </section>
                              `}
                    </aside>
                  `}
                </div>
              </section>
            </section>
          `;
        }

        return html`
          <section className="tasks-layout">
            <aside className="sidebar">
              <div className="sidebar-section">
                <h3>Очереди</h3>
                ${queues.map((queue) => html`
                  <button key=${queue.name} type="button" className="sidebar-item" onClick=${() => setFilters((current) => ({ ...current, state: queue.kind === "dead" ? "done_error" : current.state }))}>
                    <span className=${`queue-dot ${queue.kind}`}></span>
                    <span className="sidebar-label">${queue.name}</span>
                    <strong>${queue.count}</strong>
                  </button>
                `)}
              </div>
              <div className="sidebar-section">
                <h3>Воркеры</h3>
                ${workers.map((worker) => html`
                  <button key=${worker.name} type="button" className="sidebar-item" onClick=${() => setFilters((current) => ({ ...current, worker: worker.name === "taskiq-pool" ? "all" : worker.name }))}>
                    <span className=${`worker-dot ${worker.status}`}></span>
                    <span className="sidebar-label">${worker.name}</span>
                    <small>${worker.status}</small>
                  </button>
                `)}
              </div>
              <div className="sidebar-section">
                <h3>Быстрые фильтры</h3>
                <button type="button" className="sidebar-item" onClick=${() => setFilters((current) => ({ ...current, state: "processing" }))}>
                  <span className="sidebar-label">Выполняются</span>
                  <strong>${quickFilters.active || 0}</strong>
                </button>
                <button type="button" className="sidebar-item" onClick=${() => setFilters((current) => ({ ...current, state: "start" }))}>
                  <span className="sidebar-label">Ожидают</span>
                  <strong>${quickFilters.queued || 0}</strong>
                </button>
                <button type="button" className="sidebar-item" onClick=${() => setFilters((current) => ({ ...current, state: "done_error" }))}>
                  <span className="sidebar-label">Ошибки</span>
                  <strong>${quickFilters.errors_24h || 0}</strong>
                </button>
              </div>
              <div className="broker-foot">
                <small>Broker: ${brokerInfo.name || "Redis"}</small>
                <small>tasks/min: ${brokerInfo.tasks_per_min || 0}</small>
                <small>uptime: ${formatUptime(brokerInfo.uptime_s || 0)}</small>
              </div>
            </aside>

            <section className="tasks-main">
              <div className="toolbar-card">
                <div className="section-head between compact">
                  <div>
                    <h2>Tasks</h2>
                    <p>Мониторинг задач прогнозирования в реальном времени.</p>
                  </div>
                  <span className="error-text">${tasksError}</span>
                </div>
                <div className="chip-row">
                  ${STATE_CHIPS.map((chip) => html`
                    <button key=${chip.key} type="button" className=${`state-chip ${filters.state === chip.key ? "active" : ""}`} onClick=${() => { setFilters((current) => ({ ...current, state: chip.key })); setPage(1); }}>
                      ${chip.label}
                    </button>
                  `)}
                </div>
                <div className="toolbar-row">
                  <input className="search-input" placeholder="Поиск task_id, object_reference, model_id..." value=${searchInput} onInput=${(event) => setSearchInput(event.target.value)} />
                  <select value=${filters.worker} onChange=${(event) => { setFilters((current) => ({ ...current, worker: event.target.value })); setPage(1); }}>
                    <option value="all">All workers</option>
                    ${tasksResponse.available_workers.map((worker) => html`<option key=${worker} value=${worker}>${worker}</option>`)}
                  </select>
                  <select value=${filters.model} onChange=${(event) => { setFilters((current) => ({ ...current, model: event.target.value })); setPage(1); }}>
                    <option value="all">All models</option>
                    ${tasksResponse.available_models.map((model) => html`<option key=${model} value=${model}>${model}</option>`)}
                  </select>
                </div>
              </div>

              <div className="stat-row monitor-card">
                <span>Total: ${tasksResponse.counts.total || 0}</span>
                <span>start: ${tasksResponse.counts.start || 0}</span>
                <span>processing: ${tasksResponse.counts.processing || 0}</span>
                <span>done ✓: ${tasksResponse.counts.done_success || 0}</span>
                <span>done ✗: ${tasksResponse.counts.done_error || 0}</span>
                <span>expired: ${tasksResponse.counts.expired || 0}</span>
                <span>avg runtime: ${formatSeconds(tasksResponse.avg_runtime_s)}</span>
                <span>tasks/min: ${tasksResponse.tasks_per_min || 0}</span>
                <span>обновлено: ${formatClock(tasksResponse.updated_at)}</span>
              </div>

              <div className=${`table-shell ${selectedTaskId ? "with-detail" : ""}`}>
                <div className="table-panel monitor-card">
                  <div className="table-wrap">
                    <table className="tasks-table">
                      <thead>
                        <tr>
                          <th>task_id</th>
                          <th>object_reference</th>
                          <th>model_id</th>
                          <th>state</th>
                          <th>received</th>
                          <th>runtime</th>
                          <th>src</th>
                          <th>worker</th>
                          <th>action</th>
                        </tr>
                      </thead>
                      <tbody>
                        ${tasksLoading
                          ? html`<tr><td colSpan="9" className="empty-row">Loading tasks...</td></tr>`
                          : !tasksResponse.items.length
                            ? html`<tr><td colSpan="9" className="empty-row">Задачи не найдены</td></tr>`
                            : tasksResponse.items.map((task) => html`
                                <tr key=${task.task_id} className=${`${selectedTaskId === task.task_id ? "selected-row" : ""} ${task.display_state === "expired" ? "expired-row" : ""}`} onClick=${() => setSelectedTaskId(task.task_id)}>
                                  <td className="mono clickable" title=${task.task_id}>
                                    <button type="button" className="linkish" onClick=${(event) => { event.stopPropagation(); copyTaskId(task.task_id); }}>
                                      ${truncateMiddle(task.task_id)}
                                    </button>
                                    ${copiedTaskId === task.task_id && html`<small className="copied-note">Copied!</small>`}
                                  </td>
                                  <td title=${task.object_reference}>${task.object_reference}</td>
                                  <td className="mono">${task.model_type}</td>
                                  <td>
                                    <div className=${`state-badge ${classForDisplayState(task.display_state)}`}>
                                      ${task.display_state === "processing" && html`<span className="pulse-dot"></span>`}
                                      <span>${task.display_state}</span>
                                    </div>
                                    ${task.display_state === "processing" && html`<div className="mini-progress"><span style=${{ width: `${progressPercent(task, tasksResponse.avg_runtime_s)}%` }}></span></div>`}
                                  </td>
                                  <td title=${formatDateTime(task.received_at)}>${formatRelative(task.received_at)}</td>
                                  <td className="mono">${formatSeconds(task.runtime_s)}</td>
                                  <td>
                                    <div className="src-icons">
                                      ${Object.entries(task.sources || {}).map(([name, value]) => html`<span key=${name} className=${`src-pill ${name} ${value.enabled ? "enabled" : "disabled"}`}>${sourceLabel(name)}</span>`)}
                                    </div>
                                  </td>
                                  <td>${task.worker || "unassigned"}</td>
                                  <td>
                                    ${task.actions.retry
                                      ? html`<button type="button" className="table-action" onClick=${(event) => { event.stopPropagation(); retryTask(task); }}>Retry</button>`
                                      : html`<button type="button" className="table-action muted" disabled>${task.display_state === "processing" ? "Revoke" : "-"}</button>`}
                                  </td>
                                </tr>
                              `)}
                      </tbody>
                    </table>
                  </div>
                  <div className="table-footer">
                    <span>Showing ${startRow}-${endRow} of ${tasksResponse.total || 0}</span>
                    <div className="pagination">
                      <button type="button" disabled=${page <= 1} onClick=${() => setPage((current) => Math.max(current - 1, 1))}>Prev</button>
                      <span>${page} / ${pageCount}</span>
                      <button type="button" disabled=${page >= pageCount} onClick=${() => setPage((current) => Math.min(current + 1, pageCount))}>Next</button>
                    </div>
                  </div>
                </div>

                ${selectedTaskId && html`
                  <aside className="detail-panel monitor-card">
                    <div className="detail-head">
                      <div>
                        <h3>${(selectedTask?.task_name || "run_forecast").replace("forecasting.", "")}</h3>
                        <p>${selectedTask?.model_type || "--"}</p>
                      </div>
                      <button type="button" className="close-btn" onClick=${() => { setSelectedTaskId(""); setSelectedTask(null); }}>✕</button>
                    </div>

                    ${detailLoading && !selectedTask
                      ? html`<p className="empty-state">Loading task details...</p>`
                      : selectedTask && html`
                          <section className="detail-section">
                            <h4>TASK</h4>
                            <dl>
                              <div><dt>task_id</dt><dd className="mono">${selectedTask.task_id}</dd></div>
                              <div><dt>state</dt><dd>${selectedTask.display_state}</dd></div>
                              <div><dt>worker</dt><dd>${selectedTask.worker || "unassigned"}</dd></div>
                              <div><dt>redis TTL</dt><dd>${selectedTask.expires_at ? `${Math.max(Math.floor((new Date(selectedTask.expires_at).getTime() - Date.now()) / 1000), 0)}s` : "--"}</dd></div>
                            </dl>
                          </section>

                          <section className="detail-section">
                            <h4>REQUEST</h4>
                            <pre className="json-viewer compact">${JSON.stringify(selectedTaskRequest, null, 2)}</pre>
                          </section>

                          <section className="detail-section">
                            <h4>TIMING</h4>
                            <dl>
                              <div><dt>received</dt><dd>${formatDateTime(selectedTask.received_at)}</dd></div>
                              <div><dt>runtime</dt><dd>${formatSeconds(selectedTask.runtime_s)}</dd></div>
                            </dl>
                          </section>

                          <section className="detail-section">
                            <h4>SOURCES</h4>
                            <div className="detail-pills">
                              ${Object.entries(selectedTask.sources || {}).map(([name, value]) => html`<span key=${name} className=${`detail-pill ${name} ${value.enabled ? "enabled" : "disabled"}`}>${sourceLabel(name)} ${sourceName(name)} ${value.enabled ? "✓" : "—"}</span>`)}
                            </div>
                          </section>

                          <section className="detail-section">
                            <h4>POLL HISTORY</h4>
                            <div className="history-list">
                              ${(selectedTask.poll_history || []).map((entry, idx) => html`<div key=${`${entry.timestamp}-${idx}`} className="history-row"><span>${formatClock(entry.timestamp)}</span><strong>${entry.status}</strong><small>${entry.state}</small></div>`)}
                            </div>
                          </section>

                          ${selectedTask.display_state === "done 200" && html`
                            <section className="detail-section">
                              <h4>RESULT</h4>
                              <div className="result-metrics">
                                <article><span>HTTP</span><strong>200</strong></article>
                                <article><span>quality</span><strong>${selectedTask.quality ?? "--"}</strong></article>
                                <article><span>confidence</span><strong>${selectedTask.model_confidence ?? "--"}</strong></article>
                              </div>
                              <div className="result-preview">
                                <table>
                                  <thead><tr><th>timestamp_ms</th><th>value</th><th>qds</th></tr></thead>
                                  <tbody>
                                    ${(selectedTask.result_preview || []).map((row, idx) => html`<tr key=${idx}><td className="mono">${row[0]}</td><td>${row[1]}</td><td>${row[2]}</td></tr>`)}
                                  </tbody>
                                </table>
                              </div>
                            </section>
                          `}

                          ${selectedTask.display_state.startsWith("done ") && selectedTask.display_state !== "done 200" && html`
                            <section className="detail-section">
                              <h4>ERROR</h4>
                              <div className="error-banner">${selectedTask.error || selectedTaskResult?.message || "Request failed"}</div>
                            </section>
                          `}

                          <div className="detail-actions">
                            <button type="button" className="ghost-btn" disabled title="Broker-level revoke is not wired yet">Revoke</button>
                            <button type="button" className="ghost-btn" onClick=${() => copyTaskId(selectedTask.task_id)}>Copy task_id</button>
                            <button type="button" className="primary-btn" disabled=${!selectedTask.actions.retry} onClick=${() => retryTask(selectedTask)}>Retry</button>
                          </div>
                        `}
                  </aside>
                `}
              </div>
            </section>
          </section>
        `;
      }, [activeTab, workers, queues, runtimeStatus, registeredModels, selectedModelId, selectedModelConfig, modelsError, tasksResponse, tasksLoading, selectedTaskId, selectedTask, detailLoading, copiedTaskId, filters.state, filters.worker, filters.model, searchInput, page, modelsData, filteredModels, modelsLoading, selectedModelDetail, modelDetailLoading, modelRunsHistory, modelRunsLoading, modelDetailTab, modelsViewMode, modelsHealthFilter, modelsListSearch, modelsFilterSidebar, modelStats]);

      return html`
        <div className="monitor-shell">
          <header className="topbar">
            <div className="brand-block">
              <strong>ML Forecast Platform</strong>
              <nav className="top-tabs">
                ${TAB_ITEMS.map((tab) => html`<button key=${tab} type="button" className=${`tab-btn ${activeTab === tab ? "active" : ""}`} onClick=${() => setActiveTab(tab)}>${tab}</button>`)}
              </nav>
            </div>
            <div className="topbar-actions">
              <button type="button" className=${`auto-toggle ${autoRefresh ? "active" : ""}`} onClick=${() => setAutoRefresh((current) => !current)}>↻ auto</button>
              <span className=${`live-indicator ${liveOk ? "online" : "offline"}`}>● live</span>
              <span className="topbar-time">${new Date().toLocaleTimeString("ru-RU")}</span>
              <button type="button" className="primary-btn" onClick=${() => { setSubmitError(""); setIsNewTaskOpen(true); }}>+ New task</button>
            </div>
          </header>

          <main className="monitor-content">${content}</main>

          ${isNewTaskOpen && html`
            <div className="modal-backdrop" onClick=${() => setIsNewTaskOpen(false)}>
              <div className="modal-card" onClick=${(event) => event.stopPropagation()}>
                <div className="detail-head">
                  <div>
                    <h3>New forecast task</h3>
                    <p>Создание новой задачи через POST /predict</p>
                  </div>
                  <button type="button" className="close-btn" onClick=${() => setIsNewTaskOpen(false)}>✕</button>
                </div>
                <div className="form-grid">
                  <label><span>Task name</span><input value="forecasting.run_forecast" disabled /></label>
                  <label>
                    <span>Queue</span>
                    <select value=${newTaskForm.queue} onChange=${(event) => setNewTaskForm((current) => ({ ...current, queue: event.target.value }))}>
                      <option value="forecast.default">forecast.default</option>
                      <option value="forecast.priority">forecast.priority</option>
                    </select>
                  </label>
                  <label className="wide"><span>object_reference</span><input value=${newTaskForm.object_reference} onInput=${(event) => setNewTaskForm((current) => ({ ...current, object_reference: event.target.value }))} /></label>
                  <label className="wide">
                    <span>model_id</span>
                    <select value=${newTaskForm.model_id} onChange=${(event) => setNewTaskForm((current) => ({ ...current, model_id: event.target.value }))}>
                      <option value="none">none</option>
                      ${registeredModels.map((model) => html`<option key=${model.model_id} value=${model.model_id}>${model.model_id}</option>`)}
                    </select>
                  </label>
                  <label>
                    <span>Priority</span>
                    <select value=${newTaskForm.priority} onChange=${(event) => setNewTaskForm((current) => ({ ...current, priority: event.target.value }))}>
                      <option value="normal">normal</option>
                      <option value="high">high</option>
                    </select>
                  </label>
                  <label><span>countdown</span><input value=${newTaskForm.countdown} onInput=${(event) => setNewTaskForm((current) => ({ ...current, countdown: event.target.value }))} /></label>
                  <label><span>expires</span><input value=${newTaskForm.expires} onInput=${(event) => setNewTaskForm((current) => ({ ...current, expires: event.target.value }))} /></label>
                  <label className="wide"><span>Дополнительные kwargs (JSON)</span><textarea rows="6" value=${newTaskForm.kwargs} onInput=${(event) => setNewTaskForm((current) => ({ ...current, kwargs: event.target.value }))}></textarea></label>
                </div>
                <p className="hint-text">Текущий backend принимает для POST /predict только object_reference и model_id. Остальные поля оставлены как UI scaffold.</p>
                <p className="error-text">${submitError}</p>
                <div className="modal-actions">
                  <button type="button" className="ghost-btn" onClick=${() => setIsNewTaskOpen(false)}>Отмена</button>
                  <button type="button" className="primary-btn" onClick=${() => submitNewTask()}>Отправить POST /predict</button>
                </div>
              </div>
            </div>
          `}
        </div>
      `;
}

createRoot(document.getElementById("root")).render(React.createElement(App));
