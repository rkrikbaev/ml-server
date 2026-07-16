# Mariya Polkovnikova


from typing import Any, Dict, List, Optional
from pathlib import Path
import json
import logging
import tempfile

from mlflow.tracking import MlflowClient

from pydantic import BaseModel, field_validator, model_validator


logger = logging.getLogger(__name__)


class ModelConfig(BaseModel):
    """
    Configuration loaded from cache_config.json in the model directory.

    All parameters that were previously sent by the client are now
    stored alongside the model and loaded from this file.
    """

    step: int = 3600              # seconds; internally converted to ms
    input_range: Optional[int] = None
    output_range: int = 24
    model_type: str = "prophet"
    fallback: str = "none"
    sources: Dict[str, Any] = {}

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

    @field_validator("sources")
    @classmethod
    def check_sources(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        if len(v) == 0:
            raise ValueError("'sources' must be non-empty")
        return v

    @field_validator("fallback")
    @classmethod
    def check_fallback(cls, v: str) -> str:
        allowed = {"none", "naive", "ar", "prophet", "xgb", "solar", "wind"}
        normalized = str(v).strip().lower()
        if normalized in {"", "false", "null"}:
            normalized = "none"
        if normalized not in allowed:
            raise ValueError(f"'fallback' must be one of: {', '.join(sorted(allowed))}")
        return normalized

    @field_validator("model_type")
    @classmethod
    def check_model_type(cls, v: str) -> str:
        allowed = {"xgb", "prophet", "naive", "ar", "solar", "wind"}
        normalized = str(v).strip().lower()
        if normalized not in allowed:
            raise ValueError(f"'model_type' must be one of: {', '.join(sorted(allowed))}")
        return normalized

    def _get_source(self, *names: str) -> Dict[str, Any]:
        requested = {name.lower() for name in names}

        for source_name, source_payload in self.sources.items():
            if not isinstance(source_payload, dict):
                continue

            candidate_names = {
                str(source_name).lower(),
                str(source_payload.get("type") or "").lower(),
            }
            if candidate_names & requested:
                return source_payload

        return {}

    @property
    def use_dynamic_normalization(self) -> bool:
        return False

    @property
    def clip_negatives_to_0(self) -> bool:
        return False

    @property
    def historical_data_url(self) -> Optional[str]:
        source = self._get_source("historical_data", "historical", "scada")
        value = source.get("url")
        return str(value) if value not in (None, "") else None

    @property
    def archives(self) -> List[str]:
        source = self._get_source("historical_data", "historical", "scada")
        request = source.get("request") if isinstance(source.get("request"), dict) else {}
        archives = request.get("archive")
        if archives is None:
            archives = request.get("archives")
        if archives is None:
            return []
        if isinstance(archives, list):
            return [str(item) for item in archives if item not in (None, "")]
        return [str(archives)]

    @property
    def historical_data_request_overrides(self) -> Optional[Dict[str, Any]]:
        source = self._get_source("historical_data", "historical", "scada")
        request = source.get("request") if isinstance(source.get("request"), dict) else {}
        overrides = {key: value for key, value in request.items() if key not in {"archive", "archives"}}
        return overrides or None

    @property
    def weather_url(self) -> Optional[str]:
        source = self._get_source("weather")
        value = source.get("url")
        return str(value) if value not in (None, "") else None

    @property
    def weather_lat(self) -> Optional[float]:
        source = self._get_source("weather")
        location = source.get("location") if isinstance(source.get("location"), dict) else {}
        value = location.get("latitude")
        return float(value) if value is not None else None

    @property
    def weather_lon(self) -> Optional[float]:
        source = self._get_source("weather")
        location = source.get("location") if isinstance(source.get("location"), dict) else {}
        value = location.get("longitude")
        return float(value) if value is not None else None

    @property
    def weather_hours(self) -> Optional[int]:
        source = self._get_source("weather")
        value = source.get("hours")
        return int(value) if value is not None else None

    @property
    def weather_units(self) -> Optional[str]:
        source = self._get_source("weather")
        request = source.get("request") if isinstance(source.get("request"), dict) else {}
        value = request.get("units")
        return str(value) if value not in (None, "") else None

    @property
    def cmms_url(self) -> Optional[str]:
        source = self._get_source("cmms")
        value = source.get("url")
        return str(value) if value not in (None, "") else None

    @property
    def cmms_request_overrides(self) -> Optional[Dict[str, Any]]:
        source = self._get_source("cmms")
        request = source.get("request") if isinstance(source.get("request"), dict) else {}
        return dict(request) if request else None



def _normalize_sources_config(raw_config: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize config using hierarchical global + sources schema."""

    def normalize_source_entry(source_name: str, source_payload: Dict[str, Any]) -> Dict[str, Any]:
        normalized_source: Dict[str, Any] = {}

        # Infer type from pattern when not explicit
        # e.g. {"url": "...", "parameters": [...], "pattern": "historical"}
        _pattern = str(source_payload.get("pattern") or "").lower()
        _HISTORICAL_PATTERNS = {"historical", "historic"}
        source_type = source_payload.get("type") or (
            "historical" if _pattern in _HISTORICAL_PATTERNS else source_name
        )
        if source_type is not None:
            normalized_source["type"] = source_type

        if source_payload.get("url") is not None:
            normalized_source["url"] = source_payload.get("url")

        if source_payload.get("pattern") is not None:
            normalized_source["pattern"] = source_payload.get("pattern")

        request_payload = source_payload.get("request")
        if request_payload is None:
            request_payload = source_payload.get("request_body")
        if isinstance(request_payload, dict):
            normalized_source["request"] = dict(request_payload)

        # Map top-level "parameters" list → request.archive
        # Format: {"url": "...", "parameters": ["/path/to/archive"], "pattern": "historical"}
        parameters = source_payload.get("parameters")
        if isinstance(parameters, list) and parameters:
            if "request" not in normalized_source:
                normalized_source["request"] = {}
            normalized_source["request"].setdefault("archive", parameters)

        location_payload = source_payload.get("location")
        if isinstance(location_payload, dict):
            normalized_source["location"] = dict(location_payload)

        if source_payload.get("hours") is not None:
            normalized_source["hours"] = source_payload.get("hours")

        return normalized_source

    normalized: Dict[str, Any] = {
        "step": raw_config.get("step", 3600),
        "input_range": raw_config.get("input_range", 72),
        "output_range": raw_config.get("output_range", 24),
        "model_type": raw_config.get("model_type", raw_config.get("type", "prophet")),
        "fallback": raw_config.get("fallback", "none"),
        "sources": {},
    }

    environment_cfg = raw_config.get("environment") if isinstance(raw_config.get("environment"), dict) else {}
    window_cfg = environment_cfg.get("window") if isinstance(environment_cfg.get("window"), dict) else {}
    if raw_config.get("step") is None and window_cfg.get("step") is not None:
        normalized["step"] = window_cfg.get("step")
    if raw_config.get("input_range") is None and window_cfg.get("input_range") is not None:
        normalized["input_range"] = window_cfg.get("input_range")
    if raw_config.get("output_range") is None and window_cfg.get("output_range") is not None:
        normalized["output_range"] = window_cfg.get("output_range")

    sources_cfg = raw_config.get("sources")
    if isinstance(sources_cfg, dict):
        for source_name, source_payload in sources_cfg.items():
            if isinstance(source_payload, dict):
                key = str(source_name)
                normalized["sources"][key] = normalize_source_entry(key, source_payload)
    elif isinstance(sources_cfg, list):
        for idx, source_payload in enumerate(sources_cfg):
            if not isinstance(source_payload, dict):
                continue
            source_name = (
                str(source_payload.get("name"))
                if source_payload.get("name")
                else str(source_payload.get("type") or f"source_{idx}")
            )
            normalized["sources"][source_name] = normalize_source_entry(source_name, source_payload)

    existing_types = {
        str(source.get("type")).lower()
        for source in normalized["sources"].values()
        if isinstance(source, dict) and source.get("type") is not None
    }

    if "historical_data" not in existing_types and "scada" not in existing_types:
        has_historical = (
            raw_config.get("historical_data_url") is not None
            or raw_config.get("historical_data_request_overrides") is not None
            or raw_config.get("archives") is not None
        )
        if has_historical:
            request: Dict[str, Any] = {}
            historical_overrides = raw_config.get("historical_data_request_overrides")
            if isinstance(historical_overrides, dict):
                request.update(historical_overrides)
            if raw_config.get("archives") is not None and "archive" not in request:
                request["archive"] = list(raw_config.get("archives", []))

            historical_source: Dict[str, Any] = {
                "type": "historical_data",
                "url": raw_config.get("historical_data_url"),
            }
            if request:
                historical_source["request"] = request
            normalized["sources"]["historical_data"] = historical_source

    if "weather" not in existing_types:
        has_weather = (
            raw_config.get("weather_url") is not None
            or raw_config.get("weather_lat") is not None
            or raw_config.get("weather_lon") is not None
            or raw_config.get("weather_hours") is not None
        )
        if has_weather:
            weather_source: Dict[str, Any] = {
                "type": "weather",
                "url": raw_config.get("weather_url"),
            }
            location: Dict[str, Any] = {}
            if raw_config.get("weather_lat") is not None:
                location["latitude"] = raw_config.get("weather_lat")
            if raw_config.get("weather_lon") is not None:
                location["longitude"] = raw_config.get("weather_lon")
            if location:
                weather_source["location"] = location
            if raw_config.get("weather_hours") is not None:
                weather_source["hours"] = raw_config.get("weather_hours")
            normalized["sources"]["weather"] = weather_source

    if "cmms" not in existing_types:
        has_cmms = (
            raw_config.get("cmms_url") is not None
            or raw_config.get("cmms_request_overrides") is not None
        )
        if has_cmms:
            cmms_source: Dict[str, Any] = {
                "type": "cmms",
                "url": raw_config.get("cmms_url"),
            }
            cmms_overrides = raw_config.get("cmms_request_overrides")
            if isinstance(cmms_overrides, dict):
                cmms_source["request"] = dict(cmms_overrides)
            normalized["sources"]["cmms"] = cmms_source

    if not normalized["sources"] and isinstance(environment_cfg.get("sources"), dict):
        env_sources = environment_cfg.get("sources", {})

        historical = env_sources.get("historical") if isinstance(env_sources.get("historical"), dict) else {}
        if historical:
            historical_source: Dict[str, Any] = {
                "type": "historical_data",
                "url": historical.get("url"),
            }
            archives = historical.get("archives")
            if archives is not None:
                historical_source["request"] = {"archive": list(archives)}
            normalized["sources"]["historical_data"] = historical_source

        weather = env_sources.get("weather") if isinstance(env_sources.get("weather"), dict) else {}
        if weather:
            weather_source: Dict[str, Any] = {
                "type": "weather",
                "url": weather.get("url"),
            }
            location = {}
            if weather.get("lat") is not None:
                location["latitude"] = weather.get("lat")
            if weather.get("lon") is not None:
                location["longitude"] = weather.get("lon")
            if location:
                weather_source["location"] = location
            if weather.get("hours") is not None:
                weather_source["hours"] = weather.get("hours")
            normalized["sources"]["weather"] = weather_source

        cmms = env_sources.get("cmms") if isinstance(env_sources.get("cmms"), dict) else {}
        if cmms:
            cmms_source: Dict[str, Any] = {
                "type": "cmms",
                "url": cmms.get("url"),
            }
            if isinstance(cmms.get("request"), dict):
                cmms_source["request"] = dict(cmms.get("request"))
            normalized["sources"]["cmms"] = cmms_source

    return normalized


def _parse_model_config_payload(payload: Dict[str, Any], source_name: str) -> ModelConfig:
    if not isinstance(payload, dict):
        raise ValueError(f"Invalid model config format from {source_name}: expected object")

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
    3) search cache_config.json in standard bundle paths
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
        "bundle/configuration/cache_config.json",
        "configuration/cache_config.json",
        "config/cache_config.json",
        "cache_config.json",
    )

    for run_id in candidate_run_ids:
        for artifact_path in artifact_candidates:
            try:
                with tempfile.TemporaryDirectory() as tmp_dir:
                    local_path = client.download_artifacts(run_id, artifact_path, tmp_dir)
                    path = Path(local_path)
                    if not path.is_file():
                        continue

                    if path.suffix.lower() == ".json":
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


def load_model_config(
    model_id: str,
    bundle_path: Optional[Path] = None,
    require_bundle: bool = False,
) -> ModelConfig:
    """
    Load model configuration from synced MLflow bundle cache_config.json,
    then local cache_config.json, with fallback to MLflow artifacts.

    :param str model_id: Model identifier — relative path under /workspace/models
        (e.g. "prophet/watt/h/AKMOLA/@regions/Akmola/load").

    :param Optional[Path] bundle_path: Optional path to downloaded MLflow bundle.
    :param bool require_bundle: If true and bundle_path is provided, do not fallback
        to local/legacy sources when cache_config.json is absent in bundle.

    :return: Validated model configuration.
    :rtype: ModelConfig

    :raises FileNotFoundError: If local cache_config.json is missing and no MLflow config is found.
    :raises ValueError: If configuration contains invalid values.
    """

    if bundle_path is not None:
        for rel_path in (
            "configuration/cache_config.json",
            "config/cache_config.json",
            "cache_config.json",
        ):
            candidate = bundle_path / rel_path
            if not candidate.is_file():
                continue
            with open(candidate) as f:
                raw_config = json.load(f)
                return _parse_model_config_payload(raw_config, str(candidate))

        if require_bundle:
            raise FileNotFoundError(
                f"cache_config.json not found in MLflow bundle for model_id={model_id} at {bundle_path}"
            )

    # Support environment variable for models directory (for testing)
    from os import getenv
    models_base_path = Path(getenv("MODELS_PATH", "/workspace/models"))
    
    model_dir = models_base_path / model_id
    local_cache_config_path = model_dir / "cache_config.json"
    if local_cache_config_path.is_file():
        with open(local_cache_config_path) as f:
            raw_config = json.load(f)
            return _parse_model_config_payload(raw_config, str(local_cache_config_path))

    mlflow_config = _load_model_config_from_mlflow(model_id)
    if mlflow_config is not None:
        return mlflow_config

    raise FileNotFoundError(
        f"Model config not found in local file {local_cache_config_path} "
        f"and no MLflow cache_config found for model_id={model_id}"
    )
