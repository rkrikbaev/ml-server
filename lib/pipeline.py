# Data Quality Pipeline — standalone module
#
# Self-contained: depends only on pydantic, numpy, scipy (optional).
# Imported by:
#   src/api/data_quality/models.py   (re-exports Pydantic schemas)
#   src/api/data_quality/pipeline.py (re-exports pipeline classes/functions)
#   procedures/workflow/DATA_QUALITY_STANDALONE.ipynb
#
# 4-step validation pipeline for SCADA time-series data:
#   1. Chronological control  (dedup, sort, grid alignment)
#   2. Static bounds          (hard limits, rolling Z-score spikes)
#   3. Dynamic control        (rate-of-change, stuck-at detection)
#   4. Imputation             (linear / cubic / forward-fill by gap length)

from __future__ import annotations

import logging
import math
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator

logger = logging.getLogger(__name__)


# ─── Helpers ────────────────────────────────────────────────────────────────


def _parse_time(value: Union[str, int, float, None]) -> Optional[datetime]:
    """
    Parse a flexible time value into a UTC-aware datetime.

    Accepts:
    - ``None`` or empty string  -> returns None (caller applies default)
    - ISO-8601 string           -> "2026-01-01T00:00:00Z" / "2026-01-01T00:00:00+00:00"
    - Numeric string or int     -> Unix timestamp in **milliseconds**
    """
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            pass
        try:
            ms = float(value)
        except ValueError:
            raise ValueError(
                f"Cannot parse time value: {value!r}. "
                "Expected ISO-8601 string or Unix ms timestamp."
            )
        return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)
    if isinstance(value, (int, float)) and math.isfinite(value):
        return datetime.fromtimestamp(float(value) / 1000.0, tz=timezone.utc)
    raise ValueError(f"Cannot parse time value: {value!r}")


def _now_trunc_hour() -> datetime:
    now = datetime.now(tz=timezone.utc)
    return now.replace(minute=0, second=0, microsecond=0)


def _ts_to_iso(ts_ms: int) -> str:
    """Convert millisecond Unix timestamp to ISO-8601 string (UTC)."""
    return datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def _dt_to_ms(dt: datetime) -> int:
    """Convert datetime to millisecond Unix timestamp."""
    return int(dt.timestamp() * 1000)


def _find_nan_runs(mask: np.ndarray) -> List[Tuple[int, int]]:
    """
    Return list of (start_idx, end_idx) for contiguous True runs in *mask*.
    Both indices are inclusive.
    """
    runs: List[Tuple[int, int]] = []
    n = len(mask)
    i = 0
    while i < n:
        if mask[i]:
            j = i
            while j < n and mask[j]:
                j += 1
            runs.append((i, j - 1))
            i = j
        else:
            i += 1
    return runs


# ─── Pydantic schemas ────────────────────────────────────────────────────────


class ScoringWeights(BaseModel):
    """Configurable penalty weights for the quality score formula."""

    w_missing:   float = Field(default=1.0, ge=0.0, description="Penalty for missing points")
    w_duplicate: float = Field(default=0.2, ge=0.0, description="Penalty for duplicates")
    w_outlier:   float = Field(default=0.8, ge=0.0, description="Penalty for spike outliers")
    w_stuck:     float = Field(default=1.0, ge=0.0, description="Penalty for stuck-signal points")


class AssessRequest(BaseModel):
    """
    Request schema for POST /data-quality/assess.

    Wire format (matches SCADA ecosystem)
    --------------------------------------
    ``object_ref``  SCADA archive path or list of paths.
    ``from``        Window start. ISO-8601, Unix ms, or omit -> to - 24 steps.
    ``to``          Window end.   ISO-8601, Unix ms, or omit -> current hour (UTC).
    ``step``        Time step in seconds (e.g. 3600 for hourly).
    """

    model_config = ConfigDict(populate_by_name=True)

    # Wire fields
    object_ref: Union[str, List[str], None] = Field(
        default=None, description="SCADA archive path(s)"
    )
    from_: Union[str, int, float, None] = Field(
        default=None, alias="from",
        description="Window start: ISO-8601 or Unix ms timestamp",
    )
    to: Union[str, int, float, None] = Field(
        default=None, description="Window end: ISO-8601 or Unix ms timestamp"
    )
    step: int = Field(default=3600, gt=0, description="Step in seconds")

    # Optional tuning
    scada_url:          Optional[str]   = Field(default=None, description="Override SCADA URL")
    allow_look_ahead:   bool            = Field(default=True)
    weights:            ScoringWeights  = Field(default_factory=ScoringWeights)
    z_score_window:     int             = Field(default=48, ge=5, le=500)
    z_score_threshold:  float           = Field(default=3.0, ge=1.0)
    stuck_window:       int             = Field(default=10, ge=3)

    # Computed / normalised (set by validator, used by pipeline)
    tag_ids:            List[str]          = Field(default_factory=list)
    start_time:         Optional[datetime] = Field(default=None)
    end_time:           Optional[datetime] = Field(default=None)
    expected_frequency: int               = Field(default=3600)

    @model_validator(mode="after")
    def _normalise(self) -> "AssessRequest":
        self.expected_frequency = self.step

        if self.object_ref is None or self.object_ref == "":
            tag_ids: List[str] = []
        elif isinstance(self.object_ref, list):
            tag_ids = [str(t) for t in self.object_ref if t not in (None, "")]
        else:
            tag_ids = [str(self.object_ref)]
        if not tag_ids:
            raise ValueError("object_ref must be a non-empty archive path or list of paths")
        self.tag_ids = tag_ids

        end_dt = _parse_time(self.to)
        if end_dt is None:
            end_dt = _now_trunc_hour()
        self.end_time = end_dt

        start_dt = _parse_time(self.from_)
        if start_dt is None:
            start_dt = end_dt - timedelta(seconds=self.step * 24)
        self.start_time = start_dt

        if self.end_time <= self.start_time:
            raise ValueError("'to' must be after 'from'")
        return self


class AnomalyRecord(BaseModel):
    """A single detected anomaly or quality event."""

    tag_id:           str
    # anomaly_type: missing | duplicate | hard_limit | spike_outlier | stuck_signal | rate_of_change
    anomaly_type:     str
    timestamp:        str           # ISO 8601
    raw_value:        Optional[float] = None
    # action_taken: replaced_with_nan | deduplicated | marked_as_nan_no_fill
    #               | linear_interpolated | cubic_interpolated | forward_filled | long_gap_not_filled
    action_taken:     str
    duration_seconds: Optional[int] = None   # for stuck_signal / long_gap


class TagStats(BaseModel):
    total_expected_points:  int
    missing_points_count:   int
    duplicates_count:       int
    outliers_count:         int
    stuck_sequences_count:  int
    rate_of_change_count:   int
    long_gaps_count:        int
    quality_score:          float


class MetricsScoring(BaseModel):
    overall_quality_score: float
    tags: Dict[str, TagStats]


class Metadata(BaseModel):
    timestamp_start:            str
    timestamp_end:              str
    expected_frequency_seconds: int
    total_tags_processed:       int
    elapsed_seconds:            float
    allow_look_ahead:           bool


class AssessResponse(BaseModel):
    metadata:        Metadata
    metrics_scoring: MetricsScoring
    anomalies_log:   List[AnomalyRecord]
    cleaned_data:    List[Dict[str, Any]]


# ─── Step 1: Chronological control ──────────────────────────────────────────


def _step1_chronological(
    raw_timestamps: np.ndarray,
    raw_values: np.ndarray,
    grid_ms: np.ndarray,
    tag_id: str,
    anomalies: List[AnomalyRecord],
) -> Tuple[np.ndarray, int]:
    """
    1. Deduplicate timestamps (mean aggregation).
    2. Sort ascending.
    3. Align to regular grid; fill gaps with NaN.

    Returns aligned values array (same length as grid_ms) and duplicate count.
    """
    dup_count = 0
    if len(raw_timestamps) != len(np.unique(raw_timestamps)):
        seen: Dict[int, List[float]] = {}
        for ts, val in zip(raw_timestamps.tolist(), raw_values.tolist()):
            seen.setdefault(ts, []).append(val)

        dedup_ts: List[int] = []
        dedup_vals: List[float] = []
        for ts, vals in sorted(seen.items()):
            if len(vals) > 1:
                dup_count += len(vals) - 1
                anomalies.append(AnomalyRecord(
                    tag_id=tag_id,
                    timestamp=_ts_to_iso(int(ts)),
                    anomaly_type="duplicate",
                    raw_value=float(vals[0]) if not math.isnan(vals[0]) else None,
                    action_taken="deduplicated",
                ))
            dedup_ts.append(ts)
            dedup_vals.append(float(np.nanmean(vals)))

        raw_timestamps = np.array(dedup_ts,   dtype=np.int64)
        raw_values     = np.array(dedup_vals, dtype=float)

    sort_idx       = np.argsort(raw_timestamps)
    raw_timestamps = raw_timestamps[sort_idx]
    raw_values     = raw_values[sort_idx]

    aligned    = np.full(len(grid_ms), np.nan, dtype=float)
    ts_to_val: Dict[int, float] = {
        int(ts): float(val)
        for ts, val in zip(raw_timestamps.tolist(), raw_values.tolist())
    }
    for i, grid_ts in enumerate(grid_ms.tolist()):
        val = ts_to_val.get(int(grid_ts))
        if val is not None:
            aligned[i] = val

    return aligned, dup_count


# ─── Step 2: Static bounds ───────────────────────────────────────────────────


def _step2_static_bounds(
    values: np.ndarray,
    grid_ms: np.ndarray,
    tag_id: str,
    anomalies: List[AnomalyRecord],
    z_window: int,
    z_threshold: float,
) -> Tuple[np.ndarray, int]:
    """
    Hard limits: replace ±inf with NaN.
    Soft limits: rolling Z-score spike detection -> NaN.

    Returns cleaned values and spike count.
    """
    arr = values.copy()
    spike_count = 0

    hard_mask = np.isinf(arr)
    for idx in np.where(hard_mask)[0]:
        anomalies.append(AnomalyRecord(
            tag_id=tag_id,
            timestamp=_ts_to_iso(int(grid_ms[idx])),
            anomaly_type="hard_limit",
            raw_value=float(arr[idx]),
            action_taken="replaced_with_nan",
        ))
    arr[hard_mask] = np.nan

    n    = len(arr)
    half = z_window // 2
    for i in range(n):
        if np.isnan(arr[i]):
            continue
        lo    = max(0, i - half)
        hi    = min(n, i + half + 1)
        window = arr[lo:hi]
        valid  = window[~np.isnan(window)]
        if len(valid) < 5:
            continue
        mu    = float(np.mean(valid))
        sigma = float(np.std(valid))
        if sigma < 1e-10:
            continue
        if abs(arr[i] - mu) / sigma > z_threshold:
            anomalies.append(AnomalyRecord(
                tag_id=tag_id,
                timestamp=_ts_to_iso(int(grid_ms[i])),
                anomaly_type="spike_outlier",
                raw_value=float(arr[i]),
                action_taken="replaced_with_nan",
            ))
            arr[i] = np.nan
            spike_count += 1

    return arr, spike_count


# ─── Step 3: Dynamic control ─────────────────────────────────────────────────


def _step3_dynamic(
    values: np.ndarray,
    grid_ms: np.ndarray,
    tag_id: str,
    anomalies: List[AnomalyRecord],
    stuck_window: int,
) -> Tuple[np.ndarray, int, int]:
    """
    Rate-of-change: |diff| > 99.9th percentile -> NaN.
    Stuck-at: >= stuck_window identical consecutive values -> NaN.

    Returns cleaned values, roc_count, stuck_count.
    """
    arr = values.copy()
    roc_count = stuck_count = 0

    valid_mask    = ~np.isnan(arr)
    valid_indices = np.where(valid_mask)[0]
    if len(valid_indices) >= 2:
        diffs = np.abs(np.diff(arr[valid_mask]))
        if len(diffs) > 0 and not np.all(diffs == 0):
            threshold = float(np.nanpercentile(diffs, 99.9))
            for k in range(len(diffs)):
                if diffs[k] > threshold:
                    fi = int(valid_indices[k + 1])
                    anomalies.append(AnomalyRecord(
                        tag_id=tag_id,
                        timestamp=_ts_to_iso(int(grid_ms[fi])),
                        anomaly_type="rate_of_change",
                        raw_value=float(arr[fi]),
                        action_taken="replaced_with_nan",
                    ))
                    arr[fi] = np.nan
                    roc_count += 1

    n = len(arr)
    i = 0
    while i < n:
        if np.isnan(arr[i]):
            i += 1
            continue
        ref = arr[i]
        j   = i + 1
        while j < n and not np.isnan(arr[j]) and arr[j] == ref:
            j += 1
        if j - i >= stuck_window:
            duration_s = int((grid_ms[j - 1] - grid_ms[i]) / 1000)
            anomalies.append(AnomalyRecord(
                tag_id=tag_id,
                timestamp=_ts_to_iso(int(grid_ms[i])),
                anomaly_type="stuck_signal",
                raw_value=float(ref),
                action_taken="marked_as_nan_no_fill",
                duration_seconds=duration_s,
            ))
            arr[i+1:j] = np.nan
            stuck_count += j - i - 1
        i = j

    return arr, roc_count, stuck_count


# ─── Step 4: Imputation ──────────────────────────────────────────────────────


def _step4_impute(
    values: np.ndarray,
    grid_ms: np.ndarray,
    tag_id: str,
    anomalies: List[AnomalyRecord],
    allow_look_ahead: bool,
    long_gap_threshold: int = 30,
) -> Tuple[np.ndarray, int]:
    """
    Fill NaN runs by length:
      L <= 3       -> linear interpolation
      3 < L <= 30  -> cubic spline (scipy) or linear fallback
      L > 30       -> leave as NaN (long gap)

    If allow_look_ahead=False, forward-fill only.

    Returns imputed values and long_gaps_count.
    """
    arr      = values.copy()
    nan_mask = np.isnan(arr)
    runs     = _find_nan_runs(nan_mask)
    long_gaps = 0

    if not allow_look_ahead:
        last_val: Optional[float] = None
        for i in range(len(arr)):
            if not np.isnan(arr[i]):
                last_val = arr[i]
            elif last_val is not None:
                arr[i] = last_val
                anomalies.append(AnomalyRecord(
                    tag_id=tag_id,
                    timestamp=_ts_to_iso(int(grid_ms[i])),
                    anomaly_type="missing",
                    action_taken="forward_filled",
                ))
        return arr, long_gaps

    for start_i, end_i in runs:
        gap_len = end_i - start_i + 1

        if gap_len > long_gap_threshold:
            duration_s = int((grid_ms[end_i] - grid_ms[start_i]) / 1000)
            anomalies.append(AnomalyRecord(
                tag_id=tag_id,
                timestamp=_ts_to_iso(int(grid_ms[start_i])),
                anomaly_type="missing",
                action_taken="long_gap_not_filled",
                duration_seconds=duration_s,
            ))
            long_gaps += 1
            continue

        left_i  = start_i - 1
        right_i = end_i + 1
        has_left  = left_i >= 0 and not np.isnan(arr[left_i])
        has_right = right_i < len(arr) and not np.isnan(arr[right_i])
        if not has_left and not has_right:
            continue

        if gap_len <= 3:
            action = "linear_interpolated"
            if has_left and has_right:
                x0, x1 = float(grid_ms[left_i]), float(grid_ms[right_i])
                y0, y1 = arr[left_i], arr[right_i]
                for k in range(start_i, end_i + 1):
                    t = (float(grid_ms[k]) - x0) / (x1 - x0)
                    arr[k] = y0 + t * (y1 - y0)
            elif has_left:
                arr[start_i:end_i+1] = arr[left_i]
            else:
                arr[start_i:end_i+1] = arr[right_i]
        else:
            action = "cubic_interpolated"
            try:
                from scipy.interpolate import CubicSpline  # type: ignore
                radius = min(3 * gap_len, len(arr) // 2)
                lo = max(0, start_i - radius)
                hi = min(len(arr), end_i + radius + 1)
                seg_x = grid_ms[lo:hi].astype(float)
                seg_y = arr[lo:hi].copy()
                valid = ~np.isnan(seg_y)
                if valid.sum() >= 4:
                    cs = CubicSpline(seg_x[valid], seg_y[valid])
                    for k in range(start_i, end_i + 1):
                        arr[k] = float(cs(float(grid_ms[k])))
                else:
                    raise ValueError("not enough valid points for cubic spline")
            except Exception:
                action = "linear_interpolated"
                if has_left and has_right:
                    x0, x1 = float(grid_ms[left_i]), float(grid_ms[right_i])
                    y0, y1 = arr[left_i], arr[right_i]
                    for k in range(start_i, end_i + 1):
                        t = (float(grid_ms[k]) - x0) / (x1 - x0)
                        arr[k] = y0 + t * (y1 - y0)
                elif has_left:
                    arr[start_i:end_i+1] = arr[left_i]
                else:
                    arr[start_i:end_i+1] = arr[right_i]

        for k in range(start_i, end_i + 1):
            anomalies.append(AnomalyRecord(
                tag_id=tag_id,
                timestamp=_ts_to_iso(int(grid_ms[k])),
                anomaly_type="missing",
                action_taken=action,
            ))

    return arr, long_gaps


# ─── Scoring ─────────────────────────────────────────────────────────────────


def _compute_score(
    n_total:   int,
    n_missing: int,
    n_dup:     int,
    n_outliers: int,
    n_stuck:   int,
    weights:   ScoringWeights,
) -> float:
    """
    Score = 100 * (1 - (W1*N_missing + W2*N_dup + W3*N_outliers + W4*N_stuck) / N_total)
    Clamped to [0, 100].
    """
    if n_total == 0:
        return 0.0
    penalty = (
        weights.w_missing   * n_missing +
        weights.w_duplicate * n_dup +
        weights.w_outlier   * n_outliers +
        weights.w_stuck     * n_stuck
    )
    return float(max(0.0, min(100.0, 100.0 * (1.0 - penalty / n_total))))


# ─── Main pipeline class ─────────────────────────────────────────────────────


class DataQualityPipeline:
    """
    Full data quality assessment pipeline for one or many SCADA time-series tags.

    Usage::

        pipeline = DataQualityPipeline(request)
        response = pipeline.run(raw_payloads)
    """

    def __init__(self, request: AssessRequest) -> None:
        self.request   = request
        self._start_ms = _dt_to_ms(request.start_time)
        self._end_ms   = _dt_to_ms(request.end_time)
        self._step_ms  = request.expected_frequency * 1000
        self._grid_ms  = np.arange(
            self._start_ms, self._end_ms + 1, self._step_ms, dtype=np.int64
        )

    def run(
        self,
        raw_payloads: Dict[str, List[List[float]]],
        wall_start: Optional[float] = None,
    ) -> AssessResponse:
        t0 = wall_start or time.monotonic()
        all_anomalies:  List[AnomalyRecord]        = []
        tag_stats:      Dict[str, TagStats]         = {}
        cleaned_series: Dict[str, np.ndarray]       = {}

        for tag_id in self.request.tag_ids:
            raw = raw_payloads.get(tag_id, [])
            stats, cleaned, tag_anomalies = self._process_tag(tag_id, raw)
            tag_stats[tag_id]      = stats
            cleaned_series[tag_id] = cleaned
            all_anomalies.extend(tag_anomalies)

        cleaned_data: List[Dict[str, Any]] = []
        for i, grid_ts in enumerate(self._grid_ms.tolist()):
            row: Dict[str, Any] = {"timestamp": _ts_to_iso(int(grid_ts))}
            for tag_id, arr in cleaned_series.items():
                val = float(arr[i]) if i < len(arr) and not np.isnan(arr[i]) else None
                row[tag_id] = round(val, 6) if val is not None else None
            cleaned_data.append(row)

        scores  = [s.quality_score for s in tag_stats.values()]
        overall = round(float(np.mean(scores)) if scores else 0.0, 2)
        elapsed = round(time.monotonic() - t0, 4)

        return AssessResponse(
            metadata=Metadata(
                timestamp_start=self.request.start_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                timestamp_end=self.request.end_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                expected_frequency_seconds=self.request.expected_frequency,
                total_tags_processed=len(self.request.tag_ids),
                elapsed_seconds=elapsed,
                allow_look_ahead=self.request.allow_look_ahead,
            ),
            metrics_scoring=MetricsScoring(
                overall_quality_score=overall,
                tags=tag_stats,
            ),
            anomalies_log=all_anomalies,
            cleaned_data=cleaned_data,
        )

    def _process_tag(
        self,
        tag_id: str,
        raw: List[List[float]],
    ) -> Tuple[TagStats, np.ndarray, List[AnomalyRecord]]:
        """Run all 4 pipeline steps for a single tag."""
        anomalies: List[AnomalyRecord] = []
        grid_ms = self._grid_ms
        n_total = len(grid_ms)

        if raw:
            raw_ts   = np.array([item[0] for item in raw], dtype=np.int64)
            raw_vals = np.array([item[1] for item in raw], dtype=float)
        else:
            raw_ts   = np.array([], dtype=np.int64)
            raw_vals = np.array([], dtype=float)

        aligned, dup_count = _step1_chronological(
            raw_ts, raw_vals, grid_ms, tag_id, anomalies
        )
        missing_before = int(np.isnan(aligned).sum())

        after_static, spike_count = _step2_static_bounds(
            aligned, grid_ms, tag_id, anomalies,
            self.request.z_score_window, self.request.z_score_threshold,
        )
        after_dynamic, roc_count, stuck_count = _step3_dynamic(
            after_static, grid_ms, tag_id, anomalies, self.request.stuck_window,
        )
        imputed, long_gaps = _step4_impute(
            after_dynamic, grid_ms, tag_id, anomalies, self.request.allow_look_ahead,
        )

        score = _compute_score(
            n_total=n_total,
            n_missing=missing_before,
            n_dup=dup_count,
            n_outliers=spike_count,
            n_stuck=stuck_count,
            weights=self.request.weights,
        )
        stats = TagStats(
            total_expected_points=n_total,
            missing_points_count=missing_before,
            duplicates_count=dup_count,
            outliers_count=spike_count,
            stuck_sequences_count=stuck_count,
            rate_of_change_count=roc_count,
            long_gaps_count=long_gaps,
            quality_score=round(score, 2),
        )
        return stats, imputed, anomalies


__all__ = [
    # helpers
    "_parse_time", "_now_trunc_hour", "_ts_to_iso", "_dt_to_ms", "_find_nan_runs",
    # pipeline steps
    "_step1_chronological", "_step2_static_bounds", "_step3_dynamic", "_step4_impute",
    "_compute_score",
    # schemas
    "ScoringWeights", "AssessRequest", "AnomalyRecord", "TagStats",
    "MetricsScoring", "Metadata", "AssessResponse",
    # pipeline
    "DataQualityPipeline",
]
