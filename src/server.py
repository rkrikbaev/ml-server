# Config logging
import logging
import os
import datetime
import json

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

def init():

    normalizations = dict()
    model = None

    file_name = 'normalization.json'
    model_path = os.path.join('/workspace/server/model', file_name).lower()

    logger.debug(f'Model normalization path: {model_path}')

    if os.path.exists(model_path):
        try:
            with open(model_path, 'r') as f:
                normalizations = json.load(f)  # Use json.load() to load JSON from a file
        except json.JSONDecodeError as e:
            logger.error(f"Error decoding JSON from {model_path}: {e}")
    else:
        logger.warning('Normalization not exist')

    file_name = 'model.joblib'
    model_path = os.path.join('/workspace/server/model', file_name).lower()

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

    [d] = await request.json()
    logger.debug(f"data as dict: {d}")

    model_name = None
    model_type = None
    model_version = None
    model_target = None
    model_input_range = None
    model_input_granularity = None
    task_id = None
    task_message = ''
    task_status = None

    r = dict()

    try:
        model_name = d["model_name"]
        model_type = d["model_type"]
        model_version = d["model_version"]
        model_target = d["model_target"]
        model_input_range = d["model_input_range"]
        model_input_granularity = d["model_input_granularity"]
        model_output_range = d["model_output_range"]
        task_id = d["task_id"]
        task_message = f'Run task [{task_id}]'
        task_status = d["task_status"]
    except KeyError as e:
        task_status = "FAILED"
        task_message = f'Fail to parse income JSON'
        logger.error(e)
    finally:
        r = {
            'task_id': task_id,
            'task_status': task_status,
            'task_message': task_message,
            'task_result': []
        }

    model, normalization = init()

    logger.debug(model)
    
    y, timestamps = extract_from_fp_record(d, model_target)

    if len(y) == 0:
        r['task_status'] = 'FAILED'
        r['task_message'] = f'task {task_id} Data in the dataset is incorrect'
        return r
    if not model:
        preds = y[-model_output_range:]
        r['task_message']=f'Not found the model by name: {model_name}, type: {model_type} and version: {model_version}. The result is income dataset applied on output time range'
    else:
        preds = predict(
            y=y,
            timestamps=timestamps,
            model=model,
            div=normalization['div'],
            sub=normalization['sub'],
            n_predict_steps=model_input_range
        )[0]

    pred_timestamps = timestamps + model_input_range * model_input_granularity

    # Prepare response
    result = [[int(ts), float(p)] for ts, p in zip(pred_timestamps, preds)]

    logger.debug(f"len(result): {len(result)}")

    r['task_status'] = 'SUCCESS'
    r['task_result']= result

    logger.debug(f"Output: {r}")

    return r

if __name__ == "__main__":
    # Run server
    uvicorn.run(app, host="0.0.0.0", port=8000)
