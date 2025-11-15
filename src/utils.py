# Config logging
import logging
import os

logging.basicConfig(
    format='%(asctime)s,%(msecs)d %(name)s %(levelname)s %(message)s',
    datefmt='%H:%M:%S',
    level=os.environ.get('LOGLEVEL', 'INFO'),
)
logger = logging.getLogger(__file__)

import joblib
import json
import numpy as np
import pandas as pd
import re
from prophet.serialize import model_from_json
from xgboost import XGBRegressor
from typing import List, Dict, Tuple, Literal


class SbreModel:
    pass


# Normalize colnames
# https://stackoverflow.com/a/14173535
RU_TO_EN_SYMBOLS = (
    u"абвгдеёжзийклмнопрстуфхцчшщъыьэюяАБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ",
    u"abvgdeejzijklmnoprstufhzcss_y_euaABVGDEEJZIJKLMNOPRSTUFHZCSS_Y_EUA")

# Holidays
# 2022
HOLIDAYS_2022 = [
    '03.01.2022',
    '04.01.2022',
    '07.01.2022',
    '07.03.2022',
    '08.03.2022',
    '21.03.2022',
    '22.03.2022',
    '23.03.2022',
    '02.05.2022',
    '09.05.2022',
    '10.05.2022',
    '06.07.2022',
    '29.08.2022',
    '30.08.2022',
    '24.10.2022',
    '25.10.2022',
    '16.12.2022',
]
FORCE_NON_HOLIDAYS_2022 = [
    '05.03.2022',
    '27.08.2022',
    '22.10.2022',
]
# 2023
HOLIDAYS_2023 = [
    '02.01.2023',
    '03.01.2023',
    '08.03.2023',
    '21.03.2023',
    '22.03.2023',
    '23.03.2023',
    '01.05.2023',
    '08.05.2023',
    '09.05.2023',
    '28.06.2023',
    '06.07.2023',
    '07.07.2023',
    '30.08.2023',
    '25.10.2023',
    '18.12.2023',
]
FORCE_NON_HOLIDAYS_2023 = [
    '01.07.2023',
]


# TODO: move holiday features extraction to client side
HOLIDAYS = pd.to_datetime(
    HOLIDAYS_2022 +
    HOLIDAYS_2023,
    format='%d.%m.%Y'
).date
FORCE_NON_HOLIDAYS = pd.to_datetime(
    FORCE_NON_HOLIDAYS_2022 +
    FORCE_NON_HOLIDAYS_2023,
    format='%d.%m.%Y'
).date

MES_TO_REGION = {
    'Aktubinskij_MES': 'AKTOBE',
    'Vostocnyj_MES': 'VOSTOK',
    'Ujnyj_MES': 'UZHNIY',
    'Akmolinskij_MES': 'AKMOLA',
    'Zentral_nyj_MES': 'CENTER',
    'Almatinskij_MES': 'ALMATY',
    'Severnyj_MES': 'SEVER',
    'Zapadnyj_MES': 'ZAPAD',
    'Sarbajskij_MES': 'KOSTANAY',
}


# https://stackoverflow.com/a/46801075
def get_valid_filename(name, faceplate=False):
    s = str(name).strip().replace(" ", "_").replace("\n", "_")
    s = re.sub(r"(?u)[^-\w.]", "", s)
    if s in {"", ".", ".."}:
        raise ValueError("Could not derive file name from '%s'" % name)
    
    # Additional processing for faceplate
    if faceplate:
        # Transliterate
        tr = {ord(a):ord(b) for a, b in zip(*RU_TO_EN_SYMBOLS)}
        s = s.translate(tr)

        # Replace '.', '-', ' ' to '_'
        s = s.replace('.', '_')
        s = s.replace('-', '_')
        s = s.replace(' ', '_')
        
        # Remove '_' from starts and ends
        s = s.rstrip('_')
        s = s.strip('_')

        # Remove repeated '_'s
        s = re.sub(r'(_)\1+', '\\1', s)
    
    return s


def timestamps_to_calendar_features(timestamps: List[int] | np.ndarray, n_predict_steps: int) -> Dict[str, np.ndarray]:
    # Convert to pandas datetime
    df = pd.DataFrame({'dt': timestamps})
    df['dt'] = pd.to_datetime(df['dt'], unit='ns')

    # Weekday
    df['weekday'] = df['dt'].dt.weekday

    # Holidays
    df['is_holiday'] = df['dt'].dt.date.isin(HOLIDAYS)
    df['is_forced_non_holiday'] = df['dt'].dt.date.isin(FORCE_NON_HOLIDAYS)
    df['is_day_off'] = df['weekday'].isin({5, 6}) & (~df['is_forced_non_holiday']) | df['is_holiday']

    is_today_day_off = df['is_day_off'].astype(int)
    is_tomorrow_day_off = (df['is_day_off'].astype(float).shift(-n_predict_steps).fillna(0) > 0).astype(int)
    df['day_off_change'] = is_today_day_off - is_tomorrow_day_off

    return {
        'is_day_off': df['is_day_off'].values, 
        'day_off_change': df['day_off_change'].values,
        'weekday': df['weekday'].values,
        'hour': df['dt'].dt.hour.values,
    }


def extract_data(values: list, interpolate: bool) -> Tuple[str, str, np.ndarray, np.ndarray]:
    if len(values) > 0:
        logger.debug(f'dataset values: {values}')
    else:
        logger.debug('Zero len of dataset')
        raise ValueError('Zero len of dataset')

    # Get timestamps
    timestamps = np.array([ts for ts, _ in values], dtype=int)
    
    # Assert no nans in timestamps
    has_nan = np.any(np.isnan(timestamps))
    if has_nan:
        logger.info('NaN values in timestamps')
        raise ValueError('NaN values in timestamps')
    
    # Get y
    y = np.array([val for _, val in values], dtype=float)

    # Interpolate nan values in y
    if interpolate:
        y = interpolate_nan_1d(y)

    return y, timestamps


def load_model_and_normalization(model_rel_dirpath: str = None, model_type: Literal['lr', 'xgb', 'prophet'] = 'lr'):
    assert model_type in ['lr', 'xgb', 'prophet']

    normalizations = dict()
    model = None

    file_name = 'normalization.json'
    model_dirpath = '/workspace/models'
    if model_rel_dirpath is not None:
        model_dirpath = os.path.join(model_dirpath, model_rel_dirpath)
    model_path = os.path.join(model_dirpath, file_name)
    logger.debug(f'Model normalization path: {model_path}')

    if os.path.exists(model_path):
        try:
            with open(model_path, 'r') as f:
                normalizations = json.load(f)  # Use json.load() to load JSON from a file
        except json.JSONDecodeError as e:
            logger.error(f"Error decoding JSON from {model_path}: {e}")
    else:
        logger.warning('Normalization not exist')

    if model_type == 'lr':
        file_name = 'model.joblib'
    else:
        if model_type == 'xgb':
            file_name = 'model.json'
        else:
            file_name = 'prophet_model.json'
        
    model_path = os.path.join(model_dirpath, file_name)
    logger.debug(f'Model path: {model_path}')
    
    if os.path.exists(model_path):
        try:
            if model_type == 'lr':
                model = joblib.load(model_path)
            elif model_type == 'xgb':
                model = XGBRegressor()
                model.load_model(model_path)
            else:
                assert model_type == 'prophet'
                with open(model_path, 'r') as f:
                    j = f.read()
                    model = model_from_json(j)
        except Exception as e:
            logger.error(f"Error loading model from {model_path}: {e}")
    else:
        logger.warning('Model not exist')
    
    logger.debug(f'model object: {model}')
    logger.debug(f'normalization object: {normalizations}')

    return model, normalizations


# https://stackoverflow.com/a/6520696
def nan_helper(y):
    """Helper to handle indices and logical indices of NaNs.

    Input:
        - y, 1d numpy array with possible NaNs
    Output:
        - nans, logical indices of NaNs
        - index, a function, with signature indices= index(logical_indices),
          to convert logical indices of NaNs to 'equivalent' indices
    Example:
        >>> # linear interpolation of NaNs
        >>> nans, x= nan_helper(y)
        >>> y[nans]= np.interp(x(nans), x(~nans), y[~nans])
    """

    return np.isnan(y), lambda z: z.nonzero()[0]


def interpolate_nan_1d(y):
    if np.all(np.isnan(y)):
        return y
    nans, x = nan_helper(y)
    y[nans] = np.interp(x(nans), x(~nans), y[~nans])
    return y
