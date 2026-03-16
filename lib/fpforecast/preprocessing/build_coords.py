import argparse
import numpy as np
import pandas as pd
from pathlib import Path

from fpforecast.constants import ALLOWED_LAT_LON_BOUNDS, DEFAULT_LAT, DEFAULT_LON


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        'input_dirpath',
        type=Path,
        help='Path to directory with "imports" and "current" subdirectories containing excel files with station coordinates.'
    )
    parser.add_argument(
        'output_filepath',
        type=Path,
        help='Path to output CSV file with consolidated station coordinates.'
    )
    return parser.parse_args()


def build_coords_import(dirpath: Path):
    dfs = []
    for filepath in dirpath.glob('*.xlsx'):
        df_ss = pd.read_excel(filepath)
        dfs.append(df_ss)
    df_all_ss = pd.concat(dfs, ignore_index=True)
    df_all_ss['prototype@weather'] = df_all_ss['prototype@weather'].str.replace('/weather', '').str.replace('/PROJECT/KAZ', '').str.replace('/PROJECT', '')
    df_all_ss = df_all_ss[~((df_all_ss['lat'] == ':atom:null') | (df_all_ss['lon'] == ':atom:null'))][['prototype@weather', 'lat', 'lon']]

    df_all_ss['lat'] = df_all_ss['lat'].astype(float)
    df_all_ss['lon'] = df_all_ss['lon'].astype(float)

    # Fix swapped lat/lon
    mask = (
        df_all_ss['lat'].between(ALLOWED_LAT_LON_BOUNDS['lat_min'], ALLOWED_LAT_LON_BOUNDS['lat_max']) & 
        df_all_ss['lon'].between(ALLOWED_LAT_LON_BOUNDS['lon_min'], ALLOWED_LAT_LON_BOUNDS['lon_max'])
    )
    tmp = df_all_ss.loc[~mask, 'lat'].copy()
    df_all_ss.loc[~mask, 'lat'] = df_all_ss.loc[~mask, 'lon']
    df_all_ss.loc[~mask, 'lon'] = tmp

    # Drop stations still out of bounds
    mask = (
        df_all_ss['lat'].between(ALLOWED_LAT_LON_BOUNDS['lat_min'], ALLOWED_LAT_LON_BOUNDS['lat_max']) & 
        df_all_ss['lon'].between(ALLOWED_LAT_LON_BOUNDS['lon_min'], ALLOWED_LAT_LON_BOUNDS['lon_max'])
    )
    df_all_ss = df_all_ss[mask].reset_index(drop=True)

    MAPPING_OLD_TO_NEW = {
        '/VOSTOK/@regions/AbayRegion': '/VOSTOK/@regions/Abai',
        '/UZHNIY/@regions/UkO': '/UZHNIY/@regions/Turkestan',
        '/UZHNIY/@regions/KzO': '/UZHNIY/@regions/KysylOrda',
        '/UZHNIY/@regions/JamO': '/UZHNIY/@regions/Zhambyl',
        '/SEVER/@regions/Pavlodar2': '/SEVER/@regions/Pavlodar',
        '/KOSTANAY/@regions/Kostanay2': '/KOSTANAY/@regions/Kostanay',
        '/ALMATY/@regions/AlmO': '/ALMATY/@regions/Almaty',
        '/AKTOBE/@regions/ZkO': '/AKTOBE/@regions/West Kazakhstan',
        '/AKTOBE/@regions/Aktobe': '/AKTOBE/@regions/Aktobe',
        '/AKMOLA/@regions/SevKazObl2': '/AKMOLA/@regions/North Kazakhstan',
        '/AKMOLA/@regions/Akmola2': '/AKMOLA/@regions/Akmola',
    }
    df_all_ss['prototype@weather'] = df_all_ss['prototype@weather'].replace(MAPPING_OLD_TO_NEW)
    return df_all_ss


def build_coords_current(dirpath: Path):
    dfs = []
    for filepath in dirpath.glob('*.xlsx'):
        df_ss = pd.read_excel(filepath)
        mask = \
            (df_ss['lat'] != ':atom:null') & \
            (df_ss['lon'] != ':atom:null') 
        df_ss = df_ss[mask]
        df_ss['lat'] = df_ss['lat'].astype(float)
        df_ss['lon'] = df_ss['lon'].astype(float)

        df_ss = df_ss[['prototype@weather', 'lat', 'lon']]
        df_ss['prototype@weather'] = '/' + df_ss['prototype@weather'].str.split('/').str[2:-1].str.join('/')

        dfs.append(df_ss)
    df_all_ss = pd.concat(dfs, ignore_index=True)
    return df_all_ss


def build_coords(dirpath: Path):
    df_import = build_coords_import(dirpath / 'imports')
    df_current = build_coords_current(dirpath / 'current')

    # Concatenate and drop duplicates: imports are preferred over current
    df_all_ss = pd.concat([df_import, df_current], ignore_index=True)
    df_all_ss = df_all_ss.drop_duplicates(subset=['prototype@weather'], keep='first').reset_index(drop=True)
    
    # Drop
    TO_DROP = [
        '/@regions/ALMATY/test',
        '/test/view_elements/substation',
        '/AKMOLA/@regions/SevKaz_obl',
    ]
    df_all_ss = df_all_ss[~df_all_ss['prototype@weather'].isin(TO_DROP)].reset_index(drop=True)

    mask = ~((np.isclose(df_all_ss['lat'], DEFAULT_LAT, atol=1e-2)) & (np.isclose(df_all_ss['lon'], DEFAULT_LON, atol=1e-2))) & \
        (df_all_ss['lat'] >= ALLOWED_LAT_LON_BOUNDS['lat_min']) & (df_all_ss['lat'] <= ALLOWED_LAT_LON_BOUNDS['lat_max']) & \
        (df_all_ss['lon'] >= ALLOWED_LAT_LON_BOUNDS['lon_min']) & (df_all_ss['lon'] <= ALLOWED_LAT_LON_BOUNDS['lon_max']) & \
        (df_all_ss['lat'].notna()) & (df_all_ss['lon'].notna())
    df_all_ss = df_all_ss[mask].reset_index(drop=True)

    # Add "/{mes_name}" row with default coordinates
    # calculate them as mean cooridnates of \
    # all other stations except ones that has "@regions" in their names
    for mes_name in df_all_ss['prototype@weather'].str.split('/').str[1].unique():
        non_region_mask = (~df_all_ss['prototype@weather'].str.contains('@regions')) & \
            (df_all_ss['prototype@weather'].str.contains(f'/{mes_name}/'))
        df_all_ss = pd.concat([
            df_all_ss,
            pd.DataFrame([{
                'prototype@weather': f'/{mes_name}',
                'lat': df_all_ss.loc[non_region_mask, 'lat'].mean(),
                'lon': df_all_ss.loc[non_region_mask, 'lon'].mean(),
            }])
        ], ignore_index=True)

    # Strip "/"
    df_all_ss['prototype@weather'] = df_all_ss['prototype@weather'].str.strip('/')

    # Sort by 'prototype@weather'
    df_all_ss = df_all_ss.sort_values(by='prototype@weather').reset_index(drop=True)

    return df_all_ss


def main(args):
    df_all_ss = build_coords(args.input_dirpath)
    df_all_ss.to_csv(args.output_filepath, index=False)


if __name__ == '__main__':
    args = parse_args()
    main(args)
