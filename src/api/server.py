# Mariya Polkovnikova
# 2026.03.10, 04:18 PM


from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Body
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError, HTTPException

from api.utils import get_fields
from .broker import broker, api_predict
from .data import PredictCreateSchema, PredictSchema
from .message import HTTPState, HTTPMessages


@asynccontextmanager
async def lifespan(app: FastAPI):
    await broker.startup()
    yield
    await broker.shutdown()

app = FastAPI(lifespan=lifespan)
messages = HTTPMessages()


# --- ERRORS ---

# 404
@app.exception_handler(404)
def not_found_exception_handler(_request: Request, _exc: HTTPException):
    return messages.not_found()


# 422
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
    details = {}
    fields = get_fields()

    for item in exc.errors():
        field = item["loc"]
        if field[2] in fields.setdefault(field[1], []):
            details.setdefault(field[1], []).append(f"'{field[2]}' : {item["msg"]}")

    return messages.to_json_response(None, messages.unprocessable_entity(details), "")


# --- API ---

@app.post("/predict")
async def process_data(data: PredictSchema = Body(...)) -> JSONResponse:
    # 1st run
    if isinstance(data, PredictCreateSchema):  # 202: START
        task = await api_predict.kiq(data)
        return messages.to_json_response(
            task.task_id,
            messages.accepted_start(task.task_id, data.fp_path),
            HTTPState.START
        )

    # 2nd run
    task_id = data.task_id

    is_ready = await broker.result_backend.is_result_ready(task_id)
    if not is_ready:  # 202: PROCESSING
        return messages.to_json_response(
            task_id,
            messages.accepted_processing(task_id),
            HTTPState.PROCESSING
        )

    # 200, 422, 500, 503
    result = await broker.result_backend.get_result(task_id)
    return messages.to_json_response(task_id, result.return_value, HTTPState.DONE)
