# Config logging
import logging
import os

logging.basicConfig(
    format='%(asctime)s,%(msecs)d %(name)s %(levelname)s %(message)s',
    datefmt='%H:%M:%S',
    level=os.environ.get('LOGLEVEL', 'INFO'),
)
logger = logging.getLogger(__file__)

import http
import asyncio
import uvicorn
import numpy as np
from fastapi import FastAPI, Request

from inference import init_model, predict, predict_default, get_full_days_mask
from utils import extract_data


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
        period = (d["period"] * 3600) // d["step"]  # convert period from hours to number of timestamps
        task_id = d["task_id"]
        model_path = d.get("model_path", None)
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

    y, timestamps = [], []
    for i in range(len(d['task_input'])):
        try:
            y_, timestamps_ = extract_data(d['task_input'][i], interpolate=not online)
            y.append(y_)
            timestamps.append(timestamps_)
        except Exception as e:
            r['task_status'] = 'ОШИБКА'
            r['task_message'] = f'У задача с идентификатором {task_id} некорректные данные в датасете'
            logger.error(e)
            return r
    
    # Try to use sbre if possible
    if step == 3600 and len(y) >= 2:
        if check_sbre(y, timestamps):
            logger.info("Using sbre model")
            online = False
            model_path = 'sbre'

    # Try to init model by path
    if model_path not in ['none', 'sbre']:
        m, _ = init_model(model_path, step)
        if m is None:
            logger.warning(f"Cannot init model from path {model_path}, using online model instead")
            online = True
            model_path = 'none'

    # Init actual model
    logger.info(f"Init model from path: {model_path}, step: {step}, online: {online}")
    model, normalization = init_model(model_path, step)

    logger.debug(f"len(y): {len(y)}, {[len(y_) for y_ in y]}")

    if (not model and not online):
        preds, pred_timestamps = predict_default(
            y=y,
            timestamps=timestamps,
        )
        r['task_status'] = 'ОШИБКА'
        r['task_message']=f'Ошибка инициализации, проверьте наличие файлов модели. Результат равен входным данным, наложенным на запрошенный выходной интервал.'
    else:
        try:
            preds, pred_timestamps = predict(
                y=y,
                timestamps=timestamps,
                model=model,
                normalization=normalization,
                step=step,
                output_range=period,
                online=online,
            )
        except Exception as e:
            r['task_status'] = 'ОШИБКА'
            r['task_message'] = f'Ошибка вызова прогноза для задачи с идентификатором {task_id}'
            logger.error(e)
            return r
    logger.info(preds)

    # Prepare response
    # result = [[int(ts), f'{float(p):.1f}'] for ts, p in zip(pred_timestamps, preds)]
    result = [[int(ts), round(float(p), 1)] for ts, p in zip(pred_timestamps, preds)]

    # Replace nans with None
    for i in range(len(result)):
        if np.isnan(result[i][1]):
            result[i][1] = None

    logger.info(f'result: {result}')

    logger.info(f"len(result): {len(result)}")

    r['task_status'] = 'УСПЕШНО'
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
