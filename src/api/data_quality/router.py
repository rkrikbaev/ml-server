# Data Quality Assessment — FastAPI router
#
# POST /data-quality/assess
#   Body: { "object_ref": "...", "from": "...", "to": "...", "step": 3600 }
#
#   → normalises the request (see AssessRequest validator)
#   → fetches raw data from SCADA for the window + archives
#   → runs the 4-step validation pipeline
#   → returns a structured quality report

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from api.collector import HistoricalDataClient, get_historical_data_client

from .models import AssessRequest
from .pipeline import DataQualityPipeline, _dt_to_ms

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/data-quality", tags=["data-quality"])


def _error(status: int, message: str) -> JSONResponse:
    return JSONResponse(
        content={"status": status, "message": message},
        status_code=status,
    )


@router.post("/assess")
async def assess(request: AssessRequest) -> JSONResponse:
    """
    Assess the quality of SCADA time-series data.

    Minimal request body::

        {
            "object_ref": "/path/to/archive",
            "from":       "2026-05-01T00:00:00Z",
            "to":         "2026-05-28T00:00:00Z",
            "step":       3600
        }

    ``from`` and ``to`` also accept Unix millisecond timestamps or may be
    omitted / left empty (defaults: ``to`` = current hour, ``from`` = ``to`` − 24 steps).

    ``object_ref`` may be a single archive path string or a JSON array of paths.

    Returns a JSON document with:
    - ``metadata``        — request parameters and elapsed time
    - ``metrics_scoring`` — per-tag and overall quality scores (0–100)
    - ``anomalies_log``   — detailed anomaly records with timestamps and actions
    - ``cleaned_data``    — grid-aligned, imputed series ready for analysis
    """
    t0 = time.monotonic()

    # request.start_time / end_time / tag_ids / expected_frequency are already
    # normalised by the AssessRequest validator — use them directly.
    start_ms = _dt_to_ms(request.start_time)
    end_ms = _dt_to_ms(request.end_time)

    # ── Build SCADA request payload ──────────────────────────────────────────
    scada_payload: Dict[str, Any] = {
        "from": start_ms,
        "to": end_ms,
        "archive": request.tag_ids,
        "step": request.expected_frequency,
    }

    # ── Fetch raw data from SCADA ────────────────────────────────────────────
    client: HistoricalDataClient = get_historical_data_client()

    if request.scada_url:
        client.urls = [HistoricalDataClient.normalize_runtime_url(request.scada_url)]

    raw_result: Any = None
    try:
        raw_result = await client.post_with_callback(
            request_data=scada_payload,
            callback=lambda data: data,
            error_handler=lambda err: {"_error": err or "SCADA request failed"},
        )
    except Exception as exc:
        logger.exception("SCADA fetch failed during data-quality assessment: %s", exc)
        return _error(503, f"SCADA fetch error: {exc}")

    # ── Handle SCADA errors / stub fallback ──────────────────────────────────
    if raw_result is None:
        if HistoricalDataClient.should_use_stub():
            raw_result = HistoricalDataClient.build_stub_payload(scada_payload)
            logger.warning("SCADA unavailable; using synthetic stub for data-quality assessment")
        else:
            return _error(503, "SCADA returned no data for the requested window")

    if isinstance(raw_result, dict) and "_error" in raw_result:
        if HistoricalDataClient.should_use_stub():
            raw_result = HistoricalDataClient.build_stub_payload(scada_payload)
        else:
            return _error(503, f"SCADA error: {raw_result['_error']}")

    # ── Map SCADA response → per-tag lists ────────────────────────────────────
    # SCADA response is keyed by archive name: { "/path/to/archive": [[ts, val], ...] }
    raw_payloads: Dict[str, List[List[float]]] = {}
    for tag_id in request.tag_ids:
        series = raw_result.get(tag_id)
        if series and isinstance(series, list):
            raw_payloads[tag_id] = series
        else:
            logger.warning("No data returned by SCADA for tag_id=%s", tag_id)
            raw_payloads[tag_id] = []

    # ── Run pipeline ─────────────────────────────────────────────────────────
    pipeline = DataQualityPipeline(request)
    response = pipeline.run(raw_payloads, wall_start=t0)

    return JSONResponse(
        content=response.model_dump(),
        status_code=200,
    )
