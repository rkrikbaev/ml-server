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
from typing import List, Dict

from utils import timestamps_to_calendar_features, load_model_and_normalization


def extract_features(
    timestamps: List[np.ndarray],
    y: List[np.ndarray],
    sub: Dict[str, float],
    div: Dict[str, float],
    n_predict_steps: int = 24,
    step_granularity_s: int = 3600,
):
    values = []

    # Add y features
    for y_, feature_name in zip(y, ['y', 'temperature']):
        # Normalize
        y_ = (y_ - sub[feature_name]) / div[feature_name]

        # Truncate due to truncation during training
        y_ = y_[:-1]
        
        values.append(y_)

    # Add calendar features
    # Note: here the features are used for the first day of the prediction period
    # so the timestamps are shifted & day_off_change feature not used, so n_predict_steps arg is not used either
    calendar_features = timestamps_to_calendar_features(timestamps[0] + n_predict_steps * step_granularity_s * 1000, n_predict_steps=0)
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

    return np.concatenate(values)


def predict(
    model,
    timestamps: List[np.ndarray],
    y: List[np.ndarray],
    sub: Dict[str, float],
    div: Dict[str, float],
    n_predict_steps: int,
    step_granularity_s: int,
):
    # Get features
    X = extract_features(
        timestamps,
        y,
        sub=sub,
        div=div,
        n_predict_steps=n_predict_steps,
        step_granularity_s=step_granularity_s,
    )[None, :]

    # Predict
    y_pred = model.predict(X)

    # Unnormalize
    y_pred = y_pred * div['y'] + sub['y']

    return y_pred


def init_model():
    return load_model_and_normalization('xgb')
