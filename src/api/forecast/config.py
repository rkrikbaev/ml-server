# Mariya Polkovnikova


from typing import Any, Dict, List, Optional
from pathlib import Path
import json

from pydantic import BaseModel, field_validator, model_validator


class ModelConfig(BaseModel):
    """
    Configuration loaded from config.json in the model directory.

    All parameters that were previously sent by the client are now
    stored alongside the model and loaded from this file.
    """

    step: int = 3600              # seconds; internally converted to ms
    input_range: Optional[int] = None
    output_range: int = 48        # short: hours, medium: months, long: years
    clip_negatives_to_0: bool = True
    use_dynamic_normalization: bool = False
    archives: List[str]
    historical_data_url: Optional[str] = None
    historical_data_request_overrides: Dict[str, Any] = {}
    weather_lat: Optional[float] = None
    weather_lon: Optional[float] = None
    weather_url: Optional[str] = None
    weather_units: str = "metric"
    weather_hours: Optional[int] = None
    cmms_url: Optional[str] = None
    cmms_request_overrides: Dict[str, Any] = {}

    @field_validator("step")
    @classmethod
    def check_step(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("'step' must be greater than 0")
        return v

    @field_validator("output_range")
    @classmethod
    def check_output_range(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("'output_range' must be greater than 0")
        return v

    @field_validator("input_range")
    @classmethod
    def check_input_range(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v <= 0:
            raise ValueError("'input_range' must be greater than 0")
        return v

    @field_validator("archives")
    @classmethod
    def check_archives(cls, v: List[str]) -> List[str]:
        if len(v) == 0:
            raise ValueError("'archives' must be non-empty")
        return v

    @field_validator("weather_units")
    @classmethod
    def check_weather_units(cls, v: str) -> str:
        if v not in {"metric", "imperial"}:
            raise ValueError("'weather_units' must be either 'metric' or 'imperial'")
        return v

    @field_validator("weather_hours")
    @classmethod
    def check_weather_hours(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v <= 0:
            raise ValueError("'weather_hours' must be greater than 0")
        return v

    @model_validator(mode="after")
    def check_weather_coordinates(self) -> "ModelConfig":
        if (self.weather_lat is None) != (self.weather_lon is None):
            raise ValueError("'weather_lat' and 'weather_lon' must be provided together")
        return self


def _normalize_sources_config(raw_config: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize a model config with short/medium/long source sections."""
    selected_mode = None
    for mode_name in ("short", "medium", "long"):
        if isinstance(raw_config.get(mode_name), dict):
            selected_mode = raw_config[mode_name]
            break

    if selected_mode is None:
        return raw_config

    output_range = raw_config.get("output_range", selected_mode.get("output_range", 48))

    normalized: Dict[str, Any] = {
        "step": selected_mode.get("step", 3600),
        "input_range": selected_mode.get("input_range"),
        "output_range": output_range,
        "clip_negatives_to_0": raw_config.get("clip_negatives_to_0", True),
        "use_dynamic_normalization": raw_config.get("use_dynamic_normalization", False),
        "archives": [],
        "historical_data_url": None,
        "historical_data_request_overrides": {},
        "weather_lat": None,
        "weather_lon": None,
        "weather_url": None,
        "weather_units": raw_config.get("weather_units", "metric"),
        "weather_hours": raw_config.get("weather_hours"),
        "cmms_url": None,
        "cmms_request_overrides": {},
    }

    def resolve_window_size(source_type: str, source_pattern: Optional[str]) -> Optional[int]:
        default_pattern_by_type = {
            "historical_data": "historic",
            "scada": "historic",
            "weather": "future",
            "cmms": "planned",
        }
        pattern = (source_pattern or default_pattern_by_type.get(source_type, "historic")).lower()

        if pattern == "historic":
            return selected_mode.get("input_range")
        if pattern in {"future", "planned"}:
            return output_range
        return None

    for source in selected_mode.get("sources", []):
        source_type = source.get("type")
        source_pattern = source.get("pattern")
        window_size = resolve_window_size(source_type, source_pattern)

        if source_type in {"scada", "historical_data"}:
            request_body = dict(source.get("request_body", {}))
            normalized["historical_data_url"] = source.get("url")
            normalized["archives"] = list(request_body.get("archive", []))
            normalized["step"] = request_body.get("step", normalized["step"])

            overrides = dict(request_body)
            if window_size is not None:
                overrides["range_size"] = window_size
            if source_pattern is not None:
                overrides["pattern"] = source_pattern
            if selected_mode.get("from") is not None:
                overrides["from"] = selected_mode["from"]
            if selected_mode.get("to") is not None:
                overrides["to"] = selected_mode["to"]
            normalized["historical_data_request_overrides"] = overrides

        elif source_type == "weather":
            normalized["weather_url"] = source.get("url")
            location = source.get("location", {})
            normalized["weather_lat"] = location.get("latitude")
            normalized["weather_lon"] = location.get("longitude")
            if window_size is not None:
                normalized["weather_hours"] = window_size

        elif source_type == "cmms":
            normalized["cmms_url"] = source.get("url")
            overrides = dict(source.get("request_body", {}))
            if window_size is not None:
                overrides["range_size"] = window_size
            if source_pattern is not None:
                overrides["pattern"] = source_pattern
            normalized["cmms_request_overrides"] = overrides

    return normalized


def load_model_config(model_id: str) -> ModelConfig:
    """
    Load model configuration from config.json in the model directory.

    :param str model_id: Model identifier — relative path under /workspace/models
        (e.g. "prophet/watt/h/AKMOLA/@regions/Akmola/load").

    :return: Validated model configuration.
    :rtype: ModelConfig

    :raises FileNotFoundError: If config.json is not found in the model directory.
    :raises ValueError: If config.json contains invalid values.
    """

    # Support environment variable for models directory (for testing)
    from os import getenv
    models_base_path = Path(getenv("MODELS_PATH", "/workspace/models"))
    
    config_path = models_base_path / model_id / "config.json"

    if not config_path.is_file():
        raise FileNotFoundError(f"Model config not found: {config_path}")

    with open(config_path) as f:
        raw_config = json.load(f)
        if isinstance(raw_config, dict):
            if raw_config.get("historical_data_url") is None and raw_config.get("scada_url") is not None:
                raw_config["historical_data_url"] = raw_config["scada_url"]
            if not raw_config.get("historical_data_request_overrides") and raw_config.get("scada_request_overrides"):
                raw_config["historical_data_request_overrides"] = raw_config["scada_request_overrides"]
            raw_config.pop("scada_url", None)
            raw_config.pop("scada_request_overrides", None)
            raw_config = _normalize_sources_config(raw_config)
        return ModelConfig(**raw_config)
