# Config logging
import logging
import os
import datetime
import json
import http
import environ
import uvicorn
import joblib
from fastapi import FastAPI, Request

from inference import extract_from_fp_record, predict, get_valid_filename, MES_TO_REGION

logging.basicConfig(
    format='%(asctime)s,%(msecs)d %(name)s %(levelname)s %(message)s',
    datefmt='%H:%M:%S',
    level=os.environ.get('LOGLEVEL', 'DEBUG'),
)
logger = logging.getLogger(__file__)

# Read environment variables
env = environ.Env()
environ.Env.read_env()

# Example of reading environment variables
model_name = env('MODEL_NAME')
model_type = env('MODEL_TYPE')
model_version = env('MODEL_VERSION')

app = FastAPI()

def init():

    normalizations = dict()
    model = None

    file_name = 'normalization.json'
    model_path = os.path.join('/workspace/model', file_name).lower()

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
    model_path = os.path.join('/workspace/model', file_name).lower()

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

    period = None   # number of timestamps to predict
    step = None     # how many seconds between timestamps
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
        task_message = f'Run task [{task_id}]'
        task_status = d["task_status"]
    except KeyError as e:
        task_status = "FAILED"
        task_message = f'Fail to parse incoming JSON object: {e}'
        task_message = f'Fail to parse incoming JSON object: {e}'
        logger.error(e)
        raise http.HTTPException(status_code=400, detail=task_message)
        raise http.HTTPException(status_code=400, detail=task_message)
    finally:
        r = {
            'task_id': task_id,
            'task_status': task_status,
            'task_message': task_message,
            'task_output': []
        }

    model, normalization = init()

    logger.debug(model)
    try:
        y, timestamps = extract_from_fp_record(d)
    except Exception as e:
        r['task_status'] = 'FAILED'
        r['task_message'] = f'task {task_id} Fail to extract data from income JSON'
        logger.error(e)
        return r
    
    input_range = len(y) # number of elements in the dataset
    try:
        y, timestamps = extract_from_fp_record(d)
    except Exception as e:
        r['task_status'] = 'FAILED'
        r['task_message'] = f'task {task_id} Fail to extract data from income JSON'
        logger.error(e)
        return r
    
    input_range = len(y) # number of elements in the dataset

    if len(y) == 0:
        r['task_status'] = 'FAILED'
        r['task_message'] = f'task {task_id} Data in the dataset is incorrect'
        return r
    if not model:
        preds = y[-period:]
        preds = y[-period:]
        r['task_message']=f'Not found the model by name: {model_name}, type: {model_type} and version: {model_version}'
    else:
        preds = predict(
            y=y,
            timestamps=timestamps,
            model=model,
            div=normalization['div'],
            sub=normalization['sub'],
            n_predict_steps=input_range
            n_predict_steps=input_range
        )[0]

    pred_timestamps = timestamps + input_range * step
    pred_timestamps = timestamps + input_range * step

    # Prepare response
    result = [[int(ts), float(p)] for ts, p in zip(pred_timestamps, preds)]

    logger.debug(f"len(result): {len(result)}")

    r['task_status'] = 'SUCCESS'
    r['task_output']= result

    logger.debug(f"Output: {r}")

    return r

if __name__ == "__main__":
    # Run server
    uvicorn.run(app, host="0.0.0.0", port=8000)
