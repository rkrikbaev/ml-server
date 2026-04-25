# API Contract: Current `/predict` Behavior

**Date:** 21.04.2026  
**Status:** ✅ Matches current codebase  
  "message": "HISTORICAL_DATA is not available, so it is impossible to take values ​​at this time. Error: ...",

---

## Summary

The current `/predict` API is a **two-step asynchronous task contract**.

The client does **not** receive the forecast in the first request. Instead:

1. SCADA sends a prediction creation request.
2. The server returns `202 Accepted` with a `task_id`.
3. SCADA polls `/predict` with that `task_id`.
4. The server returns either `202 processing` or the final `200/422/500/503` result.

The server loads inference settings from a local `config.json` in the model directory, not from MLflow.

---

## Request Contract

### 1. Create Prediction Task

```json
POST /predict
{
  "object_reference": "/KAZ/AKMOLA/@models/P_WATT",
  "model_id": "prophet/watt/h/AKMOLA/@regions/Akmola/load"
}
```

### Field Notes

- `object_reference` is required.
- `model_id` is required and must be non-empty.
- `model_id: "none"` is supported and means online mode.
- `horizon`, `step`, `output_range`, `archives`, and optional weather settings are loaded from model `config.json`.

### 2. Poll Prediction Task

```json
POST /predict
{
  "task_id": "8f52f2d9-2b8c-4f93-95d9-4f7d73a1e1aa"
}
```

---

## Response Contract

### A. Task Accepted

Returned on the first request.

```json
HTTP 202 Accepted
{
  "status": 202,
  "task_id": "8f52f2d9-2b8c-4f93-95d9-4f7d73a1e1aa",
  "object_reference": "/KAZ/AKMOLA/@models/P_WATT",
  "state": "start"
}
```

### B. Task Still Processing

Returned while polling before the task completes.

```json
HTTP 202 Accepted
{
  "status": 202,
  "task_id": "8f52f2d9-2b8c-4f93-95d9-4f7d73a1e1aa",
  "state": "processing"
}
```

### C. Task Completed Successfully

```json
HTTP 200 OK
{
  "status": 200,
  "data": {
    "message": "",
    "output": [
      [1713628800000, 1245.3, 0],
      [1713632400000, 1298.7, 0]
    ],
    "quality": 0,
    "model_confidence": 1.0
  },
  "object_reference": "/KAZ/AKMOLA/@models/P_WATT",
  "task_id": "8f52f2d9-2b8c-4f93-95d9-4f7d73a1e1aa",
  "state": "done"
}
```

### Output Field Semantics

- `output` is an array of triples: `[timestamp_ms, value_or_null, qds]`
- `quality` is the final output quality descriptor
- `model_confidence` is currently always `1.0`
- `message` is empty on success and contains a reason when the task degrades or fails logically

### D. Validation Error

```json
HTTP 422 Unprocessable Entity
{
  "status": 422,
  "message": "A valid JSON format was expected, but the data was not received or was invalid.",
  "details": {
    "body": [
      "'object_reference' : Field required"
    ]
  }
}
```

### E. Model Config Missing

```json
HTTP 422 Unprocessable Entity
{
  "status": 422,
  "message": "Model launch aborted: config.json not found for model 'prophet/watt/h/AKMOLA/@regions/Akmola/load'.",
  "task_id": "8f52f2d9-2b8c-4f93-95d9-4f7d73a1e1aa",
  "state": "done"
}
```

### F. External Source Unavailable

#### SCADA unavailable

```json
HTTP 503 Service Unavailable
{
  "status": 503,
  "message": "HISTORICAL_DATA is not available, so it is impossible to take values ​​at this time. Error: ...",
  "task_id": "8f52f2d9-2b8c-4f93-95d9-4f7d73a1e1aa",
  "state": "done"
}
```

#### Weather is optional

Weather fetch failures currently do **not** fail the whole prediction task. The pipeline continues without weather data.

### G. Internal Server Error

```json
HTTP 500 Internal Server Error
{
  "status": 500,
  "message": "Internal server error: ...",
  "task_id": "8f52f2d9-2b8c-4f93-95d9-4f7d73a1e1aa",
  "state": "done"
}
```

---

## Data Flow Used by Current Code

### Step 1. Request Validation

The request is validated by Pydantic discriminated schemas:

- create request: `object_reference`, `model_id`
- update request: `task_id`

Validation failures return `422`, not `400`.

### Step 2. Task Scheduling

The first `/predict` call enqueues `api_predict` in the broker and returns `202 start`.

### Step 3. Model Config Loading

The worker loads model settings from:

```text
${MODELS_PATH:-/workspace/models}/{model_id}/config.json
```

Current supported model config format:

```json
{
  "short": {
    "input_range": 72,
    "output_range": 24,
    "step": 3600,
    "sources": [
      {
        "type": "historical_data",
        "pattern": "historic",
        "url": "http://127.0.0.1:7080/api/v1/read/archives",
        "request_body": {
          "archive": ["/root/FP/.../archives/out_value"],
          "step": 3600
        }
      },
      {
        "type": "weather",
        "pattern": "future",
        "url": "http://127.0.0.1:8050/api/v1/forecast",
        "request_body": {
          "measurements": ["pressure", "temperature"]
        },
        "location": {
          "latitude": 51.1605,
          "longitude": 71.4704
        }
      },
      {
        "type": "cmms",
        "pattern": "planned",
        "url": "http://localhost:8000/api/v1/cmms",
        "request_body": {
          "state": "operational",
          "type": "generator"
        }
      }
    ]
  }
}
```

Runtime normalization currently works as follows:

- `historic` sources use `input_range`
- `future` and `planned` sources use `output_range`
- historical_data supports per-model `url` and `request_body`
- weather supports per-model `url`, `location`, and derived `weather_hours`
- CMMS config is normalized and applied in runtime postprocessing for planned reductions

### Step 4. Input Collection

#### Primary history source

Historical load data is requested from the historical-data collector:

- request payload always contains `archive` and `step`
- if explicit `from`/`to` are present in source overrides, they are used as-is
- otherwise the worker derives `from`/`to` from the normalized window size:
  - `pattern = historic` → use `input_range`
  - `pattern = future|planned` → use `output_range`
- response is validated and converted into model-ready arrays

#### Weather source

If `weather_lat` and `weather_lon` are present in `config.json`, the worker fetches weather forecast data using the weather client.

Current behavior:

- weather is fetched through `WeatherClientAsync.get_forecast(...)`
- weather payload is passed into prediction metadata
- weather is currently **optional** and **non-fatal**
- weather is **not yet transformed into explicit model features** in the current pipeline

#### CMMS

CMMS planned data is used in runtime postprocessing.

Request to CMMS (worker side):

```json
{
  "from": 1776880800000,
  "to": 1776963600000,
  "step": 3600,
  "type": "0704011504"
}
```

Expected CMMS response:

```json
{
  "0704011504": [
    {
      "p_station": 1688,
      "p_descent": 325,
      "start_requested": 1771095600000,
      "end_requested": 1778871540000
    }
  ]
}
```

Runtime conversion rules:

- request window is built for planned horizon (`output_range`) with `step` in seconds
- worker quantizes timestamps in `[from, to]` by `step`
- for each quantized timestamp, reduction is sum of `p_descent` for active maintenance windows
- activity window check: `start_requested <= ts <= end_requested`
- resulting per-timestamp reductions are subtracted from base forecast by exact timestamp match

### Step 5. Prediction

The server calls the current forecast adapter pipeline with:

- historical-data timestamps and values
- `step`
- `output_range`
- `online`
- optional payloads in metadata

### Step 6. Result Building

The worker converts predictions into:

```json
[
  [timestamp_ms, value_or_null, qds]
]
```

Then wraps them into:

```json
{
  "message": "",
  "output": [...],
  "quality": 0,
  "model_confidence": 1.0,
  "planned_adjustments_applied": 3
}
```

The broker appends `object_reference`, and the API layer appends `task_id` and `state`.

---

## Differences From Older Documentation

The following statements are **not true for the current implementation**:

- `/predict` is not a single synchronous request/response endpoint
- MLflow is not used for active model lookup in the running pipeline
- `run_id` is not returned
- `horizon` is not returned as a first-class response field
- `forecast` is not returned as an array of objects; the current field is `data.output`
- external APIs are not orchestrated through `data_source_config`

---

## Validation Scenarios

### Valid create request

```json
{
  "object_reference": "/KAZ/AKMOLA/@models/P_WATT",
  "model_id": "prophet/watt/h/AKMOLA/@regions/Akmola/load"
}
```

Expected:

- `202 Accepted`
- `task_id` returned
- `state = start`

### Valid poll request before completion

```json
{
  "task_id": "8f52f2d9-2b8c-4f93-95d9-4f7d73a1e1aa"
}
```

Expected:

- `202 Accepted`
- `state = processing`

### Valid poll request after completion

Expected:

- `200 OK`
- `state = done`
- final payload under `data`

### Missing `object_reference`

Expected:

- `422 Unprocessable Entity`

### Unknown model config path

Expected:

- `422 Unprocessable Entity`
- `config.json not found` message

---

## SCADA Integration Notes

- SCADA must support the two-step async contract
- SCADA should persist `task_id` between the create request and polling
- SCADA should read the final forecast from `data.output`

---

## Current Source of Truth

This document reflects the behavior implemented in:

- `src/api/server.py`
- `src/api/data/predict.py`
- `src/api/broker/broker.py`
- `src/api/broker/tasks/predict.py`
- `src/api/forecast/config.py`
- `src/api/collector/historical_client.py`
- `src/api/collector/weather_client.py`

---

**Document Version:** 2.0  
**Last Updated:** 21.04.2026  
**Maintained By:** ML Infrastructure Team
