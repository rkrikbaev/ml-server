# Mariya Polkovnikova


from typing import Any, Dict, List, Optional
from pathlib import Path
import json
import yaml
import logging
import tempfile

from mlflow.tracking import MlflowClient

from pydantic import BaseModel, field_validator, model_validator


logger = logging.getLogger(__name__)


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
    model_type: str = "prophet"
    fallback: str = "none"
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

    @field_validator("fallback")
    @classmethod
    def check_fallback(cls, v: str) -> str:
        allowed = {"none", "naive", "ar", "prophet", "xgb"}
        normalized = str(v).strip().lower()
        if normalized in {"", "false", "null"}:
            normalized = "none"
        if normalized not in allowed:
            raise ValueError(f"'fallback' must be one of: {', '.join(sorted(allowed))}")
        return normalized

    @field_validator("model_type")
    @classmethod
    def check_model_type(cls, v: str) -> str:
        allowed = {"xgb", "prophet", "naive", "ar"}
        normalized = str(v).strip().lower()
        if normalized not in allowed:
            raise ValueError(f"'model_type' must be one of: {', '.join(sorted(allowed))}")
        return normalized

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
        "model_type": raw_config.get("model_type", raw_config.get("type", "prophet")),
        "fallback": raw_config.get("fallback", "none"),
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


def _normalize_unified_yaml_config(raw_config: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize unified YAML model config into ModelConfig-compatible schema."""
    model = raw_config.get("model", {}) if isinstance(raw_config.get("model"), dict) else {}
    time_series = raw_config.get("time_series", {}) if isinstance(raw_config.get("time_series"), dict) else {}
    data_source = raw_config.get("data_source", {}) if isinstance(raw_config.get("data_source"), dict) else {}

    input_range = time_series.get("input_range_hours")
    if input_range is None:
        input_range = data_source.get("lookback_period")

    output_range = time_series.get("output_range_hours")
    if output_range is None:
        output_range = model.get("horizon", 48)

    normalized: Dict[str, Any] = {
        "step": time_series.get("step_seconds", 3600),
        "input_range": input_range,
        "output_range": output_range,
        "clip_negatives_to_0": raw_config.get("clip_negatives_to_0", True),
        "use_dynamic_normalization": raw_config.get("use_dynamic_normalization", False),
        "model_type": model.get("type", raw_config.get("type", "prophet")),
        "fallback": model.get("fallback", raw_config.get("fallback", "none")),
        "archives": [],
        "historical_data_url": None,
        "historical_data_request_overrides": {},
        "weather_lat": None,
        "weather_lon": None,
        "weather_url": None,
        "weather_units": raw_config.get("weather_units", "metric"),
        "weather_hours": None,
        "cmms_url": None,
        "cmms_request_overrides": {},
    }

    apis = data_source.get("apis", [])
    if not isinstance(apis, list):
        return normalized

    source_location = data_source.get("location", {}) if isinstance(data_source.get("location"), dict) else {}

    for source in apis:
        if not isinstance(source, dict):
            continue

        source_type = source.get("type")
        source_pattern = str(source.get("pattern", "")).lower()
        request_body = dict(source.get("request_body", {})) if isinstance(source.get("request_body"), dict) else {}

        if source_type in {"scada", "historical_data"}:
            normalized["historical_data_url"] = source.get("url")
            normalized["archives"] = list(request_body.get("archive", []))
            normalized["step"] = request_body.get("step", normalized["step"])

            overrides = dict(request_body)
            if source_pattern == "historic" and normalized.get("input_range") is not None:
                overrides["range_size"] = normalized["input_range"]
            if source_pattern in {"future", "planned"} and normalized.get("output_range") is not None:
                overrides["range_size"] = normalized["output_range"]
            if source_pattern:
                overrides["pattern"] = source_pattern
            normalized["historical_data_request_overrides"] = overrides

        elif source_type == "weather":
            normalized["weather_url"] = source.get("url")
            location = source.get("location", {}) if isinstance(source.get("location"), dict) else {}
            request_location = request_body.get("location", {}) if isinstance(request_body.get("location"), dict) else {}
            normalized["weather_lat"] = location.get("latitude", request_location.get("latitude", source_location.get("latitude")))
            normalized["weather_lon"] = location.get("longitude", request_location.get("longitude", source_location.get("longitude")))
            if normalized.get("output_range") is not None:
                normalized["weather_hours"] = normalized["output_range"]

        elif source_type == "cmms":
            normalized["cmms_url"] = source.get("url")
            overrides = dict(request_body)
            if source_pattern == "planned" and normalized.get("output_range") is not None:
                overrides["range_size"] = normalized["output_range"]
            if source_pattern:
                overrides["pattern"] = source_pattern
            normalized["cmms_request_overrides"] = overrides

    return normalized


def _parse_model_config_payload(payload: Dict[str, Any], source_name: str) -> ModelConfig:
    if not isinstance(payload, dict):
        raise ValueError(f"Invalid model config format from {source_name}: expected object")

    if any(isinstance(payload.get(k), dict) for k in ("model", "time_series", "data_source")):
        normalized = _normalize_unified_yaml_config(payload)
        return ModelConfig(**normalized)

    if payload.get("historical_data_url") is None and payload.get("scada_url") is not None:
        payload["historical_data_url"] = payload["scada_url"]
    if not payload.get("historical_data_request_overrides") and payload.get("scada_request_overrides"):
        payload["historical_data_request_overrides"] = payload["scada_request_overrides"]
    payload.pop("scada_url", None)
    payload.pop("scada_request_overrides", None)
    normalized = _normalize_sources_config(payload)
    return ModelConfig(**normalized)


def _load_model_config_from_mlflow(model_id: str) -> Optional[ModelConfig]:
    """Load model config from MLflow artifacts by model_id.

    Strategy:
    1) try latest run by tag/param model_id
    2) try registered-model latest version by name=model_id
    3) search common artifact paths for unified/yaml/json config
    """
    client = MlflowClient()

    candidate_run_ids: list[str] = []

    # 1) Find recent runs by model_id tag/param across all experiments.
    try:
        experiments = client.search_experiments()
        experiment_ids = [exp.experiment_id for exp in experiments]
        for filter_string in (
            f"tags.model_id = '{model_id}'",
            f"params.model_id = '{model_id}'",
        ):
            runs = client.search_runs(
                experiment_ids=experiment_ids,
                filter_string=filter_string,
                max_results=20,
                order_by=["attributes.start_time DESC"],
            )
            for run in runs:
                run_id = run.info.run_id
                if run_id not in candidate_run_ids:
                    candidate_run_ids.append(run_id)
    except Exception as error:
        logger.warning("MLflow run search failed for model_id=%s: %s", model_id, error)

    # 2) If registered model exists, prefer its latest versions.
    try:
        latest_versions = client.get_latest_versions(model_id)
        for version in latest_versions:
            run_id = getattr(version, "run_id", None)
            if run_id and run_id not in candidate_run_ids:
                candidate_run_ids.insert(0, run_id)
    except Exception:
        # Not every model_id is a registered model name.
        pass

    if not candidate_run_ids:
        return None

    artifact_candidates = (
        "config_unified.yaml",
        "config.yaml",
        "config.json",
        "artifacts/config_unified.yaml",
        "artifacts/config.yaml",
        "artifacts/config.json",
        "model/config_unified.yaml",
        "model/config.yaml",
        "model/config.json",
    )

    for run_id in candidate_run_ids:
        for artifact_path in artifact_candidates:
            try:
                with tempfile.TemporaryDirectory() as tmp_dir:
                    local_path = client.download_artifacts(run_id, artifact_path, tmp_dir)
                    path = Path(local_path)
                    if not path.is_file():
                        continue

                    if path.suffix.lower() in {".yaml", ".yml"}:
                        with open(path) as f:
                            payload = yaml.safe_load(f) or {}
                    elif path.suffix.lower() == ".json":
                        with open(path) as f:
                            payload = json.load(f)
                    else:
                        continue

                    config = _parse_model_config_payload(payload, f"MLflow run={run_id} artifact={artifact_path}")
                    logger.info(
                        "Loaded model config from MLflow for model_id=%s run_id=%s artifact=%s",
                        model_id,
                        run_id,
                        artifact_path,
                    )
                    return config
            except Exception:
                continue

    return None


def load_model_config(model_id: str) -> ModelConfig:
    """
    Load model configuration from config_unified.yaml in model directory,
    with fallback to MLflow artifacts.

    :param str model_id: Model identifier — relative path under /workspace/models
        (e.g. "prophet/watt/h/AKMOLA/@regions/Akmola/load").

    :return: Validated model configuration.
    :rtype: ModelConfig

    :raises FileNotFoundError: If local config_unified.yaml is missing and no MLflow config is found.
    :raises ValueError: If configuration contains invalid values.
    """

    # Support environment variable for models directory (for testing)
    from os import getenv
    models_base_path = Path(getenv("MODELS_PATH", "/workspace/models"))
    
    model_dir = models_base_path / model_id
    unified_yaml_path = model_dir / "config_unified.yaml"

    if unified_yaml_path.is_file():
        with open(unified_yaml_path) as f:
            raw_config = yaml.safe_load(f) or {}
            return _parse_model_config_payload(raw_config, str(unified_yaml_path))

    mlflow_config = _load_model_config_from_mlflow(model_id)
    if mlflow_config is not None:
        return mlflow_config

    raise FileNotFoundError(
        f"Model config not found in local file {unified_yaml_path} and no MLflow config found for model_id={model_id}"
    )
