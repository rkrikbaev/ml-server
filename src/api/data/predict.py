# Mariya Polkovnikova
# 2026.03.12, 02:54 PM


from typing import Annotated, List, Any
from pydantic import (
    BaseModel,
    ConfigDict,
    Discriminator,
    Field,
    Tag,
    field_validator,
    model_validator,
    computed_field,

)

from api import TAG_CREATE, TAG_UPDATE


class PredictCreateSchema(BaseModel):
    """
    Settings for prediction creation.
    """

    model_config = ConfigDict(strict=True, extra="forbid")

    model_path: str = "none"
    step: int = 3_600
    output_range: int = 1
    clip_negatives_to_0: bool = True
    use_dynamic_normalization: bool = Field(default=False, alias="use_dynamic_normalization")
    archives: List[str]
    fp_path: str

    @computed_field
    @property
    def mode(self) -> str:
        if self.step < 86400000:
            return "day"
        elif self.step >= 2419200000:
            return "year"
        else:
            return "month"

    @computed_field
    @property
    def online(self) -> bool:
        return self.model_path == "none"

    @field_validator("model_path")
    @classmethod
    def check_model_path(cls, v: str) -> str:
        if len(v) == 0: raise ValueError("'model_path' must be non-empty")
        return v

    @field_validator("step")
    @classmethod
    def check_step(cls, v: int) -> int:
        if v <= 0: raise ValueError("'step' must be greater than 0")
        return v

    @field_validator("output_range")
    @classmethod
    def check_output_range(cls, v: int) -> int:
        if v <= 0: raise ValueError("'output_range' must be greater than 0")
        return v

    @field_validator("archives")
    @classmethod
    def check_archives(cls, v: List[str]) -> List[str]:
        if len(v) == 0: raise ValueError("'archives' must be non-empty")
        return v

    @field_validator("fp_path")
    @classmethod
    def check_fp_path(cls, v: str) -> List[str]:
        if len(v) == 0: raise ValueError("'fp_path' must be non-empty")
        if "/" not in v and "\\" not in v: raise ValueError("'fp_path' must contain '/' or '\\'")
        return v

    @model_validator(mode="after")
    def process_calculated_fields(self) -> "PredictCreateSchema":
        self.step *= 1000  # ms
        self.output_range = self.output_range * 3_600_000 // self.step
        return self


class PredictUpdateSchema(BaseModel):
    """
    Settings for prediction update.
    """

    model_config = ConfigDict(strict=True, extra="forbid")

    task_id: str


def predict_discriminator(v: Any) -> str:
    """
    Discriminator for prediction creation and update.

    :param Any v: Value to discriminate.

    :return: TAG_CREATE or TAG_UPDATE.
    :rtype: str
    """

    if isinstance(v, dict) and "task_id" in v:
        return TAG_UPDATE
    return TAG_CREATE


PredictSchema = Annotated[
    Annotated[PredictCreateSchema, Tag("create")] | Annotated[PredictUpdateSchema, Tag("update")],
    Discriminator(predict_discriminator)
]
