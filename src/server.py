# Add lib/oik-new to path
# TODO: remove after fpforecast package is ready
import sys
import os
sys.path.insert(0, str(os.path.join(os.path.dirname(__file__), '..', 'lib', 'oik-new')))

# Config logging
import logging
import os

logging.basicConfig(
    format='%(asctime)s,%(msecs)d %(name)s %(levelname)s %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    level=os.environ.get('LOGLEVEL', 'INFO'),
)
logger = logging.getLogger(__file__)

import http
import asyncio
import uvicorn
import numpy as np
from fastapi import FastAPI, Request
from typing import List

from inference import predict, predict_default, get_full_days_mask
from utils import (
    extract_data, 
    init_model, 
    QDS_BASE,
    QDS_INCORRECT_INPUT,
    QDS_ERROR
)


app = FastAPI()

# Set maximum number of concurrent requests
try:
    MAX_CONCURRENT_REQUESTS = int(os.environ.get('MAX_CONCURRENT_REQUESTS', '8'))
except ValueError:
    MAX_CONCURRENT_REQUESTS = 8
    logger.warning(f"Invalid value for MAX_CONCURRENT_REQUESTS, using default: {MAX_CONCURRENT_REQUESTS}")
semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)


def check_sbre(y, timestamps):
    mask = get_full_days_mask(timestamps, offset_days=1)
    return not np.all(np.isnan(y[1][mask]))


async def _process_data(request: Request):
    logger.info("Request...")
    [d] = await request.json()
    logger.info(f"Request data: {d}")

    period = None   # number of timestamps to predict
    step = None     # how many seconds between timestamps
    task_id = None
    model_path = None
    task_message = ''
    task_status = None

    r = dict()

    try:
        step = d["step"]  # in seconds
        period = (d["period"] * 3600000) // d["step"]  # convert period from hours to number of timestamps
        task_id = d["task_id"]
        model_path = d.get("model_path", None)
        clip_negatives_to_0 = d.get("clip_negatives_to_0", True)
        online = model_path == 'none'
        task_message = f'Запущена задача с идентификатором [{task_id}]'
    except KeyError as e:
        task_status = "ОШИБКА"
        task_message = f'Ошибка парсинга входящего JSON'
        logger.error(e)
        raise http.HTTPException(status_code=400, detail=task_message)
    finally:
        r = {
            'task_id': task_id,
            'task_status': task_status,
            'task_message': task_message,
            'task_output': []
        }

    y, timestamps, qds = [], [], []
    for i in range(len(d['task_input'])):
        try:
            timestamps_, y_, qds_ = extract_data(d['task_input'][i], interpolate=not online)
            y.append(y_)
            timestamps.append(timestamps_)
            qds.append(qds_)
        except Exception as e:
            r['task_status'] = 'ОШИБКА'
            r['task_message'] = f'У задача с идентификатором {task_id} некорректные данные в датасете'
            logger.error(e)
            return r
    
    # Prepare base QDS for predictions
    # TODO: get QDS from model
    # - if the inputs are too different from training data, set corresponding bits
    base_pred_qds = QDS_BASE

    # Init model
    logger.info(f"Init model from path: {model_path}, step: {step}, online: {online}")
    model = init_model(model_path, step)
    if model is None:
        logger.warning(f"Cannot init model from path {model_path}, using online model instead")
        online = True
        base_pred_qds = QDS_ERROR
        model = init_model('none', step)

    logger.debug(f"len(y): {len(y)}, {[len(y_) for y_ in y]}")
    logger.debug(f"len(qds): {len(qds)}, {[len(qds_) for qds_ in qds]}")
    if (not model and not online):
        preds, pred_timestamps = predict_default(
            y=y,
            timestamps=timestamps,
        )
        base_pred_qds = QDS_ERROR
        r['task_status'] = 'ОШИБКА'
        r['task_message']=f'Ошибка инициализации, проверьте наличие файлов модели. Результат равен входным данным, наложенным на запрошенный выходной интервал.'
    else:
        try:
            preds, pred_timestamps = predict(
                y=y,
                timestamps=timestamps,
                model=model,
                step=step,
                output_range=period,
                online=online,
            )
        except Exception as e:
            r['task_status'] = 'ОШИБКА'
            r['task_message'] = f'Ошибка вызова прогноза для задачи с идентификатором {task_id}'
            base_pred_qds = QDS_ERROR
            logger.error(e)
            return r
    logger.info(preds)

    # Calculate output QDS & total QDS
    input_total_qds = QDS_BASE
    qds = np.array(qds)
    if (np.bitwise_or.reduce(qds.ravel()) & QDS_INCORRECT_INPUT) == QDS_INCORRECT_INPUT:
        input_total_qds = QDS_INCORRECT_INPUT  # At least one incorrect input
    if (
        (np.bitwise_and.reduce(qds.ravel()) & QDS_INCORRECT_INPUT) == QDS_INCORRECT_INPUT or
        (np.bitwise_or.reduce(qds.ravel()) & QDS_ERROR) == QDS_ERROR
    ):
        input_total_qds = QDS_ERROR  # All inputs incorrect or at least one error input
    
    total_qds = max(base_pred_qds, input_total_qds)
    result_qds = np.full_like(preds, total_qds, dtype=int)
    logger.info(f"total_qds: {total_qds}, result_qds: {result_qds}")

    # Clip negatives to 0 if needed
    if clip_negatives_to_0:
        preds = np.maximum(preds, 0)

    # Prepare response
    result = [[int(ts), round(float(p), 1), int(q)] for ts, p, q in zip(pred_timestamps, preds, result_qds)]

    # Replace nans with None
    for i in range(len(result)):
        if np.isnan(result[i][1]):
            result[i][1] = None

    logger.info(f'result: {result}')

    logger.info(f"len(result): {len(result)}")

    r['task_status'] = 'УСПЕШНО'
    r['state'] = {'quality': total_qds}
    r['task_output']= result

    logger.info(f"Output: {r}")

    return r


@app.post("/predict/")
async def process_data(request: Request):
    async with semaphore:
        return await _process_data(request)


if __name__ == "__main__":
    # Run server
    uvicorn.run(app, host="0.0.0.0", port=8000)
