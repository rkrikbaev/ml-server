# WORKFLOW: Complete Integration Index

This document provides a master overview of the entire ml-server prediction pipeline, linking all 11 stages with data contracts, error paths, and key cross-references.

---

## Pipeline Architecture

```
STAGE 0: Init
  ├─ Lifespan startup/shutdown
  ├─ Broker configuration (Redis or in-memory)
  ├─ Result backend initialization
  └─ Infrastructure ready

STAGE 1: Request Parsing
  ├─ FastAPI validates JSON
  ├─ Discriminator routes to CREATE or UPDATE branch
  └─ Schema validation (PredictCreateSchema or PredictUpdateSchema)

STAGE 2: Task Enqueue
  ├─ api_predict.kiq(data) → TaskIQ broker
  ├─ Task recorded in monitor (state=START)
  └─ HTTP 202 + task_id returned

STAGES 3-6: Worker Execution (Background)
  ├─ Stage 3: Load config, init worker
  ├─ Stage 4: Collect historical/weather/CMMS data
  ├─ Stage 5: Initialize model, run inference
  └─ Stage 6: Post-process, build result
  
STAGE 7: Polling & Result Retrieval
  ├─ Poll 1: HTTP 202 PROCESSING (if not ready)
  ├─ Poll N: HTTP 200/4xx/5xx DONE (when ready)
  └─ Results retrieved from Redis backend

STAGE 8: Monitoring & Analytics
  ├─ Task history (/ui/tasks)
  ├─ Model metrics (/ui/models)
  └─ System health (/ui/runtime-status)

STAGE 9: Error Handling
  ├─ Validation errors → 422
  ├─ Data quality errors → 422
  ├─ Service unavailable → 503
  └─ Unexpected errors → 500

STAGE 10: Configuration & Deployment
  ├─ Environment variables
  ├─ Docker Compose orchestration
  └─ Multi-instance setup

STAGE 11: Testing & Verification
  ├─ Unit tests (individual components)
  ├─ Integration tests (stage handoffs)
  ├─ Smoke tests (end-to-end happy path)
  └─ Negative tests (error scenarios)
```

---

## Data Flow & Contracts

### Request → Response Path

```
Client HTTP Request
  ↓
Stage 1: FastAPI Validation
  ├─ Input: HTTP POST body (JSON)
  ├─ Validation: PredictSchema discriminator
  └─ Output: PredictCreateSchema or PredictUpdateSchema
  
Stage 2: Task Enqueue
  ├─ Input: PredictCreateSchema {model_id, object_reference, model_selection}
  ├─ Action: api_predict.kiq() → TaskIQ broker
  └─ Output: HTTP 202 {task_id, state="start"}
  
Stage 3: Worker Task Init
  ├─ Input: {model_id, online, selector}
  ├─ Action: load_model_config() → MLflow registry
  └─ Output: ModelConfig (normalized runtime parameters)
  
Stage 4: Data Collection
  ├─ Input: ModelConfig {step, input_range, output_range, sources}
  ├─ Actions: 
  │   ├─ Historical.fetch_model_data() → SCADA archives
  │   ├─ Weather.fetch() → optional weather API
  │   └─ CMMS.fetch_planned_series() → optional maintenance
  └─ Output: {historical_data, weather_data, cmms_payload, health_flag}
  
Stage 5: Inference
  ├─ Input: Historical data + weather (optional)
  ├─ Actions:
  │   ├─ init_model() → select adapter (Prophet/XGBoost/Naive/AR)
  │   ├─ predict() → generate forecasts
  │   └─ get_pred_timestamps() → build timestamp array
  └─ Output: {output: [...], pred_ts: [...], model_confidence}
  
Stage 6: Post-Processing
  ├─ Input: Predictions + CMMS payload + quality assessment
  ├─ Actions:
  │   ├─ _apply_planned_adjustments() → adjust by timestamp
  │   ├─ count_input_health() → quality score
  │   └─ _build_result() → final response structure
  └─ Output: HTTP response {status, data, message, quality}
  
Stage 7: Polling
  ├─ Input: task_id
  ├─ Action: result_backend.is_result_ready(task_id)
  └─ Output: HTTP 202 (processing) or 200/4xx/5xx (done)
  
Client HTTP Response
```

### Data Structures

#### PredictCreateSchema (Stage 1–2)

```python
{
    "model_id": "prophet_watt_AKMOLA",
    "object_reference": "AKMOLA/KSTS/01",
    "model_selection": {
        "version": "v1.0",  # optional
        "version_alias": "Production"  # optional
    }
}
```

#### ModelConfig (Stage 3 onward)

```python
{
    "model_type": "prophet",
    "step": 3600,
    "input_range": 168,
    "output_range": 24,
    "fallback": "ar",
    "historical_data_archives": [
        {"pattern": "...", "url": "...", "request_overrides": {...}}
    ],
    "weather_enabled": True,
    "weather_lat": 50.123,
    "weather_lon": 50.456,
    "weather_units": "metric",
    "weather_hours": 12,
    "cmms_enabled": False,
    "cmms_url": None
}
```

#### Historical Data Payload (Stage 4)

```python
{
    "object": "AKMOLA/KSTS/01",
    "from": "2026-04-29T12:00:00Z",
    "to": "2026-04-30T12:00:00Z",
    "step": 3600,
    "timestamps": [1714425600000, 1714429200000, ...],
    "values": [120.5, 118.3, 115.9, ...]
}
```

#### Final Result Payload (Stage 6 → Stage 7)

```json
{
  "status": 200,
  "message": "Forecast completed successfully",
  "data": {
    "output": [125.2, 128.5, 131.3, ...],
    "quality": 95,
    "model_confidence": 0.87,
    "planned_adjustments_applied": 2,
    "input_statistics": {
      "min": 100.0,
      "max": 150.0,
      "mean": 125.0,
      "health_flag": 95
    },
    "output_statistics": {
      "min": 125.2,
      "max": 131.3,
      "mean": 128.3
    },
    "object_reference": "AKMOLA/KSTS/01"
  }
}
```

---

## Error Paths & Recovery

### Stage 1 Error (Validation Failure)

```
Invalid JSON / Missing fields / Invalid schema
  ↓
FastAPI RequestValidationError
  ↓
exception_handler → ValidationException
  ↓
HTTP 422 Unprocessable Entity
{
  "status": 422,
  "message": "A valid JSON format was expected...",
  "details": {"body": ["'model_id' : field required"]}
}
```

**Recovery:** Client fixes request and retries

### Stage 3 Error (Config Not Found)

```
load_model_config(model_id="invalid")
  ↓
config_path not found
  ↓
Worker task returns HTTP 422
  ↓
Result stored in Redis → Client polls
  ↓
HTTP 422 "Model launch aborted: config.json not found..."
```

**Recovery:** Verify model_id exists in /workspace/models/{model_id}/config.json

### Stage 4 Error (No Historical Data)

```
_get_historical_data_payload()
  ↓
HISTORICAL_DATA API returns 0 records or error
  ↓
Worker catches exception
  ↓
HTTP 422 "Model launch aborted: no input data received..."
```

**Recovery:** 
- Verify object_reference exists in SCADA archives
- Check SCADA_STUB_ENABLED flag (set to true for testing)
- Verify time window (from_ts / to_ts) has data

### Stage 4 Error (Weather/CMMS Unavailable)

```
_get_weather_payload() or _get_planned_adjustments()
  ↓
External API timeout or HTTP error
  ↓
Worker catches, logs warning, CONTINUES
  ↓
HTTP 200 (success, but weather/CMMS skipped)
```

**Recovery:** None required; workflow degrades gracefully

### Stage 5 Error (Model Execution Failure)

```
predict() → adapter raises NaN / numerical error
  ↓
Worker catches exception
  ↓
HTTP 422 "Forecast execution error: ..."
```

**Recovery:** 
- Check input_statistics.health_flag (data quality)
- Verify model files exist in model registry
- Review model adapter logs

### Stage 7 Error (Result Not Ready after TTL)

```
Poll after 1+ hour (REDIS_TIMEOUT expired)
  ↓
Result evicted from Redis
  ↓
broker.result_backend.get_result(task_id) returns None
  ↓
HTTP 404 or stale task state
```

**Recovery:** Regenerate prediction (submit new task)

---

## Key Functions & Code References

### Stage 0: Startup/Shutdown

| Function | File | Purpose |
|----------|------|---------|
| `lifespan(app)` | `server.py:24` | FastAPI lifecycle hooks |
| `broker.startup()` | `broker.py:13` | Connect to Redis/init TaskIQ |
| `broker.shutdown()` | `broker.py:13` | Graceful worker shutdown |

### Stage 1: Validation

| Function | File | Purpose |
|----------|------|---------|
| `PredictSchema` | `data/predict.py:96` | Discriminated union schema |
| `predict_discriminator()` | `data/predict.py:97` | Route to CREATE or UPDATE |
| `process_data()` | `server.py:412` | Main endpoint handler |

### Stage 2: Enqueue

| Function | File | Purpose |
|----------|------|---------|
| `api_predict.kiq()` | `broker.py:32` | Enqueue task via TaskIQ |
| `record_task_created()` | `task_monitor.py:143` | Record in task monitor |
| `accepted_start()` | `message.py:89` | Build HTTP 202 response |

### Stage 3: Worker Init

| Function | File | Purpose |
|----------|------|---------|
| `predict_logic()` | `tasks/predict.py` | Main worker entrypoint |
| `load_model_config()` | `forecast/config.py:30` | Load & normalize config |
| `sync_with_registry()` | `forecast/provider.py` | Sync MLflow bundle |

### Stage 4: Data Collection

| Function | File | Purpose |
|----------|------|---------|
| `_get_historical_data_payload()` | `tasks/predict.py` | Fetch SCADA data |
| `_get_weather_payload()` | `tasks/predict.py` | Fetch weather (optional) |
| `_get_planned_adjustments()` | `tasks/predict.py` | Fetch CMMS (optional) |
| `HistoricalDataClient.fetch_model_data()` | `collector/historical_client.py` | API call |
| `count_input_health()` | `forecast/evaluation.py` | Calculate quality score |

### Stage 5: Inference

| Function | File | Purpose |
|----------|------|---------|
| `init_model()` | `forecast/model.py` | Create model adapter |
| `predict()` | `forecast/inference.py` | Run inference |
| `get_pred_timestamps()` | `forecast/inference.py` | Build timestamp array |

### Stage 6: Post-Processing

| Function | File | Purpose |
|----------|------|---------|
| `_apply_planned_adjustments()` | `tasks/predict.py` | Apply CMMS corrections |
| `_build_result()` | `tasks/predict.py` | Build final payload |
| `ok_done()` | `message.py:84` | HTTP 200 success response |

### Stage 7: Polling

| Function | File | Purpose |
|----------|------|---------|
| `broker.result_backend.is_result_ready()` | `broker.py:13` | Check if result ready |
| `broker.result_backend.get_result()` | `broker.py:13` | Retrieve result |
| `to_json_response()` | `message.py:56` | Add state + task_id |

### Stage 8: Monitoring

| Function | File | Purpose |
|----------|------|---------|
| `list_tasks()` | `task_monitor.py:226` | Query task list |
| `get_task()` | `task_monitor.py:?` | Get task detail |
| `get_models_analytics()` | `task_monitor.py:?` | Calculate model metrics |
| `ui_tasks()` | `server.py:335` | Endpoint `/ui/tasks` |
| `ui_models()` | `server.py:106` | Endpoint `/ui/models` |

### Stage 9: Error Handling

| Function | File | Purpose |
|----------|------|---------|
| `HTTPMessages` class | `message.py:25` | Response templates |
| `not_found()` | `message.py:94` | HTTP 404 |
| `unprocessable_entity_*()` | `message.py:101–120` | HTTP 422 variants |
| `service_unavailable_*()` | `message.py:127–145` | HTTP 503 variants |
| `internal_server_error()` | `message.py:124` | HTTP 500 |

### Stage 10: Configuration

| Variable | File | Default | Purpose |
|----------|------|---------|---------|
| `REDIS_URL` | `config.py:5` | `redis://redis:6379/0` | Broker connection |
| `REDIS_TIMEOUT` | `config.py:6` | `3600` | Result TTL |
| `TEST_MODE` | `broker.py:8` | `false` | Use in-memory broker |
| `MODEL_REGISTRY_CACHE_DIR` | `docker-compose.yml` | `/tmp/local_models_cache` | MLflow cache |

### Stage 11: Testing

| Command | File | Purpose |
|---------|------|---------|
| `make test` | `Makefile` | Run unit tests |
| `make smoke-positive` | `Makefile` | End-to-end happy path |
| `make smoke-negative` | `Makefile` | Error scenarios |
| `make test-predict` | `Makefile` | 2-phase /predict flow |

---

## Deployment Checklist

### Pre-Deployment

- [ ] All unit tests pass (`make test`)
- [ ] Positive smoke test passes (`make smoke-positive`)
- [ ] Negative smoke test passes (`make smoke-negative`)
- [ ] Docker Compose file reviewed (volumes, ports, env vars)
- [ ] Model configs validated (all required fields present)
- [ ] Redis connection verified
- [ ] MLflow registry accessible
- [ ] External APIs reachable (SCADA, weather, CMMS)

### During Deployment

- [ ] docker-compose up -d
- [ ] make wait-api (or equivalent readiness check)
- [ ] Verify lifespan startup completed (logs)
- [ ] Verify worker processes started (8 workers expected)
- [ ] Check Redis queue empty (no stuck tasks)

### Post-Deployment

- [ ] call GET /ui/runtime-status (health check)
- [ ] call POST /predict (create task)
- [ ] call POST /predict {task_id} (poll task)
- [ ] Verify result quality in GET /ui/tasks/{task_id}
- [ ] Monitor task monitor analytics (success_rate, runtimes)
- [ ] Set up log aggregation (ELK, CloudWatch, etc.)

---

## Performance Expectations

| Operation | Time |
|-----------|------|
| Request parsing (Stage 1) | <10ms |
| Task enqueue (Stage 2) | <50ms |
| Model config load (Stage 3) | <200ms |
| Historical data fetch (Stage 4) | 2–10s |
| Weather fetch (Stage 4, optional) | <5s |
| Inference (Stage 5) | 1–5s |
| Result building (Stage 6) | <100ms |
| Total execution (Stages 3–6) | 5–25s |
| First poll (Stage 7) | <50ms |
| Repeated poll overhead | <5ms |

---

## Useful Commands & Queries

### Redis Management

```bash
# Check queue depth
redis-cli XLEN predict

# View pending tasks
redis-cli XREAD STREAMS predict 0

# Clear queue (⚠️ caution)
redis-cli DEL predict

# Monitor result backend
redis-cli MONITOR  # Real-time Redis actions
```

### MLflow Registry

```bash
# List registered models
curl http://localhost:5050/api/2.0/mlflow/registered-models/list

# List model versions
curl "http://localhost:5050/api/2.0/mlflow/model-registry/get-latest-versions?name=prophet_watt_AKMOLA"
```

### Task Monitor

```bash
# List running tasks
curl http://localhost:8030/ui/tasks?state=processing&page_size=100

# Get specific task
curl http://localhost:8030/ui/tasks/{task_id}

# Export task data to CSV (for analysis)
curl http://localhost:8030/ui/tasks?page_size=500 | jq '.items[] | [.task_id,.model_id,.runtime_s,.quality] | @csv'
```

### Docker Compose

```bash
# View all container logs
docker-compose logs -f

# Watch Redis commands
docker-compose exec redis redis-cli MONITOR

# Inspect model server environment
docker-compose exec model-server env | grep MLFLOW

# Interactive shell in container
docker-compose exec model-server /bin/bash
```

---

## Common Issues & Solutions

| Issue | Diagnosis | Solution |
|-------|-----------|----------|
| API returns 503 MLflow | logs show "Failed to connect to MLflow" | Check MLflow container is running, MLFLOW_TRACKING_URI correct |
| Task stuck in "processing" | task older than REDIS_TIMEOUT | Results expired; poll returns 404 or task state inconsistent |
| High memory usage | Docker memory limit hit | Increase deploy.resources.limits.memory |
| Tasks queuing up | worker pool too small | Increase `--workers` in docker-compose.yml command |
| Weather always missing | logs show "weather=None" | Check WEATHER_URL env var, may be intentional on test |
| input_health very low | quality < 50% | Check historical data availability, verify time window |

---

## Document Navigation

| Stage | File | Focus |
|-------|------|-------|
| 0 | [WORKFLOW_STAGE0.md](WORKFLOW_STAGE0.md) | **Initialization** — FastAPI startup, broker setup, infrastructure |
| 1 | [WORKFLOW_STAGE1.md](WORKFLOW_STAGE1.md) | **Request parsing** — JSON validation, schema discrimination |
| 2 | [WORKFLOW_STAGE2.md](WORKFLOW_STAGE2.md) | **Task enqueue** — TaskIQ broker, task monitor |
| 3 | [WORKFLOW_STAGE3.md](WORKFLOW_STAGE3.md) | **Worker Init** — Config load, model registry sync |
| 4 | [WORKFLOW_STAGE4.md](WORKFLOW_STAGE4.md) + [STAGE4_DATA_COLLECTION](WORKFLOW_STAGE4_DATA_COLLECTION.md) | **Data collection** — Historical, weather, CMMS |
| 5 | [WORKFLOW_STAGE5.md](WORKFLOW_STAGE5.md) | **Inference** — Model init, prediction, timestamps |
| 6 | [WORKFLOW_STAGE6.md](WORKFLOW_STAGE6.md) | **Post-processing** — Result building, input_health, adjustments |
| 7 | [WORKFLOW_STAGE7.md](WORKFLOW_STAGE7.md) | **Polling** — Result retrieval, state transitions |
| 8 | [WORKFLOW_STAGE8.md](WORKFLOW_STAGE8.md) | **Monitoring** — Task tracking, model metrics, UI endpoints |
| 9 | [WORKFLOW_STAGE9.md](WORKFLOW_STAGE9.md) | **Error handling** — HTTP contracts, status codes, recovery |
| 10 | [WORKFLOW_STAGE10.md](WORKFLOW_STAGE10.md) | **Configuration** — Docker, environment, deployment |
| 11 | [WORKFLOW_STAGE11.md](WORKFLOW_STAGE11.md) | **Testing** — Unit, integration, smoke, verification checklist |

---

## Quick Reference: Task States

```
state="start"           ← Enqueued, not yet executing (HTTP 202)
state="processing"      ← Worker executing Stages 3–6 (HTTP 202)
state="done"            ← Stages 3–6 complete, result available (HTTP 200/4xx/5xx)
state="expired"         ← Result TTL exceeded (REDIS_TIMEOUT), no longer in Redis
display_state="done 200"  ← Human-readable: status code appended
```

---

## Final Verification

All 11 stages documented and **synchronized with code**:

- ✅ Stage 0: Startup/shutdown lifecycle
- ✅ Stage 1: Request validation
- ✅ Stage 2: Task enqueuing
- ✅ Stage 3: Worker initialization
- ✅ Stage 4: Data collection
- ✅ Stage 5: Model inference
- ✅ Stage 6: Post-processing
- ✅ Stage 7: Polling and result retrieval
- ✅ Stage 8: Monitoring and analytics
- ✅ Stage 9: Error handling and HTTP contracts
- ✅ Stage 10: Configuration and deployment
- ✅ Stage 11: Testing and verification

**This integration index serves as the master reference for understanding, maintaining, and extending the ml-server prediction pipeline.**
