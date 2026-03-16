# Mariya Polkovnikova
# 2026.03.12, 05:37 PM


from typing import List

from .predict import PredictCreateSchema, PredictUpdateSchema


def get_fields() -> List:
    """
    Get a list of field names from 'PredictCreateSchema' and
    'PredictUpdateSchema'.

    :return: List of field names.
    :rtype: List[str]
    """

    predict_create = list(PredictCreateSchema.model_fields.keys())
    predict_update = list(PredictUpdateSchema.model_fields.keys())
    return predict_create + predict_update
