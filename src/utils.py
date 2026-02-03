import logging
import numpy as np
import pandas as pd
import re
from prophet import Prophet
from pathlib import Path
from typing import List, Dict, Tuple
from fpforecast.models.ar import ModelWithMetaInfoAr
from fpforecast.models.prophet import ModelWithMetaInfoProphet


logger = logging.getLogger(__file__)

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

# IV — Invalid (128)
#   Самый высокий приоритет. Если установлен — значение недостоверно и не используется в расчетах.
#   → всегда перекрывает все остальные.
# NT — Not topical / Timeout (64)
#   Данные устарели. Обычно трактуются как недостоверные, но ниже по приоритету, чем invalid.
# BL — Blocked (16)
#   Значение не поступает из-за блокировки источника. Отображается как недоступное, но не всегда снимается из расчетов (зависит от конфигурации).
# SB — Substituted (32)
#   Значение заменено оператором или системой. Достоверность условная, ниже по приоритету, чем ошибки IV/NT/BL.
# OV — Overflow (1)
#   Признак переполнения/некорректного диапазона. Используется в основном для аналогов. Обычно отображается как предупреждение, но данные могут учитываться.
# RES — Резервные биты (2–4)
#   Используются по назначению (например, специфично для типа ТИ/ТС). По приоритету — ниже IV/NT, но выше OV.
# QDS = 0
#   Сигнал в норме.


QDS_BASE = 0  # base QDS value
QDS_INCORRECT_INPUT = 64  # incorrect input bit in QDS
QDS_ERROR = 128  # error bit in QDS

QDS_NONCRITICAL_VALUES = [1, 2, 4, 8, 16, 32, 64]
QDS_CRITICAL_VALUES = [128]
QDS_VALUES = QDS_NONCRITICAL_VALUES + QDS_CRITICAL_VALUES

NON_CRITICAL_THRESHOLD_TO_SET_INCORRECT = 0.5
CRITICAL_THRESHOLD_TO_SET_ERROR = 0.1
NONCRITICAL_THRESHOLD_TO_SET_ERROR = 0.7


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
    df['dt'] = pd.to_datetime(df['dt'], unit='ms')

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
    timestamps = np.array([ts for ts, _, _ in values], dtype=int)
    
    # Assert no nans in timestamps
    has_nan = np.any(np.isnan(timestamps))
    if has_nan:
        logger.info('NaN values in timestamps')
        raise ValueError('NaN values in timestamps')
    
    # Get QDS
    qds = np.array([QDS_INCORRECT_INPUT if qds is None else qds for _, _, qds in values], dtype=int)

    # Get y
    y = np.array([val for _, val, _ in values], dtype=float)

    # For nan values in y, force corresponding qds to 128 (error)
    for i in range(len(y)):
        if np.isnan(y[i]):
            qds[i] = QDS_INCORRECT_INPUT  # set error bit

    # Interpolate nan values in y
    if interpolate:
        y = interpolate_nan_1d(y)

    return timestamps, y, qds


def init_model(model_rel_dirpath: str | None, step: int):
    if model_rel_dirpath is None:
        logger.debug('No model_rel_dirpath provided')
        model = None
    elif model_rel_dirpath == 'none':
        logger.debug('model_rel_dirpath is "none"')
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
            growth='flat',
            # mcmc_samples=100,
            n_changepoints=5,
            seasonality_mode='multiplicative',
            seasonality_prior_scale=30.0,
            **seasonality_kwargs,
        )
    elif model_rel_dirpath == 'sbre':
        logger.debug('model_rel_dirpath is "sbre"')
        model = SbreModel()
    else:
        model_type = model_rel_dirpath.split('/')[0]
        assert model_type in ['xgb', 'prophet']

        base_dirpath = Path('/workspace/models')
        model_rel_dirpath = Path(model_rel_dirpath)

        model_dirpath = base_dirpath / model_rel_dirpath
        if model_type == 'xgb':
            logger.debug(f'Trying to loading xgb model from {model_dirpath}')
            model_filepath = model_dirpath / 'xgb_model.json'
            model_class = ModelWithMetaInfoAr
        elif model_type == 'prophet':
            logger.debug(f'Trying to loading prophet model from {model_dirpath}')
            model_filepath = model_dirpath / 'prophet_model.json'
            model_class = ModelWithMetaInfoProphet
        
        if not model_filepath.is_file():
            logger.warning(f'Model file not found: {model_filepath}')
            model = None
        else:
            logger.debug(f'Loading model from {model_filepath}')
            model = model_class.load_model(model_filepath)

    logger.debug(f'Initialized model: {model}')
    return model


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
