"""
Tests for SolarAdapter — solar generation forecasting adapter.

Covers:
  - No-model irradiance-naive fallback
  - Weather feature extraction from hourly payload
  - Cyclic time feature correctness
  - Feature-row shape matches expected_features
  - Predictions are clipped to >= 0
  - Graceful handling of missing / partial weather data
  - model_type="solar" accepted by ModelConfig validator
  - init_model returns SolarAdapter for model_type="solar"
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from adapters.adapters import SolarAdapter
from adapters.base_interface import PredictionInput, PredictionOutput
from adapters.config import ModelConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

STEP_MS = 3_600_000  # 1 hour


def _make_input(
    n_history: int = 48,
    output_range: int = 24,
    weather_data=None,
    base_ts: int = 1_700_000_000_000,
) -> PredictionInput:
    features = np.linspace(0.0, 100.0, n_history)
    timestamps = [base_ts + i * STEP_MS for i in range(n_history)]
    return PredictionInput(
        features=features,
        metadata={
            "step": STEP_MS,
            "output_range": output_range,
            "timestamps": timestamps,
            "weather_data": weather_data,
        },
    )


def _make_hourly_weather(n: int = 24) -> dict:
    return {
        "hourly": [
            {
                "solar_radiation": float(i * 40),   # 0..920 W/m²
                "temperature": 20.0,
                "cloud_cover": 10.0,
            }
            for i in range(n)
        ]
    }


# ---------------------------------------------------------------------------
# No-model (irradiance-naive) fallback
# ---------------------------------------------------------------------------


def test_naive_fallback_no_weather():
    adapter = SolarAdapter(model_name="solar_test")
    inp = _make_input(weather_data=None)
    out = adapter.predict(inp)
    assert isinstance(out, PredictionOutput)
    assert len(out.predictions) == 24
    # Without weather all values are NaN
    assert all(np.isnan(v) for v in out.predictions)


def test_naive_fallback_with_weather_scales_by_ghi():
    adapter = SolarAdapter(model_name="solar_test")
    weather = _make_hourly_weather(24)
    inp = _make_input(n_history=48, output_range=24, weather_data=weather)
    out = adapter.predict(inp)

    assert len(out.predictions) == 24
    # First hour: GHI=0 → generation=0
    assert out.predictions[0] == pytest.approx(0.0)
    # Subsequent hours: proportional to GHI
    for i in range(1, 24):
        expected_scale = min(i * 40 / 1000.0, 1.0)
        last_nonzero = 100.0  # last value in linspace(0, 100, 48)
        assert out.predictions[i] == pytest.approx(last_nonzero * expected_scale, rel=1e-4)


def test_naive_fallback_all_zeros_history():
    adapter = SolarAdapter(model_name="solar_test")
    weather = _make_hourly_weather(24)
    inp = PredictionInput(
        features=np.zeros(24),
        metadata={
            "step": STEP_MS,
            "output_range": 24,
            "timestamps": list(range(24)),
            "weather_data": weather,
        },
    )
    out = adapter.predict(inp)
    assert all(v == pytest.approx(0.0) for v in out.predictions)


# ---------------------------------------------------------------------------
# Weather feature extraction
# ---------------------------------------------------------------------------


def test_extract_weather_at_step_returns_correct_values():
    adapter = SolarAdapter()
    weather = {
        "hourly": [
            {"solar_radiation": 500.0, "temperature": 25.0, "cloud_cover": 30.0},
            {"solar_radiation": 600.0, "temperature": 26.0, "cloud_cover": 20.0},
        ]
    }
    vec0 = adapter._extract_weather_at_step(weather, 0)
    assert vec0[0] == pytest.approx(500.0)
    assert vec0[1] == pytest.approx(25.0)
    assert vec0[2] == pytest.approx(30.0)

    vec1 = adapter._extract_weather_at_step(weather, 1)
    assert vec1[0] == pytest.approx(600.0)


def test_extract_weather_out_of_bounds_returns_zeros():
    adapter = SolarAdapter()
    weather = {"hourly": [{"solar_radiation": 100.0, "temperature": 20.0, "cloud_cover": 5.0}]}
    vec = adapter._extract_weather_at_step(weather, step_index=99)
    np.testing.assert_array_equal(vec, np.zeros(SolarAdapter.N_WEATHER_FEATURES))


def test_extract_weather_none_returns_zeros():
    adapter = SolarAdapter()
    vec = adapter._extract_weather_at_step(None, 0)
    np.testing.assert_array_equal(vec, np.zeros(SolarAdapter.N_WEATHER_FEATURES))


# ---------------------------------------------------------------------------
# Cyclic time features
# ---------------------------------------------------------------------------


def test_cyclic_time_features_midnight():
    # Unix epoch midnight UTC: 1970-01-01T00:00:00Z  (ms=0)
    vec = SolarAdapter._cyclic_time_features(0)
    assert len(vec) == SolarAdapter.N_TIME_FEATURES
    # hour=0: sin_h=0, cos_h=1
    assert vec[0] == pytest.approx(0.0, abs=1e-9)   # sin_hour
    assert vec[1] == pytest.approx(1.0, abs=1e-9)   # cos_hour


def test_cyclic_time_features_noon():
    # 1970-01-01T12:00:00Z
    ts_ms = 12 * 3600 * 1000
    vec = SolarAdapter._cyclic_time_features(ts_ms)
    # hour=12: sin(pi)≈0, cos(pi)=-1
    assert vec[0] == pytest.approx(0.0, abs=1e-9)   # sin_hour
    assert vec[1] == pytest.approx(-1.0, abs=1e-9)  # cos_hour


# ---------------------------------------------------------------------------
# Feature row shape
# ---------------------------------------------------------------------------


def test_feature_row_shape_matches_expected():
    adapter = SolarAdapter()
    series = np.linspace(10.0, 200.0, 72)
    weather = _make_hourly_weather(24)
    for expected in (20, 32, 50, 100):
        row = adapter._build_feature_row(series, 0, 1_700_000_000_000, weather, expected)
        assert row.shape == (1, expected), f"Failed for expected={expected}"


def test_feature_row_short_history_pads_with_last_value():
    adapter = SolarAdapter()
    series = np.array([5.0, 10.0])
    row = adapter._build_feature_row(series, 0, 1_700_000_000_000, None, expected_features=16)
    assert row.shape == (1, 16)
    # Lag portion should not contain NaN
    assert not np.any(np.isnan(row))


# ---------------------------------------------------------------------------
# Output clipping (solar cannot be negative)
# ---------------------------------------------------------------------------


def test_predictions_are_clipped_to_zero_with_mock_booster():
    """Booster returns negative values; SolarAdapter must clip them."""
    import xgboost as xgb  # noqa: F401 (skip test if not installed)

    mock_booster = MagicMock(spec=xgb.Booster)
    mock_booster.num_features.return_value = 10
    # Predict returns a negative value
    mock_booster.predict.return_value = np.array([-50.0])

    adapter = SolarAdapter(model_name="solar_clip_test", legacy_model=mock_booster)
    adapter.load()

    inp = _make_input(n_history=48, output_range=3)
    out = adapter.predict(inp)
    assert all(v >= 0.0 for v in out.predictions), "Negative predictions not clipped"


# ---------------------------------------------------------------------------
# Metadata in output
# ---------------------------------------------------------------------------


def test_output_metadata_model_type_is_solar():
    adapter = SolarAdapter()
    out = adapter.predict(_make_input(weather_data=_make_hourly_weather()))
    assert out.metadata is not None
    assert out.metadata.get("model_type") == "solar"


def test_output_metadata_weather_used_true_when_provided():
    adapter = SolarAdapter()
    out = adapter.predict(_make_input(weather_data=_make_hourly_weather()))
    assert out.metadata["weather_used"] is True


def test_output_metadata_weather_used_false_when_missing():
    adapter = SolarAdapter()
    out = adapter.predict(_make_input(weather_data=None))
    assert out.metadata["weather_used"] is False


# ---------------------------------------------------------------------------
# ModelConfig validates model_type="solar"
# ---------------------------------------------------------------------------


def test_model_config_accepts_solar_type():
    cfg = ModelConfig(
        model_type="solar",
        step=3600,
        output_range=24,
        sources={"historical_data": {"type": "historical_data", "url": "http://scada/api"}},
    )
    assert cfg.model_type == "solar"


def test_model_config_accepts_solar_fallback():
    cfg = ModelConfig(
        model_type="xgb",
        fallback="solar",
        step=3600,
        output_range=24,
        sources={"historical_data": {"type": "historical_data", "url": "http://scada/api"}},
    )
    assert cfg.fallback == "solar"


# ---------------------------------------------------------------------------
# init_model dispatches to SolarAdapter
# ---------------------------------------------------------------------------


def test_init_model_solar_no_file_with_fallback(tmp_path):
    """When xgb_model.json is absent and fallback=naive, should return NaiveAdapter."""
    from adapters.model import init_model
    from adapters.adapters import NaiveAdapter

    # Empty model dir — no xgb_model.json
    model_dir = tmp_path / "solar_model"
    model_dir.mkdir()

    model = init_model(
        model_rel_dirpath=str(model_dir),
        step=STEP_MS,
        fallback="naive",
        model_type="solar",
    )
    assert isinstance(model, NaiveAdapter)


def test_init_model_solar_normalizes_type():
    """_normalize_model_type should accept 'solar'."""
    from adapters.model import _normalize_model_type
    assert _normalize_model_type("solar") == "solar"
    assert _normalize_model_type("SOLAR") == "solar"
