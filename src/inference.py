import logging
import numpy as np
import pandas as pd
from copy import copy
from typing import List

from fpforecast.models.ar import ModelWithMetaInfoAr
from fpforecast.models.prophet import ModelWithMetaInfoProphet
from utils import SbreModel


logger = logging.getLogger(__file__)
GMT_TO_ASTANA_HOURS = 5


def get_last_past_index(timestamps: np.ndarray) -> int:
    return len(timestamps) // 2


def get_full_days_mask(timestamps: np.ndarray, offset_days: int):
    last_past_index = get_last_past_index(timestamps)
    df = pd.DataFrame({'dt': timestamps})
    df['dt'] = pd.to_datetime(df['dt'], unit='ms')
    date = df['dt'].dt.floor('D')
    current_date = date.iloc[last_past_index]
    target_date = current_date + pd.Timedelta(days=offset_days)
    mask = date == target_date
    return mask.values


def get_month(timestamps: np.ndarray):
    df = pd.DataFrame({'dt': timestamps})
    df['dt'] = pd.to_datetime(df['dt'], unit='ms')
    return df['dt'].dt.month.mode().iloc[0]


def get_weekday(timestamps: np.ndarray) -> bool:
    last_past_index = get_last_past_index(timestamps)
    df = pd.DataFrame({'dt': timestamps})
    df['dt'] = pd.to_datetime(df['dt'], unit='ms')
    return df['dt'].dt.weekday.iloc[last_past_index]


def build_pred_timestamps(timestamps: np.ndarray, offset_days: int):
    # Get prev day timestamps and add +2 days
    history_mask = get_full_days_mask(timestamps, offset_days)
    pred_timestamps = timestamps[history_mask] + 2 * 24 * 3600 * 1000
    return pred_timestamps


def predict_default(
    timestamps: List[np.ndarray],
    y: List[np.ndarray],
):
    # Get weekday
    weekday = get_weekday(timestamps[0])

    # Shallow copy as we modify the lists (not arrays in it)
    # below
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


def timestamps_to_timezoned_timestamps(
    timestamps: List[int] | np.ndarray,
    timezone_offset_hours: int
) -> np.ndarray:
    # Convert to pandas datetime
    df = pd.DataFrame({'dt': timestamps})
    df['dt'] = pd.to_datetime(df['dt'], unit='ms')

    # Apply timezone offset
    df['dt'] = df['dt'] + pd.to_timedelta(timezone_offset_hours, unit='h')

    # Convert back to timestamps in ms
    return (df['dt'].astype(np.int64) // 10**6).values


def get_last_past_index(timestamps: np.ndarray) -> int:
    return len(timestamps) // 2


def get_pred_timestamps(ts: np.ndarray, step: int, output_range: int):
    # Convert to Astana timezone
    ts_zoned = timestamps_to_timezoned_timestamps(ts, GMT_TO_ASTANA_HOURS)

    last_past_index = get_last_past_index(ts_zoned)
    pred_start_dt = pd.to_datetime(ts_zoned[last_past_index], unit='ms')
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
):
    # По умолчанию считаем, что данные соответствуют распределению
    is_matching = True  

    if isinstance(model, ModelWithMetaInfoAr):
        last_past_index, pred_timestamps = get_pred_timestamps(timestamps[0], step, output_range)

        # Подготовка окна данных
        W_past = model.W_past
        W_future = model.W_future
        assert output_range == W_future, \
            f'Output range {output_range} != W_future {W_future} of the AR model'

        df = pd.DataFrame(
            {
                'value': y[0][last_past_index-W_past:last_past_index+W_future],
            },
            index=pd.to_datetime(timestamps[0][last_past_index-W_past:last_past_index+output_range], unit='ms')
        )

        for feature_info in model.features_info:
            if feature_info.name in df.columns:
                continue
            df[feature_info.name] = np.nan

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
                'ds': pd.to_datetime(pred_timestamps, unit='ms'),
            }
        )
        df_pred = model.predict(df)
        y_pred = df_pred['yhat'].values
        logger.debug(f'{len(y_pred)=}, {y_pred=}')

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
                    'ds': pd.to_datetime(timestamps[0][:len(timestamps[0]) // 2], unit='ms'),
                    'y': y_history,
                }
            )
            model.fit(df_train)

        _, pred_timestamps = get_pred_timestamps(timestamps[0], step, output_range)
        df_future = pd.DataFrame({'ds': pd.to_datetime(pred_timestamps, unit='ms')})
        df_forecast = model.predict(df_future)
        y_pred = df_forecast['yhat'].values

    # Возвращаем три параметра: прогноз, метки времени и флаг качества
    return y_pred, pred_timestamps, is_matching
