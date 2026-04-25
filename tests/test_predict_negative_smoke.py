import os
import time

import requests


API_URL = os.getenv("PREDICT_API_URL", "http://localhost:18888/predict")
OBJECT_REFERENCE = "/KAZ/AKMOLA/AKMOLA/@models/P_WATT"
MODEL_ID = "prophet_watt_h_AKMOLA_test"


def _post_json(payload):
    response = requests.post(API_URL, json=payload, timeout=30)
    return response.status_code, response.json()


def test_predict_smoke_historical_data_unavailable_returns_503_done():
    first_status, first = _post_json(
        {
            "object_reference": OBJECT_REFERENCE,
            "model_id": MODEL_ID,
        }
    )

    assert first_status == 202
    assert first["status"] == 202
    assert first["state"] == "start"
    assert first["object_reference"] == OBJECT_REFERENCE
    assert first["task_id"]

    task_id = first["task_id"]
    final_response = None

    for _ in range(20):
        current_status, current = _post_json({"task_id": task_id})
        assert current["task_id"] == task_id

        if current["state"] == "processing":
            assert current_status == 202
            time.sleep(0.2)
            continue

        assert current_status == 503
        assert current["state"] == "done"
        final_response = current
        break

    assert final_response is not None, "task did not reach done state in time"
    assert final_response["status"] == 503
    assert final_response["object_reference"] == OBJECT_REFERENCE
    assert "HISTORICAL_DATA is not available" in final_response["message"]