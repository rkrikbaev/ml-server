# Mariya Polkovnikova
# 2026.03.10, 04:18 PM


from contextlib import asynccontextmanager
from os import getenv
from pathlib import Path
import json
import os
import resource

from fastapi import FastAPI, Request, Body, Query
from fastapi.responses import JSONResponse, FileResponse
from fastapi.exceptions import RequestValidationError, HTTPException

from api.utils import get_fields
from .broker import broker, api_predict
from .data import PredictCreateSchema, PredictSchema
from .forecast import load_model_config
from .message import HTTPState, HTTPMessages


@asynccontextmanager
async def lifespan(app: FastAPI):
    await broker.startup()
    yield
    await broker.shutdown()

app = FastAPI(lifespan=lifespan)
messages = HTTPMessages()
UI_DIR = Path(__file__).resolve().parent / "ui"


# --- ERRORS ---

# 404
@app.exception_handler(404)
def not_found_exception_handler(_request: Request, _exc: HTTPException):
    return messages.to_json_response(messages.not_found())


# 422
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
    details = {}
    fields = get_fields()

    for item in exc.errors():
        field = item["loc"]
        if field[2] in fields.setdefault(field[1], []):
            details.setdefault(field[1], []).append(f"'{field[2]}' : {item["msg"]}")

    return messages.to_json_response(messages.unprocessable_entity(details))


# --- API ---

@app.get("/ui")
async def ui_index() -> FileResponse:
    return FileResponse(UI_DIR / "index.html")


@app.get("/ui/styles.css")
async def ui_styles() -> FileResponse:
    return FileResponse(UI_DIR / "styles.css", media_type="text/css")


@app.get("/ui/app.js")
async def ui_script() -> FileResponse:
    return FileResponse(UI_DIR / "app.js", media_type="application/javascript")


@app.get("/ui/model-config")
async def ui_model_config(model_id: str = Query(..., min_length=1)) -> JSONResponse:
    models_base_path = Path(getenv("MODELS_PATH", "/workspace/models"))
    config_path = models_base_path / model_id / "config.json"

    if not config_path.is_file():
        content = {
            "status": 404,
            "message": f"Model config not found: {config_path}",
            "model_id": model_id,
        }
        return JSONResponse(content=content, status_code=404)

    with open(config_path) as f:
        raw_config = json.load(f)

    normalized_config = load_model_config(model_id).model_dump()

    return JSONResponse(
        content={
            "status": 200,
            "model_id": model_id,
            "config_path": str(config_path),
            "raw_config": raw_config,
            "normalized_config": normalized_config,
        },
        status_code=200,
    )


@app.get("/ui/models")
async def ui_models() -> JSONResponse:
    models_base_path = Path(getenv("MODELS_PATH", "/workspace/models"))

    if not models_base_path.is_dir():
        return JSONResponse(
            content={
                "status": 404,
                "message": f"Models path not found: {models_base_path}",
                "models": [],
            },
            status_code=404,
        )

    model_items = []
    for model_dir in sorted(models_base_path.iterdir()):
        if not model_dir.is_dir():
            continue

        config_path = model_dir / "config.json"
        if not config_path.is_file():
            continue

        model_items.append(
            {
                "model_id": model_dir.name,
                "config_path": str(config_path),
                "updated_at": int(config_path.stat().st_mtime),
            }
        )

    return JSONResponse(
        content={
            "status": 200,
            "count": len(model_items),
            "models": model_items,
        },
        status_code=200,
    )


@app.get("/ui/runtime-status")
async def ui_runtime_status() -> JSONResponse:
    load_avg = os.getloadavg() if hasattr(os, "getloadavg") else (0.0, 0.0, 0.0)
    rss_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss

    return JSONResponse(
        content={
            "status": 200,
            "cpu_load": {
                "load_1m": round(load_avg[0], 3),
                "load_5m": round(load_avg[1], 3),
                "load_15m": round(load_avg[2], 3),
            },
            "memory": {
                "rss_kb": int(rss_kb),
                "rss_mb": round(rss_kb / 1024, 2),
            },
        },
        status_code=200,
    )

@app.post("/predict")
async def process_data(data: PredictSchema = Body(...)) -> JSONResponse:
    # 1st run
    if isinstance(data, PredictCreateSchema):  # 202: START
        task = await api_predict.kiq(data)
        return messages.to_json_response(
            messages.accepted_start(task.task_id, data.object_reference),
            task.task_id,
            HTTPState.START
        )

    # 2nd run
    task_id = data.task_id

    is_ready = await broker.result_backend.is_result_ready(task_id)
    if not is_ready:  # 202: PROCESSING
        return messages.to_json_response(
            messages.accepted_processing(task_id),
            task_id,
            HTTPState.PROCESSING
        )

    # 200, 422, 500, 503
    result = await broker.result_backend.get_result(task_id)
    return messages.to_json_response(result.return_value, task_id, HTTPState.DONE)
