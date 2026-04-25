import React, { useEffect, useMemo, useState } from "https://esm.sh/react@18.3.1";
import { createRoot } from "https://esm.sh/react-dom@18.3.1/client";
import htm from "https://esm.sh/htm@3.1.1";

const html = htm.bind(React.createElement);
const STORAGE_KEY = "forecast-wizard-state-v1";
const STEP_TITLES = [
  "Источник данных",
  "Редактор / очистка",
  "Модель",
  "Запуск",
  "Результаты",
];
const MODEL_LIST = ["Prophet", "ARIMA", "XGBoost"];

const REQUEST_STATS_DEFAULT = {
  total: 0,
  success: 0,
  failed: 0,
  totalDurationMs: 0,
  lastDurationMs: 0,
  byType: {
    upload: 0,
    autofix: 0,
    modelRun: 0,
    modelList: 0,
    modelConfig: 0,
  },
};

function sleep(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function parseCsvLine(line) {
  const result = [];
  let value = "";
  let inQuotes = false;

  for (let i = 0; i < line.length; i += 1) {
    const char = line[i];
    const next = line[i + 1];
    if (char === '"') {
      if (inQuotes && next === '"') {
        value += '"';
        i += 1;
      } else {
        inQuotes = !inQuotes;
      }
      continue;
    }

    if (char === "," && !inQuotes) {
      result.push(value.trim());
      value = "";
      continue;
    }

    value += char;
  }

  result.push(value.trim());
  return result;
}

function parseCsv(text) {
  const lines = text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);

  if (lines.length < 2) {
    throw new Error("CSV must include header and at least one row");
  }

  const headers = parseCsvLine(lines[0]);
  const rows = lines.slice(1).map((line, index) => {
    const cols = parseCsvLine(line);
    const row = { __row_id: index };
    headers.forEach((header, i) => {
      row[header] = cols[i] ?? "";
    });
    return row;
  });

  return { headers, rows };
}

function toNumber(value) {
  const num = Number(String(value).replace(",", "."));
  return Number.isFinite(num) ? num : null;
}

function computeMedian(values) {
  if (!values.length) {
    return 0;
  }
  const sorted = [...values].sort((a, b) => a - b);
  const half = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[half] : (sorted[half - 1] + sorted[half]) / 2;
}

function quantile(values, q) {
  if (!values.length) {
    return 0;
  }
  const sorted = [...values].sort((a, b) => a - b);
  const pos = (sorted.length - 1) * q;
  const base = Math.floor(pos);
  const rest = pos - base;
  if (sorted[base + 1] !== undefined) {
    return sorted[base] + rest * (sorted[base + 1] - sorted[base]);
  }
  return sorted[base];
}

function computeColumnStats(rows, headers) {
  const stats = {};

  headers.forEach((header) => {
    const values = rows
      .map((row) => toNumber(row[header]))
      .filter((value) => value !== null);

    if (!values.length) {
      return;
    }

    const mean = values.reduce((acc, val) => acc + val, 0) / values.length;
    const variance = values.reduce((acc, val) => acc + (val - mean) ** 2, 0) / values.length;
    const std = Math.sqrt(variance);
    stats[header] = {
      mean,
      std,
      median: computeMedian(values),
      p05: quantile(values, 0.05),
      p95: quantile(values, 0.95),
    };
  });

  return stats;
}

function detectDateColumn(headers, rows) {
  for (const header of headers) {
    const sample = rows.slice(0, 10).map((row) => row[header]);
    const parsed = sample.filter((value) => !Number.isNaN(new Date(value).getTime()));
    if (parsed.length >= Math.max(3, Math.floor(sample.length * 0.6))) {
      return header;
    }
  }
  return null;
}

function buildSeries(rows, target, rangeStart, rangeEnd) {
  const safeStart = clamp(rangeStart, 0, rows.length - 1);
  const safeEnd = clamp(rangeEnd, safeStart, rows.length - 1);
  return rows
    .slice(safeStart, safeEnd + 1)
    .map((row, index) => {
      const value = toNumber(row[target]);
      return {
        i: safeStart + index,
        value,
      };
    })
    .filter((point) => point.value !== null);
}

function renderMiniPath(series, width, height, pad = 14) {
  if (!series.length) {
    return "";
  }
  const values = series.map((point) => point.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = Math.max(max - min, 1);

  return series
    .map((point, idx) => {
      const x = pad + (idx / Math.max(series.length - 1, 1)) * (width - pad * 2);
      const y = height - pad - ((point.value - min) / span) * (height - pad * 2);
      return `${x},${y}`;
    })
    .join(" ");
}

function calcMetrics(actual, predicted) {
  const n = Math.min(actual.length, predicted.length);
  if (!n) {
    return {
      mape: 0,
      rmse: 0,
      mae: 0,
      r2: 0,
      maxDeviation: 0,
      score: 0,
    };
  }

  let absPct = 0;
  let sq = 0;
  let abs = 0;
  let maxDev = 0;

  for (let i = 0; i < n; i += 1) {
    const error = predicted[i] - actual[i];
    const denom = Math.max(Math.abs(actual[i]), 1e-6);
    absPct += Math.abs(error) / denom;
    sq += error ** 2;
    abs += Math.abs(error);
    maxDev = Math.max(maxDev, Math.abs(error));
  }

  const mean = actual.reduce((acc, value) => acc + value, 0) / n;
  const ssTot = actual.reduce((acc, value) => acc + (value - mean) ** 2, 0);
  const ssRes = actual.reduce((acc, value, i) => acc + (value - predicted[i]) ** 2, 0);

  const mape = (absPct / n) * 100;
  const rmse = Math.sqrt(sq / n);
  const mae = abs / n;
  const r2 = ssTot > 0 ? 1 - ssRes / ssTot : 0;
  const scale = Math.max(...actual.map((value) => Math.abs(value)), 1);
  const penalty = mape * 0.45 + (rmse / scale) * 22 + (mae / scale) * 18 + (1 - r2) * 10 + (maxDev / scale) * 10;
  const score = clamp(100 - penalty, 0, 100);

  return {
    mape,
    rmse,
    mae,
    r2,
    maxDeviation: maxDev,
    score,
  };
}

function forecastWithModel(model, train, horizon) {
  const last = train[train.length - 1] ?? 0;
  if (model === "Prophet") {
    const window = Math.min(24, train.length);
    const tail = train.slice(-window);
    const avg = tail.reduce((acc, value) => acc + value, 0) / Math.max(tail.length, 1);
    const trend = train.length > 8 ? (train[train.length - 1] - train[train.length - 8]) / 8 : 0;
    return Array.from({ length: horizon }, (_, idx) => avg + trend * (idx + 1));
  }

  if (model === "ARIMA") {
    const diffs = [];
    for (let i = 1; i < train.length; i += 1) {
      diffs.push(train[i] - train[i - 1]);
    }
    const drift = diffs.length ? diffs.reduce((acc, value) => acc + value, 0) / diffs.length : 0;
    return Array.from({ length: horizon }, (_, idx) => last + drift * (idx + 1));
  }

  const short = train.slice(-6);
  const long = train.slice(-18);
  const shortMean = short.reduce((acc, value) => acc + value, 0) / Math.max(short.length, 1);
  const longMean = long.reduce((acc, value) => acc + value, 0) / Math.max(long.length, 1);
  const boost = (shortMean - longMean) * 0.6;
  return Array.from({ length: horizon }, (_, idx) => last + boost * ((idx + 1) / Math.max(horizon, 1)));
}

function pointQuality(absPctError) {
  if (absPctError <= 5) {
    return "good";
  }
  if (absPctError <= 15) {
    return "warn";
  }
  return "bad";
}

function nowTime() {
  return new Date().toLocaleTimeString("ru-RU", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function formatMs(value) {
  return `${Math.round(value)} ms`;
}

function App() {
  const [step, setStep] = useState(1);
  const [source, setSource] = useState(() => {
    try {
      const parsed = JSON.parse(localStorage.getItem(STORAGE_KEY) || "null");
      return parsed || {
        fileName: "",
        headers: [],
        rows: [],
        target: "",
        regressors: [],
        rangeStart: 0,
        rangeEnd: 0,
        horizon: 24,
        dateColumn: null,
      };
    } catch (_error) {
      return {
        fileName: "",
        headers: [],
        rows: [],
        target: "",
        regressors: [],
        rangeStart: 0,
        rangeEnd: 0,
        horizon: 24,
        dateColumn: null,
      };
    }
  });
  const [cleanRows, setCleanRows] = useState(() => source.rows || []);
  const [cleaningMethod, setCleaningMethod] = useState("median");
  const [cleanConfirmed, setCleanConfirmed] = useState(false);
  const [selectedModels, setSelectedModels] = useState(["Prophet", "ARIMA"]);
  const [params, setParams] = useState({
    prophet: { changepoint: 0.15, seasonality: 0.4, interval: 0.8 },
    arima: { p: 2, d: 1, q: 1 },
    xgb: { depth: 5, learningRate: 0.08, estimators: 200 },
    validation: { split: 20, folds: 3, metric: "MAPE" },
  });
  const [runs, setRuns] = useState({});
  const [runLogs, setRunLogs] = useState([]);
  const [runInProgress, setRunInProgress] = useState(false);
  const [requestStats, setRequestStats] = useState(REQUEST_STATS_DEFAULT);
  const [registeredModels, setRegisteredModels] = useState([]);
  const [modelsLoading, setModelsLoading] = useState(false);
  const [modelsError, setModelsError] = useState("");
  const [selectedModelId, setSelectedModelId] = useState("");
  const [selectedModelConfig, setSelectedModelConfig] = useState(null);

  useMemo(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(source));
    return null;
  }, [source]);

  const rowCount = source.rows.length;
  const rangeSeries = useMemo(
    () => (source.target ? buildSeries(cleanRows, source.target, source.rangeStart, source.rangeEnd) : []),
    [source.target, source.rangeStart, source.rangeEnd, cleanRows],
  );
  const previewPath = useMemo(() => renderMiniPath(rangeSeries, 820, 220), [rangeSeries]);
  const colStats = useMemo(() => computeColumnStats(cleanRows, source.headers), [cleanRows, source.headers]);

  const canStep2 = rowCount > 0 && !!source.target;
  const canStep3 = canStep2 && cleanConfirmed;
  const canStep4 = canStep3 && selectedModels.length > 0;
  const canStep5 = Object.values(runs).some((item) => item.status === "done");

  function switchStep(next) {
    if (next === 2 && !canStep2) {
      return;
    }
    if (next === 3 && !canStep3) {
      return;
    }
    if (next === 4 && !canStep4) {
      return;
    }
    if (next === 5 && !canStep5) {
      return;
    }
    setStep(next);
  }

  function addLog(level, message) {
    setRunLogs((current) => [
      { ts: nowTime(), level, message },
      ...current,
    ].slice(0, 200));
  }

  function trackRequest(type, startedAt, ok) {
    const durationMs = performance.now() - startedAt;
    setRequestStats((current) => ({
      ...current,
      total: current.total + 1,
      success: current.success + (ok ? 1 : 0),
      failed: current.failed + (ok ? 0 : 1),
      totalDurationMs: current.totalDurationMs + durationMs,
      lastDurationMs: durationMs,
      byType: {
        ...current.byType,
        [type]: (current.byType[type] || 0) + 1,
      },
    }));
  }

  async function onFileUpload(event) {
    const startedAt = performance.now();
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }

    try {
      const text = await file.text();
      const parsed = parseCsv(text);
      const dateColumn = detectDateColumn(parsed.headers, parsed.rows);
      const target = parsed.headers[1] || parsed.headers[0] || "";

      setSource({
        fileName: file.name,
        headers: parsed.headers,
        rows: parsed.rows,
        target,
        regressors: parsed.headers.filter((header) => header !== target).slice(0, 2),
        rangeStart: 0,
        rangeEnd: Math.max(parsed.rows.length - 1, 0),
        horizon: 24,
        dateColumn,
      });
      setCleanRows(parsed.rows);
      setCleanConfirmed(false);
      setRuns({});
      setRunLogs([]);
      addLog("info", `Loaded file ${file.name}, rows=${parsed.rows.length}`);
      trackRequest("upload", startedAt, true);
    } catch (error) {
      addLog("warn", `Upload failed: ${error.message || String(error)}`);
      trackRequest("upload", startedAt, false);
    }
  }

  function updateSourceField(field, value) {
    setSource((current) => ({ ...current, [field]: value }));
    if (field === "target" || field === "rangeStart" || field === "rangeEnd") {
      setCleanConfirmed(false);
    }
  }

  function updateCell(rowId, col, value) {
    setCleanRows((current) => current.map((row) => (row.__row_id === rowId ? { ...row, [col]: value } : row)));
    setCleanConfirmed(false);
  }

  function cellStatus(row, col) {
    const raw = row[col];
    if (raw === "" || raw === null || raw === undefined) {
      return "missing";
    }

    const num = toNumber(raw);
    if (num === null || !colStats[col]) {
      return "ok";
    }

    const { mean, std } = colStats[col];
    if (std > 0 && Math.abs((num - mean) / std) > 3) {
      return "outlier";
    }

    return "ok";
  }

  function applyAutoFix() {
    const startedAt = performance.now();
    const stats = computeColumnStats(cleanRows, source.headers);
    const numericCols = source.headers.filter((col) => stats[col]);

    const next = cleanRows.map((row, rowIndex) => {
      const clone = { ...row };
      numericCols.forEach((col) => {
        const colStat = stats[col];
        const current = toNumber(clone[col]);
        const status = cellStatus(row, col);

        if (cleaningMethod === "median") {
          if (current === null || status === "outlier") {
            clone[col] = colStat.median.toFixed(3);
          }
          return;
        }

        if (cleaningMethod === "clip") {
          if (current === null) {
            clone[col] = colStat.median.toFixed(3);
          } else {
            clone[col] = clamp(current, colStat.p05, colStat.p95).toFixed(3);
          }
          return;
        }

        if (current !== null && status !== "missing") {
          return;
        }

        const prev = toNumber(cleanRows[Math.max(0, rowIndex - 1)]?.[col]);
        const nextVal = toNumber(cleanRows[Math.min(cleanRows.length - 1, rowIndex + 1)]?.[col]);
        if (prev !== null && nextVal !== null) {
          clone[col] = ((prev + nextVal) / 2).toFixed(3);
        } else if (prev !== null) {
          clone[col] = prev.toFixed(3);
        } else if (nextVal !== null) {
          clone[col] = nextVal.toFixed(3);
        } else {
          clone[col] = colStat.median.toFixed(3);
        }
      });
      return clone;
    });

    setCleanRows(next);
    setCleanConfirmed(false);
    addLog("warn", `Auto-fix applied using method: ${cleaningMethod}`);
    trackRequest("autofix", startedAt, true);
  }

  function confirmCleaning() {
    setCleanConfirmed(true);
    addLog("info", "Cleaning step confirmed by user");
  }

  function toggleModel(model) {
    setSelectedModels((current) => (
      current.includes(model)
        ? current.filter((item) => item !== model)
        : [...current, model]
    ));
  }

  function updateParam(path, value) {
    const [head, key] = path.split(".");
    setParams((current) => ({
      ...current,
      [head]: {
        ...current[head],
        [key]: value,
      },
    }));
  }

  async function runModels() {
    const series = buildSeries(cleanRows, source.target, source.rangeStart, source.rangeEnd).map((point) => point.value);
    const horizon = clamp(Number(source.horizon) || 24, 1, Math.max(1, Math.floor(series.length / 3)));
    if (series.length <= horizon + 3) {
      addLog("warn", "Not enough points to run models. Increase selected range.");
      return;
    }

    const train = series.slice(0, -horizon);
    const actual = series.slice(-horizon);
    setRunInProgress(true);
    setRuns({});
    addLog("info", `Starting run for ${selectedModels.length} models, horizon=${horizon}`);

    for (const model of selectedModels) {
      const modelRunStartedAt = performance.now();
      setRuns((current) => ({
        ...current,
        [model]: { status: "queued", progress: 0, metrics: null, predicted: [], actual },
      }));

      for (let p = 10; p <= 70; p += 15) {
        await sleep(260);
        setRuns((current) => ({
          ...current,
          [model]: { ...current[model], status: "running", progress: p },
        }));
      }

      const predicted = forecastWithModel(model, train, horizon);
      const metrics = calcMetrics(actual, predicted);
      await sleep(220);
      setRuns((current) => ({
        ...current,
        [model]: {
          ...current[model],
          status: "done",
          progress: 100,
          metrics,
          predicted,
          actual,
        },
      }));

      const warnCount = cleanRows.reduce((acc, row) => {
        const status = cellStatus(row, source.target);
        return acc + (status === "missing" || status === "outlier" ? 1 : 0);
      }, 0);
      if (warnCount > Math.floor(cleanRows.length * 0.08)) {
        addLog("warn", `${model}: elevated data quality risk (${warnCount} flagged points)`);
      }
      addLog("info", `${model}: completed, score=${metrics.score.toFixed(2)}`);
      trackRequest("modelRun", modelRunStartedAt, true);
    }

    setRunInProgress(false);
    setStep(5);
  }

  const resultRows = useMemo(() => (
    Object.entries(runs)
      .filter(([, data]) => data.status === "done")
      .map(([model, data]) => ({ model, ...data.metrics, predicted: data.predicted, actual: data.actual }))
      .sort((a, b) => b.score - a.score)
  ), [runs]);

  const resultSummary = useMemo(() => {
    if (!resultRows.length) {
      return {
        completedModels: 0,
        bestScore: 0,
        averageScore: 0,
        warningCount: runLogs.filter((item) => item.level === "warn").length,
      };
    }
    const scores = resultRows.map((row) => row.score);
    return {
      completedModels: resultRows.length,
      bestScore: Math.max(...scores),
      averageScore: scores.reduce((acc, score) => acc + score, 0) / scores.length,
      warningCount: runLogs.filter((item) => item.level === "warn").length,
    };
  }, [resultRows, runLogs]);

  const avgRequestDuration = requestStats.total
    ? requestStats.totalDurationMs / requestStats.total
    : 0;

  async function loadRegisteredModels() {
    const startedAt = performance.now();
    setModelsLoading(true);
    setModelsError("");
    try {
      const response = await fetch("/ui/models");
      const data = await response.json();

      if (!response.ok) {
        setModelsError(data.message || "Failed to load model list");
        setRegisteredModels([]);
        trackRequest("modelList", startedAt, false);
        return;
      }

      const models = Array.isArray(data.models) ? data.models : [];
      setRegisteredModels(models);
      if (models.length && !selectedModelId) {
        setSelectedModelId(models[0].model_id);
      }
      trackRequest("modelList", startedAt, true);
    } catch (error) {
      setModelsError(String(error));
      setRegisteredModels([]);
      trackRequest("modelList", startedAt, false);
    } finally {
      setModelsLoading(false);
    }
  }

  useEffect(() => {
    loadRegisteredModels();
  }, []);

  async function openModelCard(modelId) {
    const startedAt = performance.now();
    setSelectedModelId(modelId);
    setSelectedModelConfig(null);
    try {
      const response = await fetch(`/ui/model-config?model_id=${encodeURIComponent(modelId)}`);
      const data = await response.json();
      if (!response.ok) {
        addLog("warn", `Model config load failed for ${modelId}`);
        trackRequest("modelConfig", startedAt, false);
        return;
      }
      setSelectedModelConfig(data);
      trackRequest("modelConfig", startedAt, true);
    } catch (error) {
      addLog("warn", `Model config load failed for ${modelId}: ${String(error)}`);
      trackRequest("modelConfig", startedAt, false);
    }
  }

  const deviationRows = useMemo(() => {
    if (!resultRows.length) {
      return [];
    }
    const best = resultRows[0];
    const actual = best.actual;
    return actual.map((value, idx) => {
      const row = {
        idx,
        dateLabel: source.dateColumn
          ? String(cleanRows[clamp(source.rangeEnd - actual.length + 1 + idx, 0, cleanRows.length - 1)]?.[source.dateColumn] || `t+${idx + 1}`)
          : `t+${idx + 1}`,
        actual: value,
      };

      resultRows.forEach((modelItem) => {
        const pred = modelItem.predicted[idx] ?? null;
        const absPct = pred === null ? 0 : (Math.abs(pred - value) / Math.max(Math.abs(value), 1e-6)) * 100;
        row[`${modelItem.model}_pred`] = pred;
        row[`${modelItem.model}_quality`] = pointQuality(absPct);
      });

      return row;
    });
  }, [resultRows, source.dateColumn, source.rangeEnd, cleanRows]);

  const chartModelLines = useMemo(() => {
    if (!resultRows.length) {
      return null;
    }
    const width = 900;
    const height = 260;
    const pad = 24;
    const actual = resultRows[0].actual;
    const allValues = [...actual, ...resultRows.flatMap((item) => item.predicted)];
    const min = Math.min(...allValues);
    const max = Math.max(...allValues);
    const span = Math.max(max - min, 1);

    function toLine(values) {
      return values
        .map((value, idx) => {
          const x = pad + (idx / Math.max(values.length - 1, 1)) * (width - pad * 2);
          const y = height - pad - ((value - min) / span) * (height - pad * 2);
          return `${x},${y}`;
        })
        .join(" ");
    }

    return {
      actual: toLine(actual),
      models: resultRows.map((item) => ({
        model: item.model,
        line: toLine(item.predicted),
      })),
    };
  }, [resultRows]);

  const editColumns = source.headers.slice(0, 8);
  const visibleRows = cleanRows.slice(source.rangeStart, Math.min(source.rangeStart + 35, source.rangeEnd + 1));

  return html`
    <div className="wizard-shell">
      <header className="wizard-header">
        <div>
          <p className="eyebrow">Forecast Studio</p>
          <h1>Пятишаговый мастер прогнозирования</h1>
        </div>
        <div className="step-chip">Шаг ${step} / 5</div>
      </header>

      <nav className="wizard-steps">
        ${STEP_TITLES.map((title, idx) => {
          const next = idx + 1;
          const disabled =
            (next === 2 && !canStep2) ||
            (next === 3 && !canStep3) ||
            (next === 4 && !canStep4) ||
            (next === 5 && !canStep5);
          return html`
            <button
              key=${title}
              type="button"
              className=${`step-btn ${step === next ? "active" : ""}`}
              disabled=${disabled}
              onClick=${() => switchStep(next)}
            >
              <span>${next}</span>
              <small>${title}</small>
            </button>
          `;
        })}
      </nav>

      <section className="stats-grid">
        <article className="stat-card">
          <p>Запросов выполнено</p>
          <strong>${requestStats.total}</strong>
          <small>upload: ${requestStats.byType.upload}, auto-fix: ${requestStats.byType.autofix}, model run: ${requestStats.byType.modelRun}</small>
        </article>
        <article className="stat-card">
          <p>Успешно / с ошибкой</p>
          <strong>${requestStats.success} / ${requestStats.failed}</strong>
          <small>последний ответ: ${formatMs(requestStats.lastDurationMs)}</small>
        </article>
        <article className="stat-card">
          <p>Среднее время запроса</p>
          <strong>${formatMs(avgRequestDuration)}</strong>
          <small>по всем операциям интерфейса</small>
        </article>
        <article className="stat-card">
          <p>Завершено моделей</p>
          <strong>${resultSummary.completedModels}</strong>
          <small>текущий запуск</small>
        </article>
        <article className="stat-card">
          <p>Итоговый скор</p>
          <strong>${resultSummary.bestScore.toFixed(2)}</strong>
          <small>best: ${resultSummary.bestScore.toFixed(2)}, avg: ${resultSummary.averageScore.toFixed(2)}</small>
        </article>
        <article className="stat-card">
          <p>Предупреждения</p>
          <strong>${resultSummary.warningCount}</strong>
          <small>по логам выполнения</small>
        </article>
      </section>

      <section className="panel-card model-registry-card">
        <div className="model-registry-head">
          <h2>Реестр зарегистрированных моделей</h2>
          <button type="button" className="ghost" onClick=${() => {
            setSelectedModelConfig(null);
            setSelectedModelId("");
            setModelsError("");
            loadRegisteredModels();
          }}>Сбросить выбор</button>
        </div>
        <div className="model-registry-meta">
          <span>Найдено моделей: ${registeredModels.length}</span>
          <span>Запросов по конфигу: ${requestStats.byType.modelConfig}</span>
          <span>${modelsLoading ? "Загрузка списка..." : ""}</span>
          <span className="error-text">${modelsError}</span>
        </div>
        <div className="model-cards-grid">
          ${registeredModels.map((model) => html`
            <button
              key=${model.model_id}
              type="button"
              className=${`model-card ${selectedModelId === model.model_id ? "active" : ""}`}
              onClick=${() => openModelCard(model.model_id)}
            >
              <strong>${model.model_id}</strong>
              <small>${new Date(model.updated_at * 1000).toLocaleString("ru-RU")}</small>
            </button>
          `)}
        </div>
        ${selectedModelId && html`
          <div className="model-config-panel">
            <h3>Карточка модели: ${selectedModelId}</h3>
            ${selectedModelConfig
              ? html`
                  <div className="grid two">
                    <div>
                      <label>Raw config</label>
                      <pre className="config-viewer">${JSON.stringify(selectedModelConfig.raw_config, null, 2)}</pre>
                    </div>
                    <div>
                      <label>Normalized config</label>
                      <pre className="config-viewer">${JSON.stringify(selectedModelConfig.normalized_config, null, 2)}</pre>
                    </div>
                  </div>
                `
              : html`<p className="hint">Загрузка конфигурации модели...</p>`}
          </div>
        `}
      </section>

      <section className="wizard-content">
        ${step === 1 && html`
          <section className="panel-card">
            <h2>Экран 1 — Источник данных</h2>
            <div className="grid two">
              <div>
                <label>Загрузка файла (CSV)</label>
                <input type="file" accept=".csv,text/csv" onChange=${onFileUpload} />
                <p className="hint">${source.fileName ? `Загружено: ${source.fileName}` : "Файл еще не загружен"}</p>
              </div>
              <div>
                <label>Горизонт прогноза (точек)</label>
                <input type="number" min="1" max="720" value=${source.horizon} onInput=${(e) => updateSourceField("horizon", Number(e.target.value || 24))} />
              </div>
            </div>

            ${rowCount > 0 && html`
              <div className="grid three">
                <div>
                  <label>Целевая переменная</label>
                  <select value=${source.target} onChange=${(e) => updateSourceField("target", e.target.value)}>
                    ${source.headers.map((header) => html`<option key=${header} value=${header}>${header}</option>`)}
                  </select>
                </div>
                <div>
                  <label>Регрессоры</label>
                  <select multiple size="4" value=${source.regressors} onChange=${(e) => {
                    const selected = Array.from(e.target.selectedOptions).map((option) => option.value);
                    updateSourceField("regressors", selected);
                  }}>
                    ${source.headers
                      .filter((header) => header !== source.target)
                      .map((header) => html`<option key=${header} value=${header}>${header}</option>`)}
                  </select>
                </div>
                <div className="range-block">
                  <label>Диапазон строк</label>
                  <div className="inline-inputs">
                    <input type="number" min="0" max=${Math.max(rowCount - 1, 0)} value=${source.rangeStart} onInput=${(e) => updateSourceField("rangeStart", clamp(Number(e.target.value || 0), 0, Math.max(rowCount - 1, 0)))} />
                    <span>до</span>
                    <input type="number" min="0" max=${Math.max(rowCount - 1, 0)} value=${source.rangeEnd} onInput=${(e) => updateSourceField("rangeEnd", clamp(Number(e.target.value || rowCount - 1), 0, Math.max(rowCount - 1, 0)))} />
                  </div>
                </div>
              </div>
            `}

            <div className="chart-box">
              <h3>Мини-превью ряда</h3>
              ${rangeSeries.length
                ? html`
                    <svg viewBox="0 0 820 220" className="mini-chart" preserveAspectRatio="none">
                      <polyline points=${previewPath} fill="none" stroke="#2f6b59" strokeWidth="3" />
                    </svg>
                  `
                : html`<p className="empty">Загрузите CSV и выберите target для предпросмотра.</p>`}
            </div>

            <div className="actions">
              <button type="button" disabled=${!canStep2} onClick=${() => switchStep(2)}>Далее: Редактор / очистка</button>
            </div>
          </section>
        `}

        ${step === 2 && html`
          <section className="panel-card">
            <h2>Экран 2 — Редактор / очистка</h2>
            <div className="grid three compact">
              <div>
                <label>Метод автоисправления</label>
                <select value=${cleaningMethod} onChange=${(e) => setCleaningMethod(e.target.value)}>
                  <option value="median">Медиана + замена выбросов</option>
                  <option value="interpolate">Интерполяция пропусков</option>
                  <option value="clip">Клиппинг по перцентилям</option>
                </select>
              </div>
              <div className="legend-inline">
                <span className="cell-tag outlier">Янтарный: выброс</span>
                <span className="cell-tag missing">Красный: пропуск</span>
              </div>
              <div className="actions-inline">
                <button type="button" className="ghost" onClick=${applyAutoFix}>Применить автоисправление</button>
                <button type="button" disabled=${cleanConfirmed} onClick=${confirmCleaning}>Подтвердить данные</button>
              </div>
            </div>

            <div className="table-wrap tall">
              <table>
                <thead>
                  <tr>
                    <th>#</th>
                    ${editColumns.map((col) => html`<th key=${col}>${col}</th>`)}
                  </tr>
                </thead>
                <tbody>
                  ${visibleRows.map((row) => html`
                    <tr key=${row.__row_id}>
                      <td>${row.__row_id}</td>
                      ${editColumns.map((col) => {
                        const status = cellStatus(row, col);
                        return html`
                          <td key=${`${row.__row_id}-${col}`} className=${`editable-cell ${status !== "ok" ? status : ""}`}>
                            <input
                              value=${String(row[col] ?? "")}
                              onInput=${(e) => updateCell(row.__row_id, col, e.target.value)}
                            />
                          </td>
                        `;
                      })}
                    </tr>
                  `)}
                </tbody>
              </table>
            </div>

            <div className="actions between">
              <button type="button" className="ghost" onClick=${() => switchStep(1)}>Назад</button>
              <button type="button" disabled=${!cleanConfirmed} onClick=${() => switchStep(3)}>Далее: Модель</button>
            </div>
          </section>
        `}

        ${step === 3 && html`
          <section className="panel-card">
            <h2>Экран 3 — Модель</h2>

            <div className="chip-row">
              ${MODEL_LIST.map((model) => html`
                <button
                  key=${model}
                  type="button"
                  className=${`algo-chip ${selectedModels.includes(model) ? "selected" : ""}`}
                  onClick=${() => toggleModel(model)}
                >
                  ${model}
                </button>
              `)}
            </div>

            <div className="grid two">
              <div className="sub-card">
                <h3>Prophet</h3>
                <label>Changepoint Prior</label>
                <input type="number" step="0.01" min="0.01" max="1" value=${params.prophet.changepoint} onInput=${(e) => updateParam("prophet.changepoint", Number(e.target.value))} />
                <label>Seasonality Prior</label>
                <input type="number" step="0.01" min="0.01" max="2" value=${params.prophet.seasonality} onInput=${(e) => updateParam("prophet.seasonality", Number(e.target.value))} />
                <label>Interval Width</label>
                <input type="number" step="0.01" min="0.5" max="0.99" value=${params.prophet.interval} onInput=${(e) => updateParam("prophet.interval", Number(e.target.value))} />
              </div>

              <div className="sub-card">
                <h3>ARIMA / XGBoost</h3>
                <label>ARIMA p</label>
                <input type="number" min="0" max="6" value=${params.arima.p} onInput=${(e) => updateParam("arima.p", Number(e.target.value))} />
                <label>ARIMA d</label>
                <input type="number" min="0" max="2" value=${params.arima.d} onInput=${(e) => updateParam("arima.d", Number(e.target.value))} />
                <label>ARIMA q</label>
                <input type="number" min="0" max="6" value=${params.arima.q} onInput=${(e) => updateParam("arima.q", Number(e.target.value))} />
                <label>XGB Depth</label>
                <input type="number" min="2" max="12" value=${params.xgb.depth} onInput=${(e) => updateParam("xgb.depth", Number(e.target.value))} />
                <label>XGB Learning Rate</label>
                <input type="number" step="0.01" min="0.01" max="0.5" value=${params.xgb.learningRate} onInput=${(e) => updateParam("xgb.learningRate", Number(e.target.value))} />
                <label>XGB Estimators</label>
                <input type="number" min="50" max="600" value=${params.xgb.estimators} onInput=${(e) => updateParam("xgb.estimators", Number(e.target.value))} />
              </div>
            </div>

            <div className="sub-card validation-block">
              <h3>Валидация</h3>
              <div className="grid three compact">
                <div>
                  <label>Split (%)</label>
                  <input type="number" min="10" max="40" value=${params.validation.split} onInput=${(e) => updateParam("validation.split", Number(e.target.value))} />
                </div>
                <div>
                  <label>Folds</label>
                  <input type="number" min="2" max="10" value=${params.validation.folds} onInput=${(e) => updateParam("validation.folds", Number(e.target.value))} />
                </div>
                <div>
                  <label>Primary Metric</label>
                  <select value=${params.validation.metric} onChange=${(e) => updateParam("validation.metric", e.target.value)}>
                    <option value="MAPE">MAPE</option>
                    <option value="RMSE">RMSE</option>
                    <option value="MAE">MAE</option>
                  </select>
                </div>
              </div>
            </div>

            <div className="actions between">
              <button type="button" className="ghost" onClick=${() => switchStep(2)}>Назад</button>
              <button type="button" disabled=${selectedModels.length === 0} onClick=${() => switchStep(4)}>Далее: Запуск</button>
            </div>
          </section>
        `}

        ${step === 4 && html`
          <section className="panel-card">
            <h2>Экран 4 — Запуск</h2>
            <div className="actions">
              <button type="button" disabled=${runInProgress} onClick=${runModels}>Запустить выбранные модели</button>
            </div>

            <div className="run-grid">
              ${selectedModels.map((model) => {
                const run = runs[model] || { status: "idle", progress: 0, metrics: null };
                return html`
                  <article key=${model} className="run-card">
                    <div className="run-head">
                      <strong>${model}</strong>
                      <span className=${`status ${run.status}`}>${run.status}</span>
                    </div>
                    <div className="progress-rail"><span style=${{ width: `${run.progress}%` }}></span></div>
                    ${run.metrics
                      ? html`
                          <div className="metrics-inline">
                            <span>MAPE: ${run.metrics.mape.toFixed(2)}</span>
                            <span>RMSE: ${run.metrics.rmse.toFixed(2)}</span>
                            <span>Score: ${run.metrics.score.toFixed(2)}</span>
                          </div>
                        `
                      : html`<p className="hint">Предварительные метрики появятся после завершения.</p>`}
                  </article>
                `;
              })}
            </div>

            <div className="log-box">
              <h3>Лог выполнения</h3>
              <div className="log-list">
                ${runLogs.length
                  ? runLogs.map((entry, idx) => html`
                      <div key=${`${entry.ts}-${idx}`} className=${`log-item ${entry.level}`}>
                        <span>[${entry.ts}]</span>
                        <strong>${entry.level.toUpperCase()}</strong>
                        <p>${entry.message}</p>
                      </div>
                    `)
                  : html`<p className="empty">Лог пока пуст.</p>`}
              </div>
            </div>

            <div className="actions between">
              <button type="button" className="ghost" onClick=${() => switchStep(3)}>Назад</button>
              <button type="button" disabled=${!canStep5} onClick=${() => switchStep(5)}>Открыть результаты</button>
            </div>
          </section>
        `}

        ${step === 5 && html`
          <section className="panel-card">
            <h2>Экран 5 — Результаты</h2>

            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Модель</th>
                    <th>MAPE</th>
                    <th>RMSE</th>
                    <th>MAE</th>
                    <th>R²</th>
                    <th>Макс. откл.</th>
                    <th>Итоговый скор</th>
                  </tr>
                </thead>
                <tbody>
                  ${resultRows.map((row) => html`
                    <tr key=${row.model}>
                      <td>${row.model}</td>
                      <td>${row.mape.toFixed(2)}</td>
                      <td>${row.rmse.toFixed(3)}</td>
                      <td>${row.mae.toFixed(3)}</td>
                      <td>${row.r2.toFixed(3)}</td>
                      <td>${row.maxDeviation.toFixed(3)}</td>
                      <td><strong>${row.score.toFixed(2)}</strong></td>
                    </tr>
                  `)}
                </tbody>
              </table>
            </div>

            <div className="chart-box">
              <h3>Прогноз vs факт (все модели)</h3>
              ${!chartModelLines
                ? html`<p className="empty">Сначала запустите модели на шаге 4.</p>`
                : html`
                    <svg viewBox="0 0 900 260" className="mini-chart" preserveAspectRatio="none">
                      <polyline points=${chartModelLines.actual} fill="none" stroke="#1f2f3a" strokeWidth="3.2" />
                      ${chartModelLines.models.map((item, idx) => {
                        const colors = ["#b85c38", "#2f6b59", "#8062d6", "#3a90b8"];
                        return html`<polyline key=${item.model} points=${item.line} fill="none" stroke=${colors[idx % colors.length]} strokeWidth="2.4" />`;
                      })}
                    </svg>
                    <div className="legend">
                      <span><i style=${{ background: "#1f2f3a" }}></i>Факт</span>
                      ${chartModelLines.models.map((item, idx) => {
                        const colors = ["#b85c38", "#2f6b59", "#8062d6", "#3a90b8"];
                        return html`<span key=${item.model}><i style=${{ background: colors[idx % colors.length] }}></i>${item.model}</span>`;
                      })}
                    </div>
                  `}
            </div>

            <div className="table-wrap tall">
              <h3>Отклонения по датам / точкам</h3>
              <table>
                <thead>
                  <tr>
                    <th>Дата/точка</th>
                    <th>Факт</th>
                    ${resultRows.map((row) => html`<th key=${`pred-${row.model}`}>${row.model}</th>`)}
                    ${resultRows.map((row) => html`<th key=${`q-${row.model}`}>Качество ${row.model}</th>`)}
                  </tr>
                </thead>
                <tbody>
                  ${deviationRows.map((row) => html`
                    <tr key=${row.idx}>
                      <td>${row.dateLabel}</td>
                      <td>${row.actual.toFixed(3)}</td>
                      ${resultRows.map((item) => html`<td key=${`${row.idx}-${item.model}`}>${Number(row[`${item.model}_pred`] || 0).toFixed(3)}</td>`)}
                      ${resultRows.map((item) => html`<td key=${`${row.idx}-${item.model}-q`} className=${`quality ${row[`${item.model}_quality`]}`}>${row[`${item.model}_quality`]}</td>`)}
                    </tr>
                  `)}
                </tbody>
              </table>
            </div>

            <div className="actions between">
              <button type="button" className="ghost" onClick=${() => switchStep(4)}>Назад</button>
            </div>
          </section>
        `}
      </section>
    </div>
  `;
}

createRoot(document.getElementById("root")).render(html`<${App} />`);
