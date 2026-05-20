# WORKFLOW: Stage 0 — Application Initialization & Infrastructure Setup

**Stage 0** covers the startup and lifecycle management of the ml-server application, including FastAPI initialization, broker configuration, and infrastructure dependencies.

---

## Problem Statement

The ml-server is an **async FastAPI application** that depends on:
- **TaskIQ broker** (Redis-based task queue)
- **Result backend** (Redis or in-memory for storing task results)
- **MLflow** (model registry and artifact storage)
- **External services** (historical data, weather, CMMS)

All components must be initialized before the first client request arrives, and properly shut down when the application exits.

---

## Startup Lifecycle

### Phase 1: Application Instantiation

[`src/api/server.py:24-29`](src/api/server.py#L24):

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    await broker.startup()
    yield
    await broker.shutdown()

app = FastAPI(lifespan=lifespan)
```

**Key Points:**
- Uses FastAPI's `lifespan` context manager (PEP 492 async context)
- Lifecycle is **bound to application instance**, not global
- `yield` separates startup → running → shutdown

### Phase 2: Broker Configuration & Result Backend

[`src/api/broker/broker.py:7-28`](src/api/broker/broker.py#L7):

**Environment-based initialization:**

```python
TEST_MODE = getenv("TEST_MODE", "false").lower() == "true"
USE_IN_MEMORY_BROKER = getenv("USE_IN_MEMORY_BROKER", "false").lower() == "true"

if not USE_IN_MEMORY_BROKER:
    # Production (default): Redis
    from taskiq_redis import RedisStreamBroker, RedisAsyncResultBackend
    result_backend = RedisAsyncResultBackend(REDIS_URL, result_ex_time=REDIS_TIMEOUT)
    broker = RedisStreamBroker(REDIS_URL).with_result_backend(result_backend)
elif TEST_MODE:
    # Test mode: In-memory
    from taskiq import InMemoryBroker
    from taskiq.result_backends.dummy import DummyResultBackend
    result_backend = DummyResultBackend()
    broker = InMemoryBroker().with_result_backend(result_backend)
else:
    # Fallback: Redis (same as production)
    result_backend = RedisAsyncResultBackend(REDIS_URL, result_ex_time=REDIS_TIMEOUT)
    broker = RedisStreamBroker(REDIS_URL).with_result_backend(result_backend)
```

#### Configuration Matrix

| Mode | Environment | Broker | Result Backend | Use Case |
|------|-------------|--------|---|---|
| **Production** | `USE_IN_MEMORY_BROKER=false` (default) | `RedisStreamBroker` | `RedisAsyncResultBackend` (TTL: REDIS_TIMEOUT) | Docker, multi-instance |
| **Test** | `TEST_MODE=true` + `USE_IN_MEMORY_BROKER=undefined` | `InMemoryBroker` | `DummyResultBackend` | Unit tests, isolated |
| **Hybrid** | `USE_IN_MEMORY_BROKER=true` (explicit) | `InMemoryBroker` | `DummyResultBackend` | Single-instance test |

**Environment Variables** ([`src/api/config.py`](src/api/config.py)):

```python
REDIS_URL = "redis://redis:6379/0"         # Redis connection string
REDIS_TIMEOUT = 3600                       # Result TTL: 1 hour
PYTHONPATH = "/workspace/server:/workspace/lib"  # Module search paths
MLFLOW_TRACKING_URI = "http://mlflow:5000" # MLflow tracking server
MLFLOW_REGISTRY_URI = "http://mlflow:5000" # MLflow registry server
```

### Phase 3: TaskIQ Worker Registration

```python
@broker.task
async def api_predict(data: Dict[str, Any]) -> Dict[str, Any]:
    output = await predict_logic(
        model_id=data["model_id"],
        online=data["online"],
        selector=data.get("selector"),
    )
    output["object_reference"] = data["object_reference"]
    return output
```

**What happens:**
- `@broker.task` decorator registers this function with TaskIQ
- Enables RPC-style calls via `.kiq()` method (from Stage 2)
- Results automatically stored in result backend

### Phase 4: Infrastructure Dependencies

**Docker Compose Services** ([`docker-compose.yml`](docker-compose.yml)):

#### a) ml-server container (main application)

```yaml
model-server:
  image: fpcloud/ml:1.0.0
  command: >
    bash -c "
      taskiq worker api.broker:broker --workers 8 &
      python -u -m uvicorn api.server:app --host 0.0.0.0 --port 8000 &
      wait -n
    "
  ports:
    - "8030:8000"
  environment:
    - PYTHONUNBUFFERED=1
    - TEST_MODE=true
    - MLFLOW_TRACKING_URI=http://mlflow:5000
    - MODEL_REGISTRY_CACHE_DIR=/tmp/local_models_cache
```

**Startup sequence in container:**
1. `taskiq worker api.broker:broker --workers 8` — Start 8 worker processes listening to TaskIQ queue
2. `uvicorn api.server:app --host 0.0.0.0 --port 8000` — Start FastAPI server on port 8000
3. `wait -n` — Wait for first process to exit (if either dies, container stops)

#### b) Redis container

```yaml
redis:
  image: redis:7
  ports:
    - "6379:6379"
  healthcheck:
    test: ["CMD-SHELL", "redis-cli ping"]
    interval: 5s
    timeout: 5s
    retries: 5
```

**Role:**
- TaskIQ broker: message queue for `/predict` tasks
- Result backend: temporary storage of prediction results (TTL: 1 hour)
- Allows multi-instance scaling (results accessible from any API instance)

#### c) MLflow container

```yaml
mlflow:
  image: ghcr.io/mlflow/mlflow:latest
  command: mlflow server --host 0.0.0.0 --port 5000 \
    --backend-store-uri sqlite:////mlflow/mlflow.db \
    --default-artifact-root /mlflow/mlruns
  ports:
    - "5050:5000"
```

**Role:**
- Model registry: stores model versions and aliases (e.g., "Production")
- Artifact storage: bundles (config.json, model files) cached to `/tmp/local_models_cache`
- Accessed by Stage 3 during worker initialization

---

## Startup Sequence Diagram

```
docker-compose up
      ↓
Redis container starts
      ↓ (port 6379 ready)
MLflow container starts
      ↓ (port 5000 ready)
ml-server container starts
      ↓
taskiq worker process spawned (8 workers listening on redis://redis:6379/0)
      ↓
uvicorn FastAPI server spawned (listening on 0.0.0.0:8000)
      ↓ (both processes running)
lifespan context: await broker.startup()
      ↓ (connects to Redis, registers @broker.task functions)
Application ready for requests
```

---

## Configuration & Environment

### Model Registry Cache

**Path:** `/tmp/local_models_cache` (mounted as Docker volume `model_registry_cache`)

**Purpose:**
- Cache MLflow model bundles (config.json, adapters, fallback models)
- Reduces MLflow calls on repeated predictions for same model_id
- TTL: Controlled by Stage 3 (`MAX_CACHE_ENTRIES` if implemented)

**Environment:**
```python
MODEL_REGISTRY_CACHE_MAX = 3                        # Max cached models
MODEL_REGISTRY_CACHE_DIR = "/tmp/local_models_cache"
```

### Models Directory

**Path:** `/workspace/models` (mounted from `../local/{MODEL:-models}` on host)

**Structure per model:**
```
models/
  └─ prophet_watt_AKMOLA/
     ├─ config.json          # Runtime config with sources
     ├─ model.pkl            # Serialized model (if applicable)
     └─ ...
```

**Accessed by:** Stage 3 (`load_model_config()`)

---

## Shutdown Lifecycle

### Graceful Termination

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    await broker.startup()
    yield  # ← Application running here
    await broker.shutdown()  # Executed on SIGTERM
```

**When container receives SIGTERM (docker-compose down):**
1. Main process (uvicorn) receives signal
2. FastAPI calls `lifespan` exit handlers in reverse order
3. `await broker.shutdown()` is called
4. Redis connections closed, in-flight tasks allowed to complete (timeout: 30s typical)
5. Process exits with code 0

**Responsibilities:**
- Ensure no new tasks are enqueued during shutdown
- Wait for in-flight tasks (optional, depends on graceful shutdown policy)
- Close database connections and resource handles

---

## Error Scenarios & Recovery

### Scenario 1: Redis unavailable during startup

**Symptom:** Container starts but crashes with connection error.

**Resolution:**
- Docker Compose `depends_on` ensures Redis is **started** (not necessarily healthy)
- Use `healthcheck` in Redis service to verify readiness
- Application should retry Redis connections with exponential backoff

```yaml
depends_on:
  - redis
  - mlflow
```

### Scenario 2: MLflow registry inaccessible

**Symptom:** Container starts, but Stage 3 fails on model config load.

**Resolution:**
- MLflow unavailability is **not fatal** at startup (lazy-loaded)
- Caught at Stage 3 (worker task), returned as 503 Service Unavailable

### Scenario 3: Worker processes crash

**Symptom:** `/predict` enqueued but never executes.

**Resolution:**
- `wait -n` in docker-compose ensures container stops if workers die
- Docker `restart: unless-stopped` policy restarts container

---

## Testing & Verification

### Check Broker Status

```bash
# Inside ml-server container
redis-cli -h redis ping
# Expected output: PONG

redis-cli -h redis XINFO STREAM predict
# Lists pending tasks in queue
```

### Check Application Health

```bash
curl http://localhost:8030/ui
# Should return index.html (204 if UI not built)
```

### Verify Startup Logs

```bash
# From host
docker-compose logs model-server

# Expected lines:
# - "Uvicorn running on http://0.0.0.0:8000"
# - "taskiq worker started"
```

### Manual Task Enqueue Test

```bash
# From host, via API (Stage 1–2)
curl -X POST http://localhost:8030/predict \
  -H "Content-Type: application/json" \
  -d '{
    "model_id": "prophet_watt_AKMOLA",
    "object_reference": "AKMOLA/KSTS/01"
  }'

# Expected: HTTP 202 with task_id
```

---

## Key Components Summary

| Component | Location | Purpose | Initialized at |
|-----------|----------|---------|---|
| FastAPI app | `src/api/server.py:29` | HTTP endpoint handling | Startup |
| TaskIQ broker | `src/api/broker/broker.py:13-28` | Task queue manager | Startup |
| Result backend | `src/api/broker/broker.py:13-28` | Task result storage | Startup |
| Redis | `docker-compose.yml` | Infrastructure for broker/results | Container startup |
| MLflow | `docker-compose.yml` | Model registry & artifacts | Container startup |
| Models directory | `/workspace/models` | Runtime model configs & files | Lazy-loaded (Stage 3) |

---

## Stage 0 Contract

- ✅ FastAPI application instantiated with lifespan hooks
- ✅ TaskIQ broker configured (Redis or in-memory based on environment)
- ✅ Result backend connected and ready for task results
- ✅ Infrastructure dependencies (Redis, MLflow) available
- ✅ Worker processes listening to task queue
- ✅ Ready to accept HTTP requests on `/predict` endpoint

---

## Next Steps

**→ Stage 1**: Client sends first POST request to `/predict` with model selection.

**→ Stage 2**: Request enqueued, worker task begins (Stage 3 onwards).
