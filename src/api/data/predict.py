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
    model_validator,
)

from api import TAG_PREDICT_CREATE, TAG_PREDICT_UPDATE


class ModelSelectionSchema(BaseModel):
    """Optional selector for resolving a model in MLflow Registry."""

    model_config = ConfigDict(strict=True, extra="forbid")

    version_alias: str | None = None
    version: str | None = None

    @model_validator(mode="after")
    def validate_selection(self) -> "ModelSelectionSchema":
        if self.version_alias and self.version:
            raise ValueError("'version_alias' and 'version' are mutually exclusive")
        if self.version is not None and len(self.version) == 0:
            raise ValueError("'version' must be non-empty")
        if self.version_alias is not None and len(self.version_alias) == 0:
            raise ValueError("'version_alias' must be non-empty")
        return self


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
    model_selection: ModelSelectionSchema | None = None

    @computed_field
    @property
    def online(self) -> bool:
        return self.model_id == "none"

    @computed_field
    @property
    def selector(self) -> str:
        if self.model_selection is None:
            return "Production"
        if self.model_selection.version:
            return self.model_selection.version
        if self.model_selection.version_alias:
            return self.model_selection.version_alias
        return "Production"

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
