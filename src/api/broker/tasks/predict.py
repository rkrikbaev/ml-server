# Mariya Polkovnikova
# 2026.03.17, 11:14 AM


from typing import Dict, Any, Optional
from numpy import maximum, isnan, array
import numpy as np

import logging

from api import HTTPStatuses, HTTPMessages
from api.collector import get_cmms_client, get_historical_data_client, get_weather_client
from api.forecast import (
    QDS,
    init_model,
    count_input_qds,
    evaluate_input_quality,
    predict,
    load_model_config,
)
logger = logging.getLogger(__name__)


def _mode_from_step(step_ms: int) -> str:
    """Derive forecast mode from step in milliseconds."""
    if step_ms < 86_400_000:
        return "short"
    elif step_ms >= 2_419_200_000:
        return "long"
    return "medium"


async def _get_weather_payload(
    config: Any,
    output_range: int,
) -> Optional[Dict[str, Any]]:
    """Fetch weather forecast when model config provides coordinates."""
    if config.weather_lat is None or config.weather_lon is None:
        return None

    hours = config.weather_hours or max(output_range, 1)

    try:
        return await get_weather_client(getattr(config, "weather_url", None)).get_forecast(
            lat=config.weather_lat,
            lon=config.weather_lon,
            hours=hours,
            units=config.weather_units,
        )
    except Exception:
        return None


async def _get_historical_data_payload(
    mode: str,
    config: Any,
    step: int,
    online: bool,
) -> Any:
    """Fetch primary load history from the current historical-data client."""
    return await get_historical_data_client().fetch_model_data(
        mode=mode,
        archives=config.archives,
        step=step,
        online=online,
        historical_data_url=config.historical_data_url,
        request_overrides=config.historical_data_request_overrides,
    )


async def _get_planned_adjustments(
    mode: str,
    config: Any,
    step_ms: int,
) -> Optional[Dict[int, float]]:
    """Fetch CMMS planned adjustments as {timestamp_ms: reduction_value}."""
    if not config.cmms_url:
        return None

    try:
        payload = await get_cmms_client().fetch_planned_series(
            mode=mode,
            step_ms=step_ms,
            cmms_url=config.cmms_url,
            request_overrides=config.cmms_request_overrides,
        )
    except Exception as error:
        logger.warning("CMMS planned-data fetch failed for model_id source=%s: %s", config.cmms_url, error)
        return None

    if isinstance(payload, dict):
        if payload.get("status", 0) >= 400:
            logger.warning("CMMS planned-data source unavailable: %s", payload)
            return None
        if payload:
            logger.info("CMMS planned-data loaded from %s points=%s", config.cmms_url, len(payload))
            return payload

    return None


def _apply_planned_adjustments(
    preds: Any,
    pred_ts: Any,
    planned_adjustments: Optional[Dict[int, float]],
) -> tuple[Any, int]:
    """Apply planned reductions to forecast values by exact timestamp match."""
    if not planned_adjustments:
        return preds, 0

    adjusted = np.array(preds, copy=True, dtype=float)
    applied = 0

    for idx, ts in enumerate(pred_ts):
        reduction = planned_adjustments.get(int(ts))
        if reduction is None:
            continue

        adjusted[idx] = adjusted[idx] - float(reduction)
        applied += 1

    return adjusted, applied


async def logic(
    model_id: str,
    online: bool,
) -> Dict[str, Any]:
    """
    The core logic of the predict API.

    Loads model configuration from config.json, fetches input data from NDC,
    and runs the forecast model.

    :param str model_id: Relative path to the model under /workspace/models,
        or "none" for online (train-on-request) mode.
    :param bool online: True when model_id == "none".

    :return: Result dict for api_predict.
    :rtype: Dict[str, Any]
    """

    try:
        # --- Model config ---
        try:
            config = load_model_config(model_id)
        except Exception:
            return HTTPMessages.model_config_not_found(model_id)

        step = config.step * 1000                                  # seconds → ms
        output_range = config.output_range * 3_600_000 // step    # hours → steps
        mode = _mode_from_step(step)

        # --- HISTORICAL DATA ---
        output = await _get_historical_data_payload(mode, config, step, online)
        if isinstance(output, dict):
            return output

        timestamp, value, qds = output[0], output[1], output[2]
        del output

        # Guard: abort if NDC returned no data
        if not timestamp or not value or len(timestamp[0]) == 0:
            return HTTPMessages.model_launch_aborted_no_data()

        # --- Model initialization ---
        model = init_model(model_id, step, config.use_dynamic_normalization)

        # --- Weather ---
        weather_data = await _get_weather_payload(config, output_range)
        if weather_data is not None:
            weather_hourly = weather_data.get("hourly") if isinstance(weather_data, dict) else None
            logger.info(
                "Weather payload loaded for model_id=%s from %s lat=%s lon=%s hours=%s points=%s",
                model_id,
                getattr(config, "weather_url", None),
                config.weather_lat,
                config.weather_lon,
                config.weather_hours or max(output_range, 1),
                len(weather_hourly) if isinstance(weather_hourly, list) else 0,
            )

        # --- RZ / CMMS ---
        df_rz = None
        logger.debug("RZ collector is not wired in the current pipeline; continuing without external RZ data")

        # --- Forecast ---
        try:
            preds, pred_ts, is_matching = predict(
                y=value,
                timestamps=timestamp,
                model=model,
                step=step,
                output_range=output_range,
                online=online,
                df_rz_melt=df_rz,
                weather_data=weather_data,
            )
        except Exception as e:
            return HTTPMessages.unprocessable_entity_forecast(str(e))

        # --- CMMS planned postprocessing ---
        planned_adjustments = await _get_planned_adjustments(mode, config, step)
        preds, planned_applied_count = _apply_planned_adjustments(preds, pred_ts, planned_adjustments)
        if planned_applied_count:
            logger.info(
                "Applied CMMS planned reductions for model_id=%s points=%s",
                model_id,
                planned_applied_count,
            )

        # --- QDS assessment ---
        critical_freq, non_critical_freq = count_input_qds(timestamp, value, qds)
        input_qds, input_reason = evaluate_input_quality(critical_freq, non_critical_freq)

        return HTTPMessages.ok_done(
            _build_result(
                model,
                is_matching,
                input_qds,
                input_reason,
                config.clip_negatives_to_0,
                preds,
                pred_ts,
                planned_applied_count,
            )
        )

    except Exception as e:
        return HTTPMessages.internal_server_error(str(e))


def _build_result(
    model: Any,
    is_matching: bool,
    input_qds: int,
    input_reason: str,
    clip_negatives_to_0: bool,
    preds: Any,
    pred_ts: Any,
    planned_applied_count: int,
) -> Dict[str, Any]:
    """
    Build the final forecast result payload.

    :param Any model: Initialized model instance (or None if loading failed).
    :param bool is_matching: Whether input data matches the training distribution.
    :param int input_qds: QDS score for the input data.
    :param str input_reason: Human-readable reason for the input QDS.
    :param bool clip_negatives_to_0: Whether to floor predictions at 0.
    :param Any preds: Raw predictions array.
    :param Any pred_ts: Prediction timestamps array.

    :return: Forecast result payload.
    :rtype: Dict[str, Any]
    """

    base_pred_qds = QDS.BASE
    status = HTTPStatuses.SC200
    reason = ""

    if model is None:
        base_pred_qds = QDS.INVALID
        status = HTTPStatuses.SC422
        reason = f"Model loading error, using online model (QDS={base_pred_qds})"

    if not is_matching and status == HTTPStatuses.SC200:
        base_pred_qds = max(base_pred_qds, QDS.NOT_TOPICAL)
        status = HTTPStatuses.SC422
        reason = f"Input data does not match training distribution (QDS={base_pred_qds})"

    if status == HTTPStatuses.SC200 and input_qds:
        status = input_qds
        reason = input_reason

    final_qds = max(base_pred_qds, input_qds)

    if clip_negatives_to_0:
        preds = maximum(preds, 0)

    output = [
        [int(ts), None if isnan(p) else round(float(p), 1), int(final_qds)]
        for ts, p in zip(pred_ts, preds)
    ]

    return {
        "message": "" if status == HTTPStatuses.SC200 else reason,
        "output": output,
        "quality": final_qds,
        "model_confidence": 1.0,
        "planned_adjustments_applied": planned_applied_count,
    }
