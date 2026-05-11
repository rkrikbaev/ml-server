# WORKFLOW: Stage 9 — Error Handling & HTTP Response Contract

**Stage 9** documents the standardized error handling strategy across all stages, HTTP status codes, and the global response contract that ensures clients receive consistent, actionable error information.

---

## Problem Statement

The system has multiple failure points across Stages 1–7:
- **Stage 1**: Request validation (malformed JSON, missing fields)
- **Stage 3**: Config loading (model not found, invalid runtime parameters)
- **Stage 4**: Data collection (external API failures: historical data, weather, CMMS)
- **Stage 5**: Inference (model execution errors, numerical instability)
- **Stage 6**: Post-processing (quality checks fail)
- **Global**: Infrastructure issues (MLflow unreachable, Redis down)

All errors must be:
1. **Caught explicitly** (no unhandled exceptions bubble up)
2. **Logged** (for debugging and monitoring)
3. **Mapped to HTTP status** (200, 202, 422, 500, 503)
4. **Serialized consistently** (same JSON structure for all errors)

---

## HTTP Status Code Strategy

### HTTP 200 (Success) — Stage 6 Outcome

Used exclusively for **successful prediction completion**, regardless of data quality.

```json
{
  "status": 200,
  "state": "done",
  "task_id": "9f1c72b1...",
  "data": {
    "message": "Forecast completed successfully",
    "output": [...],
    "quality": 95,
    "model_confidence": 0.87,
    "planned_adjustments_applied": 0,
    "input_statistics": {...},
    "output_statistics": {...},
    "object_reference": "AKMOLA/KSTS/01"
  }
}
```

**Condition:** Stages 3–6 all executed without fatal errors.

### HTTP 202 (Accepted) — Task Queued

Used in the **two-phase async workflow**:

**Initial request (Stage 2):**
```json
{
  "status": 202,
  "state": "start",
  "task_id": "9f1c72b1...",
  "object_reference": "AKMOLA/KSTS/01"
}
```

**Polling while processing (Stage 7):**
```json
{
  "status": 202,
  "state": "processing",
  "task_id": "9f1c72b1..."
}
```

**Condition:** Request accepted by broker; result not yet available.

### HTTP 404 (Not Found)

**Case 1: API endpoint not found**

```json
{
  "status": 404,
  "message": "API not found"
}
```

[`src/api/server.py:37–39`](src/api/server.py#L37):

```python
@app.exception_handler(404)
def not_found_exception_handler(_request: Request, _exc: HTTPException):
    return messages.to_json_response(messages.not_found())
```

**Case 2: Model config missing (polled via `/ui/model-config`)**

```json
{
  "status": 404,
  "message": "Model config not found: /workspace/models/invalid_id/config.json",
  "model_id": "invalid_id"
}
```

[`src/api/server.py:70–103`](src/api/server.py#L70):

```python
config_path = models_base_path / model_id / "config.json"
if not config_path.is_file():
    content = {
        "status": 404,
        "message": f"Model config not found: {config_path}",
        "model_id": model_id,
    }
    return JSONResponse(content=content, status_code=404)
```

### HTTP 422 (Unprocessable Entity)

Used when **input validation fails** or **non-fatal processing errors occur**. The system attempted to handle the request but encountered a condition that prevents completion.

#### 422a: Request Validation Errors (Stage 1)

[`src/api/server.py:44–56`](src/api/server.py#L44):

```python
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
    details = {}
    for item in exc.errors():
        field = item["loc"]
        if field[2] in fields.setdefault(field[1], []):
            details.setdefault(field[1], []).append(f"'{field[2]}' : {item["msg"]}")
    
    return messages.to_json_response(messages.unprocessable_entity(details))
```

**Example 1: Missing required field**

```http
POST /predict
Content-Type: application/json

{
  "model_id": "prophet_watt_AKMOLA"
  // object_reference is missing!
}
```

**Response (HTTP 422):**
```json
{
  "status": 422,
  "message": "A valid JSON format was expected, but the data was not received or was invalid.",
  "details": {
    "body": ["'object_reference' : field required"]
  }
}
```

**Example 2: Invalid field value**

```http
POST /predict
Content-Type: application/json

{
  "model_id": "",  // Empty string!
  "object_reference": "AKMOLA/KSTS/01"
}
```

**Response (HTTP 422):**
```json
{
  "status": 422,
  "message": "A valid JSON format was expected, but the data was not received or was invalid.",
  "details": {
    "body": ["'model_id' : ensure this value has at least 1 characters"]
  }
}
```

#### 422b: Model Config Not Found (Stage 3)

[`src/api/message.py:118`](src/api/message.py#L118):

**Triggered in Stage 3 when** `load_model_config()` fails:

```json
{
  "status": 422,
  "message": "Model launch aborted: config.json not found for model 'prophet_watt_AKMOLA'."
}
```

#### 422c: No Historical Data (Stage 4)

[`src/api/message.py:120`](src/api/message.py#L120):

**Triggered in Stage 4 when** historical data collection returns empty or error:

```json
{
  "status": 422,
  "message": "Model launch aborted: no input data received from archives."
}
```

#### 422d: Poor Data Quality (Stage 4)

[`src/api/message.py:111`](src/api/message.py#L111):

**Triggered in Stage 4/6 when** QDS (input quality score) falls below threshold:

```json
{
  "status": 422,
  "message": "Incorrect data in the dataset from archives.",
  "quality": 35
}
```

#### 422e: Weather Data Invalid (Stage 4)

[`src/api/message.py:114`](src/api/message.py#L114):

```json
{
  "status": 422,
  "message": "Incorrect data in the dataset from weather service.",
  "details": "Weather service returned HTTP 503"
}
```

#### 422f: Forecast Execution Error (Stage 5)

[`src/api/message.py:111`](src/api/message.py#L111):

**Triggered in Stage 5 when** model adapter raises exception:

```json
{
  "status": 422,
  "message": "Forecast execution error: NaN detected in Prophet output"
}
```

### HTTP 500 (Internal Server Error)

**Unexpected system failures** that cannot be handled gracefully.

[`src/api/message.py:125`](src/api/message.py#L125):

```json
{
  "status": 500,
  "message": "Internal server error: Redis connection lost"
}
```

**Scenarios:**
- Unhandled exception in worker task
- Result backend crash
- Unexpected data type or structure corruption

**In practice:** Rare; most errors are caught and mapped to 422 or 503.

### HTTP 503 (Service Unavailable)

**External infrastructure dependencies are unreachable**. The system is temporarily unable to process requests.

#### 503a: Historical Data Service Down

[`src/api/message.py:132`](src/api/message.py#L132):

```json
{
  "status": 503,
  "message": "HISTORICAL_DATA is not available, so it is impossible to take values at this time.",
  "details": "Connection timeout after 30s"
}
```

**Triggered in Stage 4 when:**
- All HISTORICAL_DATA API hosts unreachable
- Connection timeout > CLIENT_TIMEOUT_ONE

#### 503b: Weather Service Down

[`src/api/message.py:128`](src/api/message.py#L128):

```json
{
  "status": 503,
  "message": "WEATHER is not available, so it is impossible to take values at this time.",
  "details": "HTTP 503 from weather API"
}
```

#### 503c: CMMS Service Down

[`src/api/message.py:138`](src/api/message.py#L138):

```json
{
  "status": 503,
  "message": "RZ is not available, so it is impossible to take values at this time."
}
```

#### 503d: MLflow Registry Unreachable

[`src/api/message.py:140`](src/api/message.py#L140):

```json
{
  "status": 503,
  "message": "MLFLOW is not available, so it is impossible to take values at this time.",
  "details": "Failed to sync model bundle from registry"
}
```

**Triggered in Stage 3 when:**
- MLflow server unreachable (Stage 3 model sync fails)
- Model bundle cannot be downloaded to cache

---

## Error Flow Across Stages

```
Request
  ↓
Stage 1 (Request parsing)
  ├─→ JSON invalid → 422 (details)
  ├─→ Field validation fails → 422 (details)
  └─→ ✓ Continue to Stage 2

Stage 2 (Enqueue)
  ├─→ Broker.kiq() fails → 500 (or 503 if Redis down)
  └─→ ✓ HTTP 202 START, return task_id

Stage 3 (Worker init)
  ├─→ Model config not found → 422 (or async handled as task failure)
  ├─→ MLflow unreachable → 503 (or retry with fallback)
  └─→ ✓ Continue to Stage 4

Stage 4 (Data collection)
  ├─→ Historical data empty → 422 (no input)
  ├─→ Historical data timeout → 503 (HISTORICAL_DATA unavailable)
  ├─→ Weather API down (optional) → skip, no 422/503
  ├─→ CMMS API down (optional) → skip, no 422/503
  └─→ ✓ Continue to Stage 5 with available data

Stage 5 (Inference)
  ├─→ Model adapter crash → 422 (forecast error)
  ├─→ Numerical error (NaN/Inf) → 422 (forecast error)
  └─→ ✓ Continue to Stage 6 with predictions

Stage 6 (Post-processing)
  ├─→ QDS too low → 422 (data quality) or 200 with quality flag
  ├─→ Exception in apply_planned_adjustments → 422 (forecast error)
  └─→ ✓ HTTP 200 DONE, return result

Stage 7 (Polling)
  └─→ Result backend returns error from Stage 3-6 → HTTP status from Stage 6
```

---

## Global Message Template

All response bodies follow this structure:

```json
{
  "status": <int>,              // HTTP status code (200, 202, 422, 500, 503)
  "state": "<string>",          // "start", "processing", "done" (Stage 2, 7)
  "task_id": "<uuid>",          // Stage 2 onwards
  "message": "<string>",        // Human-readable error/success message
  "data": {...},                // Only if status == 200
  "details": {...},             // Optional: nested error details or metadata
  "quality": <int>              // Optional: input quality score (Stage 4, 6)
}
```

---

## Error Handling Best Practices

### 1. Try-Catch at Stage Boundaries

**Stage 3 (Worker)** wraps entire logic:

```python
try:
    config = load_model_config(model_id)
    historical_payload = await _get_historical_data_payload(...)
    weather_payload = await _get_weather_payload(...)
    predictions = await predict(...)
    result = _build_result(...)
    return messages.ok_done(result)
except Exception as e:
    logger.error(f"Forecast failed: {e}")
    return messages.internal_server_error(str(e))
```

### 2. Non-Fatal Errors Degrade Gracefully

**Stage 4 (Data Collection):**

```python
# Weather is optional; failure should not abort workflow
try:
    weather_payload = await _get_weather_payload(...)
except Exception:
    logger.warning("Weather data unavailable; proceeding without it")
    weather_payload = None  # Predict will work with just historical

# But CMMS can also be skipped
if request_overrides.get("skip_cmms"):
    cmms_payload = None
else:
    try:
        cmms_payload = await _get_planned_adjustments(...)
    except Exception:
        logger.warning("CMMS data unavailable; no planned adjustments")
        cmms_payload = None
```

### 3. Distinguish Client Errors from Server Errors

| Category | Status | Meaning | Client Action |
|----------|--------|---------|---|
| **Client Error** | 422 | Request malformed or input data invalid | Fix request and retry |
| **Server Error** | 500 | Unexpected exception in processing | Retry with exponential backoff |
| **Service Down** | 503 | External dependency unreachable | Retry later (minutes/hours) |

### 4. Always Return JSON

No raw exceptions, stack traces, or HTML error pages:

```python
# ❌ WRONG
raise ValueError("Config not found")

# ✅ CORRECT
return messages.model_config_not_found(model_id)
# → {"status": 422, "message": "Model launch aborted: config.json not found..."}
```

---

## Testing Error Paths

### Test 422 (Validation)

```bash
curl -X POST http://localhost:8030/predict \
  -H "Content-Type: application/json" \
  -d '{
    "model_id": ""  # Too short
  }'
# Expected: HTTP 422 with details.body
```

### Test 422 (No Data)

```bash
curl -X POST http://localhost:8030/predict \
  -H "Content-Type: application/json" \
  -d '{
    "model_id": "prophet_watt_AKMOLA",
    "object_reference": "INVALID/PATH"  # Not in archives
  }'
# Expected: HTTP 202 START, then 422 DONE (no data)
```

### Test 503 (Service Down)

```bash
# Stop Redis
docker-compose pause redis

# Try to enqueue
curl -X POST http://localhost:8030/predict ...
# Expected: HTTP 500 or 503 (depends on when failure occurs)
```

---

## Stage 9 Contract

- ✅ All errors caught and mapped to HTTP status (200, 202, 422, 500, 503)
- ✅ Global response structure: `status`, `state`, `message`, `task_id`, `data`
- ✅ Consistent error serialization via `HTTPMessages` class
- ✅ Non-fatal errors (weather, CMMS) degrade gracefully
- ✅ Fatal errors (historical data, config) fail workflow with 422/503
- ✅ Infrastructure errors (Redis, MLflow) return 503 or 500
- ✅ All error scenarios testable and reproducible
- ✅ No unhandled exceptions bubble to client

---

## Next Steps

**→ Stage 10**: Configuration and deployment environment (Docker Compose, environment variables).

**→ Stage 11**: Testing strategy and verification checklist.
