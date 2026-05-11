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
- Notebook workflow: Jupyter Notebook Server for interactive training and long-horizon forecast experiments.
- Local runtime stack: `docker-compose.yml` (`model-server`, `redis`, `mlflow`, `jupyter-notebook-server`).

## Quick start (Docker)

From repository root:

```bash
docker-compose -f ml-server/docker-compose.yml up --build
```

Default ports (can be overridden by env vars):

- API: `http://localhost:8030`
- Redis: `localhost:6379`
- MLflow UI: `http://localhost:5050`
- Jupyter Notebook: `http://localhost:8888` (token: `ml-notebook` by default, configurable via `JUPYTER_TOKEN`)

Open Jupyter and use notebooks under `/workspace/study` or `/workspace/procedures` to train models, log artifacts to MLflow, and validate forecasts through the async `/predict` flow.

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

## Notebook quick recipe

From `ml-server` directory:

```bash
make notebook-up
make notebook-logs
```

Open Jupyter at `http://localhost:8888` (or `${JUPYTER_PORT}` if overridden).

Optional environment variables for notebook predict bootstrap:

```bash
export ML_SERVER_PREDICT_URL=http://model-server:8000/predict
export ML_SERVER_MODEL_ID=prophet_watt_h_AKMOLA_test
export ML_SERVER_OBJECT_REFERENCE=/root/FP/PROJECT/AKMOLA/@regions/KOKSHETAU/Load/P_load/archives/out_value
export ML_SERVER_VERSION_ALIAS=Production
export ML_SERVER_POLL_INTERVAL=1
export ML_SERVER_MAX_ATTEMPTS=60
```

Addressing note:
- If code runs inside Jupyter container, use `http://model-server:8000/predict` (recommended) or `http://host.docker.internal:8030/predict`.
- If code runs on host machine, use `http://localhost:8030/predict`.
- Do not use `http://0.0.0.0:8030/predict` as a client destination.

These variables are consumed by the long-term forecast bootstrap code in the study notebook and allow selecting model, alias, and polling behavior without changing notebook code.

## Jupyter remote access setup

For access from another machine, configure host binding and strong authentication before startup.

1. Set remote-access variables:

```bash
export JUPYTER_BIND_ADDRESS=0.0.0.0
export JUPYTER_PORT=8888
export JUPYTER_TOKEN='<strong-random-token>'
```

2. Optional: use password hash in addition to token:

```bash
python -c "from jupyter_server.auth import passwd; print(passwd())"
export JUPYTER_PASSWORD_HASH='sha1:...'
```

3. Restart notebook service:

```bash
cd ml-server
make notebook-down
make notebook-up
```

4. Connect from remote host:

```text
http://<server-ip>:<JUPYTER_PORT>
```

Security recommendation:
- Do not expose Jupyter to the public internet without firewall rules/VPN/reverse proxy TLS.
- Prefer opening access only from trusted IP ranges.

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
