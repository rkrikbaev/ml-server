import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional
from os import getenv
from urllib.parse import urlparse, urlunparse

from fastapi.responses import JSONResponse

from api import CLIENT_TIMEOUT_ALL, CLIENT_TIMEOUT_ONE, HEADERS, HTTPMessages
from api.collector.http_client import HTTPClient
from api.utils import generate_timestamp

logger = logging.getLogger(__name__)


def _normalize_runtime_url(url: str) -> str:
    if not url:
        return url

    parsed = urlparse(url)
    if parsed.hostname not in {"127.0.0.1", "localhost"}:
        return url

    if not Path("/.dockerenv").exists():
        return url

    netloc = parsed.netloc.replace(parsed.hostname, "host.docker.internal")
    return urlunparse(parsed._replace(netloc=netloc))


class CMMSClient(HTTPClient):
    """Fetch and normalize planned adjustments used in forecast postprocessing."""

    def __init__(self) -> None:
        cmms_url = getenv("CMMS_URL") or getenv("CMMS_API_URL")
        if not cmms_url:
            cmms_url = "http://localhost:8000/api/v1/cmms"
            logger.warning("CMMS_URL not configured, using default: %s", cmms_url)

        super().__init__(
            urls=[_normalize_runtime_url(cmms_url)],
            headers=HEADERS,
            timeout_one=CLIENT_TIMEOUT_ONE,
            timeout_all=CLIENT_TIMEOUT_ALL,
        )

    @staticmethod
    def build_request(mode: str, step_ms: int, request_overrides: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        from_tp, to_tp = generate_timestamp(mode)
        request_payload: Dict[str, Any] = {
            "from": from_tp,
            "to": to_tp,
            "step": max(step_ms // 1000, 1),
        }

        if not request_overrides:
            return request_payload

        request_payload.update(request_overrides)
        request_payload.setdefault("step", max(step_ms // 1000, 1))

        range_size = request_overrides.get("range_size")
        has_explicit_bounds = request_overrides.get("from") is not None and request_overrides.get("to") is not None
        if range_size is not None and not has_explicit_bounds:
            now_utc = datetime.now(timezone.utc)
            current_hour = now_utc.replace(minute=0, second=0, microsecond=0)
            # Planned reductions apply to future horizon, not historical window.
            from_dt = current_hour
            to_dt = from_dt + timedelta(seconds=int(range_size) * (step_ms // 1000))
            request_payload["from"] = int(from_dt.timestamp() * 1000)
            request_payload["to"] = int(to_dt.timestamp() * 1000)

        request_payload.pop("range_size", None)
        return request_payload

    @staticmethod
    def _parse_timestamp(value: Any) -> Optional[int]:
        if not isinstance(value, (int, float)):
            return None

        ts = int(value)
        if ts <= 0:
            return None
        if ts > 10_000_000_000:  # already milliseconds
            return ts
        return ts * 1000  # seconds -> milliseconds

    @staticmethod
    def _parse_value(value: Any) -> Optional[float]:
        if not isinstance(value, (int, float)):
            return None
        return float(value)

    @staticmethod
    def parse_planned_series(
        payload: Any,
        from_ms: int,
        to_ms: int,
        step_seconds: int,
        equipment_type: Optional[str] = None,
    ) -> Dict[int, float]:
        if not isinstance(payload, dict):
            logger.warning("CMMS planned payload must be an object keyed by equipment type")
            return {}

        if step_seconds <= 0 or to_ms < from_ms:
            return {}

        entries: list[tuple[int, int, float]] = []

        for equipment_code, rows in payload.items():
            if equipment_type and str(equipment_code) != str(equipment_type):
                continue

            if not isinstance(rows, list):
                continue

            for row in rows:
                if not isinstance(row, dict):
                    continue

                start_ms = CMMSClient._parse_timestamp(row.get("start_requested"))
                end_ms = CMMSClient._parse_timestamp(row.get("end_requested"))
                reduction = CMMSClient._parse_value(row.get("p_descent"))

                if start_ms is None or end_ms is None or reduction is None:
                    continue
                if end_ms < start_ms:
                    continue

                entries.append((start_ms, end_ms, reduction))

        if not entries:
            return {}

        step_ms = step_seconds * 1000
        parsed: Dict[int, float] = {}
        for ts_ms in range(from_ms, to_ms + 1, step_ms):
            total_reduction = 0.0
            for start_ms, end_ms, reduction in entries:
                if start_ms <= ts_ms <= end_ms:
                    total_reduction += reduction

            if total_reduction > 0:
                parsed[ts_ms] = total_reduction

        return parsed

    async def fetch_planned_series(
        self,
        mode: str,
        step_ms: int,
        cmms_url: Optional[str] = None,
        request_overrides: Optional[Dict[str, Any]] = None,
    ) -> JSONResponse | Dict[int, float]:
        request_payload = self.build_request(mode, step_ms, request_overrides)

        if cmms_url:
            self.urls = [_normalize_runtime_url(cmms_url)]

        def handle_error(error: Optional[str]) -> JSONResponse:
            return HTTPMessages.service_unavailable_rz(error or "")

        result = await self.post_json(request_payload, handle_error)

        if isinstance(result, JSONResponse):
            return result
        if result is None:
            return {}

        return self.parse_planned_series(
            payload=result,
            from_ms=int(request_payload.get("from", 0)),
            to_ms=int(request_payload.get("to", 0)),
            step_seconds=int(request_payload.get("step", 0)),
            equipment_type=request_payload.get("type"),
        )


_cmms_client: Optional[CMMSClient] = None


def get_cmms_client() -> HTTPClient:
    """Get or create CMMS planned-data client."""
    global _cmms_client

    if _cmms_client is None:
        _cmms_client = CMMSClient()

    return _cmms_client