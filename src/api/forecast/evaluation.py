# Mariya Polkovnikova
# 2026.03.13, 03:34 PM


from typing import List, Tuple, Optional

from api.utils import get_last_past_index
from .enums import QDS, Threshold

import numpy as np


def count_input_qds(
    timestamp: List[np.ndarray],
    value: List[np.ndarray],
    qds: List[np.ndarray]
) -> Tuple[float]:
    """
    Count critical and non-critical errors in input QDS.

    :param List[np.ndarray] timestamp: List of timestamps.
    :param List[np.ndarray] value: List of values.
    :param List[np.ndarray] qds: List of QDS values.

    :return: Critical frequency and non-critical frequency.
    :rtype: Tuple[float]
    """

    last_past_index = get_last_past_index(timestamp[0])

    qds = np.array(qds)[:, :last_past_index].ravel()
    value = np.array(value)[:, :last_past_index].ravel()

    total = len(qds)
    critical = 0
    non_critical_or_missing = 0

    for q, yv in zip(qds, value):
        if any((q & bit) == bit for bit in QDS.critical()):
            critical += 1
        if any((q & bit) == bit for bit in QDS.noncritical()) or np.isnan(yv):
            non_critical_or_missing += 1

    return (
        critical / total if total else 0.0,
        non_critical_or_missing / total if total else 0.0
    )


def evaluate_input_quality(
    critical_freq: float,
    non_critical_freq: float
) -> Tuple[int, Optional[str]]:
    """
    Evaluate input quality based on critical and non-critical frequencies.

    :param float critical_freq: Critical frequency.
    :param float non_critical_freq: Non-critical frequency.

    :return: Input QDS and reason.
    :rtype: Tuple[int, Optional[str]]
    """

    input_qds = QDS.BASE
    input_reason = None

    if critical_freq >= Threshold.CRITICAL_TO_SET_ERROR.value:
        input_qds = QDS.INVALID
        input_reason = f"Critical errors in {critical_freq * 100:.1f}% of input data (QDS={QDS.INVALID})"

    elif non_critical_freq >= Threshold.NON_CRITICAL_TO_SET_ERROR.value:
        input_qds = QDS.INVALID
        input_reason = f"Multiple errors or gaps in {non_critical_freq * 100:.1f}% of input data (QDS={QDS.INVALID})"

    elif non_critical_freq >= Threshold.NON_CRITICAL_TO_SET_INCORRECT.value:
        input_qds = QDS.NOT_TOPICAL
        input_reason = f"Errors or gaps in {non_critical_freq * 100:.1f}% of input data (QDS={QDS.NOT_TOPICAL})"

    return input_qds, input_reason
