import pandas as pd
import numpy as np
import random
import os


def fix_df(df, interpolate=True):
    """
    0) Drop duplicating indexes.
    1) Replace outliers with NaN.
    2) Add missing hourly rows with NaN.
    3) Interpolate NaN values linearly.
    """
    df = df[~df.index.duplicated(keep='first')]

    q_low = df['value'].quantile(0.01)
    q_high = df['value'].quantile(0.99)
    df.loc[(df['value'] < q_low) | (df['value'] > q_high), 'value'] = None

    df = df.asfreq('h')
    assert df.index.diff().dropna().unique().tolist() == [pd.Timedelta('1h')], f"DataFrame index is not hourly! Got: {df.index.diff().unique().tolist()}"

    if interpolate:
        df['value'] = df['value'].interpolate(method='linear')

    return df


def seed_everything(seed):
    random.seed(seed)
    os.environ['PYTHONHASHSEED'] = str(seed)
    np.random.seed(seed)
