# ????.??.??, ??, ?? ?M


from typing import List
from logging import getLogger

from .utils import SbreModel

from fpforecast.models.ar import ModelWithMetaInfoAr
from fpforecast.models.prophet import ModelWithMetaInfoProphet
from fpforecast.features import merge_rz_structure

import numpy as np
import pandas as pd


logger = getLogger(__file__)
GMT_TO_ASTANA_HOURS = 5


def get_last_past_index(timestamps: np.ndarray) -> int:
    return len(timestamps) // 2


def timestamps_to_timezoned_timestamps(
    timestamps: List[int] | np.ndarray,
    timezone_offset_hours: int
) -> np.ndarray:
    # Convert to pandas datetime
    df = pd.DataFrame({"dt": timestamps})
    df["dt"] = pd.to_datetime(df["dt"], unit="ms")

    # Apply timezone offset
    df["dt"] = df["dt"] + pd.to_timedelta(timezone_offset_hours, unit="h")

    # Convert back to timestamps in ms
    return (df["dt"].astype(np.int64) // 10**6).values


def get_pred_timestamps(ts: np.ndarray, step: int, output_range: int):
    # Convert to Astana timezone
    ts_zoned = timestamps_to_timezoned_timestamps(ts, GMT_TO_ASTANA_HOURS)

    last_past_index = get_last_past_index(ts_zoned)
    pred_start_dt = pd.to_datetime(ts_zoned[last_past_index], unit="ms")
    if step == 2592000000:
        # Round to the current month start, then add one month
        pred_start_dt = pred_start_dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        pred_start_dt = pred_start_dt + pd.DateOffset(months=1)
        pred_dt = [pred_start_dt + pd.DateOffset(months=i) for i in range(output_range)]
    elif step == 86400000:
        # Round to the current day start, then add one day
        pred_start_dt = pred_start_dt.replace(hour=0, minute=0, second=0, microsecond=0)
        pred_start_dt = pred_start_dt + pd.DateOffset(days=1)
        pred_dt = [pred_start_dt + pd.DateOffset(days=i) for i in range(output_range)]
    elif step == 3600000:
        # Round to the current hour start, then add one hour
        pred_start_dt = pred_start_dt.replace(minute=0, second=0, microsecond=0)
        pred_start_dt = pred_start_dt + pd.DateOffset(hours=1)
        pred_dt = [pred_start_dt + pd.DateOffset(hours=i) for i in range(output_range)]
    else:
        # Do not round for other steps
        pass

    pred_timestamps = [
        int(dt.timestamp() * 1000) for dt in pred_dt
    ]
    pred_timestamps = np.array(pred_timestamps, dtype=int)

    # Convert back to GMT timezone
    pred_timestamps = timestamps_to_timezoned_timestamps(pred_timestamps, -GMT_TO_ASTANA_HOURS)

    return last_past_index, pred_timestamps


def predict(
    model,
    timestamps: List[np.ndarray],
    y: List[np.ndarray],
    step: int,
    output_range: int,
    online: bool,
    df_rz_melt: pd.DataFrame | None = None,
):
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
        logger.debug(f"{len(y_pred)=}, {y_pred=}")

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
