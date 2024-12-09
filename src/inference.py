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



GMT_TO_ASTANA_HOURS = 5
def get_full_days_mask(timestamps: np.ndarray, max_n_days=None):
    df = pd.DataFrame({'dt': timestamps})
    df['dt'] = pd.to_datetime(df['dt'], unit='ms') + pd.Timedelta(hours=GMT_TO_ASTANA_HOURS)
    
    df['date_counts'] = df.groupby(df['dt'].dt.floor('D')).transform('count')
    mask = df['date_counts'] == df['date_counts'].max()

    if max_n_days is None:
        return mask.values

    cutoff_date = df[mask]['dt'].iloc[-1] - pd.Timedelta(days=max_n_days)
    mask = mask & (df['dt'] > cutoff_date)
    return mask.values


def get_month(timestamps: np.ndarray):
    df = pd.DataFrame({'dt': timestamps})
    df['dt'] = pd.to_datetime(df['dt'], unit='ms') + pd.Timedelta(hours=GMT_TO_ASTANA_HOURS)
    return df['dt'].dt.month.mode().iloc[0]


def extract_features(
    timestamps: List[np.ndarray],
    y: List[np.ndarray],
    normalization: Dict[str, Dict[str, float]],
    pred_timestamps: np.ndarray,
):
    sub, div, month_mean = normalization['sub'], normalization['div'], normalization['month_mean']

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

    # Align with full days as model is trained to predict
    # 1 day ahead and required to predict next full day
    # TODO: use teperature forecast (so, its timestamps will be for the prediction period
    # and probably need to be cropped differently)
    for i in range(len(timestamps)):
        mask = get_full_days_mask(timestamps[i], max_n_days=1)
        timestamps[i] = timestamps[i][mask]
        y[i] = y[i][mask]

    values = []

    # Add y features
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

    return np.concatenate(values), ratio


def predict_default(
    timestamps: List[np.ndarray],
    y: List[np.ndarray],
    n_predict_steps: int,
    step_granularity_s: int,
):
    # Shallow copy as we modify the lists (not arrays in it)
    # below
    timestamps = copy(timestamps)
    y = copy(y)

    # Align with full days as model is trained to predict
    # 1 day ahead and required to predict next full day
    # TODO: use teperature forecast (so, its timestamps will be for the prediction period
    # and probably need to be cropped differently)
    for i in range(len(timestamps)):
        mask = get_full_days_mask(timestamps[i], max_n_days=1)
        timestamps[i] = timestamps[i][mask]
        y[i] = y[i][mask]

    # Prepare timestamps
    pred_timestamps = build_pred_timestamps(timestamps, n_predict_steps, step_granularity_s)

    return y[0][-n_predict_steps:], pred_timestamps
    

def predict(
    model,
    timestamps: List[np.ndarray],
    y: List[np.ndarray],
    normalization: Dict[str, Dict[str, float]],
    n_predict_steps: int,
    step_granularity_s: int,
):
    # Prepare timestamps
    pred_timestamps = build_pred_timestamps(timestamps, n_predict_steps, step_granularity_s)

    # Get features
    X, train_to_test_correction_ratio = extract_features(
        timestamps,
        y,
        normalization,
        pred_timestamps,
    )

    # Predict
    X = X[None, :]
    y_pred = model.predict(X)

    # Unnormalize
    sub, div = normalization['sub'], normalization['div']
    y_pred = y_pred / train_to_test_correction_ratio
    y_pred = y_pred * div['y'] + sub['y']

    return y_pred[0], pred_timestamps


def init_model():
    return load_model_and_normalization('xgb')


def build_pred_timestamps(timestamps: List[np.ndarray], n_predict_steps: int, step_granularity_s: int):
    dt = pd.to_datetime(timestamps[0][-1], unit='ms') + pd.Timedelta(hours=GMT_TO_ASTANA_HOURS)
    first_next_full_day_datetime = dt.floor('D') + pd.Timedelta(days=1) - pd.Timedelta(hours=GMT_TO_ASTANA_HOURS)
    first_next_full_day_timestamp = (first_next_full_day_datetime - pd.Timestamp('1970-01-01')) // pd.Timedelta('1ms')
    pred_timestamps = [first_next_full_day_timestamp + i * step_granularity_s for i in range(n_predict_steps)]
    return pred_timestamps
