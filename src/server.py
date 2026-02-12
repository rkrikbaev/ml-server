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
from collections import Counter
from fastapi import FastAPI, Request

from inference import predict, predict_default, get_full_days_mask, get_last_past_index
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


# Short status codes for state['message']
STATUS_OK = "OK"
STATUS_INVALID_DATA = "DATA_FORMAT_ERROR"
STATUS_DATA_GAPS = "DATA_GAPS_WARNING"
STATUS_MODEL_FALLBACK = "MODEL_FALLBACK"
STATUS_EXECUTION_ERROR = "EXECUTION_ERROR"


def choose_status(total_qds: int, invalid_format: bool, execution_error: bool, model_fallback: bool, input_issue: bool) -> str:
    if execution_error:
        return STATUS_EXECUTION_ERROR
    if invalid_format:
        return STATUS_INVALID_DATA
    if model_fallback:
        return STATUS_MODEL_FALLBACK
    if input_issue or total_qds != QDS_BASE:
        return STATUS_DATA_GAPS
    return STATUS_OK


def append_message(current_message: str, new_message: str) -> str:
    if current_message:
        return current_message + '. ' + new_message
    else:
        return new_message


def count_errors(qds, y, timestamps):
    # Take into account only past values
    last_past_index = get_last_past_index(timestamps[0])

    qds = np.array(qds)[:, :last_past_index].ravel()
    y = np.array(y)[:, :last_past_index].ravel()
    
    qds_counts = Counter()

    qds_counts['CRITICAL'] = 0
    qds_counts['NON_CRITICAL'] = 0
    qds_counts['MISSING_QDS'] = 0
    qds_counts['MISSING_Y'] = 0
    qds_counts['NON_CRITICAL_OR_MISSING_Y'] = 0

    for q, y_current in zip(qds, y):
        # If at least one critical bit is set, count as critical
        for bit in QDS_CRITICAL_VALUES:
            if (q & bit) == bit:
                qds_counts['CRITICAL'] += 1
                break

        # If at least one non-critical bit is set, count as non-critical
        for bit in QDS_NONCRITICAL_VALUES:
            if (q & bit) == bit:
                qds_counts['NON_CRITICAL'] += 1
                break
    
        # Count missing QDS values
        if q == QDS_MISSING_QDS_VALUE:
            qds_counts['MISSING_QDS'] += 1

        # Count missing y values
        if np.isnan(y_current):
            qds_counts['MISSING_Y'] += 1
        
        # Count non-critical or missing y values
        if any((q & bit) == bit for bit in QDS_NONCRITICAL_VALUES) or np.isnan(y_current):
            qds_counts['NON_CRITICAL_OR_MISSING_Y'] += 1

    return qds_counts, qds.shape[0]


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
    invalid_format = False
    execution_error = False
    model_fallback = False
    input_issue = False

    r = dict()

    try:
        step = d["step"]  # in seconds
        period = (d["period"] * 3600000) // d["step"]  # convert period from hours to number of timestamps
        task_id = d["task_id"]
        model_path = d.get("model_path", None)
        clip_negatives_to_0 = d.get("clip_negatives_to_0", True)
        online = model_path == 'none'
        # task_message = append_message(task_message, f'Task started with ID [{task_id}]')
    except KeyError as e:
        task_status = "ОШИБКА"
        task_message = 'Failed to parse input data'
        # task_message = append_message(task_message, f'Failed to parse input JSON')
        logger.error(e)
        raise http.HTTPException(status_code=400, detail=task_message)
    finally:
        r = {
            'task_id': task_id,
            'task_status': task_status,
            'task_message': task_message,
            'task_output': [],
            'state': {'quality': QDS_ERROR},
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
            invalid_format = True
            r['task_message'] = 'Invalid input dataset format'
            # r['task_message'] = append_message(r['task_message'], f'Invalid dataset for task with ID {task_id}')
            r['state'] = {'quality': QDS_ERROR, 'message': choose_status(QDS_ERROR, invalid_format, False, False, False)}
            # previous behaviour: return full verbose task message in state
            # r['state'] = {'quality': QDS_ERROR, 'message': r['task_message']}
            logger.error(e)
            return r
    
    # Count QDS errors and set input quality level
    qds_counts, n_qds = count_errors(qds, y, timestamps)
    critical_input_freq = qds_counts['CRITICAL'] / n_qds
    non_critical_input_freq = qds_counts['NON_CRITICAL_OR_MISSING_Y'] / n_qds
    
    input_total_qds = QDS_BASE

    if non_critical_input_freq >= NONCRITICAL_THRESHOLD_TO_SET_ERROR:
        r['task_message'] = append_message(
            r['task_message'],
            f'Multiple errors or gaps in {non_critical_input_freq*100:.1f}% of input data (QDS={QDS_ERROR})'

            # f'Input data contains critical errors (QDS {QDS_NONCRITICAL_VALUES} bits set or missing Y values in {non_critical_input_freq*100:.1f}% '
            # f'of input points, which is above or equal '
            # f'to the acceptable threshold {NONCRITICAL_THRESHOLD_TO_SET_ERROR*100:.1f}%). '
            # f'QDS elevated from {input_total_qds} to {QDS_ERROR}'
        )
        input_total_qds = max(input_total_qds, QDS_ERROR)
        input_issue = True
    elif non_critical_input_freq >= NON_CRITICAL_THRESHOLD_TO_SET_INCORRECT:
        r['task_message'] = append_message(
            r['task_message'],
            f'Errors or gaps in {non_critical_input_freq*100:.1f}% of input data (QDS={QDS_INCORRECT_INPUT})'
            # f'Input data contains non-critical errors (QDS {QDS_NONCRITICAL_VALUES} bits set or missing Y values in {non_critical_input_freq*100:.1f}% '
            # f'of input points, which is above or equal '
            # f'to the acceptable threshold {NON_CRITICAL_THRESHOLD_TO_SET_INCORRECT*100:.1f}%). '
            # f'QDS elevated from {input_total_qds} to {QDS_INCORRECT_INPUT}'
        )
        input_total_qds = max(input_total_qds, QDS_INCORRECT_INPUT)
        input_issue = True
    
    if critical_input_freq >= CRITICAL_THRESHOLD_TO_SET_ERROR:
        r['task_message'] = append_message(
            r['task_message'],
            f'Critical errors in {critical_input_freq*100:.1f}% of input data (QDS={QDS_ERROR})'
            # f'Input data contains critical errors (QDS {QDS_CRITICAL_VALUES} bits set in {critical_input_freq*100:.1f}% of input points, which is above or equal '
            # f'to the acceptable threshold {CRITICAL_THRESHOLD_TO_SET_ERROR*100:.1f}%). '
            # f'QDS elevated from {input_total_qds} to {QDS_ERROR}'
        )
        input_total_qds = max(input_total_qds, QDS_ERROR)
        input_issue = True

    # if input_total_qds != QDS_BASE:
    #     r['task_message'] = append_message(
    #         r['task_message'], 
    #         f'Total input points: {n_qds}, '
    #         f'input QDS counts: {dict(qds_counts)}.'
    #     )
        
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
        base_pred_qds = max(base_pred_qds, QDS_ERROR)
        model_fallback = True
        r['task_message'] = append_message(r['task_message'], f'Model loading error, using online model (QDS={QDS_ERROR})')
        #r['task_message'] = append_message(r['task_message'], f'Online model is used due to model initialization error at path {model_path}')
        model = init_model('none', step)

    logger.debug(f"len(y): {len(y)}, {[len(y_) for y_ in y]}")
    logger.debug(f"len(qds): {len(qds)}")
    
    is_matching = True  # По умолчанию считаем, что данные соответствуют
    
    if (not model and not online):
        preds, pred_timestamps = predict_default(
            y=y,
            timestamps=timestamps,
        )
        base_pred_qds = max(base_pred_qds, QDS_ERROR)
        r['task_status'] = 'ОШИБКА'
        r['task_message'] = append_message(r['task_message'], f'Critical model initialization error (QDS={QDS_ERROR}). Result = input data on requested interval')
        #r['task_message'] = append_message(r['task_message'], f'Model initialization error, check model files. Result equals input data mapped to the requested output interval')
    else:
        try:
            preds, pred_timestamps, is_matching = predict(
                y=y,
                timestamps=timestamps,
                model=model,
                step=step,
                output_range=period,
                online=online,
            )
        except Exception as e:
            r['task_status'] = 'ОШИБКА'
            execution_error = True
            r['task_message'] = append_message(r['task_message'], f'Forecast execution error')
            #r['task_message'] = append_message(r['task_message'], f'Forecast call error for task with ID {task_id}')
            r['state'] = {'quality': QDS_ERROR, 'message': choose_status(QDS_ERROR, False, execution_error, False, False)}
            # previous behaviour: return full verbose task message in state
            # r['state'] = {'quality': QDS_ERROR, 'message': r['task_message']}
            base_pred_qds = QDS_ERROR
            logger.error(e)
            return r

    # Если модель посчитала, что входы не соответствуют обучающей выборке — пометим прогноз как некорректный (NT / 64)
    # Используем max, чтобы не понижать уже установленный более высокий уровень ошибки
    if not is_matching:
        base_pred_qds = max(base_pred_qds, QDS_INCORRECT_INPUT)
        r['task_message'] = append_message(r['task_message'], f'Data does not match training distribution (QDS={QDS_INCORRECT_INPUT})')
    logger.info(preds)
    
    # Calculate total QDS
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
    # r['state'] = {'quality': total_qds}
    #вернуть ок если нет ошибок, иначе вернуть сообщение об ошибке и код ошибки
     # If QDS is 0 and no message, return 'OK'
    if total_qds == QDS_BASE and not r['task_message']:
        r['task_message'] = 'OK'
    status = choose_status(total_qds, invalid_format, execution_error, model_fallback, input_issue)
    r['state'] = {'quality': total_qds, 'message': status}
    # previous behaviour: expose full verbose task message in state
    # r['state'] = {'quality': total_qds, 'message': r['task_message']}
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