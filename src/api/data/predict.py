# author: Rustam Krikbayev <rkrikbaev@gmail.com>
# date: 2024.06.12

from typing import Annotated, Any
from pydantic import (
    BaseModel,
    ConfigDict,
    Discriminator,
    Tag,
    field_validator,
    computed_field,
    model_validator,
)

from api import TAG_PREDICT_CREATE, TAG_PREDICT_UPDATE


class PredictCreateSchema(BaseModel):
    """
    Settings for prediction creation.

    Canonical public GET contract:
    - model_id (path)
    - object_ref (query, optional)
    - version_alias (query, optional, defaults to Production)

    Runtime parameters are loaded from bundle/configuration/cache_config.json.
    """

    model_config = ConfigDict(strict=True, extra="forbid")

    model_id: str
    object_ref: str | None = None
    version_alias: str = "Production"

    @computed_field
    @property
    def online(self) -> bool:
        return self.model_id == "none"

    @computed_field
    @property
    def selector(self) -> str:
        return self.version_alias or "Production"

    @field_validator("model_id")
    @classmethod
    def check_model_id(cls, v: str) -> str:
        if len(v) == 0:
            raise ValueError("'model_id' must be non-empty")
        return v

    @field_validator("object_ref")
    @classmethod
    def check_object_ref(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if len(v) == 0:
            raise ValueError("'object_ref' must be non-empty")
        if "/" not in v and "\\" not in v:
            raise ValueError("'object_ref' must contain '/' or '\\'")
        return v

    @field_validator("version_alias")
    @classmethod
    def check_version_alias(cls, v: str) -> str:
        if len(v) == 0:
            raise ValueError("'version_alias' must be non-empty")
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
