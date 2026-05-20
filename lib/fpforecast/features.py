import dataclasses
import holidays
import pandas as pd
import numpy as np
from typing import Literal, List

from fpforecast.constants import UTC_SHIFT_HOURS, COD_EN_TO_MES, KOD_OBLASTI_TO_PATH


@dataclasses.dataclass
class FeatureInfo:
    # Feature name
    name: str

    # Whether the feature is from the past or future time window
    span: Literal['past', 'future']

    # Feature type
    type_: Literal['categorical', 'numerical']

    # Aggregation method
    agg: Literal[
        'full', 'first', 'last', 'n_intervals', 
        'rel_start', 'rel_end', 'share', 'integral'
    ]

    # If not None, downsample the feature by taking every cycle_h-th value
    cycle_h: int | None


def make_features(df):
    """Make features."""

    features_info: List[FeatureInfo] = []

    # Input
    features_info.append(FeatureInfo(name='value', span='past', type_='numerical', agg='full', cycle_h=1))

    # Future values
    # - planned values from BEMS
    # - weather (temperature etc.) forecasts
    # - aux features (e.g. load is aux feature for loss task) forecasts
    planned_cols = [
        col for col in df.columns if 
        col.startswith('plan_') or
        col.startswith('weather_') or
        col.startswith('aux_')
    ]
    for col in planned_cols:
        features_info.append(FeatureInfo(name=col, span='future', type_='numerical', agg='full', cycle_h=1))

    # Repairs
    repair_cols = [col for col in df.columns if col.startswith('is_repair_') or col.startswith('repair_power_drop_')]
    for col in repair_cols:
        # Actually, is_repair_X and repair_power_drop_X are always paired,
        # so there is 5 features in total and starts / ends are covered by is_repair_X features
        if col.startswith('is_repair_'):
            features_info.append(FeatureInfo(name=col, span='future', type_='numerical', agg='n_intervals', cycle_h=None))
            features_info.append(FeatureInfo(name=col, span='future', type_='numerical', agg='rel_start', cycle_h=None))
            features_info.append(FeatureInfo(name=col, span='future', type_='numerical', agg='rel_end', cycle_h=None))
            features_info.append(FeatureInfo(name=col, span='future', type_='numerical', agg='share', cycle_h=None))
        elif col.startswith('repair_power_drop_'):
            features_info.append(FeatureInfo(name=col, span='future', type_='numerical', agg='integral', cycle_h=None))

    # Calendar features
    df['hour'] = df.index.hour
    features_info.append(FeatureInfo(name='hour', span='future', type_='categorical', agg='first', cycle_h=None))
    df['dayofweek'] = df.index.dayofweek
    features_info.append(FeatureInfo(name='dayofweek', span='future', type_='categorical', agg='first', cycle_h=None))
    df['month'] = df.index.month
    features_info.append(FeatureInfo(name='month', span='future', type_='categorical', agg='first', cycle_h=24))
    df['dayofyear'] = df.index.dayofyear
    features_info.append(FeatureInfo(name='dayofyear', span='future', type_='numerical', agg='first', cycle_h=None))

    # Holidays
    years = df.index.year.unique().tolist()
    holidays_kz = holidays.KZ(years=years)
    df['is_holiday'] = df.index.normalize().isin(holidays_kz).astype(int)
    features_info.append(FeatureInfo(name='is_holiday', span='future', type_='categorical', agg='first', cycle_h=24))
    features_info.append(FeatureInfo(name='is_holiday', span='past', type_='categorical', agg='first', cycle_h=24))

    return df, features_info


def read_rz_single(filepath, date_handling: Literal['priority', 'f_or_r', 'r'] = 'r') -> pd.DataFrame:
    df = pd.read_csv(filepath, skipfooter=1, converters={'shifrIMJ': str}, engine='python')

    df['shifrIMJ'] = df['shifrIMJ'].str.pad(10, fillchar='0')
    df['cod_en'] = df['shifrIMJ'].str[:2]
    df['cod_obj'] = df['shifrIMJ'].str[2:4]
    df['cod_en_obj'] = df['shifrIMJ'].str[:4]
    df['cod_en_obj_vidobor'] = df['shifrIMJ'].str[:6]

    df['data_post'] = pd.to_datetime(df['data_post'], format='%H:%M %d.%m.%Y', errors='coerce')
    if 'data_f_N' in df.columns:
        df['data_f_N'] = pd.to_datetime(df['data_f_N'], format='%H:%M %d.%m.%Y', errors='coerce')
        df['data_f_K'] = pd.to_datetime(df['data_f_K'], format='%H:%M %d.%m.%Y', errors='coerce')
    df['data_p_N'] = pd.to_datetime(df['data_p_N'], format='%H:%M %d.%m.%Y', errors='coerce')
    df['data_p_K'] = pd.to_datetime(df['data_p_K'], format='%H:%M %d.%m.%Y', errors='coerce')
    df['data_r_N'] = pd.to_datetime(df['data_r_N'], format='%H:%M %d.%m.%Y', errors='coerce')
    df['data_r_K'] = pd.to_datetime(df['data_r_K'], format='%H:%M %d.%m.%Y', errors='coerce')

    df['P_stanc'] = df['P_stanc'].str.strip().str.rstrip()
    df['p_sni'] = df['p_sni'].str.strip().str.rstrip()
    df['P_stanc'] = pd.to_numeric(df['P_stanc'], errors='coerce')
    df['p_sni'] = pd.to_numeric(df['p_sni'], errors='coerce')
    df['P_stanc'] = df['P_stanc'].fillna(0)
    df['p_sni'] = df['p_sni'].fillna(0)

    if date_handling == 'priority':
        if 'data_f_N' in df.columns:
            df['data_N'] = df['data_f_N'].fillna(df['data_r_N']).fillna(df['data_p_N'])
            df['data_K'] = df['data_f_K'].fillna(df['data_r_K']).fillna(df['data_p_K'])

            df = df.drop(columns=[
                'data_f_N', 'data_f_K',
                'data_r_N', 'data_r_K',
                'data_p_N', 'data_p_K',
            ])
        else:
            df['data_N'] = df['data_r_N'].fillna(df['data_p_N'])
            df['data_K'] = df['data_r_K'].fillna(df['data_p_K'])

            df = df.drop(columns=[
                'data_r_N', 'data_r_K',
                'data_p_N', 'data_p_K',
            ])
    elif date_handling == 'f_or_r':
        if 'data_f_N' in df.columns:
            df['data_N'] = df['data_f_N']
            df['data_K'] = df['data_f_K']
        else:
            df['data_N'] = df['data_r_N']
            df['data_K'] = df['data_r_K']
    elif date_handling == 'r':
        df['data_N'] = df['data_r_N']
        df['data_K'] = df['data_r_K']
    else:
        raise ValueError(f"Unknown date_handling value: {date_handling}")

    df = df[(~df['data_N'].isna()) & (~df['data_K'].isna())]
    df = df[df['data_K'] >= df['data_N']]
    df = df[df['data_N'] >= df['data_post']]
    df = df.sort_values('data_post')

    return df


def read_aux_remont_data(data_dirpath) -> tuple[pd.DataFrame, pd.DataFrame]:
    df_remont_obj = pd.read_csv(
        data_dirpath / 'obj.csv', 
        skipfooter=1, 
        converters={'cod_en': str, 'cod_obj': str},
        engine='python',
    )
    df_remont_obj['nam_obj'] = df_remont_obj['nam_obj'].str.strip()

    df_remont_en = pd.read_csv(
        data_dirpath / 'energo.csv', 
        skipfooter=1, 
        converters={'cod': str},
        engine='python',
    )
    df_remont_en['oblast'] = df_remont_en['oblast'].str.split()
    df_remont_en = df_remont_en.explode('oblast').reset_index(drop=True)
    df_remont_en['oblast'] = df_remont_en['oblast'].str.strip().astype(float)

    return df_remont_obj, df_remont_en


def melt_rz_data(df_rz: pd.DataFrame) -> pd.DataFrame:
    df_rz_melt = df_rz[['data_post', 'data_N', 'data_K', 'shifrIMJ', 'cod_en_obj', 'cod_en_obj_vidobor', 'mes', 'region_path', 'Kod_TypObj', 'occurence', 'p_sni']] \
        .melt(
            id_vars=['data_post', 'shifrIMJ', 'cod_en_obj', 'cod_en_obj_vidobor', 'mes', 'region_path', 'Kod_TypObj', 'occurence', 'p_sni'],
            value_vars=['data_N', 'data_K'],
            var_name='event_type',
            value_name='event_date',
        ) \
        .sort_values(by='event_date') \
        .reset_index(drop=True) \
        .dropna(subset=['event_date'])

    df_rz_melt.loc[df_rz_melt['event_type'] == 'data_K', 'occurence'] = -df_rz_melt.loc[df_rz_melt['event_type'] == 'data_K', 'occurence']
    df_rz_melt.loc[df_rz_melt['event_type'] == 'data_K', 'p_sni'] = -df_rz_melt.loc[df_rz_melt['event_type'] == 'data_K', 'p_sni']
    df_rz_melt = df_rz_melt.set_index('event_date')

    return df_rz_melt


def read_remont_data(data_dirpath) -> tuple[pd.DataFrame, pd.DataFrame]:
    df_mrz = read_rz_single(data_dirpath / 'r_MRZ.csv')
    df_orz = read_rz_single(data_dirpath / 'r_ORZ.csv')
    df_rz = pd.concat([df_mrz, df_orz], axis=0)

    df_rz['occurence'] = 1

    df_remont_obj, df_remont_en = read_aux_remont_data(data_dirpath)

    df_rz = df_rz.merge(df_remont_obj, on=['cod_en', 'cod_obj'], how='left')
    df_rz = df_rz.merge(df_remont_en, left_on='cod_en', right_on='cod', how='left')
    df_rz = df_rz.sort_values(by='data_N').reset_index(drop=True)

    # Map kod_oblasti to region path
    df_rz['region_path'] = df_rz['Kod_Oblasti'].apply(lambda x: int(x) if not np.isnan(x) else -1).map(KOD_OBLASTI_TO_PATH)

    # Map cod_en to MES
    df_rz['mes'] = df_rz['cod_en'].map(COD_EN_TO_MES)
    df_rz = df_rz.dropna(subset=['mes'])

    # TODO: map cod_en_obj to SS path

    # Drop cod_en & Kod_Oblasti after mapping
    df_rz = df_rz.drop(columns=['cod_en', 'Kod_Oblasti'])

    # Melt data
    df_rz_melt = melt_rz_data(df_rz)

    # Time-zone shift: convert to UTC
    df_rz['data_post'] = df_rz['data_post'] + pd.Timedelta(hours=-UTC_SHIFT_HOURS)
    df_rz['data_N'] = df_rz['data_N'] + pd.Timedelta(hours=-UTC_SHIFT_HOURS)
    df_rz['data_K'] = df_rz['data_K'] + pd.Timedelta(hours=-UTC_SHIFT_HOURS)
    
    return df_rz, df_rz_melt


def merge_rz_structure(df_rz_melt: pd.DataFrame, df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    index_name = df.index.name
    df = df.reset_index()
    orig_index = df.index.copy()

    df_region = df_rz_melt.reset_index()
    serieses = []
    for cod_en_obj_vidobor in df_region['cod_en_obj_vidobor'].unique():
        df_current = df_region[(df_region['cod_en_obj_vidobor'] == cod_en_obj_vidobor)].copy()
        df_current['occurence_cum'] = df_current['occurence'].cumsum()
        df_current['p_sni_cum'] = df_current['p_sni'].cumsum()
        df_current = df_current[['event_date', 'occurence_cum', 'p_sni_cum']]
        df_tmp = pd.merge(
            df,
            df_current,
            left_on='dt',
            right_on='event_date',
            how='outer',
        )
        df_tmp[['occurence_cum', 'p_sni_cum']] = df_tmp[['occurence_cum', 'p_sni_cum']].ffill()
        df_tmp = df_tmp.rename(columns={
            'occurence_cum': f'is_repair_{cod_en_obj_vidobor}',
            'p_sni_cum': f'repair_power_drop_{cod_en_obj_vidobor}',
        })
        df_tmp = df_tmp.loc[orig_index]
        serieses.append(df_tmp[[f'is_repair_{cod_en_obj_vidobor}', f'repair_power_drop_{cod_en_obj_vidobor}']].reset_index(drop=True))

    df_merged = pd.concat(serieses, axis=1)
    df = pd.concat([df.reset_index(drop=True), df_merged], axis=1)
    df = df.set_index(orig_index)

    df = df.set_index(index_name)

    return df
