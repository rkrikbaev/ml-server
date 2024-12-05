# Config logging
import logging
import os
import http
import uvicorn
from fastapi import FastAPI, Request

from inference import init_model, predict, predict_default
from utils import extract_data


logging.basicConfig(
    format='%(asctime)s,%(msecs)d %(name)s %(levelname)s %(message)s',
    datefmt='%H:%M:%S',
    level=os.environ.get('LOGLEVEL', 'DEBUG'),
)
logger = logging.getLogger(__file__)

app = FastAPI()

@app.post("/predict/")
async def process_data(request: Request):
    logger.info("Request...")
    [d] = await request.json()
    logger.info(f"Request data: {d}")

    period = None   # number of timestamps to predict
    step = None     # how many seconds between timestamps
    task_id = None
    task_message = ''
    task_status = None

    r = dict()

    try:
        step = d["step"] #model_input_granularity
        period = d["period"]  #model_output_range
        task_id = d["task_id"]
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

    model, normalization = init_model()

    y, timestamps = [], []
    for i in range(len(d['task_input'])):
        try:
            y_, timestamps_ = extract_data(d['task_input'][i])
            y.append(y_)
            timestamps.append(timestamps_)
        except Exception as e:
            r['task_status'] = 'ОШИБКА'
            r['task_message'] = f'У задача с идентификатором {task_id} некорректные данные в датасете'
            logger.error(e)
            return r
    
    logger.debug(f"len(y): {len(y)}")

    if not model:
        r['task_message']=f'Not found the model by name'
        preds, pred_timestamps = predict_default(
            y=y,
            timestamps=timestamps,
            n_predict_steps=period,
            step_granularity_s=step,
        )
        r['task_message']=f'Ошибка инициализации, проверьте наличие файлов модели. Результат равен входным данным, наложенным на запрошенный выходной интервал.'
    else:
        try:
            preds, pred_timestamps = predict(
                y=y,
                timestamps=timestamps,
                model=model,
                div=normalization['div'],
                sub=normalization['sub'],
                n_predict_steps=period,
                step_granularity_s=step,
            )[0]
        except Exception as e:
            r['task_status'] = 'ОШИБКА'
            r['task_message'] = f'Ошибка вызова прогноза для задачи с идентификатором {task_id}'
            logger.error(e)
            return r
    logger.info(preds)
    # Construct pred_timestamps as a list
    pred_timestamps = [timestamps[0][-1] + i * step for i in range(1,period+1)]
    # Prepare response
    result = [[int(ts), float(p)] for ts, p in zip(pred_timestamps, preds)]

    logger.info(f"len(result): {len(result)}")

    r['task_status'] = 'УСПЕШНО'
    r['task_output']= result

    logger.info(f"Output: {r}")

    return r

if __name__ == "__main__":
    # Run server
    uvicorn.run(app, host="0.0.0.0", port=8000)
