# Mariya Polkovnikova
# 2026.03.17, 10:09 AM


from typing import List, Tuple
from datetime import datetime, timedelta, timezone

from api import GMT_TO_ASTANA_HOURS

import numpy as np
import pandas as pd


def generate_timestamp(mode: str) -> Tuple[int, int]:
    """
    Generate timestamp for the given mode.

    :param str mode: The mode for which to generate the timestamp. Supported
        modes are "short", "medium", and "long".

    :return: A tuple containing the start timestamp (from_tp) and end
        timestamp (to_tp) in seconds since the epoch.
    :rtype: Tuple[int, int]
    """

    utc = timezone.utc
    d = datetime.now(tz=utc)

    match mode:
        case "short":
            from_tp = datetime(d.year, d.month, d.day, 0, 0, 0, 0, utc)
            to_tp = from_tp + timedelta(days=3)
        case "medium":
            from_tp = datetime(d.year, d.month, 1, 0, 0, 0, 0, utc)
            if d.month == 12:
                to_tp = datetime(d.year + 1, 1, 1, 0, 0, 0, 0, utc)
            else:
                to_tp = datetime(d.year, d.month + 1, 1, 0, 0, 0, 0, utc)
        case _:  # "long"
            from_tp = datetime(d.year, 1, 1, 0, 0, 0, 0, utc)
            to_tp = datetime(d.year + 1, 1, 1, 0, 0, 0, 0, utc)

    from_tp = int(datetime.timestamp(from_tp)) * 1000
    to_tp = int(datetime.timestamp(to_tp)) * 1000
    return from_tp, to_tp


def timestamps_to_timezoned_timestamps(
    timestamps: List[int] | np.ndarray,
    timezone_offset_hours: int
) -> np.ndarray:
    """
    Convert a list of timestamps in ms to timezoned timestamps in ms.

    :param List[int] | np.ndarray timestamps: List of timestamps in ms.
    :param int timezone_offset_hours: Timezone offset in hours.

    :return: Timezoned timestamps in ms.
    :rtype: np.ndarray
    """

    # Convert to pandas datetime
    df = pd.DataFrame({"dt": timestamps})
    df["dt"] = pd.to_datetime(df["dt"], unit="ms")

    # Apply timezone offset
    df["dt"] = df["dt"] + pd.to_timedelta(timezone_offset_hours, unit="h")

    # Convert back to timestamps in ms.
    # Pandas may preserve a datetime64[ms] dtype here, so dividing by 10**6
    # can accidentally downscale values to seconds. Convert explicitly through
    # Timestamp.timestamp() to keep millisecond precision stable.
    return df["dt"].map(lambda dt: int(dt.timestamp() * 1000)).to_numpy(dtype=np.int64)


def get_pred_timestamps(ts: np.ndarray, step: int, output_range: int) -> Tuple[int, np.ndarray]:
    """
    Get prediction timestamps for the given timestamps, step, and output
    range.

    :param np.ndarray ts: Array of timestamps in ms.
    :param int step: Step in ms.
    :param int output_range: Output range.

    :return: A tuple containing the last past index and prediction timestamps
        in ms.
    :rtype: Tuple[int, np.ndarray]
    """

    # Convert to Astana timezone
    ts_zoned = timestamps_to_timezoned_timestamps(ts, GMT_TO_ASTANA_HOURS)

    # Split point: assume input is past + future window, so past length = len(ts) - output_range
    # This avoids incorrect mid-split when W_past != W_future.

    last_past_index = len(ts_zoned) - output_range
    pred_start_dt = pd.to_datetime(ts_zoned[last_past_index], unit="ms")

    if step == 2592000000:  # Round to the current month start, then add one month
        pred_start_dt = pred_start_dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        pred_start_dt = pred_start_dt + pd.DateOffset(months=1)
        pred_dt = [pred_start_dt + pd.DateOffset(months=i) for i in range(output_range)]

    elif step == 86400000:  # Round to the current day start, then add one day
        pred_start_dt = pred_start_dt.replace(hour=0, minute=0, second=0, microsecond=0)
        pred_start_dt = pred_start_dt + pd.DateOffset(days=1)
        pred_dt = [pred_start_dt + pd.DateOffset(days=i) for i in range(output_range)]

    elif step == 3600000:  # Round to the current hour start, then add one hour
        pred_start_dt = pred_start_dt.replace(minute=0, second=0, microsecond=0)
        pred_start_dt = pred_start_dt + pd.DateOffset(hours=1)
        pred_dt = [pred_start_dt + pd.DateOffset(hours=i) for i in range(output_range)]

    else:  # Do not round for other steps
        pass

    pred_timestamps = [int(dt.timestamp() * 1000) for dt in pred_dt]
    pred_timestamps = np.array(pred_timestamps, dtype=int)

    # Convert back to GMT timezone
    pred_timestamps = timestamps_to_timezoned_timestamps(pred_timestamps, -GMT_TO_ASTANA_HOURS)

    return last_past_index, pred_timestamps
