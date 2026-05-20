# WORKFLOW: Stage 10 — Configuration, Environment & Deployment

**Stage 10** documents the deployment environment, configuration management, runtime modes, and infrastructure setup required to run the ml-server in development, testing, and production contexts.

---

## Problem Statement

The ml-server has multiple deployment scenarios:
1. **Local development** — single instance, in-memory broker, optional services
2. **Integration testing** — Docker Compose with Redis, MLflow, multiple workers
3. **Production** — distributed Redis, model registry, monitoring

Configuration must be:
- **Environment-driven** (12-factor app principles)
- **Mode-aware** (TEST_MODE, USE_IN_MEMORY_BROKER)
- **Externalized** (no hardcoded secrets or paths)
- **Validated** (with sensible defaults)

---

## Configuration Sources

### 1. Environment Variables

[`src/api/config.py`](src/api/config.py):

```python
# Redis
REDIS_URL = "redis://redis:6379/0"
REDIS_TIMEOUT = 3600  # seconds, default 1 hour

# External Services
HISTORICAL_DATA_HOSTS = ["10.210.1.11", "10.210.1.13", "10.210.1.15"]
HISTORICAL_DATA_URLS = [f"http://{host}:7080/api/read/archive" for host in HISTORICAL_DATA_HOSTS]
CMMS_URL = getenv("CMMS_URL") or getenv("CMMS_API_URL")

# HTTP Clients
CLIENT_TIMEOUT_ONE = 30     # seconds per request
CLIENT_TIMEOUT_ALL = 150    # seconds for all retries

# Timezones
GMT_TO_ASTANA_HOURS = 5
```

### 2. Docker Environment

[`docker-compose.yml`](docker-compose.yml) service `model-server`:

```yaml
environment:
  - PYTHONUNBUFFERED=1
  - PYTHONPATH=/workspace/server:/workspace/lib
  - TEST_MODE=true
  - SCADA_STUB_ENABLED=${SCADA_STUB_ENABLED:-false}
  - HISTORICAL_DATA_STUB_ENABLED=${HISTORICAL_DATA_STUB_ENABLED:-false}
  - MLFLOW_TRACKING_URI=http://mlflow:5000
  - MLFLOW_REGISTRY_URI=http://mlflow:5000
  - MLFLOW_DEFAULT_ALIAS=Production
  - MODEL_REGISTRY_CACHE_MAX=3
  - MODEL_REGISTRY_CACHE_DIR=/tmp/local_models_cache
```

### 3. Runtime Modes

#### Mode 1: Production (default)

```yaml
# Environment
USE_IN_MEMORY_BROKER: "false"  (default)
TEST_MODE: "false"              (default)
REDIS_URL: "redis://redis:6379/0"

# Broker
TaskIQ: RedisStreamBroker
Result Backend: RedisAsyncResultBackend (TTL: REDIS_TIMEOUT)
Workers: 8 (hardcoded in docker-compose.yml)

# Database
Persistent: Redis (distributed)
TTL: 1 hour (REDIS_TIMEOUT)
```

#### Mode 2: Test (Docker Compose)

```yaml
# Environment
TEST_MODE: "true"
USE_IN_MEMORY_BROKER: "undefined" (falls back to Redis)

# Broker
TaskIQ: InMemoryBroker (if explicitly set)
Result Backend: DummyResultBackend
Workers: Same container processes

# Database
In-memory only
TTL: Process lifetime (lost on restart)
```

#### Mode 3: Development (Local)

```bash
# Run without Docker
export TEST_MODE=true
export USE_IN_MEMORY_BROKER=true
python -m uvicorn api.server:app --reload

# Broker: InMemoryBroker
# Result Backend: DummyResultBackend
# Workers: None (async calls execute inline)
```

---

## Docker Compose Architecture

[`docker-compose.yml`](docker-compose.yml):

### Service 1: ml-server (model-server)

```yaml
model-server:
  image: fpcloud/ml:1.0.0
  build:
    context: .
    dockerfile: ./docker/Dockerfile
  container_name: models_${MODEL:-models}
  restart: unless-stopped
  command: >
    bash -c "
      taskiq worker api.broker:broker --workers 8 &
      python -u -m uvicorn api.server:app --host 0.0.0.0 --port 8000 &
      wait -n
    "
  ports:
    - "${PORT:-8030}:8000"
  environment:
    - TEST_MODE=true
    - MLFLOW_TRACKING_URI=http://mlflow:5000
    - MODEL_REGISTRY_CACHE_DIR=/tmp/local_models_cache
  volumes:
    - "../local/${MODEL:-models}:/workspace/models"
    - "./src:/workspace/server"
    - "../models:/workspace/lib"
    - "model_registry_cache:/tmp/local_models_cache"
  depends_on:
    - redis
    - mlflow
  networks:
    - ml
```

**Key features:**
- **Command**: Starts both TaskIQ worker pool and Uvicorn API server
- **Ports**: Maps 8030 (host) → 8000 (container)
- **Volumes**: 
  - `/workspace/models` — model configs and binaries
  - `/workspace/server` — source code (hot reload)
  - `model_registry_cache` — MLflow bundle cache
- **Depends on**: Redis and MLflow must be running

### Service 2: Redis

```yaml
redis:
  image: redis:7
  container_name: redis
  restart: unless-stopped
  ports:
    - "${REDIS_PORT:-6379}:6379"
  volumes:
    - redis_data:/data
  healthcheck:
    test: ["CMD-SHELL", "redis-cli ping"]
    interval: 5s
    timeout: 5s
    retries: 5
  networks:
    - ml
```

**Role:**
- TaskIQ broker queue (task messages)
- Result backend (prediction results with TTL)
- Shared state for multi-instance deployments

**Data persistence:**
- Mounted volume `redis_data:/data` persists across restarts
- Healthcheck ensures readiness before API starts

### Service 3: MLflow

```yaml
mlflow:
  image: ghcr.io/mlflow/mlflow:latest
  container_name: mlflow
  restart: unless-stopped
  command: mlflow server --host 0.0.0.0 --port 5000 \
    --backend-store-uri sqlite:////mlflow/mlflow.db \
    --default-artifact-root /mlflow/mlruns \
    --allowed-hosts mlflow,mlflow:5000,localhost,host.docker.internal
  ports:
    - "${MLFLOW_PORT:-5050}:5000"
  volumes:
    - "../local/mlruns:/mlflow/mlruns"
    - "mlflow_data:/mlflow"
  networks:
    - ml
```

**Role:**
- Model registry (versions, aliases, metadata)
- Artifact storage (model bundles downloaded to `/tmp/local_models_cache`)
- UI for browsing experiments (port 5050)

**Data persistence:**
- SQLite backend at `/mlflow/mlflow.db`
- Mounted volume `mlflow_data:/mlflow` for SQLite and metadata

**Allowed hosts:**
- Internal Docker network: `mlflow`, `mlflow:5000`
- Host machine: `localhost`, `127.0.0.1`, `host.docker.internal`

---

## Volume Management

### Docker Volumes

| Volume | Purpose | Mount Point | Persistent |
|--------|---------|-------------|---|
| `redis_data` | Redis persistence | `/data` (in redis container) | ✅ Yes |
| `model_registry_cache` | MLflow bundle cache | `/tmp/local_models_cache` | ✅ Yes |
| `mlflow_data` | MLflow metadata | `/mlflow` | ✅ Yes |

### Host Mounts (Bind Mounts)

| Source (Host) | Container | Purpose | Editable |
|---|---|---|---|
| `../local/{MODEL}/` | `/workspace/models` | Model configs & binaries | Read-only |
| `./src` | `/workspace/server` | Source code | ✅ Hot-reload |
| `../models` | `/workspace/lib` | Library models | Read-only |
| `../local/mlruns` | `/mlflow/mlruns` (ro) | MLflow artifacts | Read-only |

---

## Environment Variable Reference

### Broker Configuration

| Variable | Default | Type | Purpose |
|----------|---------|------|---------|
| `USE_IN_MEMORY_BROKER` | `false` | bool | Use in-memory queue instead of Redis |
| `TEST_MODE` | `false` | bool | Run in test mode (affects logging, timeout) |
| `REDIS_URL` | `redis://redis:6379/0` | URL | Redis broker and result backend |
| `REDIS_TIMEOUT` | `3600` | int | Task result TTL in seconds |

### Model Registry

| Variable | Default | Type | Purpose |
|----------|---------|------|---------|
| `MLFLOW_TRACKING_URI` | `http://mlflow:5000` | URL | MLflow server (inside Docker) |
| `MLFLOW_REGISTRY_URI` | `http://mlflow:5000` | URL | MLflow registry |
| `MLFLOW_DEFAULT_ALIAS` | `Production` | str | Default model alias |
| `MODEL_REGISTRY_CACHE_MAX` | `3` | int | Max cached model bundles |
| `MODEL_REGISTRY_CACHE_DIR` | `/tmp/local_models_cache` | path | Cache directory |
| `MODELS_PATH` | `/workspace/models` | path | Models directory |

### External Services

| Variable | Default | Type | Purpose |
|----------|---------|------|---------|
| `CMMS_URL` | `getenv("CMMS_API_URL")` | URL | CMMS (RZ) API endpoint |
| `HISTORICAL_DATA_STUB_ENABLED` | `false` | bool | Use synthetic data instead of real API |
| `SCADA_STUB_ENABLED` | `false` | bool | Use SCADA stub (legacy) |

### Python Runtime

| Variable | Default | Type | Purpose |
|----------|---------|------|---------|
| `PYTHONUNBUFFERED` | `1` | int | Disable Python output buffering |
| `PYTHONPATH` | `/workspace/server:/workspace/lib` | path | Module search |

---

## Docker Compose Workflows

### Start All Services

```bash
cd ml-server
docker-compose up -d
```

**Output:**
```
Creating redis (redis:7)
Creating mlflow (ghcr.io/mlflow/mlflow:latest)
Creating model-server (fpcloud/ml:1.0.0)
```

**Ready check:**
```bash
docker-compose ps
# All three services should show "Up X seconds"

curl http://localhost:8030/ui
# Should return HTML (if UI built)
```

### Stop All Services

```bash
docker-compose down
```

**With volume cleanup:**
```bash
docker-compose down -v
# ⚠️ Deletes all data (Redis, MLflow)
```

### Rebuild ml-server Image

```bash
docker-compose build model-server
docker-compose up -d model-server
```

### View Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f model-server
docker-compose logs -f redis
docker-compose logs -f mlflow
```

### Start in Test Mode

```bash
docker-compose -f docker-compose.yml \
  -e TEST_MODE=true \
  -e HISTORICAL_DATA_STUB_ENABLED=true \
  up -d
```

---

## Configuration Validation

### Check Runtime Config

```bash
# Inside ml-server container
curl http://localhost:8000/ui/model-config?model_id=prophet_watt_AKMOLA

# Output:
# {
#   "status": 200,
#   "raw_config": {...},
#   "normalized_config": {...}
# }
```

### Verify Broker Ready

```bash
# Inside ml-server container
redis-cli -h redis ping
# Expected: PONG

redis-cli -h redis XINFO STREAM predict
# Lists stream info (if tasks were enqueued)
```

### Check MLflow Registry

```bash
# From host
curl http://localhost:5050/api/2.0/mlflow/registered-models/list

# Output: JSON with registered models
```

---

## Performance Tuning

### TaskIQ Workers

```yaml
command: >
  bash -c "
    taskiq worker api.broker:broker --workers 8 &
    uvicorn api.server:app --host 0.0.0.0 --port 8000 &
    wait -n
  "
```

**`--workers 8`**: Number of concurrent worker processes
- **Adjust for:**
  - CPU cores available: `--workers $(nproc)`
  - Memory available: More workers → more memory
  - Task complexity: CPU-bound → more workers, I/O-bound → fewer workers

### Resource Limits

```yaml
deploy:
  resources:
    limits:
      cpus: '8'
      memory: 1024M
```

**Adjust for:**
- Available hardware
- Other containers on same host
- Peak prediction load

### Timeouts

```python
CLIENT_TIMEOUT_ONE = 30      # Per request to external API
CLIENT_TIMEOUT_ALL = 150     # Total timeout across retries
```

**Adjust for:**
- Network latency
- External service response time
- Expected prediction duration (typically 2–30 seconds)

---

## Multi-Instance Deployment

**Redis allows multiple API instances to share state:**

```yaml
api-1:
  image: fpcloud/ml:1.0.0
  ports:
    - "8031:8000"
  depends_on:
    - redis
    - mlflow

api-2:
  image: fpcloud/ml:1.0.0
  ports:
    - "8032:8000"
  depends_on:
    - redis
    - mlflow

redis:  # Shared across all api-N instances
  image: redis:7
  ports:
    - "6379:6379"
```

**Result sharing:**
- Client creates task on api-1 (returns task_id)
- Client polls on api-2 (retrieves result from Redis)
- Works seamlessly because Redis is distributed

---

## Stage 10 Contract

- ✅ Configuration externalized via environment variables
- ✅ Multiple runtime modes supported (production, test, development)
- ✅ Docker Compose defines complete infrastructure (api, Redis, MLflow)
- ✅ Volumes for persistence and hot-reload
- ✅ Health checks for service readiness
- ✅ Resource limits and performance tuning
- ✅ Multi-instance deployments supported

---

## Next Steps

**→ Stage 11**: Testing strategy, verification checklist, and smoke tests.
