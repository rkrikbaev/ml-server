# 20??.??.??, ??, ?? ?M


from enum import Enum


class Threshold(Enum):
    CRITICAL_TO_SET_ERROR = 0.1
    NON_CRITICAL_TO_SET_ERROR = 0.7
    NON_CRITICAL_TO_SET_INCORRECT = 0.5
