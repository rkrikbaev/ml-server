# 20??.??.??, ??, ?? ?M


from typing import List, Tuple, Any, Optional

from fpforecast.models.ar import ModelWithMetaInfoAr
from fpforecast.models.prophet import ModelWithMetaInfoProphet
from fpforecast.features import merge_rz_structure

from api.utils import get_pred_timestamps
from .model import SbreModel

import numpy as np
import pandas as pd


def predict(
    model: Any,
    timestamps: List[np.ndarray],
    y: List[np.ndarray],
    step: int,
    output_range: int,
    online: bool,
    df_rz_melt: Optional[pd.DataFrame] = None
) -> Tuple[Any]:
    """
    Run model prediction.

    :param Any mode: Model to use for prediction.
    :param List[np.ndarray] timestamps: List of timestamps.
    :param List[np.ndarray] y: List of values.
    :param int step: Step size.
    :param int output_range: Output range.
    :param bool online: Whether to use online mode.
    :param Optional[pd.DataFrame] df_rz_melt: Optional melted RZ dataframe.

    :return: 3 parameters: forecast, timestamps, and quality flag
    :rtype: Tuple[np.ndarray, np.ndarray, bool]
    """

    # По умолчанию считаем, что данные соответствуют распределению
    is_matching = True

    if isinstance(model, ModelWithMetaInfoAr):
        last_past_index, pred_timestamps = get_pred_timestamps(timestamps[0], step, output_range)

        # Подготовка окна данных
        W_past = model.W_past
        W_future = model.W_future
        assert output_range == W_future, \
            f"Output range {output_range} != W_future {W_future} of the AR model"

        df = pd.DataFrame(
            {
                "value": y[0][last_past_index - W_past:last_past_index + W_future],
            },
            index=pd.to_datetime(timestamps[0][last_past_index - W_past:last_past_index + output_range], unit="ms")
        )

        # Merge with rz data if available
        if df_rz_melt is not None:
            df = df.rename_axis("dt")  # rename index to dt for merging
            df = merge_rz_structure(df_rz_melt=df_rz_melt, df=df)
            df = df.copy()

        # Вызов модели: ожидаем (y, y_pred, is_matching)
        _, y_pred, is_matching = model.predict(df)

        # Приводим y_pred к 1D numpy массиву длиной output_range
        y_pred = np.asarray(y_pred).reshape(-1)[:output_range]
        if y_pred.size < output_range:
            y_pred = np.pad(y_pred, (0, output_range - y_pred.size), constant_values=np.nan)

    elif isinstance(model, ModelWithMetaInfoProphet):
        _, pred_timestamps = get_pred_timestamps(timestamps[0], step, output_range)
        df = pd.DataFrame(
            {
                "ds": pd.to_datetime(pred_timestamps, unit="ms"),
            }
        )
        df_pred = model.predict(df)
        y_pred = df_pred["yhat"].values
        print(f"{len(y_pred)=}, {y_pred=}")

    elif isinstance(model, SbreModel):
        y_pred = y[1]
        if np.all(np.isnan(y_pred)):
            y_pred = np.full_like(y_pred, np.nan)
        pred_timestamps = timestamps[1]

    else:
        if online:
            y_history = y[0][:len(timestamps[0]) // 2]
            y_non_nan = ~np.isnan(y_history)
            n_non_nans = y_non_nan.sum()

            if n_non_nans == 0:
                y_history = np.full_like(y_history, np.nan)
            elif n_non_nans == 1:
                y_history = np.full_like(y_history, y_history[y_non_nan][0])

            df_train = pd.DataFrame(
                {
                    "ds": pd.to_datetime(timestamps[0][:len(timestamps[0]) // 2], unit="ms"),
                    "y": y_history,
                }
            )
            model.fit(df_train)

        _, pred_timestamps = get_pred_timestamps(timestamps[0], step, output_range)
        df_future = pd.DataFrame({"ds": pd.to_datetime(pred_timestamps, unit="ms")})
        df_forecast = model.predict(df_future)
        y_pred = df_forecast["yhat"].values

    # Возвращаем три параметра: прогноз, метки времени и флаг качества
    return y_pred, pred_timestamps, is_matching
