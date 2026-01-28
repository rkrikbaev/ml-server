import logging
import numpy as np
import pandas as pd
from copy import copy
from typing import List, Dict

from fpforecast.models.ar import ModelWithMetaInfoAr
from fpforecast.models.prophet import ModelWithMetaInfoProphet
from utils import timestamps_to_calendar_features, SbreModel, GMT_TO_ASTANA_HOURS


logger = logging.getLogger(__file__)


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


def extract_features(
    timestamps: List[np.ndarray],
    y: List[np.ndarray],
    normalization: Dict[str, Dict[str, float]],
    offset_days: int,
):
    sub, div = normalization['sub'], normalization['div']

    # Prepare pred timestamps as + 2 of the feature days
    logger.info(f'len(timestamps[0]): {len(timestamps[0])}, timestamps[0]: {timestamps[0]}')
    pred_timestamps = build_pred_timestamps(timestamps[0], offset_days)
    logger.info(f'len(pred_timestamps): {len(pred_timestamps)}, pred_timestamps: {pred_timestamps}')

    # Shallow copy as we modify the lists (not arrays in it)
    # below
    timestamps = copy(timestamps)
    y = copy(y)
    logger.debug(f"len(y): {len(y)}, {[len(y_) for y_ in y]}")

    # Extract full day features
    history_mask = get_full_days_mask(timestamps[0], offset_days)
    for i in range(len(timestamps)):
        timestamps[i] = timestamps[i][history_mask]
        y[i] = y[i][history_mask]
    logger.debug(f"len(y): {len(y)}, {[len(y_) for y_ in y]}")

    # Add y features
    values = []
    for y_, feature_name in zip(y, ['y', 'temperature']):
        # Normalize
        y_ = (y_ - sub[feature_name]) / div[feature_name]        
        values.append(y_)

    # Add calendar features
    # Note: here the features are used for the first day of the prediction period
    # so the timestamps are shifted & day_off_change feature not used, so n_predict_steps arg is not used either
    calendar_features = timestamps_to_calendar_features(pred_timestamps, n_predict_steps=0)
    calendar_features['weekday'] = (calendar_features['weekday'] - sub['weekday']) / div['weekday']
    calendar_features['is_day_off'] = (calendar_features['is_day_off'] - sub['is_day_off']) / div['is_day_off']
    calendar_features['hour'] = (calendar_features['hour'] - sub['hour']) / div['hour']

    values.append(
        [
            calendar_features['weekday'][0],
            calendar_features['weekday'][-1],
            (calendar_features['weekday'] == calendar_features['weekday'][0]).sum() / calendar_features['weekday'].shape[0],
            (calendar_features['is_day_off'] > 0).any(),
            calendar_features['is_day_off'][0] > 0,
            calendar_features['hour'][0],
        ]
    )

    return np.concatenate(values), pred_timestamps, ratio


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


def get_pred_timestamps(ts: np.ndarray, step: int, output_range: int):
    last_past_index = get_last_past_index(ts)
    pred_start_dt = pd.to_datetime(ts[last_past_index], unit='ms')
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

    # Add back offset as we removed it with replace by rounding
    pred_dt = [dt - pd.DateOffset(hours=GMT_TO_ASTANA_HOURS) for dt in pred_dt]

    pred_timestamps = [
        int(dt.timestamp() * 1000) for dt in pred_dt
    ]
    pred_timestamps = np.array(pred_timestamps, dtype=int)

    return last_past_index, pred_timestamps
    

def predict(
    model,
    timestamps: List[np.ndarray],
    y: List[np.ndarray],
    step: int,
    output_range: int,
    online: bool,
):
    if isinstance(model, ModelWithMetaInfoAr):
        last_past_index, pred_timestamps = get_pred_timestamps(timestamps[0], step, output_range)

        # Select single window
        W_past = model.W_past
        W_future = model.W_future
        assert output_range == W_future, \
            f'Output range {output_range} != W_future {W_future} of the AR model'

        # TODO: add more features
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
        _, y_pred = model.predict(df)

        assert y_pred.shape[0] == 1
        y_pred = y_pred.reshape(-1)[:output_range]
    elif isinstance(model, ModelWithMetaInfoProphet):
        last_past_index, pred_timestamps = get_pred_timestamps(timestamps[0], step, output_range)
        df = pd.DataFrame(
            {
                'ds': pd.to_datetime(timestamps[0][last_past_index:last_past_index+output_range], unit='ms'),
            }
        )
        df_pred = model.predict(df)
        y_pred = df_pred['yhat'].values
        logger.debug(f'{len(y_pred)=}, {y_pred=}')
    elif isinstance(model, SbreModel):
        # Return the first input as prediction
        y_pred = y[1]

        # If it is all NaNs, return nan
        if np.all(np.isnan(y_pred)):
            y_pred = np.full_like(y_pred, np.nan)

        pred_timestamps = timestamps[1]
    else:
        if online:
            # If too few data points are not NaN, either 
            # use the first non-NaN input as prediction
            # or fill with nans
            y = y[0][:len(timestamps[0]) // 2]
            y_non_nan = ~np.isnan(y)
            n_non_nans = y_non_nan.sum()
            if n_non_nans == 0:
                y = np.full_like(y, np.nan)
            elif n_non_nans == 1:
                y = np.full_like(y, y[y_non_nan][0])

            # Fit the model on the provided data
            # TODO: add other regressors
            df_train = pd.DataFrame(
                {
                    'ds': pd.to_datetime(timestamps[0][:len(timestamps[0]) // 2], unit='ms'),
                    'y': y,
                }
            )
            model.fit(df_train)

        _, pred_timestamps = get_pred_timestamps(timestamps[0], step, output_range)
        df_future = pd.DataFrame({'ds': pd.to_datetime(pred_timestamps, unit='ms')})
        df_forecast = model.predict(df_future)
        y_pred = df_forecast['yhat'].values

    return y_pred, pred_timestamps
