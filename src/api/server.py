# Mariya Polkovnikova
# 2026.03.10, 04:18 PM


from contextlib import asynccontextmanager
from os import getenv
from pathlib import Path
import json
import os
import resource

from fastapi import FastAPI, Request, Query
from fastapi.responses import JSONResponse, FileResponse
from fastapi.exceptions import RequestValidationError, HTTPException

from api.utils import get_fields
from .broker import broker, api_predict
from .data import PredictCreateSchema
from adapters import load_model_config
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
        if len(field) > 2 and field[2] in fields.setdefault(field[1], []):
            details.setdefault(field[1], []).append(f"'{field[2]}' : {item['msg']}")

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
        
        # model_id is opaque; optional metadata is read from config only.
        flattened = raw_config.copy()
        for key in ("short", "medium", "long"):
            if key in raw_config and isinstance(raw_config[key], dict):
                flattened = {**raw_config, **raw_config[key]}
                break

        model_type_raw = flattened.get("model_type", flattened.get("framework"))
        model_type = str(model_type_raw) if model_type_raw not in (None, "") else "unknown"
        horizon_raw = flattened.get("horizon", flattened.get("horizon_name"))
        horizon = str(horizon_raw) if horizon_raw not in (None, "") else "unknown"
        region_raw = flattened.get("region", flattened.get("region_code"))
        region = str(region_raw) if region_raw not in (None, "") else "unknown"
        
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
        
        # Detect sources from config
        has_weather = False
        has_cmms = False
        for cfg in [raw_config] + [raw_config.get(k, {}) for k in ("short", "medium", "long")]:
            if isinstance(cfg, dict):
                if any(cfg.get(k) not in (None, "") for k in ("weather_url", "weather_lat", "weather_lon")):
                    has_weather = True
                if cfg.get("cmms_url") not in (None, ""):
                    has_cmms = True

        # Normalize health value
        health_raw = stats.get("health_status", "ok")
        health = {"ok": "ok", "warning": "warning", "warn": "warning", "error": "error", "err": "error"}.get(health_raw, "ok")

        model_items.append({
            "model_id": model_id,
            "model_type": model_type,
            "horizon": horizon,
            "horizon_category": horizon_category,
            "region": region,
            "config_path": str(config_path),
            "config_updated_at": int(config_path.stat().st_mtime * 1000),
            "health": health,
            "run_count": stats.get("total_runs", 0),
            "success_rate": stats.get("success_rate", 0),
            "avg_runtime_s": stats.get("avg_runtime_s", 0),
            "mape": stats.get("avg_mape"),
            "last_run_at": stats.get("last_run_at"),
            "last_run_state": stats.get("last_run_state"),
            "sources": {
                "scada": {"enabled": True},
                "weather": {"enabled": has_weather},
                "cmms": {"enabled": has_cmms},
            },
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


@app.get("/ui/models/detail")
async def ui_model_detail(model_id: str = Query(..., min_length=1)) -> JSONResponse:
    """Детальная информация о конкретной модели"""
    models_base_path = Path(getenv("MODELS_PATH", "/workspace/models"))
    config_path = models_base_path / model_id / "config.json"

    raw_config: dict = {}
    if config_path.is_file():
        try:
            with open(config_path) as f:
                raw_config = json.load(f)
        except (OSError, json.JSONDecodeError):
            raw_config = {}

    # Flatten nested horizon section
    flattened = raw_config.copy()
    for key in ("short", "medium", "long"):
        if key in raw_config and isinstance(raw_config[key], dict):
            flattened = {**raw_config, **raw_config[key]}
            break

    analytics = get_models_analytics()
    stats = {m["model_id"]: m for m in analytics.get("models", [])}.get(model_id, {})

    health_raw = stats.get("health_status", "ok")
    health = {"ok": "ok", "warning": "warning", "warn": "warning", "error": "error", "err": "error"}.get(health_raw, "ok")

    model_type_raw = flattened.get("model_type", flattened.get("framework"))
    model_type = str(model_type_raw) if model_type_raw not in (None, "") else "unknown"
    horizon_raw = flattened.get("horizon", flattened.get("horizon_name"))
    horizon = str(horizon_raw) if horizon_raw not in (None, "") else "—"
    region_raw = flattened.get("region", flattened.get("region_code"))
    region = str(region_raw) if region_raw not in (None, "") else "—"

    has_weather = any(flattened.get(k) not in (None, "") for k in ("weather_url", "weather_lat", "weather_lon"))
    has_cmms = flattened.get("cmms_url") not in (None, "")

    # Last run info
    runs_data = get_model_runs(model_id, limit=1)
    _runs_list = runs_data.get("runs") or []
    last_run_task = _runs_list[0] if _runs_list else None
    last_run = None
    if last_run_task:
        last_run = {
            "task_id": last_run_task.get("task_id"),
            "state": last_run_task.get("display_state"),
            "worker": last_run_task.get("worker"),
            "received_at": last_run_task.get("received_at"),
            "object_ref": last_run_task.get("object_ref"),
        }

    # Extract SCADA archive list
    scada_sources: list = []
    hist = flattened.get("historical_data")
    if isinstance(hist, list):
        scada_sources = hist
    elif isinstance(hist, dict):
        scada_sources = [hist]

    return JSONResponse(
        content={
            "status": 200,
            "model_id": model_id,
            "model_type": model_type,
            "health": health,
            "region": region,
            "horizon": horizon,
            "mape": stats.get("avg_mape"),
            "run_count": stats.get("total_runs", 0),
            "avg_runtime_s": stats.get("avg_runtime_s", 0),
            "success_rate": stats.get("success_rate", 0),
            "last_run_at": stats.get("last_run_at"),
            "last_run_state": stats.get("last_run_state"),
            "updated_at": int(config_path.stat().st_mtime) if config_path.is_file() else None,
            "seasonality_mode": flattened.get("seasonality_mode"),
            "yearly_seasonality": flattened.get("yearly_seasonality"),
            "weekly_seasonality": flattened.get("weekly_seasonality"),
            "daily_seasonality": flattened.get("daily_seasonality"),
            "sources": {
                "scada": {"enabled": True},
                "weather": {"enabled": has_weather},
                "cmms": {"enabled": has_cmms},
            },
            "scada_sources": scada_sources,
            "raw_config": raw_config,
            "last_run": last_run,
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

@app.get("/predict/{model_id}")
async def process_data(
    model_id: str,
    version_alias: str = Query("Production"),
    object_ref: str | None = Query(None),
) -> JSONResponse:
    data = PredictCreateSchema(
        model_id=model_id,
        version_alias=version_alias,
        object_ref=object_ref,
    )
    task = await api_predict.kiq(data)
    record_task_created(task.task_id, data.object_ref, data.model_id)
    return messages.to_json_response(
        messages.accepted_start(task.task_id, data.object_ref),
        task.task_id,
        HTTPState.START
    )


@app.get("/tasks/{task_id}")
async def poll_task(task_id: str) -> JSONResponse:

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
