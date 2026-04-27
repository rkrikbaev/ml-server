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
  if (!value) return "--:--:--";
  return new Date(value).toLocaleTimeString("ru-RU");
}

function formatDateTime(value) {
  if (!value) return "--";
  return new Date(value).toLocaleString("ru-RU");
}

function formatRelative(value) {
  if (!value) return "--";
  const diffSeconds = Math.max(Math.floor((Date.now() - new Date(value).getTime()) / 1000), 0);
  if (diffSeconds < 60) return `${diffSeconds}s ago`;
  const diffMinutes = Math.floor(diffSeconds / 60);
  if (diffMinutes < 60) return `${diffMinutes}m ago`;
  const diffHours = Math.floor(diffMinutes / 60);
  if (diffHours < 24) return `${diffHours}h ago`;
  return `${Math.floor(diffHours / 24)}d ago`;
}

function formatSeconds(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "--";
  return `${Number(value).toFixed(1)}s`;
}

function truncateMiddle(value, head = 8, tail = 4) {
  if (!value || value.length <= head + tail + 1) return value || "--";
  return `${value.slice(0, head)}…${value.slice(-tail)}`;
}

function classForDisplayState(state) {
  if (state === "start") return "state-start";
  if (state === "processing") return "state-processing";
  if (state === "done 200") return "state-done-success";
  if (state && state.startsWith("done ")) return "state-done-error";
  if (state === "expired") return "state-expired";
  return "state-default";
}

function progressPercent(task, avgRuntime) {
  if (task.display_state !== "processing") return 0;
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

function SourceIcons({ sources }) {
  if (!sources) return null;
  return html`
    <div className="src-icons">
      ${Object.entries(sources).map(([name, val]) => html`
        <span key=${name} className=${`src-pill ${name} ${val.enabled ? "enabled" : "disabled"}`}>
          ${sourceLabel(name)}
        </span>
      `)}
    </div>
  `;
}

function App() {
  const [activeTab, setActiveTab] = useState("Tasks");
  const [filters, setFilters] = useState({ state: "all", search: "", worker: "all", model: "all" });
  const [searchInput, setSearchInput] = useState("");
  const [page, setPage] = useState(1);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [tasksResponse, setTasksResponse] = useState({
    items: [], total: 0,
    counts: { total: 0, start: 0, processing: 0, done_success: 0, done_error: 0, expired: 0 },
    avg_runtime_s: 0, tasks_per_min: 0, updated_at: null,
    sidebar: { queues: [], workers: [], quick_filters: {}, broker: {} },
    available_models: [], available_workers: [],
  });
  const [tasksLoading, setTasksLoading] = useState(false);
  const [tasksError, setTasksError] = useState("");
  const [selectedTaskId, setSelectedTaskId] = useState("");
  const [selectedTask, setSelectedTask] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [taskDetailTab, setTaskDetailTab] = useState("details");
  const [taskModelConfig, setTaskModelConfig] = useState(null);
  const [taskModelConfigLoading, setTaskModelConfigLoading] = useState(false);
  const [runtimeStatus, setRuntimeStatus] = useState(null);
  const [liveOk, setLiveOk] = useState(true);
  const [registeredModels, setRegisteredModels] = useState([]);
  const [modelsError, setModelsError] = useState("");
  const [isNewTaskOpen, setIsNewTaskOpen] = useState(false);
  const [newTaskForm, setNewTaskForm] = useState({
    object_reference: "/KAZ/AKMOLA/@models/P_WATT",
    model_id: "none",
  });
  const [submitError, setSubmitError] = useState("");
  const [copiedTaskId, setCopiedTaskId] = useState("");

  // Models tab state
  const [modelsListSearch, setModelsListSearch] = useState("");
  const [modelsHealthFilter, setModelsHealthFilter] = useState("all");
  const [modelsViewMode, setModelsViewMode] = useState("list");
  const [modelsFilterSidebar, setModelsFilterSidebar] = useState({ modelType: "all", horizon: "all", region: "all" });
  const [modelsData, setModelsData] = useState([]);
  const [modelsLoading, setModelsLoading] = useState(false);
  const [selectedModelId, setSelectedModelId] = useState("");
  const [selectedModelDetail, setSelectedModelDetail] = useState(null);
  const [modelDetailLoading, setModelDetailLoading] = useState(false);
  const [modelRunsHistory, setModelRunsHistory] = useState([]);
  const [modelRunsLoading, setModelRunsLoading] = useState(false);
  const [modelDetailTab, setModelDetailTab] = useState("overview");

  // Debounce search
  useEffect(() => {
    const handle = window.setTimeout(() => {
      setFilters((c) => ({ ...c, search: searchInput.trim() }));
      setPage(1);
    }, 300);
    return () => window.clearTimeout(handle);
  }, [searchInput]);

  async function loadRuntimeStatus() {
    try {
      const r = await fetch("/ui/runtime-status");
      if (!r.ok) throw new Error(`runtime-status ${r.status}`);
      setRuntimeStatus(await r.json());
      setLiveOk(true);
    } catch { setLiveOk(false); }
  }

  async function loadTasks({ silent = false } = {}) {
    if (!silent) setTasksLoading(true);
    try {
      const params = new URLSearchParams({
        state: filters.state, search: filters.search,
        worker: filters.worker, model: filters.model,
        page: String(page), page_size: String(PAGE_SIZE),
      });
      const r = await fetch(`/ui/tasks?${params}`);
      const data = await r.json();
      if (!r.ok) throw new Error(data.message || `tasks ${r.status}`);
      setTasksResponse(data);
      setTasksError("");
      setLiveOk(true);
    } catch (e) {
      setTasksError(String(e));
      setLiveOk(false);
    } finally {
      if (!silent) setTasksLoading(false);
    }
  }

  async function loadTaskDetail(taskId, { silent = false } = {}) {
    if (!taskId) { setSelectedTask(null); return; }
    if (!silent) setDetailLoading(true);
    try {
      const r = await fetch(`/ui/tasks/${encodeURIComponent(taskId)}`);
      const data = await r.json();
      if (!r.ok) throw new Error(data.message || `task ${r.status}`);
      setSelectedTask(data.task);
      setLiveOk(true);
    } catch { setSelectedTask(null); }
    finally { if (!silent) setDetailLoading(false); }
  }

  async function loadTaskModelConfig(modelId) {
    if (!modelId || modelId === "none") { setTaskModelConfig(null); return; }
    setTaskModelConfigLoading(true);
    try {
      const r = await fetch(`/ui/model-config?model_id=${encodeURIComponent(modelId)}`);
      const data = await r.json();
      if (!r.ok) throw new Error(data.message || "model-config error");
      setTaskModelConfig(data);
    } catch { setTaskModelConfig(null); }
    finally { setTaskModelConfigLoading(false); }
  }

  async function loadRegisteredModels() {
    try {
      const r = await fetch("/ui/models");
      const data = await r.json();
      if (!r.ok) throw new Error(data.message || `models ${r.status}`);
      const items = Array.isArray(data.models) ? data.models : [];
      setRegisteredModels(items);
      if (!newTaskForm.model_id || newTaskForm.model_id === "none") {
        setNewTaskForm((c) => ({ ...c, model_id: items[0]?.model_id || "none" }));
      }
    } catch {}
  }

  async function submitNewTask(retryRequest = null) {
    const payload = retryRequest || {
      object_reference: newTaskForm.object_reference,
      model_id: newTaskForm.model_id,
    };
    setSubmitError("");
    try {
      const r = await fetch("/predict", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await r.json();
      if (!r.ok && r.status !== 202) throw new Error(data.message || `predict ${r.status}`);
      setIsNewTaskOpen(false);
      setActiveTab("Tasks");
      setSelectedTaskId(data.task_id || "");
      await loadTasks();
      if (data.task_id) await loadTaskDetail(data.task_id);
    } catch (e) { setSubmitError(String(e)); }
  }

  async function retryTask(task) {
    if (!task?.request) return;
    await submitNewTask(task.request);
  }

  async function copyTaskId(taskId) {
    if (!taskId) return;
    try {
      await navigator.clipboard.writeText(taskId);
      setCopiedTaskId(taskId);
      window.setTimeout(() => setCopiedTaskId((c) => (c === taskId ? "" : c)), 1500);
    } catch { setCopiedTaskId(""); }
  }

  async function loadModelsList() {
    setModelsLoading(true);
    try {
      const r = await fetch("/ui/models");
      const data = await r.json();
      if (!r.ok) throw new Error(data.message || `models ${r.status}`);
      setModelsData(Array.isArray(data.models) ? data.models : []);
      setModelsError("");
      setLiveOk(true);
    } catch (e) { setModelsError(String(e)); setLiveOk(false); }
    finally { setModelsLoading(false); }
  }

  async function loadModelDetail(modelId) {
    if (!modelId) { setSelectedModelDetail(null); return; }
    setModelDetailLoading(true);
    try {
      const r = await fetch(`/ui/models/detail?model_id=${encodeURIComponent(modelId)}`);
      const data = await r.json();
      if (!r.ok) throw new Error(data.message || `model detail ${r.status}`);
      setSelectedModelDetail(data);
      setLiveOk(true);
    } catch (e) { setSelectedModelDetail(null); setModelsError(String(e)); }
    finally { setModelDetailLoading(false); }
  }

  async function loadModelRuns(modelId) {
    if (!modelId) { setModelRunsHistory([]); return; }
    setModelRunsLoading(true);
    try {
      const r = await fetch(`/ui/models/${encodeURIComponent(modelId)}/runs`);
      const data = await r.json();
      if (!r.ok) throw new Error(data.message || `model runs ${r.status}`);
      setModelRunsHistory(Array.isArray(data.runs) ? data.runs : []);
    } catch { setModelRunsHistory([]); }
    finally { setModelRunsLoading(false); }
  }

  function navigateToTasksWithModel(modelId) {
    setActiveTab("Tasks");
    setSearchInput(modelId);
    setSelectedModelId("");
    setSelectedModelDetail(null);
  }

  function openNewTaskWithModel(modelId) {
    setNewTaskForm((c) => ({ ...c, model_id: modelId || "none" }));
    setSubmitError("");
    setIsNewTaskOpen(true);
  }

  function getModelHealth(model) {
    if (!model) return "unknown";
    const h = model.health || model.health_status;
    if (h === "error" || h === "err") return "error";
    if (h === "warning" || h === "warn") return "warning";
    if (h === "ok") return "ok";
    return "unknown";
  }

  function getHealthColor(health) {
    if (health === "error") return "state-done-error";
    if (health === "warning") return "state-start";
    if (health === "ok") return "state-done-success";
    return "state-default";
  }

  function getMapeColor(mape) {
    if (mape === null || mape === undefined) return "";
    if (mape < 7) return "mape-good";
    if (mape < 12) return "mape-warn";
    return "mape-bad";
  }

  // Effects
  useEffect(() => {
    if (activeTab === "Models") loadModelsList();
  }, [activeTab]);

  useEffect(() => {
    if (activeTab === "Tasks") loadTasks();
  }, [filters.state, filters.search, filters.worker, filters.model, page, activeTab]);

  useEffect(() => {
    if (activeTab === "Models" && selectedModelId) {
      loadModelDetail(selectedModelId);
      loadModelRuns(selectedModelId);
    }
  }, [selectedModelId, activeTab]);

  useEffect(() => {
    if (selectedTaskId) loadTaskDetail(selectedTaskId, { silent: true });
  }, [selectedTaskId]);

  useEffect(() => {
    if (!autoRefresh) return;
    const interval = window.setInterval(() => {
      if (activeTab === "Tasks") {
        loadTasks({ silent: true });
        loadRuntimeStatus();
        if (selectedTaskId) loadTaskDetail(selectedTaskId, { silent: true });
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

  useEffect(() => {
    // Load model config when switching to model tab in task detail
    if (taskDetailTab === "model" && selectedTask) {
      const modelId = selectedTask.model_id;
      if (modelId && modelId !== "none" && (!taskModelConfig || taskModelConfig.model_id !== modelId)) {
        loadTaskModelConfig(modelId);
      }
    }
  }, [taskDetailTab, selectedTask]);

  const selectedTaskRequest = selectedTask?.request || null;
  const selectedTaskResult = selectedTask?.result || null;
  const pageCount = Math.max(1, Math.ceil((tasksResponse.total || 0) / PAGE_SIZE));
  const startRow = tasksResponse.total ? (page - 1) * PAGE_SIZE + 1 : 0;
  const endRow = Math.min(page * PAGE_SIZE, tasksResponse.total || 0);
  const queues = tasksResponse.sidebar?.queues || [];
  const workers = tasksResponse.sidebar?.workers || [];
  const quickFilters = tasksResponse.sidebar?.quick_filters || {};
  const brokerInfo = tasksResponse.sidebar?.broker || {};

  const filteredModels = useMemo(() => {
    return modelsData.filter((m) => {
      const matchSearch = !modelsListSearch || m.model_id.toLowerCase().includes(modelsListSearch.toLowerCase());
      const health = getModelHealth(m);
      const matchHealth = modelsHealthFilter === "all" || health === modelsHealthFilter;
      const matchType = modelsFilterSidebar.modelType === "all" || m.model_type === modelsFilterSidebar.modelType;
      const matchHorizon = modelsFilterSidebar.horizon === "all" || m.horizon === modelsFilterSidebar.horizon;
      const matchRegion = modelsFilterSidebar.region === "all" || m.region === modelsFilterSidebar.region;
      return matchSearch && matchHealth && matchType && matchHorizon && matchRegion;
    });
  }, [modelsData, modelsListSearch, modelsHealthFilter, modelsFilterSidebar]);

  const modelStats = useMemo(() => {
    const total = modelsData.length;
    const active = modelsData.filter((m) => getModelHealth(m) === "ok").length;
    const warnings = modelsData.filter((m) => getModelHealth(m) === "warning").length;
    const errors = modelsData.filter((m) => getModelHealth(m) === "error").length;
    return { total, active, warnings, errors };
  }, [modelsData]);

  // ── TASK DETAIL PANEL ──────────────────────────────────────────────────────
  function renderTaskDetailPanel() {
    return html`
      <aside className="detail-panel monitor-card">
        <div className="detail-head">
          <div>
            <h3>${(selectedTask?.task_name || "run_forecast").replace("forecasting.", "")}</h3>
            <p>${selectedTask?.model_type || "--"}</p>
          </div>
          <button type="button" className="close-btn" onClick=${() => { setSelectedTaskId(""); setSelectedTask(null); }}>✕</button>
        </div>

        <div className="detail-tabs">
          <button type="button" className=${`tab-btn ${taskDetailTab === "details" ? "active" : ""}`} onClick=${() => setTaskDetailTab("details")}>Детали</button>
          <button type="button" className=${`tab-btn ${taskDetailTab === "model" ? "active" : ""}`} onClick=${() => setTaskDetailTab("model")}>Данные модели</button>
          <button type="button" className=${`tab-btn ${taskDetailTab === "sources" ? "active" : ""}`} onClick=${() => setTaskDetailTab("sources")}>Источники</button>
        </div>

        ${detailLoading && !selectedTask
          ? html`<p className="empty-state">Loading task details...</p>`
          : selectedTask && html`
              ${taskDetailTab === "details" && html`
                <section className="detail-section">
                  <h4>TASK</h4>
                  <dl>
                    <div><dt>task_id</dt><dd className="mono">${selectedTask.task_id}</dd></div>
                    <div><dt>state</dt><dd><span className=${`state-badge ${classForDisplayState(selectedTask.display_state)}`}>${selectedTask.display_state}</span></dd></div>
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
                    ${Object.entries(selectedTask.sources || {}).map(([name, val]) => html`
                      <span key=${name} className=${`detail-pill ${name} ${val.enabled ? "enabled" : "disabled"}`}>
                        ${sourceLabel(name)} ${sourceName(name)} ${val.enabled ? "✓" : "—"}
                      </span>
                    `)}
                  </div>
                </section>

                <section className="detail-section">
                  <h4>POLL HISTORY</h4>
                  <div className="history-list">
                    ${(selectedTask.poll_history || []).map((entry, idx) => html`
                      <div key=${`${entry.timestamp}-${idx}`} className="history-row">
                        <span>${formatClock(entry.timestamp)}</span>
                        <strong>${entry.status}</strong>
                        <small>${entry.state}</small>
                      </div>
                    `)}
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
                          ${(selectedTask.result_preview || []).map((row, idx) => html`
                            <tr key=${idx}><td className="mono">${row[0]}</td><td>${row[1]}</td><td>${row[2]}</td></tr>
                          `)}
                        </tbody>
                      </table>
                    </div>
                  </section>
                `}

                ${selectedTask.display_state && selectedTask.display_state.startsWith("done ") && selectedTask.display_state !== "done 200" && html`
                  <section className="detail-section">
                    <h4>ERROR</h4>
                    <div className="error-banner">${selectedTask.error || selectedTaskResult?.message || "Request failed"}</div>
                  </section>
                `}

                <div className="detail-actions">
                  <button type="button" className="ghost-btn" onClick=${() => copyTaskId(selectedTask.task_id)}>Copy ID</button>
                  <button type="button" className="primary-btn" disabled=${!selectedTask.actions?.retry} onClick=${() => retryTask(selectedTask)}>Retry</button>
                </div>
              `}

              ${taskDetailTab === "model" && html`
                ${taskModelConfigLoading
                  ? html`<p className="empty-state">Loading model config...</p>`
                  : !taskModelConfig
                    ? html`
                        <p className="empty-state">
                          ${selectedTask.model_id === "none" || !selectedTask.model_id
                            ? "Онлайн-режим: модель строится на лету, конфиг отсутствует."
                            : "Конфиг модели не найден на диске."}
                        </p>
                      `
                    : html`
                        <section className="detail-section">
                          <h4>MODEL</h4>
                          <dl>
                            <div><dt>model_id</dt><dd className="mono">${taskModelConfig.model_id}</dd></div>
                            <div><dt>path</dt><dd className="mono muted-text">${taskModelConfig.config_path}</dd></div>
                          </dl>
                        </section>

                        ${taskModelConfig.normalized_config && html`
                          <section className="detail-section">
                            <h4>PARAMETERS</h4>
                            <dl>
                              ${Object.entries(taskModelConfig.normalized_config).filter(([k]) =>
                                ["seasonality_mode","yearly_seasonality","weekly_seasonality","daily_seasonality","step","output_range"].includes(k)
                              ).map(([k, v]) => html`
                                <div key=${k}><dt>${k}</dt><dd>${v !== null && v !== undefined ? String(v) : "--"}</dd></div>
                              `)}
                            </dl>
                          </section>
                        `}

                        <section className="detail-section">
                          <h4>RAW CONFIG</h4>
                          <pre className="json-viewer">${JSON.stringify(taskModelConfig.raw_config || {}, null, 2)}</pre>
                        </section>

                        <div className="detail-actions">
                          <button type="button" className="ghost-btn" onClick=${() => {
                            const blob = new Blob([JSON.stringify(taskModelConfig.raw_config, null, 2)], {type: "application/json"});
                            const a = document.createElement("a");
                            a.href = URL.createObjectURL(blob);
                            a.download = `${taskModelConfig.model_id.replace(/\//g, "_")}_config.json`;
                            a.click();
                          }}>↓ JSON</button>
                          <button type="button" className="ghost-btn" onClick=${() => setSelectedModelId(selectedTask.model_id)}>Открыть в Models</button>
                        </div>
                      `}
              `}

              ${taskDetailTab === "sources" && html`
                <section className="detail-section">
                  <h4>SOURCES</h4>
                  <div className="detail-pills">
                    ${Object.entries(selectedTask.sources || {}).map(([name, val]) => html`
                      <span key=${name} className=${`detail-pill ${name} ${val.enabled ? "enabled" : "disabled"}`}>
                        ${sourceLabel(name)} ${sourceName(name)}
                      </span>
                    `)}
                  </div>
                </section>
                <section className="detail-section">
                  <p className="empty-state">Сырые данные источников хранятся в воркере и не передаются в monitor.<br/>Используйте логи воркера для детальной диагностики.</p>
                </section>
              `}
            `}
      </aside>
    `;
  }

  // ── MODEL DETAIL PANEL ─────────────────────────────────────────────────────
  function renderModelDetailPanel() {
    const m = selectedModelDetail;
    return html`
      <aside className="model-detail-panel monitor-card">
        <div className="detail-head">
          <div>
            <div className="model-detail-title">
              <span className=${`health-dot ${getHealthColor(getModelHealth(m || { health: "unknown" }))}`}></span>
              <h3>${m?.model_id || selectedModelId}</h3>
            </div>
            <p>${m?.model_type || "--"}</p>
          </div>
          <button type="button" className="close-btn" onClick=${() => { setSelectedModelId(""); setSelectedModelDetail(null); setModelRunsHistory([]); }}>✕</button>
        </div>

        <div className="detail-tabs">
          <button type="button" className=${`tab-btn ${modelDetailTab === "overview" ? "active" : ""}`} onClick=${() => setModelDetailTab("overview")}>Обзор</button>
          <button type="button" className=${`tab-btn ${modelDetailTab === "config" ? "active" : ""}`} onClick=${() => setModelDetailTab("config")}>Конфигурация</button>
          <button type="button" className=${`tab-btn ${modelDetailTab === "history" ? "active" : ""}`} onClick=${() => setModelDetailTab("history")}>История</button>
        </div>

        ${modelDetailLoading && !m
          ? html`<p className="empty-state">Loading...</p>`
          : html`
              ${modelDetailTab === "overview" && html`
                <section className="detail-content">
                  <div className="metrics-cards">
                    <article className="metric-card">
                      <span>MAPE</span>
                      <strong className=${getMapeColor(m?.mape)}>${m?.mape != null ? `${Number(m.mape).toFixed(2)}%` : "--"}</strong>
                    </article>
                    <article className="metric-card">
                      <span>Runs</span>
                      <strong>${m?.run_count || 0}</strong>
                    </article>
                    <article className="metric-card">
                      <span>Avg Runtime</span>
                      <strong>${formatSeconds(m?.avg_runtime_s)}</strong>
                    </article>
                    <article className="metric-card">
                      <span>Success</span>
                      <strong>${m?.success_rate != null ? `${Number(m.success_rate).toFixed(0)}%` : "--"}</strong>
                    </article>
                  </div>

                  ${m?.last_run && html`
                    <section className="detail-section">
                      <h4>ПОСЛЕДНИЙ ПРОГОН</h4>
                      <div className="last-run-block">
                        <div className="last-run-row">
                          <span>task_id</span>
                          <button type="button" className="linkish mono task-link" onClick=${() => {
                            setActiveTab("Tasks");
                            setSelectedTaskId(m.last_run.task_id);
                          }}>${truncateMiddle(m.last_run.task_id, 12, 6)}</button>
                        </div>
                        <div className="last-run-row">
                          <span>state</span>
                          <span className=${`state-badge small ${classForDisplayState(m.last_run.state)}`}>${m.last_run.state}</span>
                        </div>
                        <div className="last-run-row">
                          <span>worker</span>
                          <span>${m.last_run.worker || "—"}</span>
                        </div>
                        <div className="last-run-row">
                          <span>received</span>
                          <span>${formatRelative(m.last_run.received_at)}</span>
                        </div>
                        <div className="last-run-row">
                          <span>object</span>
                          <span className="muted-text small-text">${m.last_run.object_reference || "—"}</span>
                        </div>
                      </div>
                    </section>
                  `}

                  <section className="detail-section">
                    <h4>АТРИБУТЫ</h4>
                    <dl>
                      <div><dt>region</dt><dd>${m?.region || "—"}</dd></div>
                      <div><dt>horizon</dt><dd>${m?.horizon || "—"}</dd></div>
                      <div><dt>last run</dt><dd>${m?.last_run_at ? formatRelative(m.last_run_at) : "--"}</dd></div>
                      <div><dt>config updated</dt><dd>${m?.updated_at ? formatDateTime(m.updated_at * 1000) : "--"}</dd></div>
                    </dl>
                  </section>

                  <section className="detail-section">
                    <h4>ИСТОЧНИКИ</h4>
                    <div className="detail-pills">
                      ${Object.entries(m?.sources || {}).map(([name, val]) => html`
                        <span key=${name} className=${`detail-pill ${name} ${val.enabled ? "enabled" : "disabled"}`}>
                          ${sourceLabel(name)} ${sourceName(name)}
                        </span>
                      `)}
                    </div>
                  </section>

                  <div className="detail-actions model-footer-actions">
                    <button type="button" className="primary-btn" onClick=${() => openNewTaskWithModel(selectedModelId)}>▶ Запустить</button>
                    <button type="button" className="ghost-btn" onClick=${() => navigateToTasksWithModel(selectedModelId)}>→ Tasks</button>
                    <button type="button" className="ghost-btn muted" disabled>MLflow ↗</button>
                  </div>
                </section>
              `}

              ${modelDetailTab === "config" && html`
                <section className="detail-content">
                  ${m && html`
                    <section className="detail-section">
                      <h4>ПАРАМЕТРЫ</h4>
                      <dl>
                        <div><dt>seasonality_mode</dt><dd>${m.seasonality_mode || "--"}</dd></div>
                        <div><dt>yearly_seasonality</dt><dd>${m.yearly_seasonality != null ? String(m.yearly_seasonality) : "--"}</dd></div>
                        <div><dt>weekly_seasonality</dt><dd>${m.weekly_seasonality != null ? String(m.weekly_seasonality) : "--"}</dd></div>
                        <div><dt>daily_seasonality</dt><dd>${m.daily_seasonality != null ? String(m.daily_seasonality) : "--"}</dd></div>
                      </dl>
                    </section>

                    ${m.scada_sources && m.scada_sources.length > 0 && html`
                      <section className="detail-section">
                        <h4>АРХИВЫ SCADA</h4>
                        <div className="sources-list">
                          ${m.scada_sources.map((s, i) => html`
                            <span key=${i} className="source-tag">${typeof s === "string" ? s : JSON.stringify(s)}</span>
                          `)}
                        </div>
                      </section>
                    `}

                    <section className="detail-section">
                      <h4>RAW CONFIG</h4>
                      <pre className="json-viewer">${JSON.stringify(m.raw_config || {}, null, 2)}</pre>
                    </section>

                    <div className="detail-actions">
                      <button type="button" className="ghost-btn" onClick=${() => {
                        const blob = new Blob([JSON.stringify(m.raw_config, null, 2)], {type: "application/json"});
                        const a = document.createElement("a");
                        a.href = URL.createObjectURL(blob);
                        a.download = `${m.model_id.replace(/\//g, "_")}_config.json`;
                        a.click();
                      }}>↓ JSON</button>
                    </div>
                  `}
                </section>
              `}

              ${modelDetailTab === "history" && html`
                <section className="detail-content">
                  ${modelRunsLoading
                    ? html`<p className="empty-state">Loading history...</p>`
                    : !modelRunsHistory.length
                      ? html`<p className="empty-state">Нет завершённых прогонов</p>`
                      : html`
                          <div className="runs-table-wrap">
                            <table className="runs-table">
                              <thead>
                                <tr>
                                  <th>task_id</th>
                                  <th>Started</th>
                                  <th>Runtime</th>
                                  <th>Status</th>
                                  <th>MAPE</th>
                                </tr>
                              </thead>
                              <tbody>
                                ${modelRunsHistory.map((run, idx) => html`
                                  <tr key=${run.task_id || idx} className=${idx === 0 ? "latest-run-row" : ""}>
                                    <td>
                                      <button type="button" className="linkish mono" style="font-size:11px" onClick=${() => {
                                        setActiveTab("Tasks");
                                        setSelectedTaskId(run.task_id);
                                      }}>${truncateMiddle(run.task_id)}</button>
                                    </td>
                                    <td>${formatDateTime(run.received_at)}</td>
                                    <td className="mono">${formatSeconds(run.runtime_s)}</td>
                                    <td><span className=${`state-badge small ${classForDisplayState(run.display_state)}`}>${run.display_state}</span></td>
                                    <td>${run.quality != null ? `${Number(run.quality).toFixed(1)}%` : "--"}</td>
                                  </tr>
                                `)}
                              </tbody>
                            </table>
                          </div>
                          <div className="runs-stats">
                            <span>Всего: ${modelRunsHistory.length}</span>
                            <span>✓ ${modelRunsHistory.filter((r) => r.display_state === "done 200").length}</span>
                            <span>✗ ${modelRunsHistory.filter((r) => r.display_state && r.display_state.startsWith("done ") && r.display_state !== "done 200").length}</span>
                          </div>

                          <div className="detail-actions">
                            <button type="button" className="ghost-btn" onClick=${() => navigateToTasksWithModel(selectedModelId)}>→ Все в Tasks</button>
                            <button type="button" className="primary-btn" onClick=${() => openNewTaskWithModel(selectedModelId)}>▶ Запустить</button>
                          </div>
                        `}
                </section>
              `}
            `}
      </aside>
    `;
  }

  // ── CONTENT TABS ───────────────────────────────────────────────────────────
  const content = useMemo(() => {
    if (activeTab === "Workers") return html`
      <section className="monitor-card placeholder-card">
        <div className="section-head"><h2>Workers</h2><p>Текущая сводка по пулу taskiq и runtime сервера.</p></div>
        <div className="worker-grid">
          ${workers.map((w) => html`
            <article key=${w.name} className=${`worker-card ${w.status}`}>
              <strong>${w.name}</strong><span>${w.status}</span><small>active: ${w.active_tasks}</small>
            </article>
          `)}
          <article className="worker-card neutral">
            <strong>Runtime</strong>
            <span>CPU 1m: ${runtimeStatus?.cpu_load?.load_1m ?? "--"}</span>
            <small>RSS: ${runtimeStatus?.memory?.rss_mb ?? "--"} MB</small>
          </article>
        </div>
      </section>
    `;

    if (activeTab === "Queues") return html`
      <section className="monitor-card placeholder-card">
        <div className="section-head"><h2>Queues</h2><p>Сводка очередей из monitor registry.</p></div>
        <div className="queue-grid">
          ${queues.map((q) => html`
            <article key=${q.name} className=${`queue-card ${q.kind}`}>
              <strong>${q.name}</strong><span>${q.count}</span>
            </article>
          `)}
        </div>
      </section>
    `;

    if (activeTab === "Models") return html`
      <section className="models-layout">
        <aside className="models-sidebar">
          <div className="sidebar-section">
            <h3>Model Type</h3>
            ${["all","Prophet","ARIMA","XGBoost","ETS"].map((t) => html`
              <button key=${t} type="button" className=${`sidebar-item ${modelsFilterSidebar.modelType === t ? "active" : ""}`}
                onClick=${() => setModelsFilterSidebar((c) => ({ ...c, modelType: t }))}>
                <span className="sidebar-label">${t === "all" ? "All types" : t}</span>
              </button>
            `)}
          </div>
          <div className="sidebar-section">
            <h3>Horizon</h3>
            ${["all","short","medium","long"].map((h) => html`
              <button key=${h} type="button" className=${`sidebar-item ${modelsFilterSidebar.horizon === h ? "active" : ""}`}
                onClick=${() => setModelsFilterSidebar((c) => ({ ...c, horizon: h }))}>
                <span className="sidebar-label">${h === "all" ? "All" : h.charAt(0).toUpperCase() + h.slice(1)}</span>
              </button>
            `)}
          </div>
          <div className="sidebar-section">
            <h3>Region</h3>
            ${["all","AKMOLA","AKTOBE","ALMATY"].map((r) => html`
              <button key=${r} type="button" className=${`sidebar-item ${modelsFilterSidebar.region === r ? "active" : ""}`}
                onClick=${() => setModelsFilterSidebar((c) => ({ ...c, region: r }))}>
                <span className="sidebar-label">${r === "all" ? "All regions" : r}</span>
              </button>
            `)}
          </div>
        </aside>

        <section className="models-main">
          <div className="toolbar-card">
            <div className="section-head between compact">
              <div><h2>Models</h2><p>Просмотр и управление моделями прогнозирования.</p></div>
              <button type="button" className="ghost-btn" onClick=${() => loadModelsList()}>Обновить</button>
            </div>
            <div className="toolbar-row">
              <input className="search-input" placeholder="Поиск по model_id..." value=${modelsListSearch} onInput=${(e) => setModelsListSearch(e.target.value)} />
              <select value=${modelsHealthFilter} onChange=${(e) => setModelsHealthFilter(e.target.value)}>
                <option value="all">All health</option>
                <option value="ok">OK</option>
                <option value="warning">Warning</option>
                <option value="error">Error</option>
              </select>
              <div className="view-toggle">
                <button type="button" className=${`view-btn ${modelsViewMode === "list" ? "active" : ""}`} onClick=${() => setModelsViewMode("list")} title="List">⊞</button>
                <button type="button" className=${`view-btn ${modelsViewMode === "cards" ? "active" : ""}`} onClick=${() => setModelsViewMode("cards")} title="Cards">▦</button>
              </div>
            </div>
          </div>

          <div className="stat-row monitor-card">
            <span>Всего: ${modelStats.total}</span>
            <span className="stat-ok">OK: ${modelStats.active}</span>
            <span className="stat-warn">Warn: ${modelStats.warnings}</span>
            <span className="stat-err">Err: ${modelStats.errors}</span>
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
                            <th>Src</th>
                            <th>Runs</th>
                            <th>Action</th>
                          </tr>
                        </thead>
                        <tbody>
                          ${modelsLoading
                            ? html`<tr><td colSpan="10" className="empty-row">Loading models...</td></tr>`
                            : !filteredModels.length
                              ? html`<tr><td colSpan="10" className="empty-row">Модели не найдены</td></tr>`
                              : filteredModels.map((model) => html`
                                  <tr key=${model.model_id} className=${selectedModelId === model.model_id ? "selected-row" : ""} onClick=${() => setSelectedModelId(model.model_id)}>
                                    <td className="center"><span className=${`health-dot ${getHealthColor(getModelHealth(model))}`}></span></td>
                                    <td className="clickable"><strong>${model.model_id}</strong></td>
                                    <td><span className="type-badge">${model.model_type || "--"}</span></td>
                                    <td><span className="horizon-badge">${model.horizon || "--"}</span></td>
                                    <td><span className=${getMapeColor(model.mape)}>${model.mape != null ? `${Number(model.mape).toFixed(1)}%` : "--"}</span></td>
                                    <td>${formatRelative(model.last_run_at)}</td>
                                    <td className="mono">${formatSeconds(model.avg_runtime_s)}</td>
                                    <td>${model.sources ? html`<${SourceIcons} sources=${model.sources} />` : "--"}</td>
                                    <td>${model.run_count || 0}</td>
                                    <td>
                                      <button type="button" className="table-action" onClick=${(e) => { e.stopPropagation(); openNewTaskWithModel(model.model_id); }}>▶</button>
                                    </td>
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
                                <div className="card-row"><span>Type</span><strong>${model.model_type || "--"}</strong></div>
                                <div className="card-row"><span>MAPE</span><strong className=${getMapeColor(model.mape)}>${model.mape != null ? `${Number(model.mape).toFixed(1)}%` : "--"}</strong></div>
                                <div className="card-row"><span>Last run</span><strong>${formatRelative(model.last_run_at)}</strong></div>
                                <div className="card-row"><span>Runs</span><strong>${model.run_count || 0}</strong></div>
                              </div>
                            </article>
                          `)}
                  </div>
                `}

            ${selectedModelId && renderModelDetailPanel()}
          </div>
        </section>
      </section>
    `;

    // Tasks tab (default)
    return html`
      <section className="tasks-layout">
        <aside className="sidebar">
          <div className="sidebar-section">
            <h3>Очереди</h3>
            ${queues.map((q) => html`
              <button key=${q.name} type="button" className="sidebar-item"
                onClick=${() => setFilters((c) => ({ ...c, state: q.kind === "dead" ? "done_error" : c.state }))}>
                <span className=${`queue-dot ${q.kind}`}></span>
                <span className="sidebar-label">${q.name}</span>
                <strong>${q.count}</strong>
              </button>
            `)}
          </div>
          <div className="sidebar-section">
            <h3>Воркеры</h3>
            ${workers.map((w) => html`
              <button key=${w.name} type="button" className="sidebar-item"
                onClick=${() => setFilters((c) => ({ ...c, worker: w.name === "taskiq-pool" ? "all" : w.name }))}>
                <span className=${`worker-dot ${w.status}`}></span>
                <span className="sidebar-label">${w.name}</span>
                <small>${w.status}</small>
              </button>
            `)}
          </div>
          <div className="sidebar-section">
            <h3>Быстрые фильтры</h3>
            <button type="button" className="sidebar-item" onClick=${() => setFilters((c) => ({ ...c, state: "processing" }))}>
              <span className="sidebar-label">Выполняются</span><strong>${quickFilters.active || 0}</strong>
            </button>
            <button type="button" className="sidebar-item" onClick=${() => setFilters((c) => ({ ...c, state: "start" }))}>
              <span className="sidebar-label">Ожидают</span><strong>${quickFilters.queued || 0}</strong>
            </button>
            <button type="button" className="sidebar-item" onClick=${() => setFilters((c) => ({ ...c, state: "done_error" }))}>
              <span className="sidebar-label">Ошибки</span><strong>${quickFilters.errors_24h || 0}</strong>
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
              <div><h2>Tasks</h2><p>Мониторинг задач прогнозирования в реальном времени.</p></div>
              <span className="error-text">${tasksError}</span>
            </div>
            <div className="chip-row">
              ${STATE_CHIPS.map((chip) => html`
                <button key=${chip.key} type="button" className=${`state-chip ${filters.state === chip.key ? "active" : ""}`}
                  onClick=${() => { setFilters((c) => ({ ...c, state: chip.key })); setPage(1); }}>
                  ${chip.label}
                </button>
              `)}
            </div>
            <div className="toolbar-row">
              <input className="search-input" placeholder="Поиск task_id, object_reference, model_id..." value=${searchInput} onInput=${(e) => setSearchInput(e.target.value)} />
              <select value=${filters.worker} onChange=${(e) => { setFilters((c) => ({ ...c, worker: e.target.value })); setPage(1); }}>
                <option value="all">All workers</option>
                ${tasksResponse.available_workers.map((w) => html`<option key=${w} value=${w}>${w}</option>`)}
              </select>
              <select value=${filters.model} onChange=${(e) => { setFilters((c) => ({ ...c, model: e.target.value })); setPage(1); }}>
                <option value="all">All models</option>
                ${tasksResponse.available_models.map((m) => html`<option key=${m} value=${m}>${m}</option>`)}
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
            <span>avg: ${formatSeconds(tasksResponse.avg_runtime_s)}</span>
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
                            <tr key=${task.task_id}
                              className=${`${selectedTaskId === task.task_id ? "selected-row" : ""} ${task.display_state === "expired" ? "expired-row" : ""}`}
                              onClick=${() => { setSelectedTaskId(task.task_id); setTaskDetailTab("details"); }}>
                              <td className="mono clickable" title=${task.task_id}>
                                <button type="button" className="linkish" onClick=${(e) => { e.stopPropagation(); copyTaskId(task.task_id); }}>
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
                                ${task.display_state === "processing" && html`
                                  <div className="mini-progress"><span style=${{ width: `${progressPercent(task, tasksResponse.avg_runtime_s)}%` }}></span></div>
                                `}
                              </td>
                              <td title=${formatDateTime(task.received_at)}>${formatRelative(task.received_at)}</td>
                              <td className="mono">${formatSeconds(task.runtime_s)}</td>
                              <td>${html`<${SourceIcons} sources=${task.sources} />`}</td>
                              <td>${task.worker || "unassigned"}</td>
                              <td>
                                ${task.actions?.retry
                                  ? html`<button type="button" className="table-action" onClick=${(e) => { e.stopPropagation(); retryTask(task); }}>Retry</button>`
                                  : html`<button type="button" className="table-action muted" disabled>—</button>`}
                              </td>
                            </tr>
                          `)}
                  </tbody>
                </table>
              </div>
              <div className="table-footer">
                <span>Showing ${startRow}–${endRow} of ${tasksResponse.total || 0}</span>
                <div className="pagination">
                  <button type="button" disabled=${page <= 1} onClick=${() => setPage((c) => Math.max(c - 1, 1))}>Prev</button>
                  <span>${page} / ${pageCount}</span>
                  <button type="button" disabled=${page >= pageCount} onClick=${() => setPage((c) => Math.min(c + 1, pageCount))}>Next</button>
                </div>
              </div>
            </div>

            ${selectedTaskId && renderTaskDetailPanel()}
          </div>
        </section>
      </section>
    `;
  }, [
    activeTab, workers, queues, runtimeStatus, tasksResponse, tasksLoading,
    selectedTaskId, selectedTask, detailLoading, taskDetailTab, taskModelConfig, taskModelConfigLoading,
    copiedTaskId, filters, searchInput, page,
    modelsData, filteredModels, modelsLoading, selectedModelId,
    selectedModelDetail, modelDetailLoading, modelRunsHistory, modelRunsLoading,
    modelDetailTab, modelsViewMode, modelsHealthFilter, modelsListSearch, modelsFilterSidebar, modelStats,
  ]);

  return html`
    <div className="monitor-shell">
      <header className="topbar">
        <div className="brand-block">
          <strong>ML Forecast Platform</strong>
          <nav className="top-tabs">
            ${TAB_ITEMS.map((tab) => html`
              <button key=${tab} type="button" className=${`tab-btn ${activeTab === tab ? "active" : ""}`} onClick=${() => setActiveTab(tab)}>${tab}</button>
            `)}
          </nav>
        </div>
        <div className="topbar-actions">
          <button type="button" className=${`auto-toggle ${autoRefresh ? "active" : ""}`} onClick=${() => setAutoRefresh((c) => !c)}>↻ auto</button>
          <span className=${`live-indicator ${liveOk ? "online" : "offline"}`}>● live</span>
          <span className="topbar-time">${new Date().toLocaleTimeString("ru-RU")}</span>
          <button type="button" className="primary-btn" onClick=${() => { setSubmitError(""); setIsNewTaskOpen(true); }}>+ New task</button>
        </div>
      </header>

      <main className="monitor-content">${content}</main>

      ${isNewTaskOpen && html`
        <div className="modal-backdrop" onClick=${() => setIsNewTaskOpen(false)}>
          <div className="modal-card" onClick=${(e) => e.stopPropagation()}>
            <div className="detail-head">
              <div><h3>New forecast task</h3><p>POST /predict</p></div>
              <button type="button" className="close-btn" onClick=${() => setIsNewTaskOpen(false)}>✕</button>
            </div>
            <div className="form-grid">
              <label className="wide">
                <span>model_id</span>
                <select value=${newTaskForm.model_id} onChange=${(e) => setNewTaskForm((c) => ({ ...c, model_id: e.target.value }))}>
                  <option value="none">none (онлайн-режим)</option>
                  ${registeredModels.map((m) => html`<option key=${m.model_id} value=${m.model_id}>${m.model_id}</option>`)}
                </select>
              </label>
              <label className="wide">
                <span>object_reference</span>
                <input value=${newTaskForm.object_reference} onInput=${(e) => setNewTaskForm((c) => ({ ...c, object_reference: e.target.value }))} />
              </label>
            </div>
            <p className="hint-text">Отправляет POST /predict с object_reference и model_id.</p>
            <p className="error-text">${submitError}</p>
            <div className="modal-actions">
              <button type="button" className="ghost-btn" onClick=${() => setIsNewTaskOpen(false)}>Отмена</button>
              <button type="button" className="primary-btn" onClick=${() => submitNewTask()}>Запустить ▶</button>
            </div>
          </div>
        </div>
      `}
    </div>
  `;
}

createRoot(document.getElementById("root")).render(React.createElement(App));
