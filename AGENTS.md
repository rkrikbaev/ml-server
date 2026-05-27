# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Project Overview

`ml-server` is an async forecast inference service built on **FastAPI + TaskIQ + Redis**. It accepts `GET /predict/{model_id}` requests, dispatches work to background TaskIQ workers, and resolves model artifacts from an **MLflow Registry** into a local bundle cache.

## Key Commands

All commands run from the `ml-server/` directory.

### Development (without Docker)

```bash
pip install -r requirements.txt
export PYTHONPATH=./src
# API server
python -m uvicorn api.server:app --reload --host 0.0.0.0 --port 8000
# Worker (separate terminal)
taskiq worker api.broker:broker
```

### Docker

```bash
docker-compose up --build           # start all services
make ml-model-status                 # container status + recent logs
make smoke-api                       # /ui/runtime-status health check
```

### Testing

```bash
make test                            # pytest tests/ (excludes smoke tests)
pytest tests/test_foo.py -v          # single test file
make smoke-positive                  # positive predict smoke (SCADA stub enabled)
make smoke-negative                  # negative predict smoke (SCADA stub disabled)
make test-predict PREDICT_MODEL_ID=model3   # end-to-end async /predict flow
```

### Linting

```bash
flake8 src/                          # E501 and E701 are ignored (.flake8)
```

### MLflow / Notebooks

```bash
make mlflow-ui                       # starts MLflow UI against mlflow.db
make notebook-up                     # start Jupyter at http://localhost:8888 (token: ml-notebook)
make notebook-down
```

## Architecture

### Request lifecycle

```
Client → GET /predict/{model_id}
  → FastAPI (src/api/server.py)
  → TaskIQ task dispatched → Redis stream
  → Worker: broker/tasks/predict.py::logic()
      1. ModelProvider.sync_with_registry() — download/validate MLflow bundle to cache
      2. load_model_config() — parse bundle/configuration/cache_config.json → ModelConfig
      3. Fetch historical data (SCADA/NDC)
      4. Optionally fetch weather data
      5. init_model() → adapter instance (AR/Prophet/XGBoost/Naive)
      6. predict() → (y_pred, pred_ts, is_matching)
      7. Return result dict
Client → GET /tasks/{task_id}  [polls until result ready]
```

### Module layout

| Path | Role |
|------|------|
| `src/api/server.py` | FastAPI app, all HTTP routes |
| `src/api/broker/broker.py` | TaskIQ broker wiring (Redis vs InMemory) |
| `src/api/broker/tasks/predict.py` | Core inference logic (`logic()`) |
| `src/api/config.py` | Env-var-driven runtime config (Redis URL, SCADA URLs, timeouts) |
| `src/api/data/predict.py` | Pydantic request schemas (`PredictCreateSchema`) |
| `src/api/message.py` | Canonical HTTP response builders (`HTTPMessages`) |
| `src/api/task_monitor.py` | In-process task state tracking |
| `src/adapters/config.py` | `ModelConfig` (Pydantic) + `load_model_config()` |
| `src/adapters/provider.py` | `ModelProvider` — MLflow bundle download & local cache |
| `src/adapters/model.py` | `init_model()` — adapter instantiation + single-entry cache |
| `src/adapters/inference.py` | `predict()` — delegates to adapter's `BaseModel.predict()` |
| `src/adapters/adapters.py` | `ARAdapter`, `ProphetAdapter`, `XGBoostAdapter`, `NaiveAdapter` |
| `src/adapters/base_interface.py` | `BaseModel`, `PredictionInput`, `PredictionOutput` contracts |

### Model resolution (MLflow → local cache)

`ModelProvider` (singleton via `get_model_provider()`) resolves by MLflow alias (default: `Production`) or explicit version, downloads the artifact bundle to:

```
$MODEL_REGISTRY_CACHE_DIR/<encoded_model_id>/<selector>/<version>/bundle/
  model/                          ← serialized model artifacts
  configuration/cache_config.json ← canonical runtime config
```

On MLflow unavailability, the most recently cached bundle for that `model_id`+`selector` is used as fallback. `bundle_path=None` in `SyncResult` means no bundle is available — the worker returns 503.

### ModelConfig and `cache_config.json`

`load_model_config()` reads `bundle/configuration/cache_config.json` and validates it into `ModelConfig`. Critical fields:

- `step` (seconds) — time resolution
- `input_range` / `output_range` — history lookback / forecast horizon (in steps)
- `model_type` — one of `prophet`, `xgb`, `ar`, `naive`
- `fallback` — fallback adapter on load failure
- `sources` — dict of data sources; `_get_source()` resolves by name or `type` field

Config supports a multi-format normalization layer (`_normalize_sources_config`) that converts legacy flat keys like `historical_data_url`, `weather_lat`, etc. into the canonical `sources` dict.

### Adapter pattern

All models implement `BaseModel` (`src/adapters/base_interface.py`):

```python
class MyAdapter(BaseModel):
    def load(self) -> None: ...
    def predict(self, input_data: PredictionInput) -> PredictionOutput: ...
```

`init_model()` in `src/adapters/model.py` maintains a single-entry in-process LRU cache keyed by `(normalized_model_path, model_type)`. It instantiates the right adapter and calls `load()`. On failure it falls back to the configured fallback adapter (or `None`).

### Broker modes

| Env | Broker |
|-----|--------|
| `USE_IN_MEMORY_BROKER=false` (default) | `RedisStreamBroker` + `RedisAsyncResultBackend` |
| `TEST_MODE=true` | `InMemoryBroker` + `DummyResultBackend` |

### Key environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `REDIS_URL` | `redis://redis:6379/0` | Redis connection |
| `HISTORICAL_DATA_URLS` / `SCADA_URL` | `http://127.0.0.1:7080/api/v1/read/archives` | SCADA data source(s) |
| `MLFLOW_TRACKING_URI` | — | MLflow server |
| `MODEL_REGISTRY_CACHE_DIR` | `/tmp/local_models_cache` | Bundle cache root |
| `MODELS_PATH` | `/workspace/models` | Legacy local model lookup |
| `HISTORICAL_DATA_STUB_ENABLED` / `SCADA_STUB_ENABLED` | `false` | Both names are aliases; when `true`, returns synthetic SCADA data (used in smoke tests) |

## Working Rules

### Mandatory reading before any logic change

**Always read `docs/Main instruction.md` before updating any inference logic, API contracts, model loading, or data collection behavior.** It is the authoritative technical specification (ТЗ) for the entire system.

Additional reference docs to check for relevant changes:
- `docs/UNIFIED.md` — unified architecture decisions
- `docs/API/MAIN.md` — API contract details
- `docs/COMMON_MODEL_INTERFACE.md` — adapter interface spec
- `docs/MODEL_STORAGE_STRUCTURE.md` — bundle layout and MLflow storage

If code changes alter documented behavior, update the relevant docs in the same change. If docs and code diverge, align code with the approved spec first, then reconcile docs.

### System purpose and constraints

- The system forecasts **energy load time series** (MW, kWh) for power grid objects (regions, substations) served by an external SCADA pull-system.
- Training is a **manual engineer workflow** in Jupyter notebooks — the server is inference-only.
- Adding a new forecasting object requires **no code changes** — only new entries in `models.csv` / `inputs.csv` and a notebook run.
- Each MLflow Experiment corresponds to one forecasting object. Model identification: `model_id` = registered MLflow model name; `version_alias` = MLflow alias (e.g. `Production`).
- `model_id` is **opaque** — never parse, normalize, or rewrite it.

### Data passport (`cache_config.json`)

The `cache_config.json` bundled with each model is the model's self-describing "data passport" — it tells the inference pipeline exactly which external REST APIs to call and what to request. The canonical location inside a downloaded bundle is `bundle/configuration/cache_config.json`. The `sources` dict is the authoritative source; legacy flat-key fields (`historical_data_url`, `weather_lat`, etc.) are normalized into `sources` by `_normalize_sources_config()`.

### API response contract

The two-step async flow:
1. `GET /predict/{model_id}?version_alias=Production&object_ref=...` → `HTTP 202` with `task_id`
2. `GET /tasks/{task_id}` → `HTTP 202` (still processing) or `HTTP 200` (done)

Final success response shape:
```json
{
  "status": 200, "state": "done", "task_id": "...", "object_ref": "...",
  "data": {
    "message": "...",
    "output": [[timestamp_ms, value, null], ...]
  }
}
```

Note: the `output` array is `[timestamp_ms, value, null]` — the third element is always `null` (reserved for future use).

### Other constraints

- The online flow (`model_id == "none"`) skips MLflow entirely and runs inference without a bundle.
- On MLflow unavailability, `ModelProvider` falls back to the most recently cached bundle for that `model_id`+`selector`. `bundle_path=None` in `SyncResult` means no bundle available → worker returns 503.
- `/workspace/models` is NOT a fallback for offline predictions (only used by legacy `load_model_config` path when no bundle is passed).
- CMMS planned-adjustment code exists but is commented out — do not activate without an explicit task.
- Supported `model_type` values: `prophet`, `xgb`, `ar`, `naive`. Supported `fallback` values: same set plus `none`.
