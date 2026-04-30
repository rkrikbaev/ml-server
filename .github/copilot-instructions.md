## Purpose
This file is the implementation-oriented quick start for AI agents working in this repository.

Use this file for:
- where code lives
- how to run and test
- project-specific coding and API conventions

Do not treat this file as the product/UI specification.
Product and architecture intent is maintained in CLAUDE.md.

## Source of truth boundaries
- Product behavior, UI/UX details, health rules, and cross-screen semantics: see CLAUDE.md.
- Engineering workflows, code locations, runtime contracts, and implementation constraints: this file.
- If these two ever differ, update this file to match the running code and keep CLAUDE.md as the product/architecture source.

## Required docs cross-check (docs/)
- Before implementing behavior changes, API updates, model-loading changes, or test workflow changes, review relevant files in docs/.
- Treat docs/ as required reference for implementation details, operational constraints, and historical decisions.
- If code changes modify documented behavior or contracts, update the corresponding docs/ pages in the same change.
- If docs/ and code conflict, align code with approved behavior and then update documentation for consistency.

## Current architecture snapshot
- FastAPI app entrypoint: src/api/server.py.
- Broker lifecycle is started and stopped in FastAPI lifespan in src/api/server.py.
- Background execution is TaskIQ via src/api/broker/broker.py.
  - Default path uses RedisStreamBroker + RedisAsyncResultBackend.
  - Optional in-memory mode is controlled by USE_IN_MEMORY_BROKER / TEST_MODE.
- Task execution entrypoint is api_predict in src/api/broker/broker.py.
  - It delegates forecasting work to predict_logic from src/api/broker/tasks.
- Predict schemas and discriminator are in src/api/data/predict.py.
- Forecast model loading and inference logic lives under src/api/forecast/.
- UI backend endpoints are in src/api/server.py:
  - /ui
  - /ui/tasks and /ui/tasks/{task_id}
  - /ui/models and /ui/models/{model_id}/runs
  - /ui/model-config
  - /ui/runtime-status
- UI task monitor data aggregation helpers are in src/api/task_monitor.py.

## Predict API contract (must keep stable)
POST /predict supports two payload shapes:

1) Create request
- Body matches PredictCreateSchema (model_id, object_reference).
- Response: 202, state start, includes task_id.
- Server enqueues task through TaskIQ.

2) Poll request
- Body matches PredictUpdateSchema (task_id).
- If not ready: 202, state processing.
- If ready: final result response built from result backend payload.

Response formatting helpers are centralized in src/api/message.py and should be reused.

## Model-loading conventions
- Runtime model artifacts are resolved from MLflow bundle cache in `/tmp/mlserver_registry_cache`.
- `/workspace/models` can still host local model configs for non-registry flows, but MLflow registry serving must use cached bundle artifacts only.

There are two separate identifiers:
1. model_id is a business key: stable, human-readable, and associated with an object/scenario.
2. run_id is a technical training identifier from MLflow.

Do not replace model_id with run_id. Maintain an explicit model_id -> run_id link.
The model_id stays stable, while MLflow version/alias can change.

Model ID rules:
- Treat model_id as an opaque user-defined identifier.
- Do not parse model_id, derive semantics from it, or use its parts in downstream logic.
- Do not normalize model_id (no case conversion, trimming, slugification, or rewriting).
- Uniqueness of model_id is controlled by the user side.
- model_id == none means online mode.

Inference resolution rules:
- Inference input remains model_id (plus object_reference when required by API).
- Resolve model by model_id and MLflow selector (alias/version).
- Default selector alias is `Production` when selector is not provided.
- Avoid loading "latest run" implicitly.
- If registry is unavailable, fallback is allowed only to the last successfully cached MLflow bundle for the same model_id.
- Do not fallback from MLflow registry serving to `/workspace/models` for offline predictions.

## MLflow tracking conventions
For each training run, log data in consistent groups:
- params: training hyperparameters.
- metrics: quality metrics (for example MAE/RMSE/MAPE).
- tags: business metadata, including model_id and object_reference.
- artifacts: serialized model, preprocessing assets, feature schema, and runtime config snapshot.

Reproducibility metadata should be logged for every run:
- Git commit SHA.
- Dataset or data snapshot identifier.
- Python/dependency versions.
- Feature list/schema version.

Registry usage:
- Treat model_id as the stable business identifier.
- Treat MLflow versions/aliases as deploy-time selectors.
- Production serving should resolve model_id -> alias/stage -> concrete model artifact.

Serving artifact layout (required):
- `bundle/model` for serialized model payload (single file or step-wise directory, depending on model type).
- `bundle/configuration/cache_config.json` as the canonical runtime configuration for inference.
- Optional auxiliary files may be stored under `bundle/assets`.

Training output must match serving layout:
- Training jobs must register/export artifacts in the same bundle structure used by runtime.
- `config.yaml` is legacy and must not be used as the runtime source for inference configuration.

## Validation and schema conventions
- object_reference must be non-empty and contain / or \\ (validated in src/api/data/predict.py).
- PredictSchema is discriminated by presence of task_id.
- Public create requests may include `model_selection.version_alias` or `model_selection.version` for MLflow resolution.
- `version_alias` and `version` are mutually exclusive; default selector is `Production`.
- Do not reintroduce legacy request fields into PredictCreateSchema unless server contract is intentionally changed.

## Runtime dependencies and integration points
- Redis settings come from src/api/config.py (REDIS_URL, REDIS_TIMEOUT).
- Task readiness/result polling uses broker.result_backend methods.
- External integrations are configured via src/api/config.py and api/send modules:
  - NDC_URLS
  - RZ_URL (RZ_API_URL env override)
- MLflow is available in Docker for experiment tracking and registry operations.
- Registry cache controls are configured via:
  - `MODEL_REGISTRY_CACHE_DIR`
  - `MODEL_REGISTRY_CACHE_MAX`
  - `MLFLOW_DEFAULT_ALIAS`
- Runtime configuration resolution must prioritize `cache_config.json` from MLflow bundle artifacts.

## Run and test workflows
Recommended (Docker):
- From repository root:
  - docker-compose -f ml-server/docker-compose.yml up --build

Local development:
- Install dependencies from ml-server/requirements.txt.
- Ensure Redis is reachable for TaskIQ.
- From ml-server:
  - export PYTHONPATH=./src
  - python -m uvicorn api.server:app --reload --host 0.0.0.0 --port 8000
  - taskiq worker api.broker:broker

Tests:
- From ml-server:
  - pytest -q

## Files to inspect first when changing behavior
1. src/api/server.py
2. src/api/broker/broker.py
3. src/api/broker/tasks/predict.py
4. src/api/data/predict.py
5. src/api/task_monitor.py
6. src/api/forecast/model.py
7. src/api/message.py

## Continuous task tracking
**Important:** Before starting implementation work, review the ToDo.md file at the repository root.
Active tasks listed there must be considered in the context of current work to ensure alignment with planned refactoring and architectural changes.

## Agent editing guidance for this repository
- Preserve the two-step /predict contract.
- Reuse existing message helpers instead of ad-hoc JSON shapes.
- Prefer additive changes for UI endpoints to avoid breaking current Tasks/Models monitor pages.
- Verify endpoint behavior with curl after backend edits.
- Keep this file concise and operational. Keep product intent in CLAUDE.md.
