"""
Normalize model-list CSV files by expanding configuration JSON into flat columns.

For each row, only the section that matches the row's "horizont key" is used.

Usage:
    python scripts/normalize_model_list_configuration.py \
        --input ../local/model_list__models__short.csv \
        --input ../local/model_list__models__med.csv \
        --input ../local/model_list__models__long.csv
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import pandas as pd


def _parse_json_cell(raw: Any) -> dict[str, Any]:
    if raw is None or (isinstance(raw, float) and math.isnan(raw)):
        return {}
    text = str(raw).strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {}


def _normalize_row(row: pd.Series) -> dict[str, Any]:
    config = _parse_json_cell(row.get("_config_raw"))
    horizon_key = str(row.get("horizont key", "")).strip().lower()

    section = config.get(horizon_key) if isinstance(config, dict) else None
    if not isinstance(section, dict):
        section = {}

    return {
        "horizon_key": horizon_key,
        "input_range": section.get("input_range"),
        "output_range": section.get("output_range"),
        "step": section.get("step"),
        "model_path": section.get("model_path"),
        "units": config.get("units") if isinstance(config, dict) else None,
    }


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

    raise ValueError("Could not detect configuration JSON column")


def normalize_file(path: Path, output: Path | None = None, drop_json: bool = False) -> Path:
    df = pd.read_csv(path)
    required = {"horizont key"}
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"{path}: missing required columns: {sorted(missing)}")

    config_column = _detect_configuration_column(df)
    df = df.copy()
    df["_config_raw"] = df[config_column]

    # # Re-runs should replace cfg_* columns instead of appending duplicates.
    # existing_cfg = [col for col in df.columns if str(col).startswith("cfg_")]
    # if existing_cfg:
    #     df = df.drop(columns=existing_cfg)

    expanded = df.apply(_normalize_row, axis=1, result_type="expand")
    result = pd.concat([df.drop(columns=["_config_raw"]), expanded], axis=1)

    if drop_json and config_column in result.columns:
        result = result.drop(columns=[config_column])

    out_path = output or path
    result.to_csv(out_path, index=False, encoding="utf-8")
    return out_path


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Normalize model-list configuration JSON into flat columns")
    parser.add_argument("--input", action="append", required=True, type=Path, help="Input CSV path")
    parser.add_argument(
        "--suffix",
        type=str,
        default="",
        help="Optional suffix for output file name (e.g. _normalized). Empty means overwrite input.",
    )
    parser.add_argument(
        "--drop-json",
        action="store_true",
        help="Drop the original JSON configuration column from output.",
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()

    for in_path in args.input:
        if args.suffix:
            out_path = in_path.with_name(f"{in_path.stem}{args.suffix}{in_path.suffix}")
        else:
            out_path = in_path
        written = normalize_file(in_path, out_path, drop_json=args.drop_json)
        print(f"normalized: {in_path} -> {written}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
