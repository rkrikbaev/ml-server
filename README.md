# ml-server

Backend service for asynchronous forecasting with a two-step `/predict` API.

The service is built on FastAPI + TaskIQ + Redis and resolves offline model bundles through MLflow Registry with local bundle caching.

## What this service does

- Accepts forecast requests via `POST /predict`.
- Runs inference asynchronously in background workers.
- Returns task status and final prediction using the same endpoint.
- Exposes operational UI/API endpoints under `/ui/*`.

## Architecture at a glance

- API server: FastAPI (`src/api/server.py`).
- Background processing: TaskIQ broker (`src/api/broker/broker.py`).
- Queue/result backend: Redis.
- Model loading and inference: `src/api/forecast/*`.
- Offline model resolution: MLflow Registry -> cached bundle in `/tmp/mlserver_registry_cache`.
- Local runtime stack: `docker-compose.yml` (`model-server`, `redis`, `mlflow`).

## Quick start (Docker)

From repository root:

```bash
docker-compose -f ml-server/docker-compose.yml up --build
```

Default ports (can be overridden by env vars):

- API: `http://localhost:8030`
- Redis: `localhost:6379`
- MLflow UI: `http://localhost:5050`

## Local development (without Docker API process)

From `ml-server` directory:

```bash
pip install -r requirements.txt
export PYTHONPATH=./src
python -m uvicorn api.server:app --reload --host 0.0.0.0 --port 8000
```

In a separate terminal, run the worker:

```bash
cd ml-server
export PYTHONPATH=./src
taskiq worker api.broker:broker
```

Redis must be available for TaskIQ.

## Predict API flow (two-step, async)

1. Start a task:

```bash
curl -X POST http://localhost:8030/predict \
	-H "Content-Type: application/json" \
	-d '{"object_reference":"/root/FP/PROJECT/AKMOLA/@regions/KOKSHETAU/Load/P_load/archives/out_value","model_id":"model3","model_selection":{"version_alias":"Production"}}'
```

Expected response: HTTP `202` with `task_id`.

Optional MLflow selector fields in create request:

- `model_selection.version_alias` - resolve by MLflow alias, default is `Production`.
- `model_selection.version` - resolve by explicit MLflow model version.
- `version_alias` and `version` are mutually exclusive.

2. Poll by `task_id`:

```bash
curl -X POST http://localhost:8030/predict \
	-H "Content-Type: application/json" \
	-d '{"task_id":"<task_id>"}'
```

Expected behavior:

- HTTP `202` while processing.
- Final successful response with status/state when done.

## Common make commands

From `ml-server` directory:

```bash
make help
make test
make smoke-positive
make smoke-negative
make test-predict PREDICT_MODEL_ID=model3
make ml-model-status
make smoke-api
```

## Testing

- Unit/integration tests (excluding smoke tests):

```bash
cd ml-server
make test
```

- Predict smoke tests:

```bash
cd ml-server
make smoke-positive
make smoke-negative
```

- End-to-end test of async `/predict` flow:

```bash
cd ml-server
make test-predict PREDICT_MODEL_ID=model3
```

## Model conventions

- Models are resolved by `model_id` (business identifier).
- `model_id` is opaque and user-defined.
- Do not parse, normalize, or rewrite `model_id`.
- Offline runtime artifacts are resolved from MLflow bundle cache under `/tmp/mlserver_registry_cache`.
- Canonical runtime config for offline serving is `bundle/configuration/cache_config.json` inside the cached MLflow bundle.
- `/workspace/models` is not a fallback source for offline predictions.
- Online flow is used when `model_id` is omitted or equals `none`.

## UI and operational endpoints

- `GET /ui`
- `GET /ui/tasks`
- `GET /ui/tasks/{task_id}`
- `GET /ui/models`
- `GET /ui/models/{model_id}/runs`
- `GET /ui/model-config`
- `GET /ui/runtime-status`

## Documentation map

Start here:

- `docs/DOCMAP.txt` - documentation overview and navigation.
- `docs/API/MAIN.md` - API reference.
- `docs/API/schema/PREDICT.md` - request schema and validation.
- `docs/API/MESSAGES.md` - response message formats.
- `START_TESTING.md` - fast testing checklist.

## Documentation policy

Before changing API behavior, runtime contracts, model-loading logic, or test flows, check relevant files in `docs/`.

If behavior or contracts changed in code, update the corresponding docs in the same change.
