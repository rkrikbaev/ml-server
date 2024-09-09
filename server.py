# Config logging
import logging
import os
import datetime

logging.basicConfig(
    format='%(asctime)s,%(msecs)d %(name)s %(levelname)s %(message)s',
    datefmt='%H:%M:%S',
    level=os.environ.get('LOGLEVEL', 'DEBUG'),
)
logger = logging.getLogger(__file__)

import uvicorn
import joblib
from fastapi import FastAPI, Request

from inference import extract_from_fp_record, predict, get_valid_filename, MES_TO_REGION

app = FastAPI()

def init(model_name, model_type, model_version):

    normalizations = dict()
    model = None
    
    file_name = 'normalization.joblib'
    model_path = os.path.join('models', model_name, model_type, model_version, file_name).lower()
    logger.debug(f'Model normalization path: {model_path}')
    if os.path.exists(model_path):
        normalizations = joblib.load(model_path)
    else:
        logger.warning('Normalization not exist')

    file_name = 'model.joblib'
    model_path = os.path.join('models', model_name, model_type, model_version, file_name).lower()
    logger.debug(f'Model path: {model_path}')
    if os.path.exists(model_path):
        model = joblib.load(model_path)
    else:
        logger.warning('Model not exist')
    
    logger.debug(f'model object: {model}')
    logger.debug(f'normalization object: {normalizations}')

    return model, normalizations

@app.post("/predict/")
async def process_data(request: Request):

    d = await request.json()
    logger.debug(f"data_dict: {d}")

    task_status = None
    model_name = None
    model_object = None
    model_type = None
    model_version = None
    goal_param = None
    period = None
    step = None
    task_id = None

    r = dict()

    try:
        model_name = d["model_name"]
        model_object = d["model_object"]
        model_type = d["model_type"]
        model_version = d["model_version"]
        goal_param = d["goal_param"]
        period = d["period"]
        step = d["step"]
        task_id = d["task_id"]
        task_status = d["task_status"]

        r = {
            'task_status': task_status,
            'task_id': task_id,
            'model_object': model_object
        }

    except KeyError as e:
        logger.error(e)

    if task_status == "QUEUED":

        model, normalization = init(model_name, model_type, model_version)

        logger.info(model)
        
        y, timestamps = extract_from_fp_record(d, goal_param)

        if not model:
            preds = y[-period:]
        else:
            preds = predict(
                y=y,
                timestamps=timestamps,
                model=model,
                div=normalization['div'],
                sub=normalization['sub'],
                n_predict_steps=period
            )[0]

        pred_timestamps = timestamps + period * step

        # Prepare response
        result = [[int(ts), float(p)] for ts, p in zip(pred_timestamps, preds)]

        logger.debug(f"result: {result}")
        logger.debug(f"len(result): {len(result)}")

        r['task_status'] = 'SUCCESS'
        r['result']= result
        r['task_updated'] = datetime.datetime.today()

    return r

if __name__ == "__main__":
    # Run server
    uvicorn.run(app, host="0.0.0.0", port=8000)