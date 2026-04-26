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
from .task_monitor import get_task, list_tasks, record_task_created, record_task_done, record_task_processing, get_models_analytics, get_model_runs


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
    
    # Получаем статистику по запускам из task_monitor
    analytics = get_models_analytics()
    analytics_by_id = {m["model_id"]: m for m in analytics.get("models", [])}
    
    if not models_base_path.is_dir():
        return JSONResponse(
            content={
                "status": 200,
                "message": f"Models path not accessible: {models_base_path}",
                "models": [],
                "total": 0,
                "error": "Models directory not found",
            },
            status_code=200,
        )
    
    model_items = []
    
    # Сканируем директорию моделей
    for model_dir in sorted(models_base_path.iterdir()):
        if not model_dir.is_dir():
            continue
        
        config_path = model_dir / "config.json"
        if not config_path.is_file():
            continue
        
        model_id = model_dir.name
        
        # Читаем config.json
        try:
            with open(config_path) as f:
                raw_config = json.load(f)
        except (OSError, json.JSONDecodeError):
            raw_config = {}
        
        # Получаем статистику из analytics
        stats = analytics_by_id.get(model_id, {})
        
        # Парсим model_id на составляющие (type/horizon/region примерно)
        # Формат предположительно: prophet/watt/h/AKMOLA или similar
        parts = model_id.split("/")
        model_type = parts[0] if len(parts) > 0 else "unknown"
        horizon = parts[1] if len(parts) > 1 else "unknown"
        region = parts[-1] if len(parts) > 2 else "unknown"
        
        # Определяем horizon категорию (short/medium/long) из config
        step = raw_config.get("step", raw_config.get("short", {}).get("step", 3600))
        if isinstance(step, dict):
            step = step.get("step", 3600)
        step_num = int(step) if step else 3600
        
        if step_num < 86400:  # < 1 day
            horizon_category = "short"
        elif step_num < 2592000:  # < 30 days
            horizon_category = "medium"  
        else:
            horizon_category = "long"
        
        model_items.append({
            "model_id": model_id,
            "model_type": model_type,
            "horizon": horizon,
            "horizon_category": horizon_category,
            "region": region,
            "config_path": str(config_path),
            "config_updated_at": int(config_path.stat().st_mtime * 1000),
            "health_status": stats.get("health_status", "ok"),
            "total_runs": stats.get("total_runs", 0),
            "successful_runs": stats.get("successful_runs", 0),
            "failed_runs": stats.get("failed_runs", 0),
            "success_rate": stats.get("success_rate", 0),
            "avg_runtime_s": stats.get("avg_runtime_s", 0),
            "avg_mape": stats.get("avg_mape"),
            "last_run_at": stats.get("last_run_at"),
            "last_run_state": stats.get("last_run_state"),
            "last_run_status_code": stats.get("last_run_status_code"),
        })
    
    return JSONResponse(
        content={
            "status": 200,
            "models": model_items,
            "total": len(model_items),
            "updated_at": analytics.get("updated_at"),
        },
        status_code=200,
    )


@app.get("/ui/models/{model_id}/runs")
async def ui_model_runs(model_id: str, limit: int = Query(50, ge=1, le=200)) -> JSONResponse:
    """История запусков для конкретной модели"""
    result = get_model_runs(model_id, limit=limit)
    return JSONResponse(content=result, status_code=200)


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


@app.get("/ui/tasks")
async def ui_tasks(
    state: str = Query("all"),
    search: str = Query(""),
    worker: str = Query("all"),
    model: str = Query("all"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> JSONResponse:
    return JSONResponse(
        content=list_tasks(
            search=search,
            state=state,
            worker=worker,
            model=model,
            page=page,
            page_size=page_size,
        ),
        status_code=200,
    )


@app.get("/ui/tasks/{task_id}")
async def ui_task_detail(task_id: str) -> JSONResponse:
    task = get_task(task_id)
    if task is None:
        return JSONResponse(
            content={
                "status": 404,
                "message": f"Task not found: {task_id}",
            },
            status_code=404,
        )

    return JSONResponse(
        content={
            "status": 200,
            "task": task,
        },
        status_code=200,
    )

@app.post("/predict")
async def process_data(data: PredictSchema = Body(...)) -> JSONResponse:
    # 1st run
    if isinstance(data, PredictCreateSchema):  # 202: START
        task = await api_predict.kiq(data)
        record_task_created(task.task_id, data.object_reference, data.model_id)
        return messages.to_json_response(
            messages.accepted_start(task.task_id, data.object_reference),
            task.task_id,
            HTTPState.START
        )

    # 2nd run
    task_id = data.task_id

    is_ready = await broker.result_backend.is_result_ready(task_id)
    if not is_ready:  # 202: PROCESSING
        record_task_processing(task_id)
        return messages.to_json_response(
            messages.accepted_processing(task_id),
            task_id,
            HTTPState.PROCESSING
        )

    # 200, 422, 500, 503
    result = await broker.result_backend.get_result(task_id)
    record_task_done(task_id, result.return_value)
    return messages.to_json_response(result.return_value, task_id, HTTPState.DONE)
