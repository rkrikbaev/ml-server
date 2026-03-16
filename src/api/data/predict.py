# Mariya Polkovnikova
# 2026.03.12, 02:54 PM


from typing import Literal, List
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
    computed_field
)


class PredictBaseSettings(BaseModel):
    """
    Base settings for prediction.
    """

    model_config = ConfigDict(strict=True)

    model_path: str = "none"
    step: int = 3_600
    output_range: int = 1
    clip_negatives_to_0: bool = True
    use_dynamic_normalization: bool = Field(default=False, alias="use_dynamic_normalization")

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

    @model_validator(mode="after")
    def process_calculated_fields(self) -> "PredictBaseSettings":
        self.step *= 1000  # ms
        self.output_range = self.output_range * 3_600_000 // self.step
        return self

    @computed_field
    @property
    def online(self) -> bool:
        return self.model_path == "none"


class PredictCreateSchema(PredictBaseSettings):
    """
    Settings for prediction creation.
    """

    model_config = ConfigDict(strict=True, extra="forbid")

    mode: Literal["day", "month", "year"] = Field(alias="name")
    archives: List[str]

    @field_validator("archives")
    @classmethod
    def check_archives(cls, v: List[str]) -> List[str]:
        if len(v) == 0: raise ValueError("'archives' must be non-empty")
        return v


class PredictUpdateSchema(PredictBaseSettings):
    """
    Settings for prediction update.
    """

    model_config = ConfigDict(strict=True, extra="forbid")

    task_id: str
