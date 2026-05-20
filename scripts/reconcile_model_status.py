"""
Reconcile model lifecycle status across offline training artifacts and prod cache.

The script builds a table by model_id and reports:
- data_collection_status from batch_summary.json
- offline_training_status from local/models/<model_id>/training artifacts
- prod_cache_status from local/mlruns using Production alias run_id
- lifecycle_status and mismatch_flag

Usage examples:
    python scripts/reconcile_model_status.py
    python scripts/reconcile_model_status.py --tracking-uri http://127.0.0.1:5050
    python scripts/reconcile_model_status.py --output-dir ../local/models/training_workspace/manual_reports/audit
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import pandas as pd


def _sanitize_slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip("/"))
    return slug[:180] if len(slug) > 180 else slug


def _read_csv_auto(path: Path) -> pd.DataFrame:
    probe = pd.read_csv(path, nrows=1)
    return pd.read_csv(path, sep=";") if len(probe.columns) <= 2 else pd.read_csv(path)


def _load_batch_maps(batch_summary_path: Path) -> tuple[dict[str, str], dict[str, str]]:
    status_map: dict[str, str] = {}
    reason_map: dict[str, str] = {}

    if not batch_summary_path.exists():
        return status_map, reason_map

    payload = json.loads(batch_summary_path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        return status_map, reason_map

    for item in payload:
        if not isinstance(item, dict):
            continue
        object_ref = str(item.get("object_ref", ""))
        status_map[object_ref] = str(item.get("status", "unknown"))
        reason_map[object_ref] = str(item.get("reason", ""))
    return status_map, reason_map


def _offline_training_status(model_home_dir: Path) -> tuple[str, dict[str, bool]]:
    training_root = model_home_dir / "training"
    report_ok = (training_root / "reports" / "recommendation.json").exists()
    manifest_ok = (
        training_root / "bundle_export" / "bundle" / "assets" / "manual_training_manifest.json"
    ).exists()
    cache_cfg_ok = (
        training_root / "bundle_export" / "bundle" / "configuration" / "cache_config.json"
    ).exists()

    checks = {
        "report_ok": report_ok,
        "manifest_ok": manifest_ok,
        "cache_config_ok": cache_cfg_ok,
    }
    ok_count = sum(int(v) for v in checks.values())
    if ok_count == 3:
        return "trained", checks
    if ok_count > 0:
        return "partial", checks
    return "missing", checks


def _find_local_run_dir(mlruns_root: Path, run_id: str | None) -> Path | None:
    if not run_id:
        return None
    if not mlruns_root.exists():
        return None

    for exp_dir in mlruns_root.iterdir():
        if not exp_dir.is_dir() or exp_dir.name == "manual_reg":
            continue
        candidate = exp_dir / run_id
        if candidate.exists():
            return candidate
    return None


def _load_alias_map(tracking_uri: str | None, model_ids: list[str]) -> dict[str, dict[str, Any]]:
    default_item = {
        "alias_status": "unknown",
        "run_id": None,
        "model_version": None,
        "alias": None,
        "reason": "tracking_uri_not_set",
    }
    info_map = {model_id: dict(default_item) for model_id in model_ids}

    if not tracking_uri:
        return info_map

    try:
        from mlflow.tracking import MlflowClient

        client = MlflowClient(tracking_uri=tracking_uri)
    except Exception as exc:  # pragma: no cover - environment-specific
        for model_id in model_ids:
            info_map[model_id] = {
                "alias_status": "unknown",
                "run_id": None,
                "model_version": None,
                "alias": None,
                "reason": str(exc),
            }
        return info_map

    for model_id in model_ids:
        try:
            mv = client.get_model_version_by_alias(model_id, "Production")
            info_map[model_id] = {
                "alias_status": "present",
                "run_id": str(mv.run_id),
                "model_version": str(mv.version),
                "alias": "Production",
                "reason": "",
            }
        except Exception as exc:  # pragma: no cover - environment-specific
            info_map[model_id] = {
                "alias_status": "missing",
                "run_id": None,
                "model_version": None,
                "alias": None,
                "reason": str(exc),
            }
    return info_map


def build_audit_df(
    models_csv: Path,
    batch_summary: Path,
    model_store_root: Path,
    mlruns_root: Path,
    tracking_uri: str | None,
) -> pd.DataFrame:
    models_df = _read_csv_auto(models_csv)
    if "object_ref" not in models_df.columns:
        raise ValueError(f"models_csv does not contain object_ref: {models_csv}")

    status_map, reason_map = _load_batch_maps(batch_summary)

    models_df = models_df.copy()
    models_df["_status"] = models_df["object_ref"].astype(str).map(status_map).fillna("not_in_summary")
    models_df["_reason"] = models_df["object_ref"].astype(str).map(reason_map).fillna("")

    model_ids = models_df["object_ref"].astype(str).apply(_sanitize_slug).tolist()
    alias_map = _load_alias_map(tracking_uri=tracking_uri, model_ids=model_ids)

    rows: list[dict[str, Any]] = []
    for _, row in models_df.iterrows():
        object_ref = str(row["object_ref"])
        model_id = _sanitize_slug(object_ref)
        model_home_dir = model_store_root / model_id

        offline_status, checks = _offline_training_status(model_home_dir)
        alias_info = alias_map.get(model_id) or {}

        run_id = alias_info.get("run_id")
        run_dir = _find_local_run_dir(mlruns_root, run_id)
        local_bundle_cfg = (
            run_dir / "artifacts" / "bundle" / "bundle" / "configuration" / "cache_config.json"
            if run_dir is not None
            else None
        )

        if alias_info.get("alias_status") == "present" and local_bundle_cfg is not None and local_bundle_cfg.exists():
            prod_cache_status = "present"
        elif alias_info.get("alias_status") == "present" and run_dir is not None:
            prod_cache_status = "partial"
        elif alias_info.get("alias_status") == "present":
            prod_cache_status = "missing_local"
        elif alias_info.get("alias_status") == "missing":
            prod_cache_status = "missing"
        else:
            prod_cache_status = "unknown"

        mismatch_flag = (
            (offline_status in {"trained", "partial"} and prod_cache_status in {"missing", "missing_local"})
            or (offline_status == "missing" and prod_cache_status == "present")
        )

        if offline_status == "trained" and prod_cache_status == "present":
            lifecycle_status = "serving_ready"
        elif offline_status in {"trained", "partial"} and prod_cache_status in {"missing", "missing_local"}:
            lifecycle_status = "trained_only"
        elif offline_status == "missing" and prod_cache_status == "present":
            lifecycle_status = "cache_without_offline"
        elif prod_cache_status == "partial" or offline_status == "partial":
            lifecycle_status = "cache_partial"
        else:
            lifecycle_status = "missing"

        rows.append(
            {
                "object_ref": object_ref,
                "model_id": model_id,
                "data_collection_status": str(row.get("_status", "unknown")),
                "data_collection_reason": str(row.get("_reason", "")),
                "offline_training_status": offline_status,
                "prod_cache_status": prod_cache_status,
                "lifecycle_status": lifecycle_status,
                "production_alias": alias_info.get("alias"),
                "model_version": alias_info.get("model_version"),
                "run_id": run_id,
                "local_run_dir": "" if run_dir is None else str(run_dir),
                "offline_report_ok": checks["report_ok"],
                "offline_manifest_ok": checks["manifest_ok"],
                "offline_cache_config_ok": checks["cache_config_ok"],
                "mismatch_flag": bool(mismatch_flag),
            }
        )

    audit_df = pd.DataFrame(rows)
    if not audit_df.empty:
        audit_df = audit_df.sort_values(
            ["mismatch_flag", "lifecycle_status", "object_ref"],
            ascending=[False, True, True],
        ).reset_index(drop=True)
    return audit_df


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Reconcile offline training and prod cache statuses by model_id")
    parser.add_argument(
        "--models-csv",
        type=Path,
        default=Path("../local/models/training_workspace/models_enabled/model_list__models__short.csv"),
        help="Path to model list CSV",
    )
    parser.add_argument(
        "--batch-summary",
        type=Path,
        default=Path("../local/models/training_workspace/models_enabled/model_data_collection/batch_summary.json"),
        help="Path to batch summary JSON",
    )
    parser.add_argument(
        "--model-store-root",
        type=Path,
        default=Path("../local/models"),
        help="Root with per-model training artifacts",
    )
    parser.add_argument(
        "--mlruns-root",
        type=Path,
        default=Path("../local/mlruns"),
        help="MLflow local runs root",
    )
    parser.add_argument(
        "--tracking-uri",
        type=str,
        default="http://127.0.0.1:5050",
        help="MLflow tracking URI to resolve Production alias; set empty string to skip",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("../local/models/training_workspace/manual_reports/audit"),
        help="Directory where CSV/JSON outputs are written",
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()

    tracking_uri = args.tracking_uri.strip() if isinstance(args.tracking_uri, str) else ""
    tracking_uri = tracking_uri or None

    audit_df = build_audit_df(
        models_csv=args.models_csv,
        batch_summary=args.batch_summary,
        model_store_root=args.model_store_root,
        mlruns_root=args.mlruns_root,
        tracking_uri=tracking_uri,
    )

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    csv_path = output_dir / "model_reconciliation.csv"
    json_path = output_dir / "model_reconciliation.json"
    summary_path = output_dir / "model_reconciliation_summary.json"

    audit_df.to_csv(csv_path, index=False)
    json_path.write_text(audit_df.to_json(orient="records", force_ascii=False, indent=2), encoding="utf-8")

    summary = {
        "total_models": int(len(audit_df)),
        "mismatches": int(audit_df["mismatch_flag"].sum()) if not audit_df.empty else 0,
        "lifecycle_counts": (
            audit_df.groupby("lifecycle_status", dropna=False)["model_id"].count().to_dict()
            if not audit_df.empty
            else {}
        ),
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"total_models={summary['total_models']}")
    print(f"mismatches={summary['mismatches']}")
    print(f"csv={csv_path}")
    print(f"json={json_path}")
    print(f"summary={summary_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
