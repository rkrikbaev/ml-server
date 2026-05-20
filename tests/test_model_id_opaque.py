import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


from api import task_monitor


def test_infer_model_type_does_not_parse_model_id_without_config(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(task_monitor, "MODELS_PATH", tmp_path)

    # model_id looks parseable, but must be treated as opaque.
    inferred = task_monitor._infer_model_type("prophet/watt/h/AKMOLA")

    assert inferred == "unknown"


def test_record_task_created_uses_model_type_from_config(monkeypatch, tmp_path) -> None:
    model_id = "prophet_watt_h_AKMOLA_test"
    model_dir = tmp_path / model_id
    model_dir.mkdir(parents=True, exist_ok=True)
    (model_dir / "config_unified.yaml").write_text("model_type: prophet\n", encoding="utf-8")

    monkeypatch.setattr(task_monitor, "MODELS_PATH", tmp_path)
    task_monitor._TASKS.clear()

    task_monitor.record_task_created(
        task_id="task-model-id-opaque",
        object_ref="/KAZ/AKMOLA/@models/P_WATT",
        model_id=model_id,
    )

    task = task_monitor.get_task("task-model-id-opaque")

    assert task is not None
    assert task["model_id"] == model_id
    assert task["model_type"] == "prophet"
