"""
Batch initialization of model environments and Stage 0-3 data collection.

Reads model definitions from CSV exports of model_list.xlsx and produces
training-ready parquet snapshots for each model:
- train_snapshot.parquet
- validation_snapshot.parquet
- test_snapshot.parquet

Also writes quality/profile reports and an environment manifest per model.

Usage examples:
    python scripts/batch_model_data_collection.py --limit 5 --source-mode stub
    python scripts/batch_model_data_collection.py --api-url http://127.0.0.1:5888/data/history
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import re
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("batch_model_data_collection")


@dataclass
class WindowConfig:
    name: str
    input_range: int
    output_range: int
    step: int
    model_path: str


@dataclass
class ModelTask:
    object_ref: str
    description: str
    region: str
    object_name: str
    model_type: str
    horizon_key: str
    weather: bool
    cmms: bool
    historical_inputs: list[str]
    window: WindowConfig
    config_raw: dict[str, Any]


@dataclass
class RunStats:
    total: int = 0
    ok: int = 0
    skipped: int = 0
    failed: int = 0


def _bool_from_cell(value: Any) -> bool:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return False
    if isinstance(value, (int, float)):
        return value > 0
    text = str(value).strip().lower()
    return text in {"1", "true", "yes", "y", "да"}


def _sanitize_slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip("/"))
    return slug[:180] if len(slug) > 180 else slug


def _parse_configuration(raw: Any) -> dict[str, Any]:
    if raw is None or (isinstance(raw, float) and math.isnan(raw)):
        return {}
    text = str(raw).strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid configuration JSON: {exc}") from exc


def _detect_configuration_column(df: pd.DataFrame) -> str:
    if "configuration" in df.columns:
        return "configuration"

    candidates = [col for col in df.columns if str(col).strip().lower() not in {"horizont key", "#"}]
    sample = df.head(30)
    for col in candidates:
        values = sample[col].dropna().astype(str)
        if values.empty:
            continue
        hits = values.str.contains(r"\{", regex=True).sum()
        if hits >= max(2, int(len(values) * 0.3)):
            return col

    raise ValueError("Could not detect configuration JSON column in models CSV")


def _extract_window(config: dict[str, Any], horizon_key: str) -> WindowConfig:
    section = config.get(horizon_key)
    if not isinstance(section, dict):
        raise ValueError(f"Configuration does not contain horizon section '{horizon_key}'")

    return WindowConfig(
        name=str(section.get("name", horizon_key)),
        input_range=int(section.get("input_range", 72)),
        output_range=int(section.get("output_range", 24)),
        step=int(section.get("step", 3600)),
        model_path=str(section.get("model_path", "")),
    )


def _load_inputs_map(inputs_csv: Path) -> dict[str, list[str]]:
    # Auto-detect delimiter
    probe = pd.read_csv(inputs_csv, nrows=1)
    df = pd.read_csv(inputs_csv, sep=";") if len(probe.columns) <= 2 else pd.read_csv(inputs_csv)

    required = {"object_ref", "input_type", "input_ref"}
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"Missing columns in inputs CSV: {sorted(missing)}. Got: {sorted(df.columns.tolist())}")

    mask = (
        (df["input_type"].astype(str).str.strip().str.lower() == "historical")
        & df["input_ref"].notna()
    )
    filtered = df[mask].copy()

    grouped: dict[str, list[str]] = {}
    for object_ref, rows in filtered.groupby("object_ref"):
        unique_values = (
            rows["input_ref"].astype(str).str.strip().replace("", np.nan).dropna().unique().tolist()
        )
        grouped[str(object_ref)] = unique_values
    return grouped


def _is_flat_format(df: pd.DataFrame) -> bool:
    """Return True when the CSV already has flat window columns (no JSON configuration)."""
    return {"input_range", "output_range", "step", "model_path"}.issubset(df.columns)


def _read_models_csv(path: Path) -> pd.DataFrame:
    """Read models CSV auto-detecting comma vs semicolon delimiter."""
    probe = pd.read_csv(path, nrows=1)
    if len(probe.columns) <= 2:
        return pd.read_csv(path, sep=";")
    return probe._append(pd.read_csv(path, skiprows=1), ignore_index=True) if False else pd.read_csv(path)


def load_model_tasks(
    models_csv: Path,
    inputs_csv: Path,
    horizon_override: str | None,
    limit: int | None,
) -> list[ModelTask]:
    # Auto-detect delimiter: if comma-parsing yields ≤2 columns, try semicolon
    probe = pd.read_csv(models_csv, nrows=1)
    models_df = pd.read_csv(models_csv, sep=";") if len(probe.columns) <= 2 else pd.read_csv(models_csv)

    flat = _is_flat_format(models_df)

    required_base = {"object_ref", "region", "onbject", "type", "weather", "cmms", "horizont key"}
    missing = required_base.difference(models_df.columns)
    if missing:
        raise ValueError(f"Missing columns in models CSV: {sorted(missing)}")

    if not flat:
        configuration_column = _detect_configuration_column(models_df)

    inputs_map = _load_inputs_map(inputs_csv)
    tasks: list[ModelTask] = []

    for _, row in models_df.iterrows():
        object_ref = str(row["object_ref"]).strip()
        if not object_ref or object_ref.lower() == "nan":
            continue

        row_horizon = str(row["horizont key"]).strip().lower()
        horizon_key = (horizon_override or row_horizon or "day").lower()

        if flat:
            window = WindowConfig(
                name=horizon_key,
                input_range=int(row.get("input_range", 72)),
                output_range=int(row.get("output_range", 24)),
                step=int(row.get("step", 3600)),
                model_path=str(row.get("model_path", "")),
            )
            config_raw: dict[str, Any] = {}
        else:
            config_raw = _parse_configuration(row[configuration_column])
            window = _extract_window(config_raw, horizon_key)

        description = str(row["description"]) if "description" in models_df.columns else str(row.get("onbject", ""))

        tasks.append(
            ModelTask(
                object_ref=object_ref,
                description=description,
                region=str(row["region"]),
                object_name=str(row["onbject"]),
                model_type=str(row["type"]),
                horizon_key=horizon_key,
                weather=_bool_from_cell(row["weather"]),
                cmms=_bool_from_cell(row["cmms"]),
                historical_inputs=inputs_map.get(object_ref, []),
                window=window,
                config_raw=config_raw,
            )
        )

    if limit is not None and limit > 0:
        tasks = tasks[:limit]
    return tasks


def _build_stub_payload(archives: list[str], from_dt: datetime, to_dt: datetime, step_s: int) -> dict[str, list[list[float]]]:
    from_ms = int(from_dt.timestamp() * 1000)
    to_ms = int(to_dt.timestamp() * 1000)
    step_ms = int(step_s * 1000)
    timestamps = np.arange(from_ms, to_ms, step_ms, dtype=np.int64)

    payload: dict[str, list[list[float]]] = {}
    for idx, archive in enumerate(archives):
        rng = np.random.default_rng(seed=42 + idx)
        n = len(timestamps)
        hours = np.array([datetime.fromtimestamp(ts / 1000, tz=timezone.utc).hour for ts in timestamps], dtype=float)
        weekly = np.sin(np.linspace(0, 4 * np.pi, n)) * 12.0
        daily = np.sin(2 * np.pi * hours / 24) * 35.0
        trend = np.linspace(0, 6, n)
        noise = rng.normal(0, 4, n)
        values = np.clip(150 + idx * 8 + weekly + daily + trend + noise, 0, None)
        payload[archive] = [[int(ts), float(v), 0] for ts, v in zip(timestamps, values)]
    return payload


def _fetch_payload(
    source_mode: str,
    api_url: str | None,
    archives: list[str],
    from_dt: datetime,
    to_dt: datetime,
    step_s: int,
    timeout: int,
    retries: int,
) -> dict[str, list[list[float]]]:
    if source_mode == "stub":
        return _build_stub_payload(archives, from_dt, to_dt, step_s)

    if not api_url:
        raise ValueError("api_url is required for source-mode=api")

    body = {
        "from": int(from_dt.timestamp() * 1000),
        "to": int(to_dt.timestamp() * 1000),
        "archive": archives,
        "step": step_s,
        "pattern": "historic",
    }

    error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            response = requests.post(api_url, json=body, timeout=timeout, headers={"Content-Type": "application/json"})
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError(f"Unexpected API payload type: {type(payload)!r}")
            return payload
        except Exception as exc:
            error = exc
            logger.warning("Attempt %d/%d failed for API request: %s", attempt, retries, exc)
    raise RuntimeError(f"Historical data request failed after {retries} attempts: {error}")


def _payload_to_frame(payload: dict[str, list[list[float]]]) -> pd.DataFrame:
    series_frames: list[pd.DataFrame] = []
    for archive_name, rows in payload.items():
        if not isinstance(rows, list) or not rows:
            continue
        frame = pd.DataFrame(rows, columns=["timestamp_ms", "value", "qds"])
        frame["ds"] = pd.to_datetime(frame["timestamp_ms"], unit="ms", utc=True, errors="coerce")
        frame = frame[["ds", "value"]].rename(columns={"value": archive_name})
        series_frames.append(frame.dropna(subset=["ds"]))

    if not series_frames:
        return pd.DataFrame(columns=["ds", "y"])

    merged = series_frames[0]
    for frame in series_frames[1:]:
        merged = merged.merge(frame, on="ds", how="outer")

    merged = merged.sort_values("ds").reset_index(drop=True)
    value_columns = [col for col in merged.columns if col != "ds"]

    # Use the first source as the primary target for universal ds/y training format.
    merged["y"] = pd.to_numeric(merged[value_columns[0]], errors="coerce")
    output = merged[["ds", "y"]].copy()
    output["y"] = output["y"].astype(float)
    return output.dropna(subset=["ds"]).sort_values("ds").reset_index(drop=True)


def _run_quality_checks(df: pd.DataFrame, step_s: int, horizon: int) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame([
            {"check": "dataset_not_empty", "status": "fail", "value": 0, "notes": "No rows after ingestion"}
        ])

    duplicate_count = int(df["ds"].duplicated().sum())
    null_ratio = float(df["y"].isna().mean())
    sample_size = int(len(df))

    time_delta = df["ds"].diff().dropna()
    expected = pd.Timedelta(seconds=int(step_s))
    gap_count = int((time_delta > expected).sum()) if not time_delta.empty else 0

    checks = [
        {"check": "dataset_not_empty", "status": "ok" if sample_size > 0 else "fail", "value": sample_size, "notes": "Rows count"},
        {"check": "timestamp_duplicates", "status": "ok" if duplicate_count == 0 else "warn", "value": duplicate_count, "notes": "Duplicated ds"},
        {"check": "target_null_ratio", "status": "ok" if null_ratio <= 0.05 else "warn", "value": round(null_ratio, 4), "notes": "Share of null y"},
        {"check": "time_gaps", "status": "ok" if gap_count == 0 else "warn", "value": gap_count, "notes": "Gaps above expected step"},
        {
            "check": "min_sample_size",
            "status": "ok" if sample_size >= max(7 * int(horizon), 200) else "warn",
            "value": sample_size,
            "notes": "Heuristic minimum sample size",
        },
        {
            "check": "target_variance",
            "status": "ok" if df["y"].dropna().nunique() > 1 else "fail",
            "value": int(df["y"].dropna().nunique()),
            "notes": "Unique non-null target values",
        },
    ]
    return pd.DataFrame(checks)


def _dataset_profile(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()

    values = df["y"].dropna()
    profile = pd.DataFrame([
        {
            "rows": len(df),
            "start": df["ds"].min(),
            "end": df["ds"].max(),
            "mean": values.mean(),
            "median": values.median(),
            "std": values.std(),
            "min": values.min(),
            "max": values.max(),
            "p05": values.quantile(0.05),
            "p95": values.quantile(0.95),
        }
    ])
    numeric_columns = profile.select_dtypes(include=[np.number]).columns.tolist()
    if numeric_columns:
        profile[numeric_columns] = profile[numeric_columns].round(6)
    return profile


def _split_dataset(df: pd.DataFrame, train_ratio: float, validation_ratio: float) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if df.empty:
        empty = df.copy()
        return empty, empty, empty

    n = len(df)
    train_end = int(n * train_ratio)
    val_end = int(n * (train_ratio + validation_ratio))

    train_df = df.iloc[:train_end].copy()
    val_df = df.iloc[train_end:val_end].copy()
    test_df = df.iloc[val_end:].copy()
    return train_df, val_df, test_df


def _resolve_source_mode(source_mode: str, api_url: str | None) -> str:
    if source_mode in {"api", "stub"}:
        return source_mode
    return "api" if api_url else "stub"


def _run_single_model(
    task: ModelTask,
    output_root: Path,
    source_mode: str,
    api_url: str | None,
    train_ratio: float,
    validation_ratio: float,
    timeout: int,
    retries: int,
    skip_existing: bool = False,
) -> dict[str, Any]:
    if not task.historical_inputs:
        return {"status": "skipped", "reason": "No historical inputs", "object_ref": task.object_ref}

    slug = _sanitize_slug(task.object_ref)
    model_root = output_root / slug
    if skip_existing and (model_root / "datasets" / "train_snapshot.parquet").exists():
        return {"status": "skipped", "reason": "Already exists", "object_ref": task.object_ref}

    to_dt = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    from_dt = to_dt - timedelta(hours=int(task.window.input_range))

    payload = _fetch_payload(
        source_mode=source_mode,
        api_url=api_url,
        archives=task.historical_inputs,
        from_dt=from_dt,
        to_dt=to_dt,
        step_s=int(task.window.step),
        timeout=timeout,
        retries=retries,
    )
    frame = _payload_to_frame(payload)
    frame = frame.drop_duplicates(subset=["ds"]).sort_values("ds").reset_index(drop=True)

    quality_df = _run_quality_checks(frame, task.window.step, task.window.output_range)
    profile_df = _dataset_profile(frame)
    train_df, val_df, test_df = _split_dataset(frame, train_ratio=train_ratio, validation_ratio=validation_ratio)

    slug = _sanitize_slug(task.object_ref)
    dataset_dir = model_root / "datasets"
    reports_dir = model_root / "reports"
    environment_dir = model_root / "environment"
    dataset_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)
    environment_dir.mkdir(parents=True, exist_ok=True)

    train_path = dataset_dir / "train_snapshot.parquet"
    val_path = dataset_dir / "validation_snapshot.parquet"
    test_path = dataset_dir / "test_snapshot.parquet"
    profile_path = reports_dir / "dataset_profile.csv"
    quality_path = reports_dir / "quality_summary.csv"

    train_df.to_parquet(train_path, index=False)
    val_df.to_parquet(val_path, index=False)
    test_df.to_parquet(test_path, index=False)
    profile_df.to_csv(profile_path, index=False)
    quality_df.to_csv(quality_path, index=False)

    env_payload = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "object_ref": task.object_ref,
        "description": task.description,
        "region": task.region,
        "object_name": task.object_name,
        "model_type": task.model_type,
        "horizon_key": task.horizon_key,
        "weather_enabled": task.weather,
        "cmms_enabled": task.cmms,
        "window": asdict(task.window),
        "historical_inputs": task.historical_inputs,
        "source_mode": source_mode,
    }

    manifest_payload = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "object_ref": task.object_ref,
        "source_mode": source_mode,
        "rows_total": int(len(frame)),
        "rows_train": int(len(train_df)),
        "rows_validation": int(len(val_df)),
        "rows_test": int(len(test_df)),
        "start": None if frame.empty else str(frame["ds"].min()),
        "end": None if frame.empty else str(frame["ds"].max()),
        "output_files": {
            "train_snapshot": str(train_path),
            "validation_snapshot": str(val_path),
            "test_snapshot": str(test_path),
            "dataset_profile": str(profile_path),
            "quality_summary": str(quality_path),
        },
    }

    (environment_dir / "model_environment.json").write_text(json.dumps(env_payload, ensure_ascii=False, indent=2))
    (model_root / "export_manifest.json").write_text(json.dumps(manifest_payload, ensure_ascii=False, indent=2))

    return {
        "status": "ok",
        "object_ref": task.object_ref,
        "output_dir": str(model_root),
        "rows_total": len(frame),
        "rows_train": len(train_df),
        "rows_validation": len(val_df),
        "rows_test": len(test_df),
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Batch Stage 0-3 model data collection from model list CSV")
    parser.add_argument("--models-csv", type=Path, default=Path("../local/model_list__models__short.csv"))
    parser.add_argument("--inputs-csv", type=Path, default=Path("../local/model_list__inputs.csv"))
    parser.add_argument("--output-root", type=Path, default=Path("../local/model_data_collection"))
    parser.add_argument("--horizon-key", type=str, default=None, help="Override horizon key: day/month/year")
    parser.add_argument("--api-url", type=str, default=None, help="Historical API endpoint")
    parser.add_argument("--source-mode", type=str, default="auto", choices=["auto", "api", "stub"])
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--train-ratio", type=float, default=0.7)
    parser.add_argument("--validation-ratio", type=float, default=0.15)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--skip-existing", action="store_true", default=False, help="Skip models whose train_snapshot.parquet already exists")
    return parser


def main() -> int:
    args = _build_parser().parse_args()

    if not (0 < args.train_ratio < 1):
        raise ValueError("train-ratio must be in (0,1)")
    if not (0 < args.validation_ratio < 1):
        raise ValueError("validation-ratio must be in (0,1)")
    if args.train_ratio + args.validation_ratio >= 1:
        raise ValueError("train-ratio + validation-ratio must be < 1")

    source_mode = _resolve_source_mode(args.source_mode, args.api_url)
    logger.info("Source mode: %s", source_mode)

    tasks = load_model_tasks(
        models_csv=args.models_csv,
        inputs_csv=args.inputs_csv,
        horizon_override=args.horizon_key,
        limit=args.limit,
    )
    args.output_root.mkdir(parents=True, exist_ok=True)
    summary: list[dict[str, Any]] = []
    stats = RunStats(total=len(tasks))

    logger.info("Loaded %d model task(s)", len(tasks))

    for idx, task in enumerate(tasks, start=1):
        logger.info("[%d/%d] %s", idx, len(tasks), task.object_ref)
        try:
            result = _run_single_model(
                task=task,
                output_root=args.output_root,
                source_mode=source_mode,
                api_url=args.api_url,
                train_ratio=args.train_ratio,
                validation_ratio=args.validation_ratio,
                timeout=args.timeout,
                retries=max(1, args.retries),
                skip_existing=args.skip_existing,
            )
            summary.append(result)
            if result.get("status") == "ok":
                stats.ok += 1
            else:
                stats.skipped += 1
        except Exception as exc:
            logger.exception("Model failed: %s", task.object_ref)
            summary.append({"status": "failed", "object_ref": task.object_ref, "error": str(exc)})
            stats.failed += 1

    summary_path = args.output_root / "batch_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2))

    logger.info(
        "Done: total=%d ok=%d skipped=%d failed=%d summary=%s",
        stats.total,
        stats.ok,
        stats.skipped,
        stats.failed,
        summary_path,
    )
    return 0 if stats.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
