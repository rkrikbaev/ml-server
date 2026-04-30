# WORKFLOW: Stage 8 — Monitoring, Analytics & UI Endpoints

**Stage 8** covers the operational monitoring layer that tracks all prediction tasks, exposes model analytics, and provides a web UI for system observability.

---

## Problem Statement

After Stage 7 (polling), the system must track:
- **Task lifecycle** — creation, processing, completion, expiration
- **Model performance** — success rates, runtimes, prediction quality (MAPE)
- **System health** — CPU load, memory usage, service availability

This information is exposed via REST API endpoints consumed by the UI and external monitoring systems.

---

## Core Components

### Task Monitor

[`src/api/task_monitor.py`](src/api/task_monitor.py) — In-memory task registry with thread-safe access.

**Data Structure per task:**

```python
{
    "task_id": "9f1c72b1-52d3-4c9a-8a6e-5e8f3b2c1a9d",
    "object_reference": "AKMOLA/KSTS/01",
    "model_id": "prophet_watt_AKMOLA",
    "model_type": "prophet",
    "state": "done",  # start | processing | done | expired
    "status_code": 200,  # HTTP status
    "received_at": "2026-04-30T12:34:56.123Z",
    "started_at": "2026-04-30T12:34:56.789Z",
    "completed_at": "2026-04-30T12:35:02.456Z",
    "expires_at": "2026-05-01T12:35:02.456Z",  # TTL = REDIS_TIMEOUT
    "runtime_s": 5.667,
    "display_state": "done 200",
    "worker": "worker-3",
    "quality": 95,
    "model_confidence": 0.87,
    "result_preview": [12.5, 13.2, 14.1],  # First 6 values
    "result": {...},  # Full HTTP response payload
    "error": null,  # If status_code != 200
    "poll_history": [
        {"timestamp": "...", "status": 202, "state": "start"},
        {"timestamp": "...", "status": 202, "state": "processing"},
        {"timestamp": "...", "status": 200, "state": "done"}
    ],
    "actions": {
        "retry": false,
        "revoke": false,
        "copy_task_id": true
    }
}
```

**Lifecycle Recording:**

| Event | Function | Triggered | Data Updated |
|-------|----------|-----------|---|
| Task created | `record_task_created()` | Stage 2 (enqueue) | state=START, status=202 |
| Task processing | `record_task_processing()` | Stage 7 (first poll) | state=PROCESSING, started_at |
| Task done | `record_task_done()` | Stage 7 (result ready) | state=DONE, completed_at, expires_at, quality, error |

**Memory Limits:**
```python
_MAX_TASKS = 500  # Keep last 500 tasks in memory (FIFO eviction)
```

---

## API Endpoints

### 1. List All Tasks

**Endpoint:** `GET /ui/tasks`

[`src/api/server.py:335–351`](src/api/server.py#L335):

```python
@app.get("/ui/tasks")
async def ui_tasks(
    state: str = Query("all"),
    search: str = Query(""),
    worker: str = Query("all"),
    model: str = Query("all"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> JSONResponse:
    return JSONResponse(
        content=list_tasks(
            search=search,
            state=state,
            worker=worker,
            model=model,
            page=page,
            page_size=page_size,
        ),
        status_code=200,
    )
```

**Request:**
```http
GET /ui/tasks?state=all&search=AKMOLA&worker=all&model=all&page=1&page_size=20
```

**Response (HTTP 200):**
```json
{
  "total": 42,
  "page": 1,
  "page_size": 20,
  "items": [
    {
      "task_id": "9f1c72b1-52d3-4c9a-8a6e-5e8f3b2c1a9d",
      "object_reference": "AKMOLA/KSTS/01",
      "model_id": "prophet_watt_AKMOLA",
      "model_type": "prophet",
      "display_state": "done 200",
      "runtime_s": 5.667,
      "received_at": "2026-04-30T12:34:56.123Z",
      "quality": 95,
      "actions": {"retry": false, "revoke": false}
    },
    ...
  ]
}
```

**Filtering Logic:**
- `state`: "all" | "start" | "processing" | "done" | "expired"
- `search`: Case-insensitive substring match on task_id, object_reference, model_id
- `worker`: Filter by assigned worker name
- `model`: Filter by model_id
- `page`, `page_size`: Pagination (max 100 items per page)

### 2. Task Detail

**Endpoint:** `GET /ui/tasks/{task_id}`

[`src/api/server.py:353–366`](src/api/server.py#L353):

```python
@app.get("/ui/tasks/{task_id}")
async def ui_task_detail(task_id: str) -> JSONResponse:
    task = get_task(task_id)
    if task is None:
        return JSONResponse(
            content={"status": 404, "message": f"Task not found: {task_id}"},
            status_code=404,
        )
    return JSONResponse(
        content={"status": 200, "task": task},
        status_code=200,
    )
```

**Response (HTTP 200):**
```json
{
  "status": 200,
  "task": {
    "task_id": "9f1c72b1-52d3-4c9a-8a6e-5e8f3b2c1a9d",
    "state": "done",
    "display_state": "done 200",
    "status_code": 200,
    "received_at": "2026-04-30T12:34:56.123Z",
    "started_at": "2026-04-30T12:34:56.789Z",
    "completed_at": "2026-04-30T12:35:02.456Z",
    "runtime_s": 5.667,
    "object_reference": "AKMOLA/KSTS/01",
    "model_id": "prophet_watt_AKMOLA",
    "quality": 95,
    "model_confidence": 0.87,
    "result_preview": [12.5, 13.2, 14.1],
    "result": {
      "status": 200,
      "state": "done",
      "task_id": "9f1c72b1...",
      "data": {
        "message": "Forecast completed successfully",
        "output": [...],
        "quality": 95,
        ...
      }
    },
    "poll_history": [...]
  }
}
```

### 3. Models List

**Endpoint:** `GET /ui/models`

[`src/api/server.py:106–214`](src/api/server.py#L106):

```python
@app.get("/ui/models")
async def ui_models() -> JSONResponse:
    models_base_path = Path(getenv("MODELS_PATH", "/workspace/models"))
    analytics = get_models_analytics()
    
    model_items = []
    for model_dir in sorted(models_base_path.iterdir()):
        if not model_dir.is_dir():
            continue
        config_path = model_dir / "config.json"
        if not config_path.is_file():
            continue
        
        model_id = model_dir.name
        # ... read config and analytics, build item
        model_items.append({...})
    
    return JSONResponse(
        content={
            "status": 200,
            "models": model_items,
            "total": len(model_items),
            "updated_at": analytics.get("updated_at"),
        },
        status_code=200,
    )
```

**Response (HTTP 200):**
```json
{
  "status": 200,
  "total": 3,
  "updated_at": "2026-04-30T12:00:00Z",
  "models": [
    {
      "model_id": "prophet_watt_AKMOLA",
      "model_type": "prophet",
      "horizon": "short",
      "horizon_category": "short",
      "region": "AKMOLA",
      "health": "ok",
      "run_count": 42,
      "success_rate": 0.95,
      "avg_runtime_s": 5.2,
      "mape": 12.5,
      "last_run_at": "2026-04-30T12:35:02Z",
      "last_run_state": "done 200",
      "sources": {
        "scada": {"enabled": true},
        "weather": {"enabled": true},
        "cmms": {"enabled": false}
      }
    },
    ...
  ]
}
```

**Per-Model Fields:**
- `run_count` — Total executions
- `success_rate` — Fraction of HTTP 200 responses
- `avg_runtime_s` — Mean execution time
- `mape` — Mean absolute percentage error (from MLflow)
- `health` — "ok" | "warning" | "error"
- `sources` — Enabled data sources (SCADA, weather, CMMS)

### 4. Model Detail

**Endpoint:** `GET /ui/models/detail?model_id=<model_id>`

[`src/api/server.py:217–310`](src/api/server.py#L217):

**Response (HTTP 200):**
```json
{
  "status": 200,
  "model_id": "prophet_watt_AKMOLA",
  "model_type": "prophet",
  "health": "ok",
  "region": "AKMOLA",
  "horizon": "short",
  "mape": 12.5,
  "run_count": 42,
  "avg_runtime_s": 5.2,
  "success_rate": 0.95,
  "last_run_at": "2026-04-30T12:35:02Z",
  "last_run_state": "done 200",
  "updated_at": 1714502400000,
  "seasonality_mode": "additive",
  "yearly_seasonality": true,
  "weekly_seasonality": true,
  "daily_seasonality": true,
  "sources": {...},
  "scada_sources": [...],
  "raw_config": {...},
  "last_run": {
    "task_id": "9f1c72b1...",
    "state": "done 200",
    "worker": "worker-3",
    "received_at": "2026-04-30T12:34:56Z",
    "object_reference": "AKMOLA/KSTS/01"
  }
}
```

### 5. Model Run History

**Endpoint:** `GET /ui/models/{model_id}/runs?limit=50`

[`src/api/server.py:312–316`](src/api/server.py#L312):

```python
@app.get("/ui/models/{model_id}/runs")
async def ui_model_runs(model_id: str, limit: int = Query(50, ge=1, le=200)) -> JSONResponse:
    result = get_model_runs(model_id, limit=limit)
    return JSONResponse(content=result, status_code=200)
```

**Response (HTTP 200):**
```json
{
  "status": 200,
  "model_id": "prophet_watt_AKMOLA",
  "total": 42,
  "runs": [
    {
      "task_id": "9f1c72b1...",
      "display_state": "done 200",
      "runtime_s": 5.667,
      "received_at": "2026-04-30T12:35:02Z",
      "quality": 95,
      "object_reference": "AKMOLA/KSTS/01"
    },
    ...
  ]
}
```

### 6. Runtime Status

**Endpoint:** `GET /ui/runtime-status`

[`src/api/server.py:318–333`](src/api/server.py#L318):

```python
@app.get("/ui/runtime-status")
async def ui_runtime_status() -> JSONResponse:
    load_avg = os.getloadavg() if hasattr(os, "getloadavg") else (0.0, 0.0, 0.0)
    rss_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    
    return JSONResponse(
        content={
            "status": 200,
            "cpu_load": {
                "load_1m": round(load_avg[0], 3),
                "load_5m": round(load_avg[1], 3),
                "load_15m": round(load_avg[2], 3),
            },
            "memory": {
                "rss_kb": int(rss_kb),
                "rss_mb": round(rss_kb / 1024, 2),
            },
        },
        status_code=200,
    )
```

**Response (HTTP 200):**
```json
{
  "status": 200,
  "cpu_load": {
    "load_1m": 2.345,
    "load_5m": 1.678,
    "load_15m": 0.912
  },
  "memory": {
    "rss_kb": 524288,
    "rss_mb": 512.0
  }
}
```

### 7. Model Config Display

**Endpoint:** `GET /ui/model-config?model_id=<model_id>`

[`src/api/server.py:70–104`](src/api/server.py#L70):

**Response (HTTP 200):**
```json
{
  "status": 200,
  "model_id": "prophet_watt_AKMOLA",
  "config_path": "/workspace/models/prophet_watt_AKMOLA/config.json",
  "raw_config": {
    "model_type": "prophet",
    "step": 3600,
    "input_range": 168,
    "output_range": 24,
    "sources": {...}
  },
  "normalized_config": {
    "model_type": "prophet",
    "step": 3600,
    "input_range": 168,
    "output_range": 24,
    "historical_data_url": "...",
    "weather_lat": 50.123,
    ...
  }
}
```

---

## Analytics Aggregation

### get_models_analytics()

Computes per-model statistics across all completed tasks:

```python
{
    "updated_at": "2026-04-30T12:00:00Z",
    "models": [
        {
            "model_id": "prophet_watt_AKMOLA",
            "total_runs": 42,
            "success_count": 40,
            "success_rate": 0.952,
            "error_count": 2,
            "avg_runtime_s": 5.234,
            "avg_mape": 12.456,
            "health_status": "ok",
            "last_run_at": "2026-04-30T12:35:02Z",
            "last_run_state": "done 200"
        },
        ...
    ]
}
```

**Calculation:**
- `success_rate = success_count / total_runs`
- `avg_runtime_s = mean(completed_at - started_at)` for all done tasks
- `avg_mape` — pulled from last MLflow run or config
- `health_status` — "ok" if success_rate > threshold, else "warning" or "error"

### get_model_runs(model_id, limit)

Returns last N tasks for a specific model, with full details.

---

## Data Flow

```
Stage 1–7 (Task execution)
      ↓
record_task_created/processing/done() [Stage 2, 7, 7]
      ↓
_TASKS dict (in-memory, thread-safe with RLock)
      ↓ (query)
list_tasks(), get_task(), get_models_analytics()
      ↓ (REST API)
/ui/tasks, /ui/models, /ui/runtime-status endpoints
      ↓
Web UI (frontend consumes via AJAX)
```

---

## Memory & Persistence

### In-Memory Storage

- **Location:** `_TASKS: OrderedDict[str, dict]` in `task_monitor.py`
- **Limit:** 500 tasks (FIFO eviction)
- **Lifetime:** Process memory; lost on restart
- **Pros:** Fast access, no external dependency
- **Cons:** Limited capacity, not shared across instances

### Result Persistence

- **Primary:** Redis (for polling, TTL = REDIS_TIMEOUT = 1 hour)
- **Secondary:** Task monitor (_TASKS) for analytics (last 500 tasks)
- **Access pattern:** 
  - Stage 7 polling uses Redis (temporary results)
  - Analytics uses _TASKS (historical view)

---

## UI Endpoints Summary

| Endpoint | Method | Purpose | Returns |
|----------|--------|---------|---------|
| `/ui/tasks` | GET | List all tasks with filters | 200 + paginated tasks |
| `/ui/tasks/{task_id}` | GET | Task detail | 200 + full task or 404 |
| `/ui/models` | GET | Models list with metrics | 200 + models |
| `/ui/models/detail` | GET | Single model detail | 200 + model or 404 |
| `/ui/models/{model_id}/runs` | GET | Model run history | 200 + run list |
| `/ui/runtime-status` | GET | System CPU/memory | 200 + metrics |
| `/ui/model-config` | GET | Raw + normalized config | 200 + config or 404 |
| `/ui` | GET | Web UI HTML | 200 + index.html |
| `/ui/styles.css` | GET | UI styles | 200 + CSS |
| `/ui/app.js` | GET | UI JavaScript | 200 + JS |

---

## Error Scenarios

| Scenario | Endpoint | Response |
|----------|----------|----------|
| Task not found | `/ui/tasks/{invalid_id}` | HTTP 404 |
| Model not found | `/ui/models/detail?model_id=invalid` | HTTP 200 (empty) |
| Invalid page size | `/ui/tasks?page_size=1000` | HTTP 200 (capped at 100) |
| No models | `/ui/models` | HTTP 200 with empty array |

---

## Stage 8 Contract

- ✅ All prediction tasks recorded with lifecycle events (created/processing/done)
- ✅ Task monitor maintains last 500 tasks in FIFO order
- ✅ Analytics computed across all models (success rates, runtimes, quality)
- ✅ REST API exposes task list, detail, model metrics, and system status
- ✅ Filtering and pagination support on task list
- ✅ Results linked to tasks via task_id
- ✅ Web UI endpoints serve HTML/CSS/JS

---

## Next Steps

**→ Stage 9**: Error handling and HTTP response contracts across all stages.
