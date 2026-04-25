# Mariya Polkovnikova
# 2026.03.12, 02:54 PM


from typing import Annotated, Any
from pydantic import (
    BaseModel,
    ConfigDict,
    Discriminator,
    Tag,
    field_validator,
    computed_field,
)

from api import TAG_PREDICT_CREATE, TAG_PREDICT_UPDATE


class PredictCreateSchema(BaseModel):
    """
    Settings for prediction creation.

    The client supplies only the object reference and the model identifier.
    All other parameters (archives, step, output_range, …) are read from
    the model's config.json on the server side.
    """

    model_config = ConfigDict(strict=True, extra="forbid")

    model_id: str = "none"
    object_reference: str

    @computed_field
    @property
    def online(self) -> bool:
        return self.model_id == "none"

    @field_validator("model_id")
    @classmethod
    def check_model_id(cls, v: str) -> str:
        if len(v) == 0:
            raise ValueError("'model_id' must be non-empty")
        return v

    @field_validator("object_reference")
    @classmethod
    def check_object_reference(cls, v: str) -> str:
        if len(v) == 0:
            raise ValueError("'object_reference' must be non-empty")
        if "/" not in v and "\\" not in v:
            raise ValueError("'object_reference' must contain '/' or '\\'")
        return v


class PredictUpdateSchema(BaseModel):
    """
    Settings for prediction update (polling).
    """

    model_config = ConfigDict(strict=True, extra="forbid")

    task_id: str


def predict_discriminator(v: Any) -> str:
    """
    Discriminator for prediction creation and update.

    :param Any v: Value to discriminate.

    :return: TAG_PREDICT_CREATE or TAG_PREDICT_UPDATE.
    :rtype: str
    """

    if isinstance(v, dict) and "task_id" in v:
        return TAG_PREDICT_UPDATE
    return TAG_PREDICT_CREATE


PredictSchema = Annotated[
    Annotated[PredictCreateSchema, Tag(TAG_PREDICT_CREATE)] | Annotated[PredictUpdateSchema, Tag(TAG_PREDICT_UPDATE)],
    Discriminator(predict_discriminator)
]
