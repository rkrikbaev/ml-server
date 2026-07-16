# Tests: data quality assessment integration in the predict pipeline
#
# Covers _assess_data_quality() and the data_quality key in _build_result().

import importlib.util
import math
import sys
import pathlib
import types

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Load src/api/broker/tasks/predict.py directly (bypasses the package
# __init__ chain that pulls in taskiq_redis, prophet, etc.)
# ---------------------------------------------------------------------------
ROOT = pathlib.Path(__file__).resolve().parents[1]

# Provide the two runtime imports that predict.py needs at module level
_stub_messages = types.ModuleType("api")
_stub_messages.HTTPStatuses = None
_stub_messages.HTTPMessages = types.SimpleNamespace(
    ok_done=lambda x: x,
    service_unavailable_mlflow=lambda m: {"status": 503, "message": m},
    model_launch_aborted_no_data=lambda: {"status": 503},
    unprocessable_entity_forecast=lambda m: {"status": 422, "message": m},
    internal_server_error=lambda m: {"status": 500, "message": m},
)
sys.modules.setdefault("api", _stub_messages)
# stub heavy sub-packages so their imports don't fail
_collector_stub = types.ModuleType("api.collector")
_collector_stub.get_cmms_client = None
_collector_stub.get_historical_data_client = None
_collector_stub.get_weather_client = None
sys.modules["api.collector"] = _collector_stub

_adapters_stub = types.ModuleType("adapters")
_adapters_stub.init_model = None
_adapters_stub.predict = None
_adapters_stub.load_model_config = None
_adapters_stub.get_model_provider = None
sys.modules["adapters"] = _adapters_stub

for _mod in ("api.collector.historical_client", "taskiq_redis"):
    sys.modules.setdefault(_mod, types.ModuleType(_mod))

# Add repo root so `lib.pipeline` resolves
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location(
    "predict_module",
    ROOT / "src" / "api" / "broker" / "tasks" / "predict.py",
)
_predict_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_predict_mod)

_assess_data_quality = _predict_mod._assess_data_quality
_build_result        = _predict_mod._build_result


# ─── Helpers ────────────────────────────────────────────────────────────────


def _make_hourly_arrays(n: int = 72, step_ms: int = 3_600_000, base: float = 300.0):
    """Return (timestamps_list, values_list) with a single clean archive."""
    from datetime import datetime, timezone, timedelta
    now = datetime.now(tz=timezone.utc).replace(minute=0, second=0, microsecond=0)
    start = now - timedelta(milliseconds=(n - 1) * step_ms)
    ts = np.array([
        int((start + timedelta(milliseconds=i * step_ms)).timestamp() * 1000)
        for i in range(n)
    ], dtype=np.int64)
    vals = np.full(n, base, dtype=float)
    return [ts], [vals]


# ─── _assess_data_quality ────────────────────────────────────────────────────


class TestAssessDataQuality:

    def test_returns_dict_on_clean_data(self):
        ts, vals = _make_hourly_arrays()
        result = _assess_data_quality(
            archives=["/path/to/arch"],
            timestamps=ts,
            values=vals,
            step_ms=3_600_000,
        )
        assert isinstance(result, dict)

    def test_overall_score_in_range(self):
        ts, vals = _make_hourly_arrays()
        result = _assess_data_quality(["/path/to/arch"], ts, vals, 3_600_000)
        score = result["overall_quality_score"]
        assert 0.0 <= score <= 100.0

    def test_required_keys_present(self):
        ts, vals = _make_hourly_arrays()
        result = _assess_data_quality(["/path/to/arch"], ts, vals, 3_600_000)
        for key in ("overall_quality_score", "window_start", "window_end",
                    "elapsed_seconds", "anomalies_count", "tags"):
            assert key in result, f"missing key: {key}"

    def test_tag_stats_keys(self):
        ts, vals = _make_hourly_arrays()
        result = _assess_data_quality(["/arch/one"], ts, vals, 3_600_000)
        tag_stats = result["tags"]["/arch/one"]
        for key in ("quality_score", "total_expected_points", "missing_points_count",
                    "duplicates_count", "outliers_count", "stuck_sequences_count",
                    "rate_of_change_count", "long_gaps_count"):
            assert key in tag_stats, f"missing tag key: {key}"

    def test_detects_spike(self):
        ts, vals = _make_hourly_arrays(n=72)
        vals[0] = vals[0].copy()
        vals[0][30] = 999_999.0   # massive spike
        result = _assess_data_quality(["/arch"], ts, vals, 3_600_000)
        assert result["tags"]["/arch"]["outliers_count"] >= 1

    def test_detects_missing(self):
        ts_arr = ts_orig, = _make_hourly_arrays(n=72)[0]
        vals_arr = v_orig, = _make_hourly_arrays(n=72)[1]
        # Remove 4 points to create a gap
        ts_short  = np.delete(ts_orig,  [20, 21, 22, 23])
        vals_short = np.delete(v_orig,  [20, 21, 22, 23])
        result = _assess_data_quality(["/arch"], [ts_short], [vals_short], 3_600_000)
        assert result["tags"]["/arch"]["missing_points_count"] >= 4

    def test_multiple_archives(self):
        ts1, v1 = _make_hourly_arrays(n=48, base=200.0)
        ts2, v2 = _make_hourly_arrays(n=48, base=400.0)
        result = _assess_data_quality(
            archives=["/arch/a", "/arch/b"],
            timestamps=ts1 + ts2,
            values=v1 + v2,
            step_ms=3_600_000,
        )
        assert len(result["tags"]) == 2
        assert "/arch/a" in result["tags"]
        assert "/arch/b" in result["tags"]

    def test_returns_none_on_empty_timestamps(self):
        result = _assess_data_quality(
            archives=["/arch"],
            timestamps=[np.array([], dtype=np.int64)],
            values=[np.array([], dtype=float)],
            step_ms=3_600_000,
        )
        assert result is None

    def test_non_fatal_on_bad_step(self):
        ts, vals = _make_hourly_arrays()
        # step_ms=0 would cause a divide-by-zero inside AssessRequest; must not raise
        result = _assess_data_quality(["/arch"], ts, vals, step_ms=0)
        assert result is None   # failure is absorbed, not propagated

    def test_5min_step(self):
        step_ms = 300_000
        ts, vals = _make_hourly_arrays(n=288, step_ms=step_ms)
        result = _assess_data_quality(["/arch"], ts, vals, step_ms)
        assert result is not None
        assert result["tags"]["/arch"]["total_expected_points"] >= 1


# ─── _build_result with data_quality ────────────────────────────────────────


class TestBuildResultDataQuality:

    def _minimal_result(self, dq=None):
        n = 10
        ts   = [np.arange(n, dtype=np.int64) * 3_600_000]
        vals = [np.full(n, 300.0)]
        pred_ts = np.arange(n, dtype=np.int64) * 3_600_000
        preds   = np.full(n, 300.0)
        return _build_result(
            model=None,
            is_matching=True,
            clip_negatives_to_0=False,
            timestamps=ts,
            values=vals,
            preds=preds,
            pred_ts=pred_ts,
            data_quality=dq,
        )

    def test_data_quality_included_when_provided(self):
        dq = {"overall_quality_score": 95.0, "tags": {}}
        result = self._minimal_result(dq=dq)
        assert "data_quality" in result
        assert result["data_quality"]["overall_quality_score"] == 95.0

    def test_data_quality_absent_when_none(self):
        result = self._minimal_result(dq=None)
        assert "data_quality" not in result

    def test_existing_keys_unaffected(self):
        dq = {"overall_quality_score": 80.0, "tags": {}}
        result = self._minimal_result(dq=dq)
        for key in ("output", "model_confidence", "input_statistics", "output_statistics"):
            assert key in result
