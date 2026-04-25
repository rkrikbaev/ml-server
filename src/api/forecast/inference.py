# 20??.??.??, ??, ?? ?M
"""
Model inference module using base model interface with adapters.
Deprecated: fpforecast module. Using base_interface + adapters pattern.
"""

from typing import List, Tuple, Any, Optional, Dict
from copy import copy

from api.forecast.base_interface import BaseModel, PredictionInput, PredictionOutput
from api.forecast.adapters import ARAdapter, ProphetAdapter

from api.utils import get_pred_timestamps
from .date import get_full_days_mask, get_weekday

import numpy as np
import pandas as pd
import logging

logger = logging.getLogger(__name__)


def predict_default(timestamps: List[np.ndarray], y: List[np.ndarray]) -> Tuple[np.ndarray]:
    """
    Run default prediction.

    :param List[np.ndarray] timestamps: List of timestamps.
    :param List[np.ndarray] y: List of values.

    :return: 2 parameters: forecast and timestamps
    :rtype: Tuple[np.ndarray, np.ndarray]
    """

    # Get weekday
    weekday = get_weekday(timestamps[0])

    # Shallow copy as we modify the lists (not arrays in it) below
    timestamps = copy(timestamps)
    y = copy(y)

    # Extract full day features
    history_mask = get_full_days_mask(timestamps[0], -1)
    for i in range(len(timestamps)):
        timestamps[i] = timestamps[i][history_mask]
        y[i] = y[i][history_mask]

    # Prepare pred timestamps as + 2 of the feature days
    pred_mask = get_full_days_mask(timestamps[0], 1)
    pred_timestamps = timestamps[0][pred_mask]

    y_pred = y[0]

    # If friday, additionally predict for sunday and monday
    if weekday == 4:
        y_pred = np.concatenate([y_pred] * 3, axis=0)

        pred_timestampss = [pred_timestamps]

        pred_mask = get_full_days_mask(timestamps[0], 2)
        pred_timestamps = timestamps[0][pred_mask]
        pred_timestampss.append(pred_timestamps)

        pred_mask = get_full_days_mask(timestamps[0], 3)
        pred_timestamps = timestamps[0][pred_mask]
        pred_timestampss.append(pred_timestamps)

        pred_timestamps = np.concatenate(pred_timestampss, axis=0)

    return y_pred, pred_timestamps


def predict(
    model: BaseModel,
    timestamps: List[np.ndarray],
    y: List[np.ndarray],
    step: int,
    output_range: int,
    online: bool,
    df_rz_melt: Optional[pd.DataFrame] = None,
    weather_data: Optional[Dict[str, Any]] = None,
) -> Tuple[Any]:
    """
    Run model prediction using base model interface.

    :param BaseModel model: Model instance (ARAdapter, ProphetAdapter, etc.)
    :param List[np.ndarray] timestamps: List of timestamps.
    :param List[np.ndarray] y: List of values.
    :param int step: Step size.
    :param int output_range: Output range.
    :param bool online: Whether to use online mode.
    :param Optional[pd.DataFrame] df_rz_melt: Optional RZ data for merging.
    :param Optional[Dict[str, Any]] weather_data: Optional weather payload.

    :return: 3 parameters: forecast, timestamps, and quality flag
    :rtype: Tuple[np.ndarray, np.ndarray, bool]
    """

    # По умолчанию считаем, что данные соответствуют распределению
    is_matching = True

    try:
        # Prepare prediction timestamps
        _, pred_timestamps = get_pred_timestamps(timestamps[0], step, output_range)
        
        # Create prediction input
        prediction_input = PredictionInput(
            features=y[0],
            metadata={
                "step": step,
                "output_range": output_range,
                "online": online,
                "rz_data": df_rz_melt is not None,
                "weather_data": weather_data,
                "timestamps": timestamps[0].tolist() if hasattr(timestamps[0], "tolist") else timestamps[0],
            }
        )
        
        # Get prediction from adapter model
        prediction_output = model.predict(prediction_input)
        
        y_pred = np.asarray(prediction_output.predictions).reshape(-1)[:output_range]
        
        # Pad with NaN if necessary
        if y_pred.size < output_range:
            y_pred = np.pad(y_pred, (0, output_range - y_pred.size), constant_values=np.nan)

        model_type = None
        if prediction_output.metadata:
            model_type = prediction_output.metadata.get("model_type")
        logger.info(f"Prediction successful: {len(y_pred)} values, model_type={model_type or type(model).__name__}")
        
        return y_pred, pred_timestamps, is_matching
        
    except Exception as e:
        logger.error(f"Prediction failed: {str(e)}")
        # Return NaN predictions on failure
        y_pred = np.full(output_range, np.nan)
        _, pred_timestamps = get_pred_timestamps(timestamps[0], step, output_range)
        return y_pred, pred_timestamps, False
