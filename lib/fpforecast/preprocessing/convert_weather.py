import argparse
import json
import logging
import os
import pandas as pd
import numpy as np
from tqdm import tqdm
from typing import List, Dict, Any
from bisect import bisect_left
from datetime import datetime
from pathlib import Path

from fpforecast.constants import ALLOWED_LAT_LON_BOUNDS, UTC_SHIFT_HOURS


logging.basicConfig(level=os.environ.get("LOGLEVEL", "INFO"))
logger = logging.getLogger(__name__)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        'input_dirpath',
        type=Path,
        help='Directory path containing weather json files.'
    )
    parser.add_argument(
        'output_filepath',
        type=Path,
        help='Output parquet filepath.'
    )
    parser.add_argument(
        '--start_dt',
        type=str,
        default='2019-01-01 00:00:00 +0000 UTC',
        help='Start datetime in format "YYYY-MM-DD HH:MM:SS +0000 UTC".'
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help='If set, process only a subset of files for debugging.'
    )
    args = parser.parse_args()
    return args


def get_ge_index(start_dt: datetime, data: List[Dict[Any, Any]]):
    """ Get index of the last element with dt_iso greater or equal than start_dt
    data is sorted by dt_iso
    dt_iso is '1979-01-01 00:00:00 +0000 UTC' format
    """
    index = bisect_left(
        data,
        start_dt,
        key=lambda x: datetime.strptime(x['dt_iso'], '%Y-%m-%d %H:%M:%S %z UTC')
    )
    return index


def preprocess_weather_single(filepath: Path) -> pd.DataFrame | None:
    with open(filepath, 'r') as f:
        data = json.load(f)

    lat, lon = data[0]['lat'], data[0]['lon']

    if (
        not (
            (lat >= ALLOWED_LAT_LON_BOUNDS['lat_min']) and 
            (lat <= ALLOWED_LAT_LON_BOUNDS['lat_max']) and
            (lon >= ALLOWED_LAT_LON_BOUNDS['lon_min']) and
            (lon <= ALLOWED_LAT_LON_BOUNDS['lon_max'])
        )
    ):
        return None

    start_index = get_ge_index(
        datetime.strptime(args.start_dt, '%Y-%m-%d %H:%M:%S %z UTC'),
        data
    )
    df = pd.DataFrame(data[start_index:])
    cols_to_keep = []

    df['dt'] = pd.to_datetime(df['dt_iso'], format='%Y-%m-%d %H:%M:%S %z UTC')
    cols_to_keep.append('dt')

    df['temp'] = df['main'].apply(lambda x: x['temp'])
    df['humidity'] = df['main'].apply(lambda x: x['humidity'])
    df['dew_point'] = df['main'].apply(lambda x: x['dew_point'])
    cols_to_keep.extend(['temp', 'humidity', 'dew_point'])

    wind_speed = df['wind'].apply(lambda x: x['speed'])
    df['win_v'] = wind_speed * df['wind'].apply(lambda x: np.sin(np.deg2rad(x['deg'])))
    df['win_u'] = wind_speed * df['wind'].apply(lambda x: np.cos(np.deg2rad(x['deg'])))
    cols_to_keep.extend(['win_u', 'win_v'])

    df['clouds_all'] = df['clouds'].apply(lambda x: x['all'])
    cols_to_keep.append('clouds_all')

    df = df[cols_to_keep]
    df = df.set_index('dt')

    # Make df multiindex by columns:
    # - first level is (lat, lon)
    # - second level is original column names
    df.columns = pd.MultiIndex.from_product([[f'{(lat, lon)}'], df.columns])

    # Shift time
    df.index = df.index.shift(UTC_SHIFT_HOURS, freq='h')  # Convert from UTC to local time
    
    return df


def main(args):
    filepaths = sorted(
        [
            filepath for filepath in args.input_dirpath.glob('**/*.json') 
            if filepath.name != '0_51_6956_75_3297_00336489hfb.json'  # corrupted file
        ]
    )

    if args.debug:
        filepaths = filepaths[:10]

    pbar = tqdm(filepaths)
    error_filepaths = []
    dfs = []
    for filepath in pbar:
        pbar.set_description(f'Processing {filepath.name}')
        try:
            df = preprocess_weather_single(filepath)
            if df is None:
                logger.info(f'Skipping {filepath} due to expected issues.')
                continue
            dfs.append(df)
        except Exception as e:
            error_filepaths.append(filepath)
            print(f'Error processing {filepath}: {e}')
    df = pd.concat(dfs, axis=1)
    df.to_parquet(args.output_filepath)


if __name__ == '__main__':
    args = parse_args()
    main(args)
