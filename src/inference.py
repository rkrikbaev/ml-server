# Config logging
import logging
import os

logging.basicConfig(
    format='%(asctime)s,%(msecs)d %(name)s %(levelname)s %(message)s',
    datefmt='%H:%M:%S',
    level=os.environ.get('LOGLEVEL', 'INFO'),
)
logger = logging.getLogger(__file__)

import argparse
import datetime
import json
import numpy as np
import pandas as pd
import re
from pathlib import Path
from typing import Any, List, Dict, Tuple
from xgboost import XGBRegressor


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
    is_holiday = df['dt'].dt.date.isin(HOLIDAYS)
    is_forced_non_holiday = df['dt'].dt.date.isin(FORCE_NON_HOLIDAYS)
    is_day_off = df['weekday'].isin({5, 6}) & ((~is_forced_non_holiday) | is_holiday)
    
    is_today_day_off = is_day_off.astype(int)
    is_tomorrow_day_off = (is_day_off.astype(float).shift(-n_predict_steps).fillna(0) > 0).astype(int)
    df['day_off_change'] = is_today_day_off - is_tomorrow_day_off

    return {
        'day_off_change': df['day_off_change'].values,
        'weekday': df['weekday'].values,
    }


def extract_features(
    timestamps: np.ndarray,
    y: np.ndarray,
    sub: Dict[str, float],
    div: Dict[str, float],
    n_predict_steps: int = 24,
):
    values = []

    # Add y feature
    y = (y - sub['y']) / div['y']
    values.append(y)

    # Add calendar features
    calendar_features = timestamps_to_calendar_features(timestamps, n_predict_steps=n_predict_steps)
    calendar_features['day_off_change'] = (calendar_features['day_off_change'] - sub['day_off_change']) / div['day_off_change']
    calendar_features['weekday'] = (calendar_features['weekday'] - sub['weekday']) / div['weekday']
    values.append(calendar_features['day_off_change'])
    values.append(calendar_features['weekday'])

    return np.concatenate(values)

def predict(
    model,
    timestamps: np.ndarray,
    y: np.ndarray,
    sub: Dict[str, float],
    div: Dict[str, float],
    n_predict_steps: int,
):
    # Get features
    X = extract_features(
        timestamps,
        y,
        sub=sub,
        div=div,
        n_predict_steps=n_predict_steps,
    )[None, :]

    # Predict
    y_pred = model.predict(X)

    # Unnormalize
    y_pred = y_pred * div['y'] + sub['y']

    return y_pred


def extract_from_fp_record(data: list, param) -> Tuple[str, str, np.ndarray, np.ndarray]:
    # Convert FP name to ids
    # region, line_id = record_dict['metadata']['region'], record_dict['metadata']['object']
    
    logger.debug(f'data: {data}')
    # logger.debug(f'param: {param}')

    if not isinstance(data, list):
        raise ValueError('Data is not a list')
    
    values = data[0]
    
    # values = d.get(param,[])

    # logger.debug(f'Values: {values}')

    if len(values) > 0:
        logger.debug(f'dataset values: {values}')
    else:
        logger.debug('Zero len of dataset')
        raise ValueError('Zero len of dataset')

    # Get timestamps
    timestamps = np.array([ts for ts, _ in values], dtype=int)
    
    # Проверка на наличие NaN
    has_nan = np.any(np.isnan(timestamps))

    # Get y
    y = np.array([val for _, val in values], dtype=float)

    # Проверка на наличие NaN
    has_nan = np.any(np.isnan(y))

    if has_nan:
        logger.info('NaN values in data')
        raise ValueError('NaN values in data')

    return y, timestamps

if __name__ == '__main__':
    # Check features shape
    # on the last 20 entries from faceplate-formatted .csv
    # for the col stated below
    fp_record_example = \
'''{
    "dataset": {
            "p_load": [
                [
                    1710799200000,
                    1718.000021111117
                ],
                [
                    1710802800000,
                    1603.8333507870418
                ],
                [
                    1710806400000,
                    1489.833346620374
                ],
                [
                    1710810000000,
                    1409.5000043055568
                ],
                [
                    1710813600000,
                    1321.1666750462987
                ],
                [
                    1710817200000,
                    1289.6666712962976
                ],
                [
                    1710820800000,
                    1259.8333307870364
                ],
                [
                    1710824400000,
                    1255.6666604629613
                ],
                [
                    1710828000000,
                    1254.166664768518
                ],
                [
                    1710831600000,
                    1280.6666654629626
                ],
                [
                    1710835200000,
                    1308.6666687962968
                ],
                [
                    1710838800000,
                    1398.209584541681
                ],
                [
                    1710842400000,
                    1540.9999836111065
                ]
            ]
        },
        {
            "temperature": [
                [
                    1710799200000,
                    1.2
                ],
                [
                    1710802800000,
                    1.2
                ],
                [
                    1710806400000,
                    1.2
                ],
                [
                    1710810000000,
                    -0.1
                ],
                [
                    1710813600000,
                    -0.1
                ],
                [
                    1710817200000,
                    -0.1
                ],
                [
                    1710820800000,
                    -0.5
                ],
                [
                    1710824400000,
                    -0.5
                ],
                [
                    1710828000000,
                    -0.5
                ],
                [
                    1710831600000,
                    -0.2
                ],
                [
                    1710835200000,
                    -0.2
                ],
                [
                    1710838800000,
                    -0.2
                ],
                [
                    1710842400000,
                    3.0
                ]
            ]
        },
    "metadata": null,
    "model_config": {
        "granularity": 3600,
        "input_window": 12,
        "output_window": 4
    },
    "model_point": "nodes_almaty_config_p_load",
    "model_run_id": "none",
    "model_tag": "/root/PROJECT/TAGS/Nodes/Almaty/config_p_load",
    "model_type": "prophet_model",
    "period": null,
    "task_id": null,
    "task_status": "QUEUED"
}'''
    fp_record_example_len = 13
    fp_record_example_dict = json.loads(fp_record_example)
    col, loss, timestamps = extract_from_fp_record(fp_record_example_dict)
    assert loss.shape == timestamps.shape == (fp_record_example_len,)

    features = extract_features(loss, 0.0, 1.0)
    assert features.shape == ((fp_record_example_len - 1) * 2 + 6,)
    logger.info(f'features.shape: {features.shape}')
    logger.debug(f'features: {features}')

    # Load model & run on random data
    parser = argparse.ArgumentParser('Evaluate XGBoost model')
    parser.add_argument('--model_filepath', type=Path, help='path to model .json file')
    args = parser.parse_args()

    if args.model_filepath is not None:
        model = XGBRegressor()
        model.load_model(args.model_filepath)

        logger.info(
            predict(
                model=model,
                col=col,
                consumption=np.random.rand(144),
                temperature=np.random.rand(144),
                timestamps=np.array([1735591200 + i * 600 for i in range(144)]),
            )
        )
