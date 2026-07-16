# lib/

Standalone Python modules used by both the ml-server FastAPI application and
standalone Jupyter notebooks.  No FastAPI or TaskIQ dependencies — only
`pydantic`, `numpy`, and optionally `scipy`.

## Modules

### `pipeline.py`

4-step SCADA time-series data quality pipeline.

**Steps:**
1. **Chronological control** — deduplication (mean aggregation), sort, grid alignment
2. **Static bounds** — hard limit (±inf → NaN), rolling Z-score spike detection
3. **Dynamic control** — rate-of-change outliers, stuck-signal detection
4. **Imputation** — linear (gaps ≤ 3), cubic spline (gaps 4–30), no-fill (gaps > 30);
   forward-fill only when `allow_look_ahead=False`

**Key exports:**

| Symbol | Kind | Description |
|--------|------|-------------|
| `AssessRequest` | Pydantic model | Request schema; accepts `from`/`to` as ISO-8601 or Unix ms |
| `AssessResponse` | Pydantic model | Full assessment result |
| `DataQualityPipeline` | Class | `run(raw_payloads)` → `AssessResponse` |
| `AnomalyRecord` | Pydantic model | Single anomaly event with type and action taken |
| `TagStats` | Pydantic model | Per-tag quality counters and score |
| `ScoringWeights` | Pydantic model | Configurable penalty weights |

**Quick usage:**

```python
from lib.pipeline import AssessRequest, DataQualityPipeline

req = AssessRequest(
    **{"from": "2026-05-01T00:00:00Z"},
    object_ref="/path/to/archive",
    to="2026-05-28T00:00:00Z",
    step=3600,
)
result = DataQualityPipeline(req).run({"/path/to/archive": [[ts_ms, value], ...]})
print(result.metrics_scoring.overall_quality_score)
```

**Consumed by:**
- `src/api/data_quality/models.py` — re-exports Pydantic schemas
- `src/api/data_quality/pipeline.py` — re-exports pipeline classes/functions
- `procedures/workflow/DATA_QUALITY_STANDALONE.ipynb` — imports directly for notebook use
