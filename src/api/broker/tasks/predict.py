

from typing import Dict, Any, List, Optional
from numpy import maximum, isnan, array
import numpy as np

import logging

from api import HTTPStatuses, HTTPMessages
from api.collector import get_cmms_client, get_historical_data_client, get_weather_client
from adapters import (
    init_model,
    predict,
    load_model_config,
    get_model_provider,
)
from lib.pipeline import AssessRequest, DataQualityPipeline

logger = logging.getLogger(__name__)


def _safe_float(value: Any) -> Optional[float]:
    if value is None or np.isnan(value):
        return None
    return round(float(value), 4)


def _build_input_statistics(
    timestamps: Any,
    values: Any,
) -> Dict[str, Any]:
    flat_timestamps = np.concatenate([np.asarray(series, dtype=np.int64) for series in timestamps])
    flat_values = np.concatenate([np.asarray(series, dtype=float) for series in values])
    valid_values = flat_values[~np.isnan(flat_values)]

    return {
        "series_count": int(len(values)),
        "point_count": int(flat_values.size),
        "valid_point_count": int(valid_values.size),
        "start_timestamp": int(flat_timestamps.min()) if flat_timestamps.size else None,
        "end_timestamp": int(flat_timestamps.max()) if flat_timestamps.size else None,
        "min": _safe_float(valid_values.min()) if valid_values.size else None,
        "max": _safe_float(valid_values.max()) if valid_values.size else None,
        "mean": _safe_float(valid_values.mean()) if valid_values.size else None,
        "std": _safe_float(valid_values.std()) if valid_values.size else None,
    }


def _build_output_statistics(
    pred_ts: Any,
    preds: Any,
) -> Dict[str, Any]:
    pred_ts = np.asarray(pred_ts, dtype=np.int64)
    preds = np.asarray(preds, dtype=float)
    valid_preds = preds[~np.isnan(preds)]

    return {
        "point_count": int(preds.size),
        "valid_point_count": int(valid_preds.size),
        "start_timestamp": int(pred_ts.min()) if pred_ts.size else None,
        "end_timestamp": int(pred_ts.max()) if pred_ts.size else None,
        "min": _safe_float(valid_preds.min()) if valid_preds.size else None,
        "max": _safe_float(valid_preds.max()) if valid_preds.size else None,
        "mean": _safe_float(valid_preds.mean()) if valid_preds.size else None,
        "std": _safe_float(valid_preds.std()) if valid_preds.size else None,
    }


def _compute_model_confidence(
    preds: Any,
    is_matching: bool,
    model: Any,
) -> float:
    """Compute confidence in [0, 1] from model state and prediction completeness."""
    preds_arr = np.asarray(preds, dtype=float)
    if preds_arr.size == 0:
        return 0.0

    valid_ratio = float(np.isfinite(preds_arr).mean())
    confidence = 1.0

    if model is None:
        confidence -= 0.35

    if not is_matching:
        confidence -= 0.30

    confidence -= (1.0 - valid_ratio) * 0.50

    return round(float(np.clip(confidence, 0.0, 1.0)), 4)


def _assess_data_quality(
    archives: List[str],
    timestamps: List[np.ndarray],
    values: List[np.ndarray],
    step_ms: int,
) -> Optional[Dict[str, Any]]:
    """
    Run the data quality pipeline on model input data and return a compact summary.

    Parameters
    ----------
    archives    : SCADA archive names, same order as timestamps/values lists.
    timestamps  : Per-archive timestamp arrays (milliseconds).
    values      : Per-archive value arrays.
    step_ms     : Time step in milliseconds.

    Returns a dict ready to embed in the prediction response, or None on error.
    """
    try:
        step_s = step_ms // 1000

        # Reconstruct raw_payloads from model-data arrays
        raw_payloads: Dict[str, List] = {}
        for archive, ts_arr, val_arr in zip(archives, timestamps, values):
            raw_payloads[archive] = [
                [int(ts), float(v)]
                for ts, v in zip(ts_arr.tolist(), val_arr.tolist())
            ]

        # Derive the assessment window from the actual data
        all_ts = np.concatenate([ts for ts in timestamps if len(ts)])
        if all_ts.size == 0:
            return None
        from_ms = int(all_ts.min())
        to_ms   = int(all_ts.max())

        req = AssessRequest(
            **{"from": from_ms},
            object_ref=archives if len(archives) > 1 else archives[0],
            to=to_ms,
            step=step_s,
            allow_look_ahead=True,
        )
        result = DataQualityPipeline(req).run(raw_payloads)

        ms = result.metrics_scoring
        md = result.metadata

        tag_summary = {
            tag_id: {
                "quality_score":        st.quality_score,
                "total_expected_points": st.total_expected_points,
                "missing_points_count": st.missing_points_count,
                "duplicates_count":     st.duplicates_count,
                "outliers_count":       st.outliers_count,
                "stuck_sequences_count": st.stuck_sequences_count,
                "rate_of_change_count": st.rate_of_change_count,
                "long_gaps_count":      st.long_gaps_count,
            }
            for tag_id, st in ms.tags.items()
        }

        summary = {
            "overall_quality_score": ms.overall_quality_score,
            "window_start":    md.timestamp_start,
            "window_end":      md.timestamp_end,
            "elapsed_seconds": md.elapsed_seconds,
            "anomalies_count": len(result.anomalies_log),
            "tags":            tag_summary,
        }

        logger.info(
            "Data quality assessment: score=%.1f anomalies=%d tags=%d elapsed=%.3fs",
            ms.overall_quality_score,
            len(result.anomalies_log),
            len(ms.tags),
            md.elapsed_seconds,
        )
        for tag_id, st in ms.tags.items():
            logger.debug(
                "  %s: score=%.1f miss=%d dup=%d spikes=%d stuck=%d roc=%d long_gaps=%d",
                tag_id,
                st.quality_score,
                st.missing_points_count,
                st.duplicates_count,
                st.outliers_count,
                st.stuck_sequences_count,
                st.rate_of_change_count,
                st.long_gaps_count,
            )

        return summary

    except Exception as exc:
        logger.warning("Data quality assessment failed (non-fatal): %s", exc)
        return None


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
    config: Any,
    step: int,
    input_range: Optional[int],
    output_range: int,
    online: bool,
) -> Any:
    """Fetch primary load history from the current historical-data client."""
    return await get_historical_data_client().fetch_model_data(
        archives=config.archives,
        step=step,
        input_range=input_range,
        output_range=output_range,
        online=online,
        historical_data_url=config.historical_data_url,
        request_overrides=config.historical_data_request_overrides,
    )


# async def _get_planned_adjustments(
#     config: Any,
#     step_ms: int,
#     output_range: int,
# ) -> Optional[Dict[int, float]]:
#     """Fetch CMMS planned adjustments as {timestamp_ms: reduction_value}."""
#     if not config.cmms_url:
#         return None

#     try:
#         payload = await get_cmms_client().fetch_planned_series(
#             step_ms=step_ms,
#             output_range=output_range,
#             cmms_url=config.cmms_url,
#             request_overrides=config.cmms_request_overrides,
#         )
#     except Exception as error:
#         logger.warning("CMMS planned-data fetch failed for model_id source=%s: %s", config.cmms_url, error)
#         return None

#     if isinstance(payload, dict):
#         if payload.get("status", 0) >= 400:
#             logger.warning("CMMS planned-data source unavailable: %s", payload)
#             return None
#         if payload:
#             logger.info("CMMS planned-data loaded from %s points=%s", config.cmms_url, len(payload))
#             return payload

#     return None


# def _apply_planned_adjustments(
#     preds: Any,
#     pred_ts: Any,
#     planned_adjustments: Optional[Dict[int, float]],
# ) -> tuple[Any, int]:
#     """Apply planned reductions to forecast values by exact timestamp match."""
#     if not planned_adjustments:
#         return preds, 0

#     adjusted = np.array(preds, copy=True, dtype=float)
#     applied = 0

#     for idx, ts in enumerate(pred_ts):
#         reduction = planned_adjustments.get(int(ts))
#         if reduction is None:
#             continue

#         adjusted[idx] = adjusted[idx] - float(reduction)
#         applied += 1

#     return adjusted, applied


async def logic(
    model_id: str,
    online: bool,
    selector: Optional[str] = None,
) -> Dict[str, Any]:

    try:
        # --- Model sync/config ---
        bundle_path = None
        model_source = model_id
        if model_id != "none":
            sync_result = get_model_provider().sync_with_registry(model_id, selector)
            if sync_result.bundle_path is None:
                return HTTPMessages.service_unavailable_mlflow(
                    f"No cached MLflow bundle available for model_id={model_id} selector={sync_result.selector}"
                )
            bundle_path = sync_result.bundle_path
            if sync_result.model_path is not None:
                model_source = str(sync_result.model_path)
            else:
                return HTTPMessages.service_unavailable_mlflow(
                    f"MLflow bundle is missing model artifacts for model_id={model_id} selector={sync_result.selector}"
                )

        try:
            config = load_model_config(model_id, bundle_path=bundle_path, require_bundle=(model_id != "none"))
        except FileNotFoundError as error:
            if model_id != "none":
                return HTTPMessages.service_unavailable_mlflow(str(error))
            return HTTPMessages.model_config_not_found(model_id)
        except ValueError as error:
            if model_id != "none":
                return HTTPMessages.unprocessable_entity_forecast(
                    f"Invalid MLflow bundle config for model_id={model_id}: {error}"
                )
            return HTTPMessages.unprocessable_entity_forecast(str(error))

        step = config.step * 1000
        input_range = config.input_range
        output_range = config.output_range

        # --- HISTORICAL DATA ---
        output = await _get_historical_data_payload(config, step, input_range, output_range, online)
        if isinstance(output, dict):
            return output

        timestamp, value = output[0], output[1]
        del output

        # Guard: abort if NDC returned no data
        if not timestamp or not value or len(timestamp[0]) == 0:
            return HTTPMessages.model_launch_aborted_no_data()

        # --- Data quality assessment ---
        dq_summary = _assess_data_quality(
            archives=config.archives,
            timestamps=timestamp,
            values=value,
            step_ms=step,
        )

        # --- Model initialization ---
        model = init_model(model_source, step, config.use_dynamic_normalization, config.fallback, config.model_type)

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
        # planned_adjustments = await _get_planned_adjustments(config, step, output_range)
        # preds, planned_applied_count = _apply_planned_adjustments(preds, pred_ts, planned_adjustments)
        # if planned_applied_count:
        #     logger.info(
        #         "Applied CMMS planned reductions for model_id=%s points=%s",
        #         model_id,
        #         planned_applied_count,
        #     )

        mlflow_model_name = sync_result.model_id if model_id != "none" else None
        mlflow_model_version = sync_result.model_version if model_id != "none" else None

        return HTTPMessages.ok_done(
            _build_result(
                model,
                is_matching,
                config.clip_negatives_to_0,
                timestamp,
                value,
                preds,
                pred_ts,
                # planned_applied_count,
                mlflow_model_name,
                mlflow_model_version,
                dq_summary,
            )
        )

    except Exception as e:
        return HTTPMessages.internal_server_error(str(e))


def _build_result(
    model: Any,
    is_matching: bool,
    clip_negatives_to_0: bool,
    timestamps: Any,
    values: Any,
    preds: Any,
    pred_ts: Any,
    # planned_applied_count: int,
    mlflow_model_name: Optional[str] = None,
    mlflow_model_version: Optional[str] = None,
    data_quality: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Build the final forecast result payload.

    :param Any model: Initialized model instance (or None if loading failed).
    :param bool is_matching: Whether input data matches the training distribution.
    :param bool clip_negatives_to_0: Whether to floor predictions at 0.
    :param Any preds: Raw predictions array.
    :param Any pred_ts: Prediction timestamps array.

    :return: Forecast result payload.
    :rtype: Dict[str, Any]
    """

    message = ""

    if model is None:
        message = "Model loading warning: fallback inference path was used."

    if not is_matching and not message:
        message = "Input data does not match training distribution."

    if clip_negatives_to_0:
        preds = maximum(preds, 0)

    output = [
        [int(ts), None if isnan(p) else round(float(p), 1), None]
        for ts, p in zip(pred_ts, preds)
    ]

    result: Dict[str, Any] = {
        "message": message,
        "output": output,
        "model_confidence": _compute_model_confidence(preds, is_matching, model),
        # "planned_adjustments_applied": planned_applied_count,
        "input_statistics": _build_input_statistics(timestamps, values),
        "output_statistics": _build_output_statistics(pred_ts, preds),
    }

    if mlflow_model_name is not None:
        result["mlflow"] = {
            "name": mlflow_model_name,
            "version": mlflow_model_version,
        }

    if data_quality is not None:
        result["data_quality"] = data_quality

    return result
