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
from prophet import Prophet
from xgboost import XGBRegressor

from utils import timestamps_to_calendar_features, load_model_and_normalization, SbreModel


def get_last_past_index(timestamps: np.ndarray) -> int:
    return len(timestamps) // 2


GMT_TO_ASTANA_HOURS = 5
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
    logger.info(f'len(timestamps[0]): {len(timestamps[0])}, timestamps[0]: {timestamps[0]}')
    pred_timestamps = build_pred_timestamps(timestamps[0], offset_days)
    logger.info(f'len(pred_timestamps): {len(pred_timestamps)}, pred_timestamps: {pred_timestamps}')

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
    normalization: Dict[str, Dict[str, float]] | None,
    step: int,
    output_range: int,
    online: bool,
):
    # Predict
    if isinstance(model, XGBRegressor):
        assert not online, "XGBRegressor model should not be used in online mode"

        # Get weekday
        weekday = get_weekday(timestamps[0])

        # Get features
        X, pred_timestamps, train_to_test_correction_ratio = extract_features(
            timestamps,
            y,
            normalization,
            offset_days=-1,
        )
        logger.info(f'X.shape: {X.shape}')

        X = X[None, :]
        y_pred = model.predict(X)[0]

        # If friday, additionally predict for sunday and monday
        if weekday == 4:
            ### Saturday: predicted as usual
            y_preds, pred_timestampss = [y_pred], [pred_timestamps]

            ### Sunday
            ### - predict for friday first, as we are in the middle of the day
            ###   and not all the GT values are present for it
            ### - then use the prediction in place of missing GT values

            # Get features
            X, _, _ = extract_features(
                timestamps,
                y,
                normalization,
                offset_days=-2,
            )

            # Predict
            X = X[None, :]
            y_pred = model.predict(X)[0]
            # Note: we do not add it to y_preds

            # Get features
            X, pred_timestamps, _ = extract_features(
                timestamps,
                y,
                normalization,
                offset_days=0,
            )

            # Partially use friday predictions as GT
            last_past_index = get_last_past_index(timestamps[0])
            future_mask = np.arange(len(timestamps[0])) > last_past_index
            friday_mask = get_full_days_mask(timestamps[0], 0)
            friday_future_mask = future_mask & friday_mask
            friday_future_mask = friday_future_mask[friday_mask]
            X[:y_pred.shape[0]] = np.where(friday_future_mask, y_pred, X[:y_pred.shape[0]])

            # Predict
            X = X[None, :]
            y_pred = model.predict(X)[0]
            
            y_preds.append(y_pred)
            pred_timestampss.append(pred_timestamps)

            ### Monday
            ### - use the saturday prediction in place of missing GT values

            # Get features
            X, pred_timestamps, _ = extract_features(
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

            y_pred, pred_timestamps = np.concatenate(y_preds, axis=0), np.concatenate(pred_timestampss, axis=0)

        # Unnormalize
        sub, div = normalization['sub'], normalization['div']
        y_pred = y_pred / train_to_test_correction_ratio
        y_pred = y_pred * div['y'] + sub['y']
    elif isinstance(model, SbreModel):
        # Return the first input as prediction
        y_pred = y[0]
        pred_timestamps = timestamps[0]
    else:
        if online:
            # Fit the model on the provided data
            # TODO: add other regressors
            df_train = pd.DataFrame(
                {
                    'ds': pd.to_datetime(timestamps[0][:len(timestamps[0]) // 2], unit='ms'),
                    'y': y[0][:len(timestamps[0]) // 2],
                }
            )
            model.fit(df_train)

        # The data interval middle is actually the current time
        pred_start_dt = pd.to_datetime(timestamps[0][len(timestamps[0]) // 2], unit='ms')
        if step == 2592000000:
            assert not online, "Prophet model should not be used in online mode for monthly step"

            # Round to next month start
            pred_start_dt = pred_start_dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            pred_dt = [pred_start_dt + pd.DateOffset(months=i) for i in range(output_range)]
        else:
            # Do not round for daily and hourly steps
            pred_dt = [pred_start_dt + pd.DateOffset(milliseconds=step * i) for i in range(output_range)]

        df_future = pd.DataFrame({'ds': pred_dt})
        df_forecast = model.predict(df_future)
        y_pred = df_forecast['yhat'].values
        pred_timestamps = [
            int(dt.timestamp() * 1000) for dt in pred_dt
        ]
        pred_timestamps = np.array(pred_timestamps, dtype=int)

    return y_pred, pred_timestamps


def init_model(model_path: str | None, step: int):
    if model_path == '':
        # Create new Prophet model to train on the provided inputs
        # and no normalization
        if step == 2592000000:
            # Monthly (30 days) step
            # expected to have 12+ months of data
            seasonality_kwargs = {
                'daily_seasonality': False,
                'weekly_seasonality': False,
                'yearly_seasonality': True,
            }
        elif step == 86400000:
            # Daily step
            # expected to have 30+ days of data
            seasonality_kwargs = {
                'daily_seasonality': True,
                'weekly_seasonality': True,
                'yearly_seasonality': False,
            }
        elif step == 3600000:
            # Hourly step
            # expected to have 30+ days of data
            seasonality_kwargs = {
                'daily_seasonality': True,
                'weekly_seasonality': False,
                'yearly_seasonality': False,
            }
        model = Prophet(
            changepoint_prior_scale=0.1,
            changepoint_range=0.9,
            growth='linear',
            # mcmc_samples=100,
            n_changepoints=5,
            seasonality_mode='multiplicative',
            seasonality_prior_scale=30.0,
            **seasonality_kwargs,
        )
        normalization = dict()
    elif model_path == 'sbre':
        return SbreModel(), {}
    else:
        # Load trained model and normalization from disk
        model, normalization = load_model_and_normalization(
            model_rel_dirpath=model_path, 
            model_type='xgb' if step == 3600000 else 'prophet'
        )
    return model, normalization
