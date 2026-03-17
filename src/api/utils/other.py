# Mariya Polkovnikova
# 2026.03.17, 10:37 AM


from typing import Tuple

import numpy as np


# --- https://stackoverflow.com/a/6520696 ---

def nan_helper(y: np.array) -> Tuple:
    """
    Helper to handle indices and logical indices of NaNs.

    :param np.array y: 1d numpy array with possible NaNs

    Example:
        >>> # linear interpolation of NaNs
        >>> nans, x= nan_helper(y)
        >>> y[nans]= np.interp(x(nans), x(~nans), y[~nans])

    :return: Tuple of 2 elements: logical indices of NaNs and a function,
        with signature indices=index(logical_indices), to convert logical
        indices of NaNs to 'equivalent' indices
    :rtype: Tuple[np.ndarray, Callable]
    """

    return np.isnan(y), lambda z: z.nonzero()[0]


def interpolate_nan_1d(y: np.array) -> np.array:
    """
    Interpolate NaN values in a 1D array using linear interpolation.

    :param np.array y: 1d numpy array with possible NaNs

    :return: 1d numpy array with NaN values interpolated
    :rtype: np.array
    """

    if np.all(np.isnan(y)):
        return y

    nans, x = nan_helper(y)
    y[nans] = np.interp(x(nans), x(~nans), y[~nans])

    return y


# --- Index ---

def get_last_past_index(arr: np.ndarray) -> int:
    """
    Get the index of the last past element in the array.

    :param np.ndarray arr: Array of elements.

    :return: Index of the last past element in the array.
    :rtype: int
    """

    return len(arr) // 2
