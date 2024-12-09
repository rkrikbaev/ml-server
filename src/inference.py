# Config logging
import logging
import os

logging.basicConfig(
    format='%(asctime)s,%(msecs)d %(name)s %(levelname)s %(message)s',
    datefmt='%H:%M:%S',
    level=os.environ.get('LOGLEVEL', 'INFO'),
)
logger = logging.getLogger(__file__)

import numpy as np
import pandas as pd
from copy import copy
from typing import List, Dict

from utils import timestamps_to_calendar_features, load_model_and_normalization


def get_last_past_index(timestamps: np.ndarray) -> int:
    return len(timestamps) // 2


GMT_TO_ASTANA_HOURS = 6
def get_full_days_mask(timestamps: np.ndarray, offset_days: int):
    last_past_index = get_last_past_index(timestamps)
    df = pd.DataFrame({'dt': timestamps})
    df['dt'] = pd.to_datetime(df['dt'], unit='ms') + pd.Timedelta(hours=GMT_TO_ASTANA_HOURS)
    date = df['dt'].dt.floor('D')
    current_date = date.iloc[last_past_index]
    target_date = current_date + pd.Timedelta(days=offset_days)
    mask = date == target_date
    return mask.values


def get_month(timestamps: np.ndarray):
    df = pd.DataFrame({'dt': timestamps})
    df['dt'] = pd.to_datetime(df['dt'], unit='ms') + pd.Timedelta(hours=GMT_TO_ASTANA_HOURS)
    return df['dt'].dt.month.mode().iloc[0]


def get_weekday(timestamps: np.ndarray) -> bool:
    last_past_index = get_last_past_index(timestamps)
    df = pd.DataFrame({'dt': timestamps})
    df['dt'] = pd.to_datetime(df['dt'], unit='ms') + pd.Timedelta(hours=GMT_TO_ASTANA_HOURS)
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
    sub, div, month_mean = normalization['sub'], normalization['div'], normalization['month_mean']

    # Prepare pred timestamps as + 2 of the feature days
    pred_timestamps = build_pred_timestamps(timestamps[0], offset_days)

    # Calculate ratio of train period month mean 
    # to current month mean
    ratio = 1.0
    current_month_mean = y[-1][-1]
    if current_month_mean is not None:
        current_month_mean = (current_month_mean - sub['y']) / div['y']
        month = str(get_month(timestamps[0]))
        ratio = month_mean[month] / current_month_mean

    # Shallow copy as we modify the lists (not arrays in it)
    # below
    timestamps = copy(timestamps)
    y = copy(y)

    # Replace nan values in y with values from the
    # predictions archive
    y[0] = np.where(np.isnan(y[0]), y[2], y[0])

    # Extract full day features
    history_mask = get_full_days_mask(timestamps[0], offset_days)
    for i in range(len(timestamps)):
        timestamps[i] = timestamps[i][history_mask]
        y[i] = y[i][history_mask]

    # Add y features
    values = []
    for y_, feature_name in zip(y, ['y', 'temperature']):
        # Normalize
        y_ = (y_ - sub[feature_name]) / div[feature_name]
        if feature_name == 'y':
            y_ = y_ * ratio
        
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


def predict(
    model,
    timestamps: List[np.ndarray],
    y: List[np.ndarray],
    normalization: Dict[str, Dict[str, float]],
):
    # Get weekday
    weekday = get_weekday(timestamps[0])

    # Get features
    X, pred_timestamps, train_to_test_correction_ratio = extract_features(
        timestamps,
        y,
        normalization,
        offset_days=-1,
    )

    # Predict
    X = X[None, :]
    y_pred = model.predict(X)[0]

    # If friday, additionally predict for sunday and monday
    if weekday == 4:
        y_preds, pred_timestampss = [y_pred], [pred_timestamps]
        print(len(pred_timestamps))

        # Get features
        X, pred_timestamps, train_to_test_correction_ratio = extract_features(
            timestamps,
            y,
            normalization,
            offset_days=0,
        )

        # Predict
        X = X[None, :]
        y_pred = model.predict(X)[0]
        
        y_preds.append(y_pred)
        pred_timestampss.append(pred_timestamps)
        print(len(pred_timestamps))

        # Get features
        X, pred_timestamps, train_to_test_correction_ratio = extract_features(
            timestamps,
            y,
            normalization,
            offset_days=1,
        )

        # Use saturday predictions as GT
        X[:y_preds[0].shape[0]] = y_preds[0]

        # Predict
        X = X[None, :]
        y_pred = model.predict(X)[0]
        
        y_preds.append(y_pred)
        pred_timestampss.append(pred_timestamps)
        print(len(pred_timestamps))

        y_pred, pred_timestamps = np.concatenate(y_preds, axis=0), np.concatenate(pred_timestampss, axis=0)

    print(len(y_pred), len(pred_timestamps))

    # Unnormalize
    sub, div = normalization['sub'], normalization['div']
    y_pred = y_pred / train_to_test_correction_ratio
    y_pred = y_pred * div['y'] + sub['y']

    return y_pred, pred_timestamps


def init_model():
    return load_model_and_normalization('xgb')
