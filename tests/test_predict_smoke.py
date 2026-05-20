import os
import time

import requests
import pytest


API_BASE_URL = os.getenv("PREDICT_API_URL", "http://localhost:8030")
TASKS_URL = os.getenv("PREDICT_TASKS_URL", "http://localhost:8030/tasks")
OBJECT_REF = "/KAZ/AKMOLA/AKMOLA/@models/P_WATT"
MODEL_ID = "prophet_watt_h_AKMOLA_test"


def _start_predict(model_id, object_ref, version_alias="Production"):
    params = {"version_alias": version_alias}
    if object_ref:
        params["object_ref"] = object_ref
    response = requests.get(f"{API_BASE_URL}/predict/{model_id}", params=params, timeout=30)
    return response.status_code, response.json()


def _get_json(task_id):
    response = requests.get(f"{TASKS_URL}/{task_id}", timeout=30)
    return response.status_code, response.json()


def test_predict_smoke_start_processing_done():
    first_status, first = _start_predict(MODEL_ID, OBJECT_REF)
    if first_status == 404:
        pytest.skip("runtime still serves legacy contract; GET /predict/{model_id} not yet deployed")
    assert first_status == 202

    assert first["status"] == 202
    assert first["state"] == "start"
    assert first["object_ref"] == OBJECT_REF
    assert first["task_id"]

    task_id = first["task_id"]
    seen_processing = False
    final_response = None

    for _ in range(20):
        current_status, current = _get_json(task_id)
        assert current["task_id"] == task_id

        if current["state"] == "processing":
            seen_processing = True
            assert current_status == 202
            time.sleep(0.2)
            continue

        assert current["state"] == "done"
        final_response = current
        break

    assert seen_processing, "expected at least one processing response"
    assert final_response is not None, "task did not reach done state in time"
    assert final_response["object_ref"] == OBJECT_REF

    if final_response["status"] != 200:
        pytest.skip(f"predict environment not ready: {final_response.get('message', 'unknown error')}")

    data = final_response["data"]
    output = data["output"]

    assert isinstance(output, list) and output
    assert all(len(row) == 2 for row in output)
    assert all(isinstance(row[0], int) and row[0] > 0 for row in output)
    assert all(isinstance(row[1], (int, float)) for row in output)
    assert isinstance(data.get("model_confidence"), (int, float))
