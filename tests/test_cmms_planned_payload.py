import sys
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


from api.collector.cmms_client import CMMSClient


def _to_ms(iso_utc: str) -> int:
    return int(datetime.fromisoformat(iso_utc).replace(tzinfo=UTC).timestamp() * 1000)


def test_parse_planned_series_maps_intervals_to_quantized_points() -> None:
    payload = {
        "0704011504": [
            {
                "p_station": 1688,
                "p_descent": 325,
                "start_requested": _to_ms("2026-04-24T10:00:00"),
                "end_requested": _to_ms("2026-04-24T13:00:00"),
            }
        ]
    }

    parsed = CMMSClient.parse_planned_series(
        payload=payload,
        from_ms=_to_ms("2026-04-24T09:00:00"),
        to_ms=_to_ms("2026-04-24T14:00:00"),
        step_seconds=3600,
        equipment_type="0704011504",
    )

    assert parsed == {
        _to_ms("2026-04-24T10:00:00"): 325.0,
        _to_ms("2026-04-24T11:00:00"): 325.0,
        _to_ms("2026-04-24T12:00:00"): 325.0,
        _to_ms("2026-04-24T13:00:00"): 325.0,
    }


def test_parse_planned_series_sums_overlapping_events() -> None:
    payload = {
        "0704011504": [
            {
                "p_station": 1688,
                "p_descent": 100,
                "start_requested": _to_ms("2026-04-24T10:00:00"),
                "end_requested": _to_ms("2026-04-24T12:00:00"),
            },
            {
                "p_station": 1688,
                "p_descent": 25,
                "start_requested": _to_ms("2026-04-24T11:00:00"),
                "end_requested": _to_ms("2026-04-24T12:00:00"),
            },
        ]
    }

    parsed = CMMSClient.parse_planned_series(
        payload=payload,
        from_ms=_to_ms("2026-04-24T10:00:00"),
        to_ms=_to_ms("2026-04-24T12:00:00"),
        step_seconds=3600,
        equipment_type="0704011504",
    )

    assert parsed == {
        _to_ms("2026-04-24T10:00:00"): 100.0,
        _to_ms("2026-04-24T11:00:00"): 125.0,
        _to_ms("2026-04-24T12:00:00"): 125.0,
    }


def test_parse_planned_series_filters_other_equipment() -> None:
    payload = {
        "other": [
            {
                "p_station": 1,
                "p_descent": 50,
                "start_requested": _to_ms("2026-04-24T10:00:00"),
                "end_requested": _to_ms("2026-04-24T11:00:00"),
            }
        ]
    }

    parsed = CMMSClient.parse_planned_series(
        payload=payload,
        from_ms=_to_ms("2026-04-24T10:00:00"),
        to_ms=_to_ms("2026-04-24T11:00:00"),
        step_seconds=3600,
        equipment_type="0704011504",
    )

    assert parsed == {}


def test_parse_planned_series_rejects_non_object_payload() -> None:
    payload = [[_to_ms("2026-04-24T10:00:00"), 10.0]]

    parsed = CMMSClient.parse_planned_series(
        payload=payload,
        from_ms=_to_ms("2026-04-24T10:00:00"),
        to_ms=_to_ms("2026-04-24T11:00:00"),
        step_seconds=3600,
        equipment_type="0704011504",
    )

    assert parsed == {}
