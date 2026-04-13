## Goal
Help AI agents become productive quickly in this repository by summarizing the architecture, run/test workflows, and project-specific conventions.

## Quick architecture snapshot
- FastAPI app entrypoint: `src/api/server.py` — creates the app and starts the TaskIQ broker during lifespan.
- Background workers: TaskIQ RedisStreamBroker configured in `src/api/broker/broker.py` (uses `taskiq_redis` and `RedisAsyncResultBackend`).
- Predict flow: clients POST to `/predict` (`src/api/server.py`) using a discriminated Pydantic schema (`src/api/data/predict.py`).
- Core predictive logic lives in `src/api/data/predict.py` (calls `api.forecast.*` and `api.send.*`). Forecast implementations are under `src/api/forecast/`.
- Models are mounted into the container at `/workspace/models` (see `docker-compose.yml`); model types: `xgb` (AR), `prophet`, and `none` (online/train-in-request).

## Important developer workflows
- Full stack (recommended): docker-compose up --build
  - Service `ml_model` runs both the TaskIQ worker and uvicorn API (see `docker-compose.yml` command).
  - Redis is required for TaskIQ; mlflow is included and mounts `../mlruns`.
- Local quick run (dev): install requirements from `requirements.txt` with Python 3.13, run Redis locally, then:
  - export PYTHONPATH=./src
  - python -m uvicorn api.server:app --reload --host 0.0.0.0 --port 8000
  - Start TaskIQ worker separately if you need background tasks: taskiq worker api.broker:broker
- Tests: repository contains pytest tests in `src/tests/`. Run with `pytest -q` from repo root (ensure deps and Redis if tests rely on it).

## Request/response pattern to follow (concrete)
- `/predict` accepts two shapes (see `src/api/data/predict.py`):
  - PredictCreateSchema (creation) — returns 202 with `task_id` and `object_reference` and HTTP state `start`.
  - PredictUpdateSchema (poll) — client includes `task_id`; server checks result backend and returns either `processing` (202) or final result (200).
- Return formatting and status handling are centralized in `src/api/message.py` — use those helpers to build responses.

## Conventions and gotchas (project-specific)
- Model path format: model identifiers are relative paths (e.g. `xgb/<model_dir>` or `prophet/<model_dir>`). `init_model` in `src/api/forecast/model.py` looks for `xgb_model.json` and `prophet_model.json` under `/workspace/models`.
- The `model_id == "none"` case triggers an online (train-from-input) model path — special behavior in `init_model` and elsewhere.
- `PredictCreateSchema` mutates `step` to milliseconds in the post-validator (`step *= 1000`) — treat `step` as seconds in external docs but as ms internally after validation.
- `object_reference` must contain a path separator (`/` or `\\`) — enforced by pydantic validators.
- Task lifecycle uses TaskIQ result backend TTL from `src/api/config.py` (REDIS_TIMEOUT). Use `broker.result_backend.is_result_ready(task_id)` and `get_result(task_id)` patterns.

## Integration points to be aware of
- Redis: `REDIS_URL` configured in `src/api/config.py`. Used by TaskIQ and result backend.
- External services:
  - NDC archives: `NDC_URLS` (list in `src/api/config.py`).
  - RZ API: `RZ_URL` (env override via `RZ_API_URL`). See `src/api/send/*` for usage.
- MLflow is provided in docker-compose for experiments; mlruns are mounted from `../mlruns`.
- MLflow is provided in docker-compose for experiments; mlruns are mounted from `../mlruns`.

### Model metadata & MLflow

All necessary model metadata (training parameters, versions, and auxiliary artifacts) is recorded in the MLflow tracking server used by this project. When models are produced or experimented with, relevant metadata and artifacts are stored under the `mlruns` directory (mounted into the container from `../mlruns`) and exposed via the MLflow UI.

- MLflow UI: open `http://localhost:${MLFLOW_PORT:-5050}` (docker-compose maps host port `${MLFLOW_PORT:-5050}` to container port `5000`).
- Artifacts: check `../mlruns` for run folders and artifacts. Model artifact names/structure are useful when constructing `model_id` paths under `/workspace/models`.
- Programmatic access: use `mlflow.tracking.MlflowClient()` or the `mlflow` CLI (`mlflow artifacts download`) to fetch model metadata/artifacts when adding or debugging model-loading logic.

Note: model files actually loaded by `init_model` are still expected (for `xgb`/`prophet`) as `xgb_model.json` or `prophet_model.json` under `/workspace/models/<type>/<dir>` — MLflow stores metadata and artifacts that complement these files and can be used to reproduce or rehydrate model directories.

## How to add a new model type (example)
1. Add loading logic in `src/api/forecast/model.py` in `init_model`. Follow the `xgb`/`prophet` examples and name the model file consistently (`<type>_model.json`).
2. Ensure `predict()` in `src/api/forecast/inference.py` supports the model class and returns `(preds, pred_ts, is_matching)`.
3. Add tests under `src/tests/` exercising both creation and polling flows for the new model.

## Files to read first (in priority order)
- `src/api/server.py` — endpoint shapes and lifespan wiring
- `src/api/broker/broker.py` and `src/api/broker/tasks/predict.py` — task wiring and TaskIQ entrypoints
- `src/api/data/predict.py` — Pydantic schemas and validation rules
- `src/api/forecast/*` — model init and prediction logic
- `src/api/message.py` — standard response format
- `docker-compose.yml` — how the container runs (worker + server) and volumes/envs

If anything above is unclear or you'd like more examples (sample predict payloads, local run scripts, or a short test harness), tell me which piece to expand and I will iterate.
## Workflow (run, test, debug)

Below are concrete, copy-pasteable commands and a minimal request example to run and test the service locally or inside Docker.

1) Full stack (recommended - Docker compose)

```bash
# from repo root
docker-compose up --build
```

The `ml_model` service (defined in `docker-compose.yml`) runs the TaskIQ worker and the uvicorn server in the same container. Redis must be up for TaskIQ result backend. The models folder is mounted into the container at `/workspace/models`.

2) Local development (no Docker)

```bash
# ensure Python 3.13 and dependencies from requirements.txt are installed
export PYTHONPATH=./src
python3.13 -m uvicorn api.server:app --reload --host 0.0.0.0 --port 8000

# in another terminal start the worker (requires Redis available at REDIS_URL)
taskiq worker api.broker:broker
```

Notes:
- The API validates `PredictCreateSchema` fields and mutates `step` to milliseconds after validation. When constructing payloads for tests or curl examples treat `step` in seconds (the schema will convert it).
- If you need to run against real archives or RZ endpoints, set `RZ_API_URL` and ensure `NDC` hosts in `src/api/config.py` are reachable.

3) Run tests

```bash
# from repo root
pytest -q
```

Some tests may require Redis or mocked external services; inspect `src/tests/` for test-specific setup.

4) Quick predict create -> poll example (curl)

Replace values below with a real `object_reference` and optional `model_id`.

```bash
# create (first POST) - returns 202 and task_id
curl -s -X POST http://localhost:8000/predict \
  -H 'Content-Type: application/json' \
  -d '{
    "model_id": "some_model_id or none",
    "object_reference": "some/path/to/object",
    "version": "v1"
  }'

# poll (second POST) - use returned task_id
curl -s -X POST http://localhost:8000/predict \
  -H 'Content-Type: application/json' \
  -d '{ "task_id": "<paste-task-id-here>" }'
```

If the task is still running the server returns 202 with state `processing` and you should poll again. Final responses use `src/api/message.py` helpers and include `output`, `reference`, `status`, `state`, and `model_confidence` fields on success.

---

If you'd like, I can also add a tiny script `scripts/run_local.sh` that wraps the commands above and a `scripts/example_request.sh` to run the curl example automatically. Tell me if you'd like those files added.
