# Mariya Polkovnikova
# 2026.03.17, 04:41 PM


from typing import Any

from api.utils import get_last_past_index

import numpy as np
import pandas as pd


def get_full_days_mask(timestamps: np.ndarray, offset_days: int) -> Any:
    """
    Get mask for full days.

    :param np.ndarray timestamps: Array of timestamps.
    :param int offset_days: Offset days.

    :return: Mask for full days.
    :rtype: Any
    """

    last_past_index = get_last_past_index(timestamps)

    df = pd.DataFrame({"dt": timestamps})
    df["dt"] = pd.to_datetime(df["dt"], unit="ms")

    date = df["dt"].dt.floor("D")
    current_date = date.iloc[last_past_index]
    target_date = current_date + pd.Timedelta(days=offset_days)

    mask = date == target_date
    return mask.values


def get_weekday(timestamps: np.ndarray) -> Any:
    """
    Get weekday for the last past index.

    :param np.ndarray timestamps: Array of timestamps.

    :return: Weekday for the last past index.
    :rtype: Any
    """

    last_past_index = get_last_past_index(timestamps)

    df = pd.DataFrame({"dt": timestamps})
    df["dt"] = pd.to_datetime(df["dt"], unit="ms")

    return df["dt"].dt.weekday.iloc[last_past_index]
