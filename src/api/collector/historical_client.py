# Mariya Polkovnikova
# 2026.04.20
#
# Historical Data Client Adapter
#
# This module requests historical data, validates the payload, and prepares
# model-ready arrays for downstream forecasting logic.

import logging
from os import getenv
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse, urlunparse

import numpy as np
from fastapi.responses import JSONResponse

from api import HEADERS, HTTPMessages
from api.collector.http_client import HTTPClient, CLIENT_TIMEOUT_ALL, CLIENT_TIMEOUT_ONE
from api.forecast import QDS
from api.utils import interpolate_nan_1d

logger = logging.getLogger(__name__)

ModelData = Tuple[List[np.ndarray], List[np.ndarray], List[np.ndarray]]
TEST_MODE = getenv("TEST_MODE", "false").lower() == "true"
HISTORICAL_DATA_STUB_ENABLED = (
    getenv("HISTORICAL_DATA_STUB_ENABLED")
    or getenv("SCADA_STUB_ENABLED", "false")
).lower() == "true"


class HistoricalDataClient(HTTPClient):
    """HTTP client and payload adapter for historical-data archives."""

    @staticmethod
    def should_use_stub() -> bool:
        """Return whether synthetic historical-data fallback is explicitly enabled."""
        return HISTORICAL_DATA_STUB_ENABLED

    @staticmethod
    def normalize_runtime_url(url: str) -> str:
        """Rewrite localhost-style URLs so they can reach host services from Docker."""
        if not url:
            return url

        parsed = urlparse(url)

        if parsed.hostname not in {"127.0.0.1", "localhost"}:
            return urlunparse(parsed)

        if not Path("/.dockerenv").exists():
            return urlunparse(parsed)

        netloc = parsed.netloc.replace(parsed.hostname, "host.docker.internal")
        return urlunparse(parsed._replace(netloc=netloc))

    def __init__(self) -> None:
        historical_data_url = getenv("HISTORICAL_DATA_API_URL") or getenv("SCADA_API_URL")

        if not historical_data_url:
            logger.warning("HISTORICAL_DATA_API_URL not configured, using default")
            historical_data_url = "http://localhost:7080/api/read/archive"

        historical_data_url = self.normalize_runtime_url(historical_data_url)

        super().__init__(
            urls=[historical_data_url],
            headers=HEADERS,
            timeout_one=CLIENT_TIMEOUT_ONE,
            timeout_all=CLIENT_TIMEOUT_ALL,
        )
        logger.info("HISTORICAL_DATA client initialized: %s", historical_data_url)

    @staticmethod
    def build_request(
        archives: List[str],
        step: int,
        input_range: Optional[int],
        output_range: int,
        request_overrides: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Build a historical-data request payload from explicit range settings."""
        if not archives:
            raise ValueError("archives must not be empty")
        if step <= 0:
            raise ValueError("step must be greater than zero")
        if output_range <= 0:
            raise ValueError("output_range must be greater than zero")

        now_utc = datetime.now(timezone.utc)
        current_hour = now_utc.replace(minute=0, second=0, microsecond=0)
        history_points = int(input_range) if input_range and input_range > 0 else int(output_range)
        to_dt = current_hour
        from_dt = to_dt - timedelta(seconds=history_points * (step // 1000))

        request_payload: Dict[str, Any] = {
            "from": int(from_dt.timestamp() * 1000),
            "to": int(to_dt.timestamp() * 1000),
            "archive": archives,
            "step": step // 1000,
        }

        if request_overrides:
            request_payload.update(request_overrides)
            request_payload.setdefault("archive", archives)
            request_payload.setdefault("step", step // 1000)

            range_size = request_overrides.get("range_size", request_overrides.get("input_range"))
            has_explicit_bounds = request_overrides.get("from") is not None and request_overrides.get("to") is not None

            if range_size is not None and not has_explicit_bounds:
                now_utc = datetime.now(timezone.utc)
                current_hour = now_utc.replace(minute=0, second=0, microsecond=0)
                to_dt = current_hour
                from_dt = to_dt - timedelta(seconds=int(range_size) * (step // 1000))
                request_payload["from"] = int(from_dt.timestamp() * 1000)
                request_payload["to"] = int(to_dt.timestamp() * 1000)

            request_payload.pop("range_size", None)
            request_payload.pop("input_range", None)

        return request_payload

    @staticmethod
    def build_stub_payload(request_payload: Dict[str, Any]) -> Dict[str, List[List[float]]]:
        """Build deterministic synthetic historical-data series for stub fallback."""
        archives = request_payload.get("archive") or ["stub_archive"]
        step_seconds = int(request_payload.get("step") or 3600)
        step_ms = max(step_seconds, 1) * 1000
        from_tp = int(request_payload.get("from") or 0)
        to_tp = int(request_payload.get("to") or 0)

        if to_tp <= from_tp:
            to_tp = from_tp + step_ms * 72

        timestamps = np.arange(from_tp, to_tp, step_ms, dtype=int)
        if timestamps.size == 0:
            timestamps = np.arange(from_tp, from_tp + step_ms * 72, step_ms, dtype=int)

        payload: Dict[str, List[List[float]]] = {}

        for index, archive_name in enumerate(archives):
            base_level = 450.0 + (index * 25.0)
            seasonal = np.sin(np.linspace(0.0, 6.0 * np.pi, len(timestamps))) * 35.0
            trend = np.linspace(0.0, 12.0, len(timestamps))
            values = base_level + seasonal + trend

            payload[str(archive_name)] = [
                [int(ts), round(float(value), 3), int(QDS.BASE)]
                for ts, value in zip(timestamps, values)
            ]

        return payload

    @staticmethod
    def validate_response_payload(payload: Dict[str, Any]) -> None:
        """Validate the minimal historical-data response schema before conversion."""
        if not isinstance(payload, dict) or not payload:
            raise ValueError("HISTORICAL_DATA response must be a non-empty object")

        for archive_name, values in payload.items():
            if not isinstance(values, list) or not values:
                raise ValueError(f"HISTORICAL_DATA series '{archive_name}' must be a non-empty list")

            for item in values:
                if not isinstance(item, (list, tuple)) or len(item) != 3:
                    raise ValueError(
                        f"HISTORICAL_DATA series '{archive_name}' must contain [timestamp, value, qds] triples"
                    )

    @staticmethod
    def extract_series(values: List[Any], interpolate: bool) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Convert one historical-data series into model-ready numpy arrays."""
        timestamps = np.array([ts for ts, _, _ in values], dtype=int)
        quality = np.array(
            [QDS.MISSING_VALUE if qds is None else qds for _, _, qds in values],
            dtype=int,
        )
        series = np.array([value for _, value, _ in values], dtype=float)

        if interpolate:
            series = interpolate_nan_1d(series)

        return timestamps, series, quality

    def prepare_model_data(self, payload: Dict[str, Any], online: bool) -> ModelData:
        """Validate and convert historical-data payload into model input arrays."""
        self.validate_response_payload(payload)

        timestamps_list: List[np.ndarray] = []
        values_list: List[np.ndarray] = []
        qds_list: List[np.ndarray] = []

        for values in payload.values():
            timestamps, series, quality = self.extract_series(values, interpolate=not online)
            timestamps_list.append(timestamps)
            values_list.append(series)
            qds_list.append(quality)

        return timestamps_list, values_list, qds_list

    async def fetch_model_data(
        self,
        archives: List[str],
        step: int,
        input_range: Optional[int],
        output_range: int,
        online: bool,
        historical_data_url: Optional[str] = None,
        request_overrides: Optional[Dict[str, Any]] = None,
    ) -> JSONResponse | ModelData:
        """Request historical data and return model-ready arrays."""
        try:
            request_payload = self.build_request(
                archives,
                step,
                input_range,
                output_range,
                request_overrides=request_overrides,
            )
        except ValueError as error:
            return HTTPMessages.unprocessable_entity_historical_data(str(error))

        if historical_data_url:
            self.urls = [self.normalize_runtime_url(historical_data_url)]

        def handle_success(response_data: Dict[str, Any]) -> ModelData:
            return self.prepare_model_data(response_data, online)

        def handle_error(error: Optional[str]) -> JSONResponse:
            return HTTPMessages.service_unavailable_historical_data(error or "")

        result = await self.post_with_callback(
            request_data=request_payload,
            callback=handle_success,
            error_handler=handle_error,
        )

        if result is None:
            if self.should_use_stub():
                logger.warning("HISTORICAL_DATA returned no result; using synthetic stub payload")
                return self.prepare_model_data(self.build_stub_payload(request_payload), online)
            return HTTPMessages.unprocessable_entity_historical_data(str(QDS.INVALID))

        if isinstance(result, dict) and result.get("status", 0) >= 400:
            if self.should_use_stub():
                logger.warning("HISTORICAL_DATA returned an error; using synthetic stub payload instead")
                return self.prepare_model_data(self.build_stub_payload(request_payload), online)
            return result

        if isinstance(result, JSONResponse):
            if self.should_use_stub():
                logger.warning("HISTORICAL_DATA request failed; using synthetic stub payload instead")
                return self.prepare_model_data(self.build_stub_payload(request_payload), online)
            return result

        return result


_historical_data_client: Optional[HistoricalDataClient] = None


def get_historical_data_client() -> HistoricalDataClient:
    """Get or create the shared historical-data client instance."""
    global _historical_data_client

    if _historical_data_client is None:
        _historical_data_client = HistoricalDataClient()

    return _historical_data_client
