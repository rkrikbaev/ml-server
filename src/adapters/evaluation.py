# Mariya Polkovnikova
# 2026.03.13, 03:34 PM


from typing import List, Tuple, Optional

from api.utils import get_last_past_index
from .enums import Threshold

import numpy as np


def count_input_health(
    timestamp: List[np.ndarray],
    value: List[np.ndarray],
) -> Tuple[float]:
    """
    Count critical and warning frequencies in input values.

    :param List[np.ndarray] timestamp: List of timestamps.
    :param List[np.ndarray] value: List of values.

    :return: Critical frequency and warning frequency.
    :rtype: Tuple[float]
    """

    last_past_index = get_last_past_index(timestamp[0])

    value = np.array(value)[:, :last_past_index].ravel()

    total = len(value)
    critical = 0
    warning_or_missing = 0

    for yv in value:
        if np.isnan(yv):
            critical += 1
            warning_or_missing += 1

    return (
        critical / total if total else 0.0,
        warning_or_missing / total if total else 0.0
    )


def evaluate_input_health(
    critical_freq: float,
    warning_freq: float
) -> Tuple[bool, Optional[str]]:
    """
    Evaluate input health based on critical and warning frequencies.

    :param float critical_freq: Critical frequency.
    :param float warning_freq: Warning frequency.

    :return: Health issue flag and reason.
    :rtype: Tuple[bool, Optional[str]]
    """

    has_issue = False
    input_reason: Optional[str] = None

    if critical_freq >= Threshold.CRITICAL_TO_SET_ERROR.value:
        has_issue = True
        input_reason = f"Critical gaps in {critical_freq * 100:.1f}% of input data"

    elif warning_freq >= Threshold.NON_CRITICAL_TO_SET_ERROR.value:
        has_issue = True
        input_reason = f"Multiple gaps in {warning_freq * 100:.1f}% of input data"

    elif warning_freq >= Threshold.NON_CRITICAL_TO_SET_INCORRECT.value:
        has_issue = True
        input_reason = f"Gaps in {warning_freq * 100:.1f}% of input data"

    return has_issue, input_reason
