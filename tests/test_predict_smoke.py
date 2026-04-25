import os
import time

import requests


API_URL = os.getenv("PREDICT_API_URL", "http://localhost:18888/predict")
OBJECT_REFERENCE = "/KAZ/AKMOLA/AKMOLA/@models/P_WATT"
MODEL_ID = "prophet_watt_h_AKMOLA_test"


def _post_json(payload):
    response = requests.post(API_URL, json=payload, timeout=30)
    response.raise_for_status()
    return response.json()


def test_predict_smoke_start_processing_done():
    first = _post_json(
        {
            "object_reference": OBJECT_REFERENCE,
            "model_id": MODEL_ID,
        }
    )

    assert first["status"] == 202
    assert first["state"] == "start"
    assert first["object_reference"] == OBJECT_REFERENCE
    assert first["task_id"]

    task_id = first["task_id"]
    seen_processing = False
    final_response = None

    for _ in range(20):
        current = _post_json({"task_id": task_id})
        assert current["task_id"] == task_id

        if current["state"] == "processing":
            seen_processing = True
            time.sleep(0.2)
            continue

        assert current["state"] == "done"
        final_response = current
        break

    assert seen_processing, "expected at least one processing response"
    assert final_response is not None, "task did not reach done state in time"
    assert final_response["status"] == 200
    assert final_response["object_reference"] == OBJECT_REFERENCE

    data = final_response["data"]
    output = data["output"]

    assert data["quality"] == 0
    assert isinstance(output, list) and output
    assert all(len(row) == 3 for row in output)
    assert all(isinstance(row[0], int) and row[0] > 0 for row in output)
    assert all(isinstance(row[1], (int, float)) for row in output)
    assert all(row[2] == 0 for row in output)
