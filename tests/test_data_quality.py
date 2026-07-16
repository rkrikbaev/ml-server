# Tests for the Data Quality Assessment pipeline
#
# Run: pytest tests/test_data_quality.py -v
#
# All tests are purely in-process — no SCADA / Redis / MLflow required.

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import List

import numpy as np
import pytest

from api.data_quality.models import AssessRequest, ScoringWeights
from api.data_quality.pipeline import (
    DataQualityPipeline,
    _compute_score,
    _find_nan_runs,
    _step1_chronological,
    _step2_static_bounds,
    _step3_dynamic,
    _step4_impute,
    _ts_to_iso,
)


# ─── Fixtures ────────────────────────────────────────────────────────────────


def _make_request(
    tag_ids: List[str] | None = None,
    start: str = "2026-01-01T00:00:00Z",
    end: str = "2026-01-01T01:00:00Z",
    freq: int = 300,          # 5-minute step
    allow_look_ahead: bool = True,
) -> AssessRequest:
    """Helper: build AssessRequest using the new wire format."""
    tags = tag_ids or ["TAG_A"]
    # object_ref accepts a single string or a list
    obj_ref = tags[0] if len(tags) == 1 else tags
    return AssessRequest(
        **{"from": start},    # "from" is a Python keyword → pass via **
        object_ref=obj_ref,
        to=end,
        step=freq,
        allow_look_ahead=allow_look_ahead,
    )


def _grid(request: AssessRequest) -> np.ndarray:
    start_ms = int(request.start_time.timestamp() * 1000)
    end_ms = int(request.end_time.timestamp() * 1000)
    step_ms = request.expected_frequency * 1000
    return np.arange(start_ms, end_ms + 1, step_ms, dtype=np.int64)


# ─── _ts_to_iso ──────────────────────────────────────────────────────────────


def test_ts_to_iso_epoch():
    assert _ts_to_iso(0) == "1970-01-01T00:00:00Z"


def test_ts_to_iso_known():
    # 2025-01-01T00:00:00 UTC  →  1735689600000 ms
    assert _ts_to_iso(1735689600000) == "2025-01-01T00:00:00Z"


# ─── _find_nan_runs ───────────────────────────────────────────────────────────


def test_find_nan_runs_no_nans():
    mask = np.array([False, False, False])
    assert _find_nan_runs(mask) == []


def test_find_nan_runs_all_nans():
    mask = np.array([True, True, True])
    assert _find_nan_runs(mask) == [(0, 2)]


def test_find_nan_runs_multiple():
    mask = np.array([False, True, True, False, True, False])
    runs = _find_nan_runs(mask)
    assert runs == [(1, 2), (4, 4)]


# ─── _compute_score ───────────────────────────────────────────────────────────


def test_compute_score_perfect():
    score = _compute_score(100, 0, 0, 0, 0, ScoringWeights())
    assert score == 100.0


def test_compute_score_all_missing():
    score = _compute_score(100, 100, 0, 0, 0, ScoringWeights())
    assert score == 0.0


def test_compute_score_clamped_below_zero():
    # penalty > 1 → score would be negative → should clamp to 0
    score = _compute_score(10, 15, 0, 0, 0, ScoringWeights())
    assert score == 0.0


def test_compute_score_partial():
    w = ScoringWeights(w_missing=1.0, w_duplicate=0.2, w_outlier=0.8, w_stuck=1.0)
    # 100 total, 10 missing, 5 dup, 3 outliers, 2 stuck
    penalty = 1.0 * 10 + 0.2 * 5 + 0.8 * 3 + 1.0 * 2
    expected = 100.0 * (1.0 - penalty / 100)
    assert abs(_compute_score(100, 10, 5, 3, 2, w) - expected) < 1e-9


def test_compute_score_zero_total():
    # Edge-case: empty grid
    assert _compute_score(0, 0, 0, 0, 0, ScoringWeights()) == 0.0


# ─── Step 1: Chronological ───────────────────────────────────────────────────


def test_step1_clean_data():
    """Clean data without gaps or duplicates should align perfectly."""
    req = _make_request(freq=3600, end="2026-01-01T03:00:00Z")
    grid = _grid(req)

    raw_ts = grid.copy()
    raw_vals = np.array([100.0, 110.0, 120.0, 130.0], dtype=float)
    anomalies = []

    aligned, dup_count = _step1_chronological(raw_ts, raw_vals, grid, "T", anomalies)

    assert dup_count == 0
    assert len(anomalies) == 0
    np.testing.assert_array_equal(aligned, raw_vals)


def test_step1_dedup():
    """Duplicate timestamps should be averaged and counted."""
    req = _make_request(freq=3600, end="2026-01-01T01:00:00Z")
    grid = _grid(req)

    ts0 = int(grid[0])
    raw_ts = np.array([ts0, ts0, int(grid[1])], dtype=np.int64)
    raw_vals = np.array([10.0, 20.0, 30.0], dtype=float)
    anomalies = []

    aligned, dup_count = _step1_chronological(raw_ts, raw_vals, grid, "T", anomalies)

    assert dup_count == 1
    assert len(anomalies) == 1
    assert anomalies[0].anomaly_type == "duplicate"
    assert aligned[0] == pytest.approx(15.0)   # mean of 10 and 20
    assert aligned[1] == pytest.approx(30.0)


def test_step1_missing_gap():
    """Missing SCADA points should become NaN in the aligned array."""
    req = _make_request(freq=3600, end="2026-01-01T03:00:00Z")
    grid = _grid(req)

    # Provide only first and last point; middle two are absent
    raw_ts = np.array([int(grid[0]), int(grid[3])], dtype=np.int64)
    raw_vals = np.array([1.0, 4.0], dtype=float)
    anomalies = []

    aligned, _ = _step1_chronological(raw_ts, raw_vals, grid, "T", anomalies)

    assert not math.isnan(aligned[0])
    assert math.isnan(aligned[1])
    assert math.isnan(aligned[2])
    assert not math.isnan(aligned[3])


# ─── Step 2: Static bounds ────────────────────────────────────────────────────


def test_step2_hard_limit_inf():
    req = _make_request(freq=3600, end="2026-01-01T02:00:00Z")
    grid = _grid(req)

    values = np.array([1.0, float("inf"), 3.0], dtype=float)
    anomalies = []

    cleaned, spikes = _step2_static_bounds(values, grid, "T", anomalies, 10, 3.0)

    assert math.isnan(cleaned[1])
    assert any(a.anomaly_type == "hard_limit" for a in anomalies)


def test_step2_spike_detection():
    """A clearly anomalous spike should be flagged."""
    req = _make_request(freq=300, end="2026-01-01T04:00:00Z")
    grid = _grid(req)

    n = len(grid)
    values = np.full(n, 100.0)
    # Inject a massive spike in the middle
    spike_idx = n // 2
    values[spike_idx] = 1_000_000.0
    anomalies = []

    cleaned, spike_count = _step2_static_bounds(
        values, grid, "T", anomalies, z_window=20, z_threshold=3.0
    )

    assert spike_count >= 1
    assert math.isnan(cleaned[spike_idx])


def test_step2_no_spike_flat_signal():
    """A perfectly flat signal should produce no spikes."""
    req = _make_request(freq=300, end="2026-01-01T04:00:00Z")
    grid = _grid(req)
    values = np.full(len(grid), 50.0)
    anomalies = []

    cleaned, spikes = _step2_static_bounds(values, grid, "T", anomalies, 20, 3.0)

    assert spikes == 0


# ─── Step 3: Dynamic ─────────────────────────────────────────────────────────


def test_step3_stuck_signal():
    """A sequence of identical values longer than stuck_window should be flagged."""
    req = _make_request(freq=3600, end="2026-01-01T12:00:00Z")
    grid = _grid(req)

    # Start the stuck run at index 0 so there is no preceding jump that could
    # also trigger the rate-of-change check, which runs first.
    values = np.full(len(grid), 42.0, dtype=float)
    # Break out of the stuck run near the end so there is variation
    values[-1] = 99.0
    anomalies = []

    cleaned, roc_count, stuck_count = _step3_dynamic(
        values, grid, "T", anomalies, stuck_window=10
    )

    # Run length at index 0 is (n-1) ≥ 10 → should be detected
    assert stuck_count >= 1
    assert any(a.anomaly_type == "stuck_signal" for a in anomalies)
    # First point of the stuck run must be kept
    assert cleaned[0] == pytest.approx(42.0)
    # Interior of the stuck run must be NaN
    assert math.isnan(cleaned[1])


def test_step3_no_stuck_below_window():
    """A run shorter than stuck_window should not be flagged."""
    req = _make_request(freq=3600, end="2026-01-01T12:00:00Z")
    grid = _grid(req)

    values = np.arange(len(grid), dtype=float)
    values[2:7] = 42.0   # run length 5, window=10
    anomalies = []

    _, _, stuck_count = _step3_dynamic(values, grid, "T", anomalies, stuck_window=10)
    assert stuck_count == 0


# ─── Step 4: Imputation ───────────────────────────────────────────────────────


def test_step4_linear_short_gap():
    """Short gaps (≤ 3) should be linearly interpolated."""
    req = _make_request(freq=3600, end="2026-01-01T05:00:00Z")
    grid = _grid(req)

    values = np.array([0.0, np.nan, np.nan, 3.0, 4.0, 5.0], dtype=float)
    anomalies = []

    imputed, long_gaps = _step4_impute(values, grid, "T", anomalies, allow_look_ahead=True)

    assert long_gaps == 0
    assert imputed[1] == pytest.approx(1.0, abs=0.01)
    assert imputed[2] == pytest.approx(2.0, abs=0.01)
    assert all(a.action_taken == "linear_interpolated" for a in anomalies if a.anomaly_type == "missing")


def test_step4_long_gap_not_filled():
    """Gaps > 30 should not be filled."""
    req = _make_request(freq=3600, end="2026-01-03T00:00:00Z")  # 48-hour window
    grid = _grid(req)

    n = len(grid)
    values = np.full(n, np.nan)
    values[0] = 10.0
    values[-1] = 20.0
    # Gap between index 1 and n-2 is 47 points → long gap
    anomalies = []

    imputed, long_gaps = _step4_impute(values, grid, "T", anomalies, allow_look_ahead=True)

    assert long_gaps >= 1
    # Interior should still be NaN
    assert math.isnan(imputed[n // 2])


def test_step4_forward_fill_only():
    """With allow_look_ahead=False, only forward-fill should be used."""
    req = _make_request(freq=3600, end="2026-01-01T04:00:00Z")
    grid = _grid(req)

    values = np.array([5.0, np.nan, np.nan, np.nan, np.nan], dtype=float)
    anomalies = []

    imputed, _ = _step4_impute(values, grid, "T", anomalies, allow_look_ahead=False)

    # All NaNs should be forward-filled with 5.0
    assert all(imputed[i] == pytest.approx(5.0) for i in range(1, 5))
    assert all(a.action_taken == "forward_filled" for a in anomalies)


# ─── Full pipeline integration ────────────────────────────────────────────────


def test_pipeline_perfect_data():
    """Perfect SCADA data → score == 100, no anomalies."""
    req = _make_request(
        tag_ids=["TAG_A"],
        start="2026-01-01T00:00:00Z",
        end="2026-01-01T01:00:00Z",
        freq=300,
    )
    pipeline = DataQualityPipeline(req)

    grid_ms = pipeline._grid_ms.tolist()
    raw = [[ts, 100.0 + i * 0.1] for i, ts in enumerate(grid_ms)]
    raw_payloads = {"TAG_A": raw}

    response = pipeline.run(raw_payloads)

    assert response.metrics_scoring.overall_quality_score == pytest.approx(100.0)
    assert response.metrics_scoring.tags["TAG_A"].duplicates_count == 0
    assert response.metrics_scoring.tags["TAG_A"].missing_points_count == 0
    assert len([a for a in response.anomalies_log if a.anomaly_type != "missing"]) == 0


def test_pipeline_missing_tags_degraded_score():
    """Missing SCADA data for a tag → score below 100."""
    req = _make_request(
        tag_ids=["MISSING_TAG"],
        start="2026-01-01T00:00:00Z",
        end="2026-01-01T01:00:00Z",
        freq=300,
    )
    pipeline = DataQualityPipeline(req)
    response = pipeline.run({"MISSING_TAG": []})

    assert response.metrics_scoring.overall_quality_score < 100.0
    assert response.metrics_scoring.tags["MISSING_TAG"].missing_points_count > 0


def test_pipeline_response_shape():
    """Response must contain all required top-level keys with correct types."""
    req = _make_request(
        tag_ids=["TAG_A", "TAG_B"],
        start="2026-01-01T00:00:00Z",
        end="2026-01-01T01:00:00Z",
        freq=600,
    )
    pipeline = DataQualityPipeline(req)
    grid_ms = pipeline._grid_ms.tolist()

    raw_payloads = {
        "TAG_A": [[ts, float(i)] for i, ts in enumerate(grid_ms)],
        "TAG_B": [[ts, float(i) * 2] for i, ts in enumerate(grid_ms)],
    }

    response = pipeline.run(raw_payloads)

    assert response.metadata.total_tags_processed == 2
    assert "TAG_A" in response.metrics_scoring.tags
    assert "TAG_B" in response.metrics_scoring.tags
    assert isinstance(response.cleaned_data, list)
    assert len(response.cleaned_data) == len(grid_ms)
    assert "timestamp" in response.cleaned_data[0]
    assert "TAG_A" in response.cleaned_data[0]


def test_pipeline_custom_weights():
    """Custom weights should produce a different score from defaults."""
    req_default = _make_request(freq=3600, end="2026-01-01T10:00:00Z")
    req_strict = AssessRequest(
        **{"from": "2026-01-01T00:00:00Z"},
        object_ref="TAG_A",
        to="2026-01-01T10:00:00Z",
        step=3600,
        allow_look_ahead=True,
        weights=ScoringWeights(w_missing=2.0),  # stricter penalty
    )

    pipeline_default = DataQualityPipeline(req_default)
    pipeline_strict = DataQualityPipeline(req_strict)

    # Inject 2 gaps
    grid_ms = pipeline_default._grid_ms.tolist()
    full_data = [[ts, 100.0] for ts in grid_ms]
    partial_data = [row for i, row in enumerate(full_data) if i not in {2, 5}]

    r_default = pipeline_default.run({"TAG_A": partial_data})
    r_strict = pipeline_strict.run({"TAG_A": partial_data})

    assert r_strict.metrics_scoring.overall_quality_score <= r_default.metrics_scoring.overall_quality_score


# ─── Request schema validation ────────────────────────────────────────────────


def test_request_end_before_start_raises():
    with pytest.raises(Exception):
        AssessRequest(
            **{"from": "2026-01-01T01:00:00Z"},
            object_ref="T",
            to="2026-01-01T00:00:00Z",   # to < from → must raise
            step=3600,
        )


def test_request_zero_frequency_raises():
    with pytest.raises(Exception):
        AssessRequest(
            **{"from": "2026-01-01T00:00:00Z"},
            object_ref="T",
            to="2026-01-02T00:00:00Z",
            step=0,   # zero step → must raise
        )


def test_request_new_wire_format_iso():
    """New wire format with ISO strings should parse correctly."""
    req = AssessRequest(
        **{"from": "2026-01-01T00:00:00Z"},
        object_ref="/path/to/archive",
        to="2026-01-01T06:00:00Z",
        step=3600,
    )
    assert req.tag_ids == ["/path/to/archive"]
    assert req.expected_frequency == 3600
    assert req.start_time == datetime(2026, 1, 1, 0, tzinfo=timezone.utc)
    assert req.end_time == datetime(2026, 1, 1, 6, tzinfo=timezone.utc)


def test_request_new_wire_format_ms_timestamps():
    """from/to as Unix millisecond timestamps should parse correctly."""
    start_ms = 1767225600000   # 2026-01-01T00:00:00Z
    end_ms = 1767247200000     # 2026-01-01T06:00:00Z
    req = AssessRequest(
        **{"from": start_ms},
        object_ref="ARCHIVE_1",
        to=end_ms,
        step=3600,
    )
    assert req.tag_ids == ["ARCHIVE_1"]
    assert req.start_time == datetime(2026, 1, 1, 0, tzinfo=timezone.utc)
    assert req.end_time == datetime(2026, 1, 1, 6, tzinfo=timezone.utc)


def test_request_empty_from_to_defaults():
    """Empty from/to strings should produce sensible defaults (no error)."""
    req = AssessRequest(
        **{"from": ""},
        object_ref="TAG_X",
        to="",
        step=3600,
    )
    # to defaults to current hour, from defaults to to - 24 steps
    assert req.end_time is not None
    assert req.start_time is not None
    assert req.end_time > req.start_time
    assert (req.end_time - req.start_time).total_seconds() == 3600 * 24


def test_request_object_ref_list():
    """object_ref as a list should populate tag_ids with all entries."""
    req = AssessRequest(
        **{"from": "2026-01-01T00:00:00Z"},
        object_ref=["TAG_A", "TAG_B", "TAG_C"],
        to="2026-01-01T12:00:00Z",
        step=3600,
    )
    assert req.tag_ids == ["TAG_A", "TAG_B", "TAG_C"]
