# Mariya Polkovnikova
# 2026.03.17, 11:14 AM


from typing import List, Dict, Any
from numpy import maximum, isnan

from api import HTTPStatuses, HTTPMessages
from api.forecast import (
    QDS,
    init_model,
    count_input_qds,
    evaluate_input_quality,
    predict
)
from api.send import get_data_from_arvhives, get_data_from_rz


async def logic(
    mode: str,
    model_path: str,
    archives: List[str],
    step: int,
    output_range: int,
    online: bool,
    clip_negatives_to_0: bool,
    use_dynamic_normalization: bool
) -> Dict[str, Any]:
    """
    The core logic of the predict API.

    :param str mode: Mode of forecast.
    :param str model_path: Path to model directory.
    :param List[str] archives: List of archives.
    :param int step: Step in milliseconds.
    :param int output_range: Output range in milliseconds.
    :param bool online: Whether to use online forecast.
    :param bool clip_negatives_to_0: Whether to clip negative predictions to
        0.
    :param bool use_dynamic_normalization: Whether to use dynamic
        normalization.

    :return: Result for api_predict.
    :rtype: Dict[str, Any]
    """

    try:
        # NDC
        output = await get_data_from_arvhives(mode, archives, step, online)
        if isinstance(output, dict): return output

        # Get: timestamp, value, qds
        timestamp, value, qds = output[0], output[1], output[2]
        del output

        # Model Initialization
        model = init_model(model_path, step, use_dynamic_normalization)

        # RZ
        mes = model_path.split("/")[3] if model_path else None
        df_rz = await get_data_from_rz(model, mes, timestamp[0], step, output_range)
        if isinstance(df_rz, dict): return df_rz

        # Primary
        try:
            preds, pred_ts, is_matching = predict(
                y=value,
                timestamps=timestamp,
                model=model,
                step=step,
                output_range=output_range,
                online=online,
                df_rz_melt=df_rz
            )
        except Exception as e:  # 422
            return HTTPMessages.unprocessable_entity_forecast(str(e))

        # QDS Assessment
        critical_freq, non_critical_freq = count_input_qds(timestamp, value, qds)
        input_qds, input_reason = evaluate_input_quality(critical_freq, non_critical_freq)

        return HTTPMessages.ok_done(
            result(
                model,
                is_matching,
                input_qds,
                input_reason,
                clip_negatives_to_0,
                preds,
                pred_ts
            )
        )

    except Exception as e:  # 500
        return HTTPMessages.internal_server_error(str(e))


def result(
    model: Any,
    is_matching: bool,
    input_qds: int,
    input_reason: str,
    clip_negatives_to_0: bool,
    preds: Any,
    pred_ts: Any
) -> Dict[str, Any]:
    """
    Return result for api_predict.

    :param Any model: Model instance.
    :param bool is_matching: Whether the input data matches the training
        distribution.
    :param int input_qds: Input QDS.
    :param str input_reason: Input reason.
    :param bool clip_negatives_to_0: Whether to clip negative predictions to
        0.
    :param Any preds: Predictions.
    :param Any pred_ts: Prediction timestamps.

    :return: Result for api_predict.
    :rtype: Dict[str, Any]
    """

    base_pred_qds = QDS.BASE
    status = HTTPStatuses.SC200
    reason = ""

    # Model
    if model is None:  # 422
        base_pred_qds = QDS.INVALID
        status = HTTPStatuses.SC422
        reason = f"Model loading error, using online model (QDS={base_pred_qds})"

    # Primary
    if not is_matching and status == HTTPStatuses.SC200:  # 422
        base_pred_qds = max(base_pred_qds, QDS.NOT_TOPICAL)
        status = HTTPStatuses.SC422
        reason = f"Input data does not match training distribution (QDS={base_pred_qds})"

    # Input issues (only if no higher-priority status)
    if status == HTTPStatuses.SC200 and input_qds:
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
    msg = "" if status == HTTPStatuses.SC200 else reason
    return {
        "message": msg,
        "output": result,
        "quality": final_qds,
        "model_confidence": 1.0
    }
