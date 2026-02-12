# Add lib/oik-new to path
# TODO: remove after fpforecast package is ready
import sys
import os
sys.path.insert(0, str(os.path.join(os.path.dirname(__file__), '..', 'lib', 'oik-new')))

# =======================
# Logging
# =======================
import logging

logging.basicConfig(
    format='%(asctime)s,%(msecs)d %(name)s %(levelname)s %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    level=os.environ.get('LOGLEVEL', 'INFO'),
)
logger = logging.getLogger(__file__)

# =======================
# Imports
# =======================
import http
import asyncio
import uvicorn
import numpy as np
from collections import Counter
from fastapi import FastAPI, Request

from inference import predict, predict_default, get_last_past_index
from utils import (
    extract_data,
    init_model,
    QDS_BASE,
    QDS_INCORRECT_INPUT,
    QDS_ERROR,
    QDS_CRITICAL_VALUES,
    QDS_NONCRITICAL_VALUES,
    NON_CRITICAL_THRESHOLD_TO_SET_INCORRECT,
    CRITICAL_THRESHOLD_TO_SET_ERROR,
    NONCRITICAL_THRESHOLD_TO_SET_ERROR,
    QDS_MISSING_QDS_VALUE,
)

# =======================
# FastAPI
# =======================
app = FastAPI()

# =======================
# Concurrency limit
# =======================
# Set maximum number of concurrent requests
try:
    MAX_CONCURRENT_REQUESTS = int(os.environ.get('MAX_CONCURRENT_REQUESTS', '8'))
except ValueError:
    MAX_CONCURRENT_REQUESTS = 8
    logger.warning(f"Invalid value for MAX_CONCURRENT_REQUESTS, using default: {MAX_CONCURRENT_REQUESTS}")
semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)


# =======================
# Status codes
# =======================
STATUS_OK = "OK"
STATUS_DATA_FORMAT_ERROR = "DATA_FORMAT_ERROR"
STATUS_EXECUTION_ERROR = "EXECUTION_ERROR"
STATUS_MODEL_FALLBACK = "MODEL_FALLBACK"
STATUS_DATA_MISMATCH = "DATA_MISMATCH"
STATUS_DATA_GAPS = "DATA_GAPS_WARNING"

# =======================
# QDS evaluation
# =======================
def count_input_qds(qds, y, timestamps):
    last_past_index = get_last_past_index(timestamps[0])

    qds = np.array(qds)[:, :last_past_index].ravel()
    y = np.array(y)[:, :last_past_index].ravel()

    total = len(qds)
    critical = 0
    non_critical_or_missing = 0

    for q, yv in zip(qds, y):
        if any((q & bit) == bit for bit in QDS_CRITICAL_VALUES):
            critical += 1
        if any((q & bit) == bit for bit in QDS_NONCRITICAL_VALUES) or np.isnan(yv):
            non_critical_or_missing += 1

    return (
        critical / total if total else 0.0,
        non_critical_or_missing / total if total else 0.0,
    )


def evaluate_input_quality(critical_freq, non_critical_freq):
    if critical_freq >= CRITICAL_THRESHOLD_TO_SET_ERROR:
        return (
            QDS_ERROR,
            STATUS_DATA_GAPS,
            f"Critical errors in {critical_freq*100:.1f}% of input data (QDS={QDS_ERROR})",
        )

    if non_critical_freq >= NONCRITICAL_THRESHOLD_TO_SET_ERROR:
        return (
            QDS_ERROR,
            STATUS_DATA_GAPS,
            f"Multiple errors or gaps in {non_critical_freq*100:.1f}% of input data (QDS={QDS_ERROR})",
        )

    if non_critical_freq >= NON_CRITICAL_THRESHOLD_TO_SET_INCORRECT:
        return (
            QDS_INCORRECT_INPUT,
            STATUS_DATA_GAPS,
            f"Errors or gaps in {non_critical_freq*100:.1f}% of input data (QDS={QDS_INCORRECT_INPUT})",
        )

    return QDS_BASE, None, None


# =======================
# Core logic
# =======================
async def _process_data(request: Request):
    logger.info("Request received")

    # -------- default response skeleton
    response = {
        "task_id": None,
        "task_status": "ОШИБКА",
        "task_output": [],
        "state": {
            "quality": QDS_ERROR,
            "message": STATUS_EXECUTION_ERROR,
        },
    }

    # -------- parse request
    try:
        [payload] = await request.json()
        step = payload["step"]
        period = (payload["period"] * 3600000) // step
        task_id = payload["task_id"]
        model_path = payload.get("model_path")
        clip_negatives_to_0 = payload.get("clip_negatives_to_0", True)
        online = model_path == "none"
        response["task_id"] = task_id
    except Exception as e:
        logger.error(e)
        response["state"]["message"] = f"{STATUS_DATA_FORMAT_ERROR}: Invalid input JSON"
        return response

    # -------- extract input data
    y, timestamps, qds = [], [], []
    try:
        for item in payload["task_input"]:
            ts, yv, qv = extract_data(item, interpolate=not online)
            timestamps.append(ts)
            y.append(yv)
            qds.append(qv)
    except Exception as e:
        logger.error(e)
        response["state"]["message"] = f"{STATUS_DATA_FORMAT_ERROR}: Invalid input dataset format"
        return response

    # -------- input QDS evaluation
    critical_freq, non_critical_freq = count_input_qds(qds, y, timestamps)
    input_qds, input_status, input_reason = evaluate_input_quality(
        critical_freq, non_critical_freq
    )

    # -------- model init
    base_pred_qds = QDS_BASE
    status = STATUS_OK
    reason = None

    model = init_model(model_path, step)
    if model is None:
        model = init_model("none", step)
        online = True
        base_pred_qds = QDS_ERROR
        status = STATUS_MODEL_FALLBACK
        reason = "Model loading error, using online model (QDS=128)"

    # -------- prediction
    try:
        preds, pred_ts, is_matching = predict(
            y=y,
            timestamps=timestamps,
            model=model,
            step=step,
            output_range=period,
            online=online,
        )
    except Exception as e:
        logger.error(e)
        response["state"]["message"] = f"{STATUS_EXECUTION_ERROR}: Forecast execution error"
        return response

    # -------- distribution mismatch
    if not is_matching and status == STATUS_OK:
        base_pred_qds = max(base_pred_qds, QDS_INCORRECT_INPUT)
        status = STATUS_DATA_MISMATCH
        reason = "Input data does not match training distribution (QDS=64)"

    # -------- input issues (only if no higher-priority status)
    if status == STATUS_OK and input_status:
        status = input_status
        reason = input_reason

    # -------- final QDS
    final_qds = max(base_pred_qds, input_qds)

    # -------- post-processing
    if clip_negatives_to_0:
        preds = np.maximum(preds, 0)

    result = [
        [int(ts), None if np.isnan(p) else round(float(p), 1), int(final_qds)]
        for ts, p in zip(pred_ts, preds)
    ]

    # -------- finalize response
    response["task_status"] = "УСПЕШНО"
    response["task_output"] = result
    # For OK status return empty message, otherwise include status and reason
    if status == STATUS_OK:
        msg = ""
    else:
        msg = f"{status}: {reason}" if reason else status
    response["state"] = {"quality": final_qds, "message": msg}

    return response


@app.post("/predict/")
async def process_data(request: Request):
    async with semaphore:
        return await _process_data(request)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
