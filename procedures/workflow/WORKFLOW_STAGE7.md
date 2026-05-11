# WORKFLOW: Stage 7 — Task Polling & Result Retrieval

**Stage 7** handles the asynchronous polling mechanism that allows clients to check prediction task status and retrieve results.

---

## Problem Statement

The prediction workflow is **asynchronous** via TaskIQ:
- Stage 3–6 execute in a background worker
- Clients need a way to **poll for completion** and **retrieve results**
- Results must persist **temporarily** in a result backend (Redis or in-memory)
- HTTP responses must distinguish between three states: **START** (initial), **PROCESSING** (in-flight), **DONE** (complete)

---

## Solution: Two-Phase Request Pattern

### Phase 1: Task Creation (Initial POST)

**Request Schema** ([`src/api/data/predict.py`](src/api/data/predict.py#L43)):
```python
class PredictCreateSchema(BaseModel):
    model_id: str = "none"
    object_reference: str
    model_selection: ModelSelectionSchema | None = None
```

**Client sends:**
```http
POST /predict
Content-Type: application/json

{
  "model_id": "prophet_watt_AKMOLA",
  "object_reference": "AKMOLA/KSTS/01",
  "model_selection": null
}
```

**Endpoint** ([`src/api/server.py:413–419`](src/api/server.py#L413)):
```python
if isinstance(data, PredictCreateSchema):  # 202: START
    task = await api_predict.kiq(data)
    record_task_created(task.task_id, data.object_reference, data.model_id)
    return messages.to_json_response(
        messages.accepted_start(task.task_id, data.object_reference),
        task.task_id,
        HTTPState.START
    )
```

**Response (HTTP 202):**
```json
{
  "status": 202,
  "state": "start",
  "task_id": "9f1c72b1-52d3-4c9a-8a6e-5e8f3b2c1a9d",
  "object_reference": "AKMOLA/KSTS/01"
}
```

**Key Details:**
- Returns **HTTP 202 Accepted** (task enqueued, not yet processed)
- Generates unique `task_id` via TaskIQ broker
- Records task creation in task monitor (`record_task_created()`)
- State = `"start"`

---

### Phase 2: Result Polling (Subsequent POST with `task_id`)

**Request Schema** ([`src/api/data/predict.py`](src/api/data/predict.py#L88)):
```python
class PredictUpdateSchema(BaseModel):
    task_id: str
```

**Client sends (repeating):**
```http
POST /predict
Content-Type: application/json

{
  "task_id": "9f1c72b1-52d3-4c9a-8a6e-5e8f3b2c1a9d"
}
```

**Endpoint** ([`src/api/server.py:422–410`](src/api/server.py#L422)):

#### a) Check if result is ready
```python
task_id = data.task_id
is_ready = await broker.result_backend.is_result_ready(task_id)
```

**Result Backend** ([`src/api/broker/broker.py:10–24`](src/api/broker/broker.py#L10)):

- **Production (default)**: Redis (`RedisAsyncResultBackend`)
  - Stores results in Redis with TTL = `REDIS_TIMEOUT` (typically 86400 seconds = 24 hours)
  - Supports distributed polling across multiple API instances
  
- **Test Mode**: In-memory dummy backend (`DummyResultBackend`)
  - Stores results in process memory
  - Suitable for single-instance testing

#### b) If NOT ready → HTTP 202 PROCESSING
```python
if not is_ready:  # 202: PROCESSING
    record_task_processing(task_id)
    return messages.to_json_response(
        messages.accepted_processing(task_id),
        task_id,
        HTTPState.PROCESSING
    )
```

**Response (HTTP 202):**
```json
{
  "status": 202,
  "state": "processing",
  "task_id": "9f1c72b1-52d3-4c9a-8a6e-5e8f3b2c1a9d"
}
```

**Key Details:**
- Task is still executing in background
- Client should **retry after a delay** (e.g., 1–5 seconds)
- Records processing state for analytics

#### c) If ready → HTTP 200/4xx/5xx DONE
```python
result = await broker.result_backend.get_result(task_id)
record_task_done(task_id, result.return_value)
return messages.to_json_response(result.return_value, task_id, HTTPState.DONE)
```

**Response scenarios:**

**Success (HTTP 200):**
```json
{
  "status": 200,
  "state": "done",
  "task_id": "9f1c72b1-52d3-4c9a-8a6e-5e8f3b2c1a9d",
  "data": {
    "message": "Forecast completed successfully",
    "output": [12.5, 13.2, 14.1, ...],
    "quality": 95,
    "model_confidence": 0.87,
    "planned_adjustments_applied": 2,
    "input_statistics": {...},
    "output_statistics": {...},
    "object_reference": "AKMOLA/KSTS/01"
  }
}
```

**Failure (HTTP 422 or 500):**
```json
{
  "status": 422,
  "state": "done",
  "task_id": "9f1c72b1-52d3-4c9a-8a6e-5e8f3b2c1a9d",
  "message": "Model launch aborted: no input data received from archives."
}
```

**Key Details:**
- Result retrieved from result backend (Redis or in-memory)
- Records task completion for analytics
- HTTP status code reflects Stage 6 outcome (200, 422, 500, etc.)
- State = `"done"`

---

## Request Discriminator Logic

**How does `/predict` know whether the request is CREATE or UPDATE?**

[`src/api/data/predict.py:97–114`](src/api/data/predict.py#L97):

```python
def predict_discriminator(v: Any) -> str:
    """Discriminator for prediction creation and update."""
    if isinstance(v, dict) and "task_id" in v:
        return TAG_PREDICT_UPDATE
    return TAG_PREDICT_CREATE

PredictSchema = Annotated[
    Annotated[PredictCreateSchema, Tag(TAG_PREDICT_CREATE)] | 
    Annotated[PredictUpdateSchema, Tag(TAG_PREDICT_UPDATE)],
    Discriminator(predict_discriminator)
]
```

**Rule:**
- If JSON has `"task_id"` field → `PredictUpdateSchema` (polling)
- Otherwise → `PredictCreateSchema` (new task)

---

## State Machine Diagram

```
CLIENT REQUEST
      ↓
   /predict endpoint
      ↓
   Discriminate request type
      ├─→ PredictCreateSchema (first call)
      │         ↓
      │   broker.kiq(task)  [enqueue in TaskIQ]
      │         ↓
      │   record_task_created()
      │         ↓
      │   HTTP 202 + task_id  [START state]
      │         ↓
      └─→ PredictUpdateSchema (polling calls)
                ↓
          is_result_ready(task_id)?
                ↓
          ┌─────┴─────┐
          │            │
        NO           YES
        ↓              ↓
    HTTP 202        get_result(task_id)
    [PROCESSING]    record_task_done()
                    ↓
                HTTP 200/4xx/5xx
                [DONE state]
                + result.return_value
```

---

## Task Lifecycle Timing

| Phase | Duration | Status | HTTP | State |
|-------|----------|--------|------|-------|
| Creation | ~0ms | Enqueued in TaskIQ | 202 | START |
| Execution | ~1–30s (Stages 3–6) | Running in worker | — | — |
| First Poll | ~0ms | Check result backend | 202 | PROCESSING |
| Subsequent Polls | ~0ms each | Check result backend | 202 | PROCESSING |
| Ready | ~0ms | Retrieve result | 200/4xx/5xx | DONE |
| TTL Expiry | +24h (Redis) | Result deleted | 404 (if polled) | — |

---

## Result Backend Configuration

### Production (Redis)

**Environment:**
- `REDIS_URL`: Connection string (e.g., `redis://redis:6379/0`)
- `REDIS_TIMEOUT`: Result TTL in seconds (default: 86400 = 24 hours)
- `USE_IN_MEMORY_BROKER`: Must be `false` or unset

**Flow:**
```python
# src/api/broker/broker.py:13-18
result_backend = RedisAsyncResultBackend(REDIS_URL, result_ex_time=REDIS_TIMEOUT)
broker = RedisStreamBroker(REDIS_URL).with_result_backend(result_backend)
```

**Characteristics:**
- Persistent across API restarts
- Supports multi-instance deployments (Docker compose)
- Results expire automatically via Redis TTL

### Test Mode (In-Memory)

**Environment:**
- `TEST_MODE`: `true`
- `USE_IN_MEMORY_BROKER`: Can be `true` (but typically `false` to use Redis anyway)

**Flow:**
```python
# src/api/broker/broker.py:19-21
result_backend = DummyResultBackend()
broker = InMemoryBroker().with_result_backend(result_backend)
```

**Characteristics:**
- No external dependencies (Redis not required)
- Results lost on daemon restart
- Single-instance only

---

## Client Polling Strategy

### Recommended Pattern

```python
import httpx
import time

async def poll_prediction(client: httpx.AsyncClient, task_id: str, max_retries=60, delay_sec=2) -> dict:
    """Poll until prediction is ready."""
    for attempt in range(max_retries):
        response = await client.post(
            "http://localhost:8001/predict",
            json={"task_id": task_id},
            timeout=10
        )
        
        data = response.json()
        
        if data.get("state") == "done":
            return data  # Ready
        
        if data.get("state") == "processing":
            print(f"Poll attempt {attempt+1}: still processing...")
            await asyncio.sleep(delay_sec)
            continue
        
        raise RuntimeError(f"Unexpected state: {data.get('state')}")
    
    raise TimeoutError(f"Task {task_id} did not complete after {max_retries * delay_sec} seconds")

# Usage
task_response = await client.post(
    "http://localhost:8001/predict",
    json={
        "model_id": "prophet_watt_AKMOLA",
        "object_reference": "AKMOLA/KSTS/01"
    }
)
task_id = task_response.json()["task_id"]

result = await poll_prediction(client, task_id)
print(f"Prediction: {result['data']['output']}")
```

### Key Points for Clients

1. **Start with CREATE request** → get `task_id`
2. **Poll periodically** with UPDATE requests (2–5 second delays typical)
3. **Watch for `state` field**:
   - `"start"` → task enqueued (rare to see, only on first response)
   - `"processing"` → still running, keep polling
   - `"done"` → ready, check `status` and `data` fields
4. **Handle errors** (422, 500, 503) → failures in Stages 3–6 bubble up here
5. **Respect TTL** → results expire after 24 hours, don't poll indefinitely

---

## Task Monitoring & Analytics

**Recorded Events:**

1. **Creation** ([`src/api/server.py:415`](src/api/server.py#L415)):
   ```python
   record_task_created(task.task_id, data.object_reference, data.model_id)
   ```
   - Stores task metadata (object_reference, model_id, created_at)

2. **Processing** ([`src/api/server.py:423`](src/api/server.py#L423)):
   ```python
   record_task_processing(task_id)
   ```
   - Records first poll while still executing

3. **Done** ([`src/api/server.py:410`](src/api/server.py#L410)):
   ```python
   record_task_done(task_id, result.return_value)
   ```
   - Stores result payload and completion status

**Accessed via UI endpoints:**
- `GET /ui/tasks` — List all tasks with filtering
- `GET /ui/tasks/{task_id}` — Detailed task info
- `GET /ui/models/{model_id}/runs` — Model-specific run history

---

## Error Handling

### Polling Errors

| Condition | HTTP | Message | Client Action |
|-----------|------|---------|----------------|
| Task valid, still executing | 202 | — | Retry after delay |
| Task valid, result ready (success) | 200 | — | Process result |
| Task valid, Stage 6 failed | 422/500 | Stage 6 error | Handle failure |
| Invalid `task_id` format | — | (depends on validation) | Check format |
| Result TTL expired (>24h old) | — | (depends on backend) | Regenerate prediction |

### Timeouts

- **Result backend timeout**: If Redis/in-memory is inaccessible, `broker.result_backend.get_result()` raises exception
- **HTTP request timeout**: Client should set timeout (recommended: 10–30 seconds per poll)

---

## Integration with Stages 3–6

**Pipeline Handoff:**
```
Stage 3 (Worker Init)
      ↓ [task_id generated]
Stage 4 (Data Collection)
      ↓ [task_id passed through]
Stage 5 (Inference)
      ↓ [task_id passed through]
Stage 6 (Post-Processing)
      ↓ [result generated via ok_done(), unprocessable_entity_*, internal_server_error()]
api_predict() returns result
      ↓
TaskIQ broker stores result in Redis/in-memory
      ↓
Stage 7 (Polling)
      ↓ [client polls with task_id]
broker.result_backend.get_result(task_id) retrieves stored result
```

**Result Payload Structure:**

When `result.return_value` is retrieved in Stage 7, it has the exact structure built by Stage 6:

```python
{
    "status": 200,  # or 422, 500, etc.
    "message": "Forecast completed successfully",
    "data": {  # if status == 200
        "output": [...],
        "quality": 95,
        "model_confidence": 0.87,
        "planned_adjustments_applied": 2,
        "input_statistics": {...},
        "output_statistics": {...},
        "object_reference": "AKMOLA/KSTS/01"
    }
}
```

---

## Summary

| Component | Code Location | Responsibility |
|-----------|----------------|-----------------|
| Request schemas | `src/api/data/predict.py` | Discriminate CREATE vs UPDATE |
| Endpoint handler | `src/api/server.py:412–410` | Route requests, manage state transitions |
| Result backend | `src/api/broker/broker.py` | Store/retrieve results (Redis or in-memory) |
| State enum | `src/api/message.py:8–28` | Track START/PROCESSING/DONE |
| Task monitor | `src/api/task_monitor.py` | Record task lifecycle for analytics |

**Stage 7 Contract:**
- ✅ Discriminate requests by presence of `task_id` field
- ✅ Enqueue tasks with TaskIQ broker on first POST
- ✅ Poll result backend on subsequent POSTs
- ✅ Return HTTP 202 while processing, HTTP 200/4xx/5xx when ready
- ✅ Store results with TTL in Redis or in-memory
- ✅ Record task events for analytics & debugging
