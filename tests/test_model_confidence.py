import sys
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from api.broker.tasks.predict import _build_result


def _series_fixture() -> tuple[list[np.ndarray], list[np.ndarray]]:
    timestamps = [np.array([1_700_000_000_000, 1_700_000_003_600], dtype=np.int64)]
    values = [np.array([100.0, 101.0], dtype=float)]
    return timestamps, values


def test_model_confidence_is_one_for_clean_input() -> None:
    timestamps, values = _series_fixture()
    preds = np.array([110.0, 111.5], dtype=float)
    pred_ts = np.array([1_700_000_007_200, 1_700_000_010_800], dtype=np.int64)

    result = _build_result(
        model=object(),
        is_matching=True,
        clip_negatives_to_0=False,
        timestamps=timestamps,
        values=values,
        preds=preds,
        pred_ts=pred_ts,
        planned_applied_count=0,
    )

    assert result["model_confidence"] == 1.0


def test_model_confidence_degrades_for_not_topical_and_partial_nan_output() -> None:
    timestamps, values = _series_fixture()
    preds = np.array([110.0, np.nan, 109.3], dtype=float)
    pred_ts = np.array([1_700_000_007_200, 1_700_000_010_800, 1_700_000_014_400], dtype=np.int64)

    result = _build_result(
        model=object(),
        is_matching=False,
        clip_negatives_to_0=False,
        timestamps=timestamps,
        values=values,
        preds=preds,
        pred_ts=pred_ts,
        planned_applied_count=0,
    )

    assert result["model_confidence"] == 0.5333


def test_model_confidence_can_drop_to_zero_for_invalid_output() -> None:
    timestamps, values = _series_fixture()
    preds = np.array([np.nan, np.nan], dtype=float)
    pred_ts = np.array([1_700_000_007_200, 1_700_000_010_800], dtype=np.int64)

    result = _build_result(
        model=None,
        is_matching=False,
        clip_negatives_to_0=False,
        timestamps=timestamps,
        values=values,
        preds=preds,
        pred_ts=pred_ts,
        planned_applied_count=0,
    )

    assert result["message"]
    assert result["model_confidence"] == 0.0
