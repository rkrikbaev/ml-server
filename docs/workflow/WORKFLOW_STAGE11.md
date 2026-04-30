# WORKFLOW: Stage 11 — Testing Strategy & Verification Checklist

**Stage 11** documents the comprehensive testing strategy for the ml-server, covering unit tests, integration tests, smoke tests, and verification procedures for all stages of the pipeline.

---

## Problem Statement

After implementing all stages (0–10), the system must be **verified** to ensure:
1. **Individual components work** (unit tests for each stage)
2. **Components integrate** (integration tests across stages)
3. **End-to-end flow works** (smoke tests with real data)
4. **Error paths are handled** (negative tests, edge cases)
5. **Performance meets expectations** (load tests, timeout verification)

---

## Test Infrastructure

### Test Suite Layout

```
ml-server/
├── tests/
│   ├── __init__.py
│   ├── fixtures/              # Test data
│   │   └── test_data/
│   ├── test_cleaning.py       # Data validation
│   ├── test_evaluate.py       # Quality assessment
│   ├── test_features.py       # Feature engineering
│   ├── test_predict_smoke.py  # Positive end-to-end
│   └── test_predict_negative_smoke.py  # Negative end-to-end
└── Makefile                   # Test commands
```

### Test Frameworks

- **pytest** — Test runner and assertion framework
- **Docker Compose** — Infrastructure (Redis, MLflow)
- **bash/curl** — API integration tests

---

## Test Levels

### Level 1: Unit Tests (Individual Stage)

**What to test:** Single function/class in isolation

**Example: Stage 4 — Historical Data Collection**

```python
# tests/test_features.py (simplified)
def test_count_input_qds():
    """Test QDS calculation"""
    data = [1.0, 2.0, 3.0, np.nan, 5.0]  # 4/5 valid = 80%
    qds = count_input_qds(data)
    assert qds == 80

def test_count_input_qds_empty():
    """Test QDS with all NaN"""
    data = [np.nan, np.nan, np.nan]
    qds = count_input_qds(data)
    assert qds == 0

def test_count_input_qds_all_valid():
    """Test QDS with no missing values"""
    data = [1.0, 2.0, 3.0, 4.0, 5.0]
    qds = count_input_qds(data)
    assert qds == 100
```

**Run:**
```bash
pytest tests/test_features.py::test_count_input_qds -v
```

### Level 2: Integration Tests (Stage-to-Stage Handoff)

**What to test:** Data flows correctly between stages

**Example: Stage 3 → Stage 4 handoff (config → data collection)**

```python
# Pseudocode
def test_config_to_data_collection():
    """Verify Stage 3 config output feeds Stage 4 correctly"""
    
    # Stage 3 output
    config = load_model_config("prophet_watt_AKMOLA")
    assert config.model_type == "prophet"
    assert config.step == 3600
    assert config.input_range == 168
    
    # Stage 4 input validation
    payload = build_historical_data_request(config)
    assert payload["from_ts"] is not None
    assert payload["to_ts"] is not None
    assert payload["step"] == 3600
```

**Run:**
```bash
pytest tests/test_evaluate.py -v
```

### Level 3: Smoke Tests (End-to-End Flow)

**What to test:** Entire workflow from request to result

#### 3a: Positive Smoke Test (Happy Path)

[`tests/test_predict_smoke.py`](tests/test_predict_smoke.py):

**Setup:**
```bash
make setup-test                           # Prepare models and fixtures
docker-compose up -d                      # Start Redis, MLflow, api
export SCADA_STUB_ENABLED=true            # Enable synthetic data
make wait-api                              # Wait for readiness
```

**Test workflow:**

```python
def test_predict_two_phase_flow():
    """Test complete Stage 1-7 workflow"""
    
    # Stage 1-2: Create task
    response_init = requests.post(
        "http://localhost:8030/predict",
        json={
            "model_id": "prophet_watt_AKMOLA",
            "object_reference": "AKMOLA/KSTS/01"
        }
    )
    
    # Verify Stage 2 response
    assert response_init.status_code == 202
    data_init = response_init.json()
    assert data_init["state"] == "start"
    task_id = data_init["task_id"]
    
    # Stage 3-6: Execute in background (worker processes)
    
    # Stage 7: Poll for result
    for attempt in range(60):
        response_poll = requests.post(
            "http://localhost:8030/predict",
            json={"task_id": task_id}
        )
        
        if response_poll.status_code == 200:
            # Result ready (Stage 6 success)
            data_result = response_poll.json()
            assert data_result["state"] == "done"
            assert "data" in data_result
            assert "output" in data_result["data"]
            assert "quality" in data_result["data"]
            return  # ✅ Success
        
        assert response_poll.status_code == 202
        assert response_poll.json()["state"] == "processing"
        time.sleep(1)
    
    pytest.fail("Task did not complete in 60 seconds")
```

**Run:**
```bash
make smoke-positive
```

**Expected output:**
```
tests/test_predict_smoke.py::test_predict_two_phase_flow PASSED [100%]
✓ Happy path verified (Stage 1-7 complete)
```

#### 3b: Negative Smoke Test (Error Path)

[`tests/test_predict_negative_smoke.py`](tests/test_predict_negative_smoke.py):

**Setup:**
```bash
export SCADA_STUB_ENABLED=false           # Use real (unavailable) data service
```

**Test scenarios:**

```python
def test_predict_no_data():
    """Stage 4 fails due to no historical data → HTTP 422"""
    
    response_init = requests.post(
        "http://localhost:8030/predict",
        json={
            "model_id": "prophet_watt_AKMOLA",
            "object_reference": "INVALID/OBJECT"  # Not in archives
        }
    )
    
    assert response_init.status_code == 202
    task_id = response_init.json()["task_id"]
    
    # Poll until done
    for attempt in range(120):
        response_poll = requests.post(
            "http://localhost:8030/predict",
            json={"task_id": task_id}
        )
        
        if response_poll.status_code == 422:
            # Stage 4 failed (or 6 failed QDS check)
            assert "no input data" in response_poll.json()["message"].lower()
            return  # ✅ Correct error
        
        if response_poll.status_code == 200:
            # Fallback to synthetic data succeeded
            return  # ✓ Acceptable
        
        time.sleep(1)
    
    pytest.fail("Expected HTTP 422 or 200")

def test_predict_validation_error():
    """Stage 1 fails due to invalid input → HTTP 422"""
    
    response = requests.post(
        "http://localhost:8030/predict",
        json={
            "model_id": "",  # Invalid: empty string
            "object_reference": "AKMOLA/KSTS/01"
        }
    )
    
    assert response.status_code == 422
    assert "details" in response.json()
```

**Run:**
```bash
make smoke-negative
```

---

## Test Commands (Makefile)

### Quick Start

```bash
make help
# Shows all available test commands
```

### Test Setup

```bash
make setup-test
# Prepares:
# - Test environment directory structure
# - Fixture models in ../local/mlruns/
# - Test data in tests/fixtures/
```

### Clean Artifacts

```bash
make clean-test
# Removes:
# - mlflow.db (test MLflow database)
# - mlflow_artifacts/ (cached models)
# - logs/ (test logs)
# - tests/fixtures/test_data/* (fixture data)
```

### Run All Unit Tests

```bash
make test
# Runs: pytest tests/ -v (excluding smoke tests)
# Duration: ~10 seconds
```

### Positive End-to-End

```bash
make smoke-positive
# 1. Recreates model-server with SCADA_STUB_ENABLED=true
# 2. Waits for API readiness
# 3. Runs positive smoke test (happy path)
# Duration: ~30 seconds
```

### Negative End-to-End

```bash
make smoke-negative
# 1. Recreates model-server with SCADA_STUB_ENABLED=false
# 2. Waits for API readiness
# 3. Runs negative smoke test (no data, error paths)
# Duration: ~120+ seconds (due to timeouts)
```

### Full Prediction Flow (Custom Model)

```bash
# Test with specific model
make test-predict PREDICT_MODEL_ID=xgb

# Variables:
# - PREDICT_MODEL_ID: Model to test (default: prophet_watt_h_AKMOLA_test)
# - PREDICT_OBJECT_REFERENCE: SCADA object to predict (auto-read from config)
# - PREDICT_URL: API endpoint (default: http://localhost:8030/predict)
# - PREDICT_MAX_ATTEMPTS: Max polling attempts (default: 30)
# - PREDICT_POLL_INTERVAL: Delay between polls (default: 1 second)

# Run it:
make test-predict PREDICT_MODEL_ID=xgb
# Expected: HTTP 202 START → 202 PROCESSING → 200 DONE
```

### Check API Status

```bash
make smoke-api
# Tests: GET /ui/runtime-status
# Outputs: CPU load, memory usage
```

### View Logs

```bash
make logs
# Shows recent container logs from model-server, redis, mlflow
```

---

## Verification Checklist

### Pre-Deployment (Stage 0)

- [ ] Redis container starts and passes healthcheck
- [ ] MLflow container starts and UI accessible at port 5050
- [ ] ml-server container starts with 8 worker processes
- [ ] FastAPI server listening on port 8000 (or mapped 8030)

**Verify:**
```bash
docker-compose ps
# All three containers should be "Up"

docker-compose logs model-server | grep "Uvicorn running"
docker-compose logs model-server | grep "taskiq worker started"
```

### Stage 1 (Request Parsing)

- [ ] Invalid JSON rejected with HTTP 422
- [ ] Missing required fields rejected with HTTP 422
- [ ] Invalid field values rejected with HTTP 422
- [ ] Valid create request accepted (HTTP 202)

**Verify:**
```bash
# ❌ Invalid JSON
curl -X POST http://localhost:8030/predict \
  -H "Content-Type: application/json" \
  -d '{invalid json}'
# Expected: HTTP 422

# ✅ Valid create
curl -X POST http://localhost:8030/predict \
  -H "Content-Type: application/json" \
  -d '{
    "model_id": "prophet_watt_AKMOLA",
    "object_reference": "AKMOLA/KSTS/01"
  }'
# Expected: HTTP 202 + task_id
```

### Stage 2 (Enqueue)

- [ ] Task enqueued in Redis queue
- [ ] Task ID returned to client
- [ ] Task recorded in task monitor

**Verify:**
```bash
# Check Redis queue
docker-compose exec redis redis-cli \
  XLEN predict
# Should increment after each POST

# Check task monitor
curl http://localhost:8030/ui/tasks
# Should list recent tasks
```

### Stage 3 (Worker Init)

- [ ] Model config loaded correctly
- [ ] MLflow model bundle synced to cache
- [ ] Worker process starts execution

**Verify:**
```bash
# Model config accessible
curl "http://localhost:8030/ui/model-config?model_id=prophet_watt_AKMOLA"
# Expected: HTTP 200 + raw_config + normalized_config

# Cache exists
ls -la /tmp/mlserver_registry_cache/
# Should contain model bundle directories
```

### Stage 4 (Data Collection)

- [ ] Historical data fetched (or stub provided)
- [ ] Weather data optional (skip if unavailable)
- [ ] CMMS data optional (skip if unavailable)
- [ ] QDS calculated

**Verify:**
```bash
# Run prediction with debug logging
docker-compose logs -f model-server | grep "Historical"
# Should see: "Fetching historical data..." or "Using SCADA stub"
```

### Stage 5 (Inference)

- [ ] Model adapter initialized
- [ ] Prediction generated
- [ ] Timestamps built correctly

**Verify:**
```bash
# Run prediction and check result
make test-predict PREDICT_MODEL_ID=prophet_watt_AKMOLA
# Look for "output" array in final result
```

### Stage 6 (Post-Processing)

- [ ] CMMS adjustments applied (if available)
- [ ] QDS threshold checked
- [ ] Result payload built correctly
- [ ] HTTP status determined

**Verify:**
```bash
# Check final result structure
curl -s http://localhost:8030/ui/tasks | jq '.items[0].result'
# Should match expected schema:
# {
#   "status": 200,
#   "data": {
#     "output": [...],
#     "quality": 95,
#     "planned_adjustments_applied": 0
#   }
# }
```

### Stage 7 (Polling)

- [ ] First poll returns HTTP 202 PROCESSING (if not ready)
- [ ] Result available within timeout
- [ ] Final poll returns HTTP 200 DONE
- [ ] State transitions: start → processing → done

**Verify:**
```bash
# Manual polling sequence
TASK_ID=$(curl -s -X POST http://localhost:8030/predict \
  -H "Content-Type: application/json" \
  -d '{...}' | jq -r '.task_id')

# Poll 1 (immediate)
curl -X POST http://localhost:8030/predict \
  -H "Content-Type: application/json" \
  -d "{\"task_id\": \"$TASK_ID\"}" | jq '.status, .state'
# Expected: 202, "processing" (or 200 if very fast)

# Poll N (after 5 seconds)
sleep 5
curl -X POST http://localhost:8030/predict \
  -H "Content-Type: application/json" \
  -d "{\"task_id\": \"$TASK_ID\"}" | jq '.status, .state'
# Expected: 200, "done"
```

### Stage 8 (Monitoring)

- [ ] Task list endpoint returns tasks
- [ ] Task detail endpoint works
- [ ] Model list shows all models
- [ ] Model metrics calculated (success_rate, avg_runtime)
- [ ] Runtime status endpoint returns CPU/memory

**Verify:**
```bash
curl http://localhost:8030/ui/tasks?page=1&page_size=10 | jq '.total'
curl http://localhost:8030/ui/models | jq '.total'
curl http://localhost:8030/ui/runtime-status | jq '.cpu_load'
```

### Stage 9 (Error Handling)

- [ ] Validation errors → HTTP 422
- [ ] Missing data → HTTP 422
- [ ] Service unavailable → HTTP 503
- [ ] Unexpected errors → HTTP 500
- [ ] All errors have consistent JSON structure

**Verify:**
```bash
make test
# Runs all unit tests including error scenarios
```

### Stage 10 (Configuration)

- [ ] Environment variables read correctly
- [ ] Docker Compose services interconnect
- [ ] Model directory mounted correctly
- [ ] Model registry cache working
- [ ] Redis persistence across restarts

**Verify:**
```bash
docker-compose exec model-server python -c \
  "from api import config; print(f'REDIS_URL={config.REDIS_URL}')"

# Verify mount
docker-compose exec model-server ls /workspace/models

# Check cache
docker-compose exec model-server ls /tmp/mlserver_registry_cache
```

### End-to-End Flow

- [ ] Complete happy-path test passes
- [ ] Complete error-path test passes
- [ ] Model training reproducible
- [ ] Performance acceptable (< 30s per prediction)

**Verify:**
```bash
make smoke-positive && make smoke-negative
# Both should PASS
```

---

## Performance Benchmarks

| Operation | Expected Time | Threshold Alert |
|-----------|---------------|---|
| Enqueue task (Stage 2) | <100ms | >500ms |
| Load model config (Stage 3) | <200ms | >1s |
| Fetch historical data (Stage 4) | 2–10s | >30s |
| Fetch weather (Stage 4, optional) | <5s | >15s |
| Run inference (Stage 5) | 1–5s | >30s |
| Build result (Stage 6) | <100ms | >500ms |
| Total (Stages 3–6) | 5–25s | >60s |
| First poll response (Stage 7) | <50ms | >500ms |

---

## Stage 11 Contract

- ✅ Unit tests for individual components
- ✅ Integration tests for stage handoffs
- ✅ Positive smoke test (happy path) reproducible
- ✅ Negative smoke test (error paths) reproducible
- ✅ Test commands in Makefile (make test, make smoke-positive, etc.)
- ✅ Verification checklist for all stages
- ✅ Performance benchmarks documented
- ✅ All tests pass before deployment

---

## Next Steps

**→ Deployment:**
1. Run full test suite (`make test && make smoke-positive && make smoke-negative`)
2. Verify Stage 10 configuration for target environment
3. Deploy Docker Compose stack to production
4. Monitor Stage 8 endpoints for health and performance

**→ Maintenance:**
- Review Stage 8 metrics daily
- Archive old tasks (prevent _TASKS from exceeding 500 limit)
- Monitor Redis memory usage
- Periodically validate Stage 9 error paths
