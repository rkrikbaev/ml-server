# Config logging
import logging
import os
import datetime
import json
import http
import uvicorn
import joblib
from fastapi import FastAPI, Request

from inference import extract_data, predict, get_valid_filename, MES_TO_REGION

logging.basicConfig(
    format='%(asctime)s,%(msecs)d %(name)s %(levelname)s %(message)s',
    datefmt='%H:%M:%S',
    level=os.environ.get('LOGLEVEL', 'DEBUG'),
)
logger = logging.getLogger(__file__)

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
        task_message = f'Run task [{task_id}]'
    except KeyError as e:
        task_status = "FAILED"
        task_message = f'Fail to parse incoming JSON object: {e}'
        logger.error(e)
        raise http.HTTPException(status_code=400, detail=task_message)
    finally:
        r = {
            'task_id': task_id,
            'task_status': task_status,
            'task_message': task_message,
            'task_output': []
        }

    model, normalization = init()

    y, timestamps = [], []
    for i in range(len(d['task_input'])):
        try:
            y_, timestamps_ = extract_data(d['task_input'][i])
            logger.info(f"y: {y}, ts: {timestamps}")
            y.append(y_)
            timestamps.append(timestamps_)
        except Exception as e:
            r['task_status'] = 'FAILED'
            r['task_message'] = f'task {task_id} Fail to extract data from income JSON'
            logger.error(e)
            return r
    
    if len(y) != len(timestamps):
        r['task_status'] = 'FAILED'
        r['task_message'] = f'task {task_id} Data in the dataset is incorrect'
        return r
    
    input_range = len(y[0]) # number of elements in the dataset

    if not model:
        preds = y[0][-period:]
        r['task_message']=f'Not found the model by name'
    else:
        preds = predict(
            y=y[0],
            timestamps=timestamps[0],
            model=model,
            div=normalization['div'],
            sub=normalization['sub'],
            n_predict_steps=input_range
        )[0]
    logger.info(preds)
    # Construct pred_timestamps as a list
    pred_timestamps = [timestamps[0][-1] + i * step for i in range(1,period+1)]
    # Prepare response
    result = [[int(ts), float(p)] for ts, p in zip(pred_timestamps, preds)]
    #pred_timestamps = timestamps[0] + input_range * step

    # Prepare response
    #result = [[int(ts), float(p)] for ts, p in zip(pred_timestamps, preds)]

    r['task_status'] = 'SUCCESS'
    r['task_output']= result

    logger.info(f"Output: {r}")

    return r

if __name__ == "__main__":
    # Run server
    uvicorn.run(app, host="0.0.0.0", port=8000)
