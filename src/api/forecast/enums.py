# 20??.??.??, ??, ?? ?M


from typing import List
from enum import IntEnum, Enum


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
    def noncritical(cls) -> List[int]:
        return [1, 2, 4, 8, 16, 32, 64]

    @classmethod
    def critical(cls) -> List[int]:
        return [128, 256]


class Threshold(Enum):
    CRITICAL_TO_SET_ERROR = 0.1
    NON_CRITICAL_TO_SET_ERROR = 0.7
    NON_CRITICAL_TO_SET_INCORRECT = 0.5
