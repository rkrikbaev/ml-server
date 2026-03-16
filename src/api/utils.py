# ????.??.??, ??, ?? ?M


from typing import Tuple
from enum import IntEnum, Enum
from datetime import datetime, timezone

from logging import getLogger

import numpy as np

logger = getLogger(__file__)


class QDS(IntEnum):
    """
    **MV — Missing value (256)**\\
    Пропущен QDS, то есть, отсутствует.

    **IV — Invalid (128)**\\
    Самый высокий приоритет. Если установлен — значение недостоверно и не
        используется в расчетах.
        → всегда перекрывает все остальные.

    **NT — Not topical / Timeout (64)**\\
    Данные устарели. Обычно трактуются как недостоверные, но ниже по
        приоритету, чем invalid.

    **BL — Blocked (16)**\\
    Значение не поступает из-за блокировки источника. Отображается как
        недоступное, но не всегда снимается из расчетов (зависит от
        конфигурации).

    **SB — Substituted (32)**\\
    Значение заменено оператором или системой. Достоверность условная, ниже
        по приоритету, чем ошибки IV/NT/BL.

    **OV — Overflow (1)**\\
    Признак переполнения/некорректного диапазона. Используется в основном
        для аналогов. Обычно отображается как предупреждение, но данные могут
        учитываться.

    **RES — Резервные биты (2–4)**\\
    Используются по назначению (например, специфично для типа ТИ/ТС). По
        приоритету — ниже IV/NT, но выше OV.

    **QDS = 0**\\
    Сигнал в норме.
    """

    BASE = 0
    # OVERFLOW = 1
    # RES_2 = 2
    # RES_3 = 3
    # RES_4 = 4
    # BLOCKED = 16
    # SUBSTITUTED = 32
    NOT_TOPICAL = 64
    INVALID = 128
    MISSING_VALUE = 256

    @classmethod
    def noncritical(cls):
        return [1, 2, 4, 8, 16, 32, 64]

    @classmethod
    def critical(cls):
        return [128, 256]


class Threshold(Enum):
    CRITICAL_TO_SET_ERROR = 0.1
    NON_CRITICAL_TO_SET_ERROR = 0.7
    NON_CRITICAL_TO_SET_INCORRECT = 0.5


class SbreModel:
    pass


def generate_timestamp(mode: str) -> Tuple[int, int]:
    """
    Generate timestamp for the given mode.

    :param str mode: The mode for which to generate the timestamp. Supported
        modes are "day" and "month".

    :return: A tuple containing the start timestamp (from_tp) and end
        timestamp (to_tp) in seconds since the epoch.
    :rtype: Tuple[int, int]
    """

    d = datetime.now(tz=timezone.utc)

    match mode:
        case "day":
            from_tp = datetime(d.year, d.month, d.day, 0, 0, 0, 0, timezone.utc)
            to_tp = datetime(d.year, d.month, d.day + 3, 0, 0, 0, 0, timezone.utc)
        case "month":
            from_tp = datetime(d.year, d.month, 1, 0, 0, 0, 0, timezone.utc)
            to_tp = datetime(d.year, d.month + 1, 1, 0, 0, 0, 0, timezone.utc)
        case _:
            from_tp = datetime(d.year, 1, 1, 0, 0, 0, 0, timezone.utc)
            to_tp = datetime(d.year + 1, 1, 1, 0, 0, 0, 0, timezone.utc)

    from_tp = int(datetime.timestamp(from_tp)) * 1000
    to_tp = int(datetime.timestamp(to_tp)) * 1000
    return from_tp, to_tp


# https://stackoverflow.com/a/6520696
def nan_helper(y: np.array) -> Tuple:
    """
    Helper to handle indices and logical indices of NaNs.

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


def interpolate_nan_1d(y: np.array) -> np.array:
    if np.all(np.isnan(y)):
        return y
    nans, x = nan_helper(y)
    y[nans] = np.interp(x(nans), x(~nans), y[~nans])
    return y
