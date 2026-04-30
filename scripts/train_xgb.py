"""
train_xgb.py
------------
Запросить данные со SCADA и обучить XGBoost (AR-XGB) модель по конфигу модели.

Использование:
    python scripts/train_xgb.py --model-dir ../local/models/xgb
    python scripts/train_xgb.py --model-dir ../local/models/xgb --lookback-days 30
    python scripts/train_xgb.py --model-dir ../local/models/xgb --dry-run
    python scripts/train_xgb.py --model-dir ../local/models/xgb --use-stub
"""

import argparse
import json
import logging
import os
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse, urlunparse
import warnings

warnings.filterwarnings("ignore")

import numpy as np
import requests
import yaml
import xgboost as xgb
from sklearn.metrics import mean_absolute_error, mean_squared_error

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("train_xgb")


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

def load_config(model_dir: Path) -> Dict[str, Any]:
    """Load first available yaml config from model directory."""
    for name in ("config_unified.yaml", "config.yaml"):
        path = model_dir / name
        if path.is_file():
            with open(path) as f:
                cfg = yaml.safe_load(f) or {}
            logger.info("Config loaded from %s", path)
            return cfg
    raise FileNotFoundError(f"No config yaml found in {model_dir}")


def _model_section(cfg: Dict[str, Any]) -> Dict[str, Any]:
    return cfg.get("model", {}) if isinstance(cfg.get("model"), dict) else {}


def _data_source(cfg: Dict[str, Any]) -> Dict[str, Any]:
    return cfg.get("data_source", {}) if isinstance(cfg.get("data_source"), dict) else {}


def _first_historical_api(cfg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    for api in _data_source(cfg).get("apis", []):
        if isinstance(api, dict) and api.get("type") == "historical_data":
            return api
    return None


def build_cache_config(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Build runtime cache_config.json compatible with serving ModelConfig."""
    model = _model_section(cfg)
    time_series = cfg.get("time_series", {}) if isinstance(cfg.get("time_series"), dict) else {}
    data_source = _data_source(cfg)

    input_range = time_series.get("input_range_hours")
    if input_range is None:
        input_range = data_source.get("lookback_period")

    output_range = time_series.get("output_range_hours")
    if output_range is None:
        output_range = model.get("horizon", 48)

    payload: Dict[str, Any] = {
        "step": int(time_series.get("step_seconds", 3600)),
        "input_range": input_range,
        "output_range": int(output_range),
        "clip_negatives_to_0": bool(cfg.get("clip_negatives_to_0", True)),
        "use_dynamic_normalization": bool(cfg.get("use_dynamic_normalization", False)),
        "model_type": str(model.get("type", cfg.get("type", "xgb"))).lower(),
        "fallback": str(model.get("fallback", cfg.get("fallback", "none"))).lower(),
        "archives": [],
        "historical_data_url": None,
        "historical_data_request_overrides": {},
        "weather_lat": None,
        "weather_lon": None,
        "weather_url": None,
        "weather_units": str(cfg.get("weather_units", "metric")),
        "weather_hours": None,
        "cmms_url": None,
        "cmms_request_overrides": {},
    }

    apis = data_source.get("apis", [])
    if not isinstance(apis, list):
        return payload

    for source in apis:
        if not isinstance(source, dict):
            continue

        source_type = source.get("type")
        source_pattern = str(source.get("pattern", "")).lower()
        request_body = dict(source.get("request_body", {})) if isinstance(source.get("request_body"), dict) else {}

        if source_type in {"historical_data", "scada"}:
            payload["historical_data_url"] = source.get("url")
            payload["archives"] = list(request_body.get("archive", []))

            overrides = dict(request_body)
            if source_pattern == "historic" and payload.get("input_range") is not None:
                overrides["range_size"] = payload["input_range"]
            if source_pattern in {"future", "planned"} and payload.get("output_range") is not None:
                overrides["range_size"] = payload["output_range"]
            if source_pattern:
                overrides["pattern"] = source_pattern
            payload["historical_data_request_overrides"] = overrides

        elif source_type == "weather":
            payload["weather_url"] = source.get("url")
            location = source.get("location", {}) if isinstance(source.get("location"), dict) else {}
            request_location = request_body.get("location", {}) if isinstance(request_body.get("location"), dict) else {}
            payload["weather_lat"] = location.get("latitude", request_location.get("latitude"))
            payload["weather_lon"] = location.get("longitude", request_location.get("longitude"))
            if payload.get("output_range") is not None:
                payload["weather_hours"] = payload["output_range"]

        elif source_type == "cmms":
            payload["cmms_url"] = source.get("url")
            overrides = dict(request_body)
            if source_pattern == "planned" and payload.get("output_range") is not None:
                overrides["range_size"] = payload["output_range"]
            if source_pattern:
                overrides["pattern"] = source_pattern
            payload["cmms_request_overrides"] = overrides

    return payload


# ---------------------------------------------------------------------------
# SCADA data fetching
# ---------------------------------------------------------------------------

def _normalize_url(url: str) -> str:
    """Replace 127.0.0.1/localhost with host.docker.internal inside Docker."""
    parsed = urlparse(url)
    if parsed.hostname in {"127.0.0.1", "localhost"} and Path("/.dockerenv").exists():
        netloc = parsed.netloc.replace(parsed.hostname, "host.docker.internal")
        url = urlunparse(parsed._replace(netloc=netloc))
    return url


def fetch_scada(
    url: str,
    archives: List[str],
    step_s: int,
    lookback_hours: int,
) -> Dict[str, List[List[float]]]:
    """POST request to SCADA archive endpoint, return raw payload."""
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    from_dt = now - timedelta(hours=lookback_hours)

    body = {
        "from": int(from_dt.timestamp() * 1000),
        "to": int(now.timestamp() * 1000),
        "archive": archives,
        "step": step_s,
        "pattern": "historic",
    }

    url = _normalize_url(url)
    logger.info("POST %s  lookback=%dh  archives=%s", url, lookback_hours, archives)
    logger.debug("Request body: %s", json.dumps(body, indent=2))

    resp = requests.post(url, json=body, timeout=30, headers={"Content-Type": "application/json"})
    resp.raise_for_status()

    payload = resp.json()
    if not isinstance(payload, dict) or not payload:
        raise ValueError(f"Unexpected SCADA response: {payload!r}")

    total_points = sum(len(v) for v in payload.values())
    logger.info("SCADA returned %d point(s) across %d archive(s)", total_points, len(payload))
    return payload


def build_stub_payload(
    archives: List[str],
    step_s: int,
    lookback_hours: int,
) -> Dict[str, List[List[float]]]:
    """Generate synthetic data with deterministic seasonality (mirrors server stub)."""
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    from_dt = now - timedelta(hours=lookback_hours)
    from_ms = int(from_dt.timestamp() * 1000)
    to_ms   = int(now.timestamp() * 1000)
    step_ms = step_s * 1000

    timestamps = np.arange(from_ms, to_ms, step_ms, dtype=np.int64)

    payload: Dict[str, List[List[float]]] = {}
    for idx, archive in enumerate(archives):
        base   = 380.0 + idx * 25.0
        n      = len(timestamps)
        hourly = np.array([(datetime.fromtimestamp(t / 1000, tz=timezone.utc)).hour for t in timestamps], dtype=float)
        daily  = np.sin(2 * np.pi * hourly / 24) * 45.0
        weekly = np.sin(np.linspace(0.0, 4 * np.pi, n)) * 20.0
        noise  = np.random.default_rng(seed=42 + idx).normal(0, 5, n)
        values = base + daily + weekly + noise
        values = np.clip(values, 0, None)
        payload[str(archive)] = [
            [int(ts), round(float(v), 3), 0] for ts, v in zip(timestamps, values)
        ]

    total = sum(len(v) for v in payload.values())
    logger.info("Stub generated %d point(s) across %d archive(s)", total, len(payload))
    return payload


# ---------------------------------------------------------------------------
# Feature engineering  (AR-XGB)
# ---------------------------------------------------------------------------

def build_ar_dataset(
    values: np.ndarray,
    lags: int,
    horizon: int,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Build supervised regression dataset from univariate time series.

    Returns:
        X  — (n_samples, lags)
        y  — (n_samples, horizon)  multi-step targets
    """
    n = len(values)
    if n < lags + horizon:
        raise ValueError(
            f"Not enough data: need at least {lags + horizon} points, got {n}"
        )

    X, y = [], []
    for i in range(lags, n - horizon + 1):
        X.append(values[i - lags: i])
        y.append(values[i: i + horizon])

    return np.array(X, dtype=np.float32), np.array(y, dtype=np.float32)


def add_time_features(X: np.ndarray, base_timestamps: np.ndarray, lags: int, step_s: int) -> np.ndarray:
    """Append hour-of-day and day-of-week features (cyclic encoded) to X."""
    n = len(X)
    hours, dows = [], []
    for i in range(lags, lags + n):
        ts_epoch = int(base_timestamps[i]) / 1000
        dt = datetime.fromtimestamp(ts_epoch, tz=timezone.utc)
        hours.append(dt.hour)
        dows.append(dt.weekday())

    hours = np.array(hours, dtype=np.float32)
    dows = np.array(dows, dtype=np.float32)

    sin_h = np.sin(2 * np.pi * hours / 24)
    cos_h = np.cos(2 * np.pi * hours / 24)
    sin_d = np.sin(2 * np.pi * dows / 7)
    cos_d = np.cos(2 * np.pi * dows / 7)

    return np.column_stack([X, sin_h, cos_h, sin_d, cos_d])


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------

def train(
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_val: np.ndarray,
    y_val: np.ndarray,
    model_params: Dict[str, Any],
    horizon: int,
) -> Dict[str, xgb.XGBRegressor]:
    """
    Train independent XGBRegressor for each forecast step.

    Returns a dict of {step: model} where each model predicts 1 step ahead.
    This approach is compatible with single-output expectations and allows
    flexible ensemble strategies.
    """
    params = {
        "n_estimators":      int(model_params.get("n_estimators", 400)),
        "max_depth":         int(model_params.get("max_depth", 6)),
        "learning_rate":     float(model_params.get("learning_rate", 0.05)),
        "subsample":         float(model_params.get("subsample", 0.9)),
        "colsample_bytree":  float(model_params.get("colsample_bytree", 0.9)),
        "reg_alpha":         float(model_params.get("reg_alpha", 0.0)),
        "reg_lambda":        float(model_params.get("reg_lambda", 1.0)),
        "objective":         str(model_params.get("objective", "reg:squarederror")),
        "eval_metric":       str(model_params.get("eval_metric", "rmse")),
        "tree_method":       "hist",
        "verbosity":         0,
        "n_jobs":            -1,
        "random_state":      42,
    }

    logger.info("XGBoost params: %s", params)

    models = {}
    for step in range(horizon):
        model = xgb.XGBRegressor(**params)
        
        # Train on step-specific target
        y_train_step = y_train[:, step]
        y_val_step = y_val[:, step]
        
        model.fit(
            X_train, y_train_step,
            eval_set=[(X_val, y_val_step)],
            verbose=False,
        )
        
        # Evaluate on validation set
        y_hat = model.predict(X_val)
        mae = mean_absolute_error(y_val_step, y_hat)
        rmse = mean_squared_error(y_val_step, y_hat) ** 0.5
        logger.info("Step %d: MAE=%.4f  RMSE=%.4f", step, mae, rmse)
        
        models[step] = model
    
    return models


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------

def save_model(
    model: Dict[str, xgb.XGBRegressor],
    model_dir: Path,
    filename: str,
    horizon: int,
    n_features: int,
    lags: int,
    metrics: Dict[str, float],
) -> Path:
    """
    Serialize multi-step XGBoost models (one per horizon step).

    Saves each step's booster as xgb_model_step_{i}.json and writes manifest.
    This format is compatible with XGBoostAdapter expectations.
    """
    model_dir.mkdir(parents=True, exist_ok=True)
    out_path = model_dir / filename

    # Save each step's booster
    step_files = []
    for step in range(horizon):
        if step not in model:
            logger.warning("Step %d not found in models dict", step)
            continue
        
        step_fname = f"xgb_model_step_{step}.json"
        model[step].get_booster().save_model(str(model_dir / step_fname))
        step_files.append(step_fname)
        logger.info("Saved step %d booster: %s", step, step_fname)

    manifest = {
        "horizon":    horizon,
        "n_features": n_features,
        "lags":       lags,
        "metrics":    metrics,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "type":       "xgb_multi",
        "steps":      step_files,
        "multi_output": True,
    }

    with open(out_path, "w") as f:
        json.dump(manifest, f, indent=2)

    logger.info("Model saved → %s (%d steps)", out_path, len(step_files))
    return out_path


def register_model_in_mlflow(
    model_id: str,
    model_dir: Path,
    manifest_path: Path,
    full_config: Dict[str, Any],
    model_params: Dict[str, Any],
    metrics: Dict[str, float],
) -> Dict[str, Any]:
    """
    Register trained model in MLflow Registry linked to a concrete run_id.

    This function avoids direct artifact upload to MLflow server and instead
    places artifacts into the run artifact directory on the host volume.
    """
    try:
        import mlflow
        from mlflow.tracking import MlflowClient
    except ImportError as exc:
        raise RuntimeError("MLflow is required for model registration") from exc

    def _safe_tag_value(value: Any, max_len: int = 5000) -> str:
        text = str(value)
        if len(text) <= max_len:
            return text
        return text[: max_len - 3] + "..."

    def _flatten_config_to_tags(value: Any, prefix: str) -> Dict[str, str]:
        tags: Dict[str, str] = {}

        if isinstance(value, dict):
            if not value:
                tags[prefix] = "{}"
                return tags
            for key in sorted(value.keys()):
                key_str = str(key).replace(" ", "_")
                child_prefix = f"{prefix}.{key_str}"
                tags.update(_flatten_config_to_tags(value[key], child_prefix))
            return tags

        if isinstance(value, list):
            if not value:
                tags[prefix] = "[]"
                return tags
            for index, item in enumerate(value):
                child_prefix = f"{prefix}[{index}]"
                tags.update(_flatten_config_to_tags(item, child_prefix))
            return tags

        if isinstance(value, bool):
            tags[prefix] = "true" if value else "false"
            return tags

        if value is None:
            tags[prefix] = "null"
            return tags

        tags[prefix] = _safe_tag_value(value)
        return tags

    def _build_config_tags(cfg: Dict[str, Any]) -> Dict[str, str]:
        tags = _flatten_config_to_tags(cfg, "config")
        tags["config_json"] = _safe_tag_value(json.dumps(cfg, ensure_ascii=True, sort_keys=True))
        return tags

    def _load_model_runtime_config_text() -> str:
        for cfg_name in ("config_unified.yaml", "config.yaml"):
            cfg_path = model_dir / cfg_name
            if cfg_path.is_file():
                return cfg_path.read_text(encoding="utf-8")
        return ""

    def _set_required_model_version_tags(version: str, runtime_config_text: str) -> None:
        client.set_model_version_tag(model_id, version, "model_id", model_id)
        if runtime_config_text:
            client.set_model_version_tag(
                model_id,
                version,
                "runtime_config_yaml",
                runtime_config_text,
            )

    def _set_model_version_config_tags(version: str, config_tags: Dict[str, str]) -> None:
        for key, value in config_tags.items():
            client.set_model_version_tag(model_id, version, key, value)

    def _backfill_required_tags_for_all_versions(runtime_config_text: str) -> None:
        versions = client.search_model_versions(f"name='{model_id}'")
        for mv in versions:
            _set_required_model_version_tags(str(mv.version), runtime_config_text)

    tracking_uri = "http://127.0.0.1:5050"
    experiment_name = "forecast_training"
    # MLflow container path (see docker-compose mapping ../mlruns:/mlflow/mlruns)
    experiment_artifact_location = "/mlflow/mlruns/manual_reg"
    host_mlruns_dir = Path(
        os.getenv(
            "MLFLOW_HOST_MLRUNS_DIR",
            str(Path(__file__).resolve().parents[2] / "local" / "mlruns"),
        )
    )

    mlflow.set_tracking_uri(tracking_uri)
    client = MlflowClient()
    config_tags = _build_config_tags(full_config)

    experiment = client.get_experiment_by_name(experiment_name)
    if experiment is None:
        experiment_id = client.create_experiment(
            experiment_name,
            artifact_location=experiment_artifact_location,
        )
    else:
        experiment_id = experiment.experiment_id

    run_name = f"train_{model_id}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    with mlflow.start_run(experiment_id=experiment_id, run_name=run_name) as run:
        run_id = run.info.run_id
        artifact_uri = run.info.artifact_uri.rstrip("/")

        mlflow.log_param("model_id", model_id)
        mlflow.log_param("model_type", "xgb")
        mlflow.log_param("horizon", int(model_params.get("horizon", 24)))
        mlflow.log_param("lags", int(model_params.get("lags", 72)))
        mlflow.log_param("n_estimators", int(model_params.get("n_estimators", 400)))
        mlflow.log_param("max_depth", int(model_params.get("max_depth", 6)))
        mlflow.log_param("learning_rate", float(model_params.get("learning_rate", 0.05)))

        for key, value in metrics.items():
            try:
                mlflow.log_metric(key, float(value))
            except Exception:
                logger.warning("Could not log metric %s=%s", key, value)

        mlflow.set_tag("model_id", model_id)
        mlflow.set_tag("registration_mode", "bundle_layout")
        if config_tags:
            mlflow.set_tags(config_tags)

    if not artifact_uri.startswith("/mlflow/mlruns"):
        raise RuntimeError(
            f"Unsupported artifact URI for registration: {artifact_uri}. "
            "Expected path under /mlflow/mlruns."
        )

    bundle_container_dir = f"{artifact_uri}/bundle"
    source_container_dir = f"{bundle_container_dir}/model"
    source_host_dir = Path(source_container_dir.replace("/mlflow/mlruns", str(host_mlruns_dir)))
    config_host_dir = Path(f"{bundle_container_dir}/configuration".replace("/mlflow/mlruns", str(host_mlruns_dir)))
    assets_host_dir = Path(f"{bundle_container_dir}/assets".replace("/mlflow/mlruns", str(host_mlruns_dir)))

    source_host_dir.mkdir(parents=True, exist_ok=True)
    config_host_dir.mkdir(parents=True, exist_ok=True)
    assets_host_dir.mkdir(parents=True, exist_ok=True)

    # Copy model manifest and boosters into bundle/model
    shutil.copy2(manifest_path, source_host_dir / manifest_path.name)
    for step_file in sorted(model_dir.glob("xgb_model_step_*.json")):
        shutil.copy2(step_file, source_host_dir / step_file.name)

    cache_config = build_cache_config(full_config)
    cache_config_path = config_host_dir / "cache_config.json"
    cache_config_path.write_text(json.dumps(cache_config, ensure_ascii=True, indent=2), encoding="utf-8")

    # Keep local model directory aligned with runtime config format.
    local_cache_config_path = model_dir / "cache_config.json"
    local_cache_config_path.write_text(json.dumps(cache_config, ensure_ascii=True, indent=2), encoding="utf-8")

    # Include active model yaml in bundle/assets for reproducibility
    for cfg_name in ("config_unified.yaml", "config.yaml"):
        cfg_path = model_dir / cfg_name
        if cfg_path.is_file():
            shutil.copy2(cfg_path, assets_host_dir / cfg_path.name)
            break

    try:
        client.get_registered_model(model_id)
    except Exception:
        client.create_registered_model(model_id)

    model_version = client.create_model_version(
        name=model_id,
        source=source_container_dir,
        run_id=run_id,
        description="Auto-registered by train_xgb.py",
    )

    runtime_config_text = _load_model_runtime_config_text()
    _set_required_model_version_tags(str(model_version.version), runtime_config_text)
    _set_model_version_config_tags(str(model_version.version), config_tags)
    _backfill_required_tags_for_all_versions(runtime_config_text)

    try:
        client.set_registered_model_alias(
            name=model_id,
            alias="Production",
            version=model_version.version,
        )
    except Exception as exc:
        logger.warning("Could not set Production alias: %s", exc)

    result = {
        "run_id": run_id,
        "model_name": model_id,
        "model_version": model_version.version,
        "source": source_container_dir,
    }
    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch SCADA data and train XGBoost model")
    parser.add_argument(
        "--model-dir",
        required=True,
        type=Path,
        help="Path to model directory containing config.yaml",
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=None,
        help="Override lookback period in days (default: from config)",
    )
    parser.add_argument(
        "--val-ratio",
        type=float,
        default=0.15,
        help="Fraction of data to use for validation (default: 0.15)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch data and report stats, but do not train or save",
    )
    parser.add_argument(
        "--use-stub",
        action="store_true",
        default=False,
        help="Use synthetic stub data instead of live SCADA (for testing/offline use)",
    )
    parser.add_argument(
        "--skip-mlflow-register",
        action="store_true",
        default=False,
        help="Skip automatic MLflow registration after training",
    )
    args = parser.parse_args()

    model_dir = args.model_dir.resolve()
    if not model_dir.is_dir():
        logger.error("Model directory not found: %s", model_dir)
        sys.exit(1)

    # --- Config ---
    cfg = load_config(model_dir)
    model_cfg = _model_section(cfg)

    model_type = str(model_cfg.get("type", cfg.get("type", "xgb"))).lower()
    if model_type not in {"xgb", "ar_xgb"}:
        logger.error("Config model.type='%s' — expected xgb or ar_xgb", model_type)
        sys.exit(1)

    lags    = int(model_cfg.get("lags", 72))
    horizon = int(model_cfg.get("horizon", 24))
    step_s  = int(cfg.get("time_series", {}).get("step_seconds", 3600))

    ds = _data_source(cfg)
    lookback_hours = int(ds.get("lookback_period", 168))
    if args.lookback_days:
        lookback_hours = args.lookback_days * 24

    api_cfg = _first_historical_api(cfg)
    if not api_cfg:
        logger.error("No 'historical_data' API entry found in data_source.apis")
        sys.exit(1)

    scada_url = api_cfg.get("url") or "http://127.0.0.1:7080/api/v1/read/archives"
    archives  = list(api_cfg.get("request_body", {}).get("archive", []))
    if not archives:
        logger.error("No archives configured in data_source.apis[*].request_body.archive")
        sys.exit(1)

    logger.info("Model dir : %s", model_dir)
    logger.info("Algorithm : AR-XGB  lags=%d  horizon=%d  step=%ds", lags, horizon, step_s)
    logger.info("Lookback  : %d hours (~%dd)", lookback_hours, lookback_hours // 24)
    logger.info("SCADA URL : %s", scada_url)
    logger.info("Archives  : %s", archives)

    # --- Fetch ---
    try:
        if args.use_stub:
            logger.warning("--use-stub: using synthetic data instead of live SCADA")
            payload = build_stub_payload(archives, step_s, lookback_hours)
        else:
            payload = fetch_scada(scada_url, archives, step_s, lookback_hours)
    except Exception as exc:
        logger.error("SCADA request failed: %s", exc)
        logger.warning("Retrying with stub data (use --use-stub to skip live SCADA explicitly)")
        payload = build_stub_payload(archives, step_s, lookback_hours)

    # Use first archive series
    first_key = next(iter(payload))
    raw = payload[first_key]
    timestamps = np.array([r[0] for r in raw], dtype=np.int64)
    values = np.array([r[1] for r in raw], dtype=np.float64)
    qds    = np.array([0 if r[2] is None else int(r[2]) for r in raw], dtype=np.int32)

    valid_mask = np.isin(qds, [0, QDS_BASE := 0], invert=False) | (qds < 64)
    n_invalid = int((qds >= 64).sum())
    logger.info(
        "Series: %d points, min=%.2f, max=%.2f, mean=%.2f, invalid QDS: %d",
        len(values), values.min(), values.max(), values.mean(), n_invalid,
    )

    if args.dry_run:
        logger.info("--dry-run: stopping before training")
        return

    if len(values) < lags + horizon + 2:
        logger.error(
            "Not enough data to build training set. Need >= %d points, got %d. "
            "Increase --lookback-days.",
            lags + horizon + 2,
            len(values),
        )
        sys.exit(1)

    # --- Features ---
    X, y = build_ar_dataset(values, lags=lags, horizon=horizon)
    X = add_time_features(X, timestamps, lags=lags, step_s=step_s)
    n_features = X.shape[1]

    split = max(1, int(len(X) * (1 - args.val_ratio)))
    X_train, X_val = X[:split], X[split:]
    y_train, y_val = y[:split], y[split:]

    logger.info(
        "Dataset: %d train / %d val  features=%d",
        len(X_train), len(X_val), n_features,
    )

    # --- Train ---
    model = train(X_train, y_train, X_val, y_val, model_cfg, horizon)

    # Compute aggregate metrics across all steps
    y_hat_val_all = np.array([model[step].predict(X_val) for step in range(horizon)]).T
    mae  = mean_absolute_error(y_val, y_hat_val_all)
    rmse = mean_squared_error(y_val, y_hat_val_all) ** 0.5
    metrics = {"mae": round(mae, 4), "rmse": round(rmse, 4)}

    # --- Save ---
    model_filename = str(model_cfg.get("file", "xgb_model.json"))
    if not model_filename or model_filename == "none":
        model_filename = "xgb_model.json"

    manifest_path = save_model(
        model=model,
        model_dir=model_dir,
        filename=model_filename,
        horizon=horizon,
        n_features=n_features,
        lags=lags,
        metrics=metrics,
    )

    if not args.skip_mlflow_register:
        model_id = model_dir.name
        reg = register_model_in_mlflow(
            model_id=model_id,
            model_dir=model_dir,
            manifest_path=manifest_path,
            full_config=cfg,
            model_params=model_cfg,
            metrics=metrics,
        )
        logger.info(
            "MLflow registered: model=%s version=%s run_id=%s",
            reg["model_name"],
            reg["model_version"],
            reg["run_id"],
        )

    logger.info("Done. MAE=%.4f  RMSE=%.4f", mae, rmse)


if __name__ == "__main__":
    main()
