import sys
from pathlib import Path

from pydantic import ValidationError


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from api.data.predict import PredictCreateSchema


def test_predict_selector_defaults_to_production() -> None:
    payload = PredictCreateSchema(
        model_id="prophet_watt_h_AKMOLA_test",
        client_object_ref="/KAZ/AKMOLA/@models/P_WATT",
    )
    assert payload.selector == "Production"


def test_predict_selector_uses_alias() -> None:
    payload = PredictCreateSchema(
        model_id="prophet_watt_h_AKMOLA_test",
        client_object_ref="/KAZ/AKMOLA/@models/P_WATT",
        model_selection={"version_alias": "champion"},
    )
    assert payload.selector == "champion"


def test_predict_selector_uses_version() -> None:
    payload = PredictCreateSchema(
        model_id="prophet_watt_h_AKMOLA_test",
        client_object_ref="/KAZ/AKMOLA/@models/P_WATT",
        model_selection={"version": "17"},
    )
    assert payload.selector == "17"


def test_predict_selector_rejects_alias_and_version_together() -> None:
    try:
        PredictCreateSchema(
            model_id="prophet_watt_h_AKMOLA_test",
            client_object_ref="/KAZ/AKMOLA/@models/P_WATT",
            model_selection={"version": "17", "version_alias": "champion"},
        )
    except ValidationError:
        return
    raise AssertionError("Expected ValidationError when both version and version_alias are set")
