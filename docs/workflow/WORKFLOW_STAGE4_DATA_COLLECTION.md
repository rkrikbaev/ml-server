# WORKFLOW STAGE 4: Data Collection

## 1. Scope

This document describes how Stage4 collects input data for inference in the current runtime pipeline.

Source of truth:

- `src/api/broker/tasks/predict.py`
- `src/api/collector/historical_client.py`
- `src/api/collector/cmms_client.py`

Input contract from Stage3:

- `config` (`ModelConfig`) normalized from a single raw `cache_config.json` format with `sources`
- `step` (ms), `input_range` (points), `output_range` (points)
- `online`

## 2. Raw Config Shape (Single Format)

Stage4 relies on config values that come from this raw structure (loaded in Stage3):

```json
{
  "model_type": "xgb/prophet",
  "fallback": "none",
  "use_dynamic_normalization": false,
  "sources": {
    "step": 3600,
    "input_range": 168,
    "output_range": 24,
    "historical": {
      "pattern": "historic",
      "archives": ["/root/FP/.../archives/out_value"],
      "url": "http://host.docker.internal:7080/api/v1/read/archives",
      "request_overrides": {
        "archive": ["/root/FP/.../archives/out_value"]
      }
    },
    "weather": {
      "pattern": "forecast",
      "lat": null,
      "lon": null,
      "url": null,
      "units": "metric",
      "hours": null
    },
    "cmms": {
      "pattern": "planned",
      "url": null,
      "request_overrides": {}
    }
  }
}
```

After normalization, Stage4 uses these `ModelConfig` fields:

- `archives`, `historical_data_url`, `historical_data_request_overrides`
- `weather_lat`, `weather_lon`, `weather_url`, `weather_units`, `weather_hours`
- `cmms_url`, `cmms_request_overrides`

## 3. Stage4 Runtime Flow

### 3.1 Historical Data (required)

Worker call:

```python
output = await _get_historical_data_payload(config, step, input_range, output_range, online)
```

Client call:

```python
await get_historical_data_client().fetch_model_data(
    archives=config.archives,
    step=step,
    input_range=input_range,
    output_range=output_range,
    online=online,
    historical_data_url=config.historical_data_url,
    request_overrides=config.historical_data_request_overrides,
)
```

Window logic in `HistoricalDataClient.build_request(...)`:

- `to` = current UTC hour
- `from` = `to - history_points * step`
- `history_points = input_range` if `input_range > 0`, else `output_range`

Validation:

- `archives` must be non-empty
- `step > 0`
- `output_range > 0`

If historical data is unavailable:

- if `HISTORICAL_DATA_STUB_ENABLED=true`: synthetic payload is used
- otherwise Stage4 returns error payload and worker finishes task with error

### 3.2 Weather (optional)

Worker call:

```python
weather_data = await _get_weather_payload(config, output_range)
```

Behavior:

- called only when `weather_lat` and `weather_lon` are set
- request hours = `config.weather_hours or max(output_range, 1)`
- any error returns `None` and does not stop pipeline

### 3.3 CMMS Planned Data (optional)

Worker call:

```python
planned_adjustments = await _get_planned_adjustments(config, step, output_range)
```

Client request is built from:

- `step_ms`
- `output_range`
- `config.cmms_request_overrides`

Window logic in `CMMSClient.build_request(...)`:

- `from` = current UTC hour
- `to` = `from + output_range * step`

Any CMMS error is non-fatal for Stage4:

- returns `None`
- pipeline continues without planned adjustments

## 4. Output of Stage4

Stage4 produces data for next stage:

- `timestamp`, `value`, `qds` (required)
- `weather_data` (optional)
- `planned_adjustments` (optional)

Guard used by worker before inference:

```python
if not timestamp or not value or len(timestamp[0]) == 0:
    return HTTPMessages.model_launch_aborted_no_data()
```

## 5. Operational Checklist

- [ ] `step`, `input_range`, `output_range` are taken from normalized `ModelConfig`
- [ ] historical request built with `archives` and `step`
- [ ] historical response converted to `timestamp/value/qds`
- [ ] optional weather does not block stage on failures
- [ ] optional CMMS does not block stage on failures
- [ ] Stage4 output is ready for inference stage
