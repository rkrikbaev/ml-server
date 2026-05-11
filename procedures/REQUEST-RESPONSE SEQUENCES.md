# ml-server request-response

## Overview

`ml-server` serves forecasts via a model-registry-centric flow:

1. Client calls `POST /predict` (create) with `object_reference`, `model_id`, and optional `model_selection`.
2. `model-server` enqueues async prediction and returns `202` with `task_id`.
3. Client polls `POST /predict` with `task_id` until the task is ready.
4. For offline models (`model_id != none`), `model-server` resolves `run_id` from MLflow Registry using selector:
  - `model_selection.version` (exact version), or
  - `model_selection.version_alias` (alias), or
  - default alias from `MLFLOW_DEFAULT_ALIAS` (default value: `Production`).
5. Bundle is loaded from runtime cache or downloaded from MLflow artifacts.
6. Inference runs using bundle model payload and `bundle/configuration/cache_config.json`.
7. A dedicated Jupyter Notebook Server is used for interactive model training, validation, and long-horizon forecast experiments; trained artifacts are logged to MLflow Registry and then consumed by `model-server`.


## Components

- `model-server`:
  - API (`uvicorn`) + background worker (`taskiq`).
  - Resolves model version from MLflow Registry.
  - Maintains runtime LRU cache of bundles.
- `mlflow`:
  - Tracking + Registry service.
  - Metadata store: `sqlite` (`/mlflow/mlflow.db`).
  - Artifact store: `/mlflow/mlruns`.
- `redis`:
  - Queue/broker for background task processing.
- `jupyter-notebook-server`:
  - Interactive workspace for data exploration, model training, and long-term forecast scenarios.
  - Logs runs/artifacts into MLflow and can call `POST /predict` for runtime validation.
  - Uses shared model/artifact volumes for reproducible experiments.
- `local/models`:
  - Local model-centric workspace and artifacts.
- `local/mlruns`:
  - MLflow artifact storage, shared between MLflow and model-server.
- `model_registry_cache` volume:
  - Runtime bundle cache in `/tmp/mlserver_registry_cache`.


## Container Architecture (ASCII)

```text
                        +-----------------------------+
                        |   Client / UI / External    |
                        +-------------+---------------+
                                      |
                          HTTP POST /predict | Notebook UI (browser)
                                      |
                                      v
+----------------------------------------------------------------------------+
|                         ml-server Docker Network                           |
|                                                                            |
|   +-----------------------+                                                |
|   | jupyter-notebook-     |---- log runs/artifacts -------------------+    |
|   | server                |                                           |    |
|   +-----------+-----------+                                           |    |
|               |                                                       v    |
|               |                                    +----------------------+|
|               +---- optional runtime validation -> |     model-server     ||
|                                                    |  uvicorn + taskiq    ||
|                                                    +----------+-----------+|
|   +----------------------+        resolve alias/version       +---------+  |
|   |     (same service)   |----------------------------------->| MLflow  |  |
|   |                      |<-----------------------------------|Tracking |  |
|   +----------+-----------+      download_artifacts(bundle)    |+Registry|  |
|              |                                                +----+----+  |
|              |                                                     |       |
|              | queue/background jobs                               |       |
|              v                                                     |       |
|         +---------+                                                |       |
|         |  Redis  |                                                |       |
|         +---------+                                                |       |
|                                                                    |       |
|   +------------------------------+                                 |       |
|   | Runtime cache volume         |<--------------------------------+       |
|   | /tmp/mlserver_registry_cache |   store bundle + metadata               |
|   | LRU max=3 bundles/model      |                                         |
|   +------------------------------+                                         |
|                                                                            |
+----------------------------------------------------------------------------+
      ^                 ^                  ^
      |                 |                  |
      | mounted ro      | mounted rw       | mounted rw into mlflow
      | into model-server and notebook     |
     +----------------------+             +----------------------+
     | local/mlruns         |<----------->| mlflow.db (sqlite)   |
     | MLflow artifacts     |             | metadata store       |
     +----------------------+             +----------------------+

     +----------------------+
     | local/models         |
     | -> /workspace/models |
     +----------------------+
```


## Predict Sequence (ASCII)

```text
Client               model-server              task queue/result backend   MLflow Registry   local/mlruns   runtime cache
  |                       |                              |                   |                 |              |
  | POST /predict         |                              |                   |                 |
  | {object_reference,    |                              |                   |                 |
  |  model_id,            |                              |                   |                 |
  |  model_selection?}    |                              |                   |                 |
  |---------------------->| enqueue task                 |                   |                 |
  |<----------------------| 202 START {task_id}          |                   |                 |
  |                       |                              |                   |                 |
  |                       | check task status            |                   |                 |
  | POST /predict         |----------------------------->|                   |                 |
  | {task_id}             |<-----------------------------| not ready.        |                 |
  |---------------------->|                              |                   |                 |
  |<----------------------| 202 PROCESSING (if running)  |                   |                 |
  |                       |                              |                   |                 |
  | (task execution)      | resolve selector -> run_id   |                   |                 |
  |                       |------------------------------------------------->|                 |
  |                       |<-------------------------------------------------| run_id          |
  |                       | check cache for {model,selector,run}             |                 |
  |                       |---------------------------------------------------------------------------------> |
  |                       |<--------------------------------------------------------------------------------- |
  |                       | cache miss -> download bundle                                      |              |
  |                       |------------------------------------------------------------------->|              |
  |                       |<-------------------------------------------------------------------| bundle/*     |
  |                       | write bundle+metadata                                              |
  |                       |---------------------------------------------------------------------------------> |
  |                       | infer forecast                                                     |
  | POST /predict         | return final task result                                           |
  | {task_id}             |                                                                    |
  |---------------------->|                                                                    |
  |<----------------------| 200/422/500/503 DONE                                               |
```


## Training Wave Sequence (External to `src`, ASCII)

The training-wave orchestration below is not implemented inside `ml-server/src`.
It is an external workflow (scripts/procedures/docs scope), kept here for platform context.

```text
Training Wave      Batch Summary/CSV       MLflow Registry         MLflow Artifacts(local/mlruns)
    |                     |                      |                           |
    | read batch_summary  |                      |                           |
    |-------------------->|                      |                           |
    |<--------------------| status=ok rows       |                           |
    | for each model_id   |                      |                           |
    | check Production alias                     |                           |
    |------------------------------------------->|                           |
    |<-------------------------------------------| exists / not exists       |
    | if exists -> skip                          |                           |
    | else: train+evaluate+bundle                |                           |
    |--------------------------------------------+-------------------------->|
    | log run artifacts                                                   (bundle/model + configuration/cache_config.json)
    |                                             create model version       |
    |------------------------------------------->|                           |
    |                                             set alias Production       |
    |------------------------------------------->|                           |
    | collect trained/skipped/failed summary     |                           |
    | write wave_report.json                     |                           |
```


## Notebook Workflow Sequence (Long-Term Forecast, ASCII)

```text
User (DS/Analyst)      Jupyter Notebook Server      MLflow Registry/Artifacts      model-server
  |                          |                              |                        |
  | open notebook            |                              |                        |
  |------------------------->|                              |                        |
  | run feature prep         |                              |                        |
  | run train/evaluate       |                              |                        |
  |------------------------->| log params/metrics/model     |                        |
  |                          |----------------------------->|                        |
  |                          | register version + alias     |                        |
  |                          |----------------------------->|                        |
  | long-term scenario eval  |                              |                        |
  | (horizon expansion)      |                              |                        |
  | request runtime check    |                              |                        |
  |------------------------->| POST /predict (create/poll)  |                        |
  |                          |------------------------------------------------------->|
  |                          |<-------------------------------------------------------|
  | view forecast outputs    |                              |                        |
  |<-------------------------|                              |                        |
```


## Key Runtime Rules

- Registry selector resolution priority: `model_selection.version` -> `model_selection.version_alias` -> `MLFLOW_DEFAULT_ALIAS` (default value: `Production`).
- Runtime cache keeps up to `MODEL_REGISTRY_CACHE_MAX` bundles per model.
- If MLflow sync fails and cached bundle exists, model-server falls back to latest cached bundle.
- Canonical runtime config source is `bundle/configuration/cache_config.json`.
- Notebook training must produce MLflow bundle layout compatible with serving: `bundle/model` + `bundle/configuration/cache_config.json`.
