# Mariya Polkovnikova
# 2026.03.15, 01:48 PM


from typing import Any

from numpy import maximum, isnan

from api.utils import QDS
from api.message import HTTPMessages


def get_api_predict(
    model: Any,
    is_matching: bool,
    input_qds: int,
    input_reason: str,
    clip_negatives_to_0: bool,
    preds: Any,
    pred_ts: Any
):
    base_pred_qds = QDS.BASE
    status = HTTPMessages.SC200
    reason = ""

    # Model
    if model is None:  # 422
        base_pred_qds = QDS.INVALID
        status = HTTPMessages.SC422
        reason = f"Model loading error, using online model (QDS={base_pred_qds})"

    # Primary
    if not is_matching and status == HTTPMessages.SC200:  # 422
        base_pred_qds = max(base_pred_qds, QDS.NOT_TOPICAL)
        status = HTTPMessages.SC422
        reason = f"Input data does not match training distribution (QDS={base_pred_qds})"

    # Input issues (only if no higher-priority status)
    if status == HTTPMessages.SC200 and input_qds:
        status = input_qds
        reason = input_reason

    # Final QDS
    final_qds = max(base_pred_qds, input_qds)

    # Post-Processing
    if clip_negatives_to_0:
        preds = maximum(preds, 0)

    result = [
        [int(ts), None if isnan(p) else round(float(p), 1), int(final_qds)]
        for ts, p in zip(pred_ts, preds)
    ]

    # Finalize response
    msg = "" if status == HTTPMessages.SC200 else reason
    return {
        "task_output": result,
        "quality": final_qds,
        "message": msg,
        "model_confidence": 1.0
    }
