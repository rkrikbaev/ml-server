# Mariya Polkovnikova
# 2026.03.12, 05:37 PM


from typing import List

from api import TAG_PREDICT_CREATE, TAG_PREDICT_UPDATE
from api.data import PredictCreateSchema, PredictUpdateSchema


def get_fields() -> List:
    """
    Get a list of field names from 'PredictCreateSchema' and
    'PredictUpdateSchema'.

    :return: List of field names.
    :rtype: List[str]
    """

    predict_create = list(PredictCreateSchema.model_fields.keys()) + list(PredictCreateSchema.model_computed_fields.keys())
    predict_update = list(PredictUpdateSchema.model_fields.keys()) + list(PredictUpdateSchema.model_computed_fields.keys())
    return {TAG_PREDICT_CREATE: predict_create, TAG_PREDICT_UPDATE: predict_update}
