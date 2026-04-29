from __future__ import annotations

from collections import OrderedDict
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from os import getenv
from pathlib import Path
from threading import RLock
from typing import Any
import json
import yaml

from .config import REDIS_TIMEOUT


MODELS_PATH = Path(getenv("MODELS_PATH", "/workspace/models"))
DEFAULT_QUEUE = "forecast.default"
DEFAULT_TASK_NAME = "forecasting.run_forecast"
_MAX_TASKS = 500
_TASKS: "OrderedDict[str, dict[str, Any]]" = OrderedDict()
_LOCK = RLock()
_STARTED_AT = datetime.now(timezone.utc)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.isoformat()


def _copy_task(task: dict[str, Any]) -> dict[str, Any]:
    item = deepcopy(task)
    now = _utc_now()
    if item.get("result") is not None:
        item["result"] = json.loads(json.dumps(item["result"], default=str))
    item["runtime_s"] = _runtime_seconds(item, now)
    item["received_at"] = _iso(item.get("received_at"))
    item["updated_at"] = _iso(item.get("updated_at"))
    item["started_at"] = _iso(item.get("started_at"))
    item["completed_at"] = _iso(item.get("completed_at"))
    item["expires_at"] = _iso(item.get("expires_at"))
    item["display_state"] = _display_state(item, now)
    item["result_preview"] = item.get("result_preview") or []
    item["poll_history"] = item.get("poll_history", [])[-12:]
    return item


def _trim_tasks() -> None:
    while len(_TASKS) > _MAX_TASKS:
        _TASKS.popitem(last=False)


def _infer_model_type(model_id: str) -> str:
    if not model_id or model_id == "none":
        return "online"

    flattened = _flatten_model_config(_load_model_config(model_id))
    model_type = flattened.get("model_type", flattened.get("framework"))
    return str(model_type) if model_type not in (None, "") else "unknown"


def _load_model_config(model_id: str) -> dict[str, Any]:
    if not model_id or model_id == "none":
        return {}

    config_path = MODELS_PATH / model_id / "config_unified.yaml"
    if not config_path.is_file():
        return {}

    try:
        with open(config_path) as f:
            payload = yaml.safe_load(f) or {}
            return payload if isinstance(payload, dict) else {}
    except (OSError, yaml.YAMLError):
        return {}


def _flatten_model_config(raw_config: dict[str, Any]) -> dict[str, Any]:
    for key in ("short", "medium", "long"):
        section = raw_config.get(key)
        if isinstance(section, dict):
            merged = dict(raw_config)
            merged.update(section)
            return merged
    return raw_config


def _detect_sources(model_id: str) -> dict[str, dict[str, Any]]:
    flattened = _flatten_model_config(_load_model_config(model_id))
    has_weather = any(flattened.get(key) not in (None, "") for key in ("weather_url", "weather_lat", "weather_lon"))
    has_cmms = flattened.get("cmms_url") not in (None, "")

    return {
        "scada": {"enabled": True, "status": "ok"},
        "weather": {"enabled": has_weather, "status": "ok" if has_weather else "missing"},
        "cmms": {"enabled": has_cmms, "status": "ok" if has_cmms else "missing"},
    }


def _runtime_seconds(task: dict[str, Any], now: datetime) -> float | None:
    started_at = task.get("started_at") or task.get("received_at")
    if started_at is None:
        return None
    finished_at = task.get("completed_at") or now
    return max((finished_at - started_at).total_seconds(), 0.0)


def _display_state(task: dict[str, Any], now: datetime | None = None) -> str:
    current = now or _utc_now()
    expires_at = task.get("expires_at")
    if isinstance(expires_at, str):
        try:
            expires_at = datetime.fromisoformat(expires_at)
        except ValueError:
            expires_at = None
    if expires_at and expires_at <= current:
        return "expired"

    state = task.get("state", "start")
    if state != "done":
        return state

    status_code = int(task.get("status_code") or 0)
    return f"done {status_code}" if status_code else "done"


def _make_task(task_id: str, object_reference: str, model_id: str) -> dict[str, Any]:
    now = _utc_now()
    return {
        "task_id": task_id,
        "task_name": DEFAULT_TASK_NAME,
        "queue": DEFAULT_QUEUE,
        "priority": "normal",
        "object_reference": object_reference,
        "model_id": model_id,
        "model_type": _infer_model_type(model_id),
        "state": "start",
        "status_code": 202,
        "received_at": now,
        "updated_at": now,
        "started_at": None,
        "completed_at": None,
        "expires_at": None,
        "worker": None,
        "request": {
            "object_reference": object_reference,
            "model_id": model_id,
        },
        "sources": _detect_sources(model_id),
        "quality": None,
        "model_confidence": None,
        "result_preview": [],
        "result": None,
        "error": None,
        "poll_history": [],
        "actions": {
            "retry": False,
            "revoke": False,
            "copy_task_id": True,
        },
    }


def record_task_created(task_id: str, object_reference: str, model_id: str) -> None:
    with _LOCK:
        task = _make_task(task_id, object_reference, model_id)
        task["poll_history"].append({
            "timestamp": _iso(task["received_at"]),
            "status": 202,
            "state": "start",
        })
        _TASKS[task_id] = task
        _trim_tasks()


def record_task_processing(task_id: str) -> None:
    with _LOCK:
        task = _TASKS.get(task_id)
        if not task:
            return

        now = _utc_now()
        if task.get("started_at") is None:
            task["started_at"] = now
        task["updated_at"] = now
        task["state"] = "processing"
        task["status_code"] = 202
        task["actions"]["revoke"] = False
        task["poll_history"].append({
            "timestamp": _iso(now),
            "status": 202,
            "state": "processing",
        })


def record_task_done(task_id: str, payload: dict[str, Any]) -> None:
    with _LOCK:
        task = _TASKS.get(task_id)
        if not task:
            return

        now = _utc_now()
        status_code = int(payload.get("status") or 200)
        task["updated_at"] = now
        task["completed_at"] = now
        task["expires_at"] = now + timedelta(seconds=REDIS_TIMEOUT)
        task["state"] = "done"
        task["status_code"] = status_code
        task["result"] = deepcopy(payload)
        data = payload.get("data") or {}
        output = data.get("output") if isinstance(data, dict) else None
        task["result_preview"] = output[:6] if isinstance(output, list) else []
        task["quality"] = data.get("quality") if isinstance(data, dict) else payload.get("quality")
        task["model_confidence"] = data.get("model_confidence") if isinstance(data, dict) else payload.get("model_confidence")
        task["error"] = payload.get("message") if status_code != 200 else None
        task["actions"]["retry"] = status_code in (422, 500, 503)
        task["poll_history"].append({
            "timestamp": _iso(now),
            "status": status_code,
            "state": "done",
        })


def list_tasks(
    *,
    search: str = "",
    state: str = "all",
    worker: str = "all",
    model: str = "all",
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    with _LOCK:
        now = _utc_now()
        items = [_copy_task(task) for task in reversed(_TASKS.values())]

    def matches(item: dict[str, Any]) -> bool:
        display_state = item["display_state"]
        model_type = item.get("model_type") or "unknown"
        worker_name = item.get("worker") or "unassigned"
        haystack = " ".join([
            item.get("task_id", ""),
            item.get("object_reference", ""),
            item.get("model_id", ""),
            worker_name,
        ]).lower()
        normalized_search = search.strip().lower()

        if normalized_search and normalized_search not in haystack:
            return False
        if worker != "all" and worker_name != worker:
            return False
        if model != "all" and model_type != model:
            return False
        if state == "all":
            return True
        if state == "done_success":
            return display_state == "done 200"
        if state == "done_error":
            return display_state.startswith("done ") and display_state != "done 200"
        return display_state == state

    filtered = [item for item in items if matches(item)]
    total = len(filtered)
    safe_page = max(page, 1)
    safe_page_size = max(1, min(page_size, 100))
    start_idx = (safe_page - 1) * safe_page_size
    end_idx = start_idx + safe_page_size
    page_items = filtered[start_idx:end_idx]

    completed = [item for item in filtered if item["display_state"].startswith("done ")]
    avg_runtime = 0.0
    if completed:
        runtimes = [item["runtime_s"] for item in completed if item["runtime_s"] is not None]
        avg_runtime = sum(runtimes) / len(runtimes) if runtimes else 0.0

    minute_ago = now - timedelta(minutes=1)
    tasks_per_min = sum(1 for item in completed if item.get("completed_at") and datetime.fromisoformat(item["completed_at"]) >= minute_ago)
    queue_total = sum(1 for item in items if item["display_state"] in ("start", "processing"))
    processing_total = sum(1 for item in items if item["display_state"] == "processing")
    recent_errors = sum(1 for item in items if item["display_state"] in ("done 422", "done 500", "done 503"))

    return {
        "status": 200,
        "items": page_items,
        "total": total,
        "page": safe_page,
        "page_size": safe_page_size,
        "counts": {
            "total": len(filtered),
            "start": sum(1 for item in filtered if item["display_state"] == "start"),
            "processing": sum(1 for item in filtered if item["display_state"] == "processing"),
            "done_success": sum(1 for item in filtered if item["display_state"] == "done 200"),
            "done_error": sum(1 for item in filtered if item["display_state"] in ("done 422", "done 500", "done 503")),
            "expired": sum(1 for item in filtered if item["display_state"] == "expired"),
        },
        "avg_runtime_s": round(avg_runtime, 1),
        "tasks_per_min": round(tasks_per_min, 1),
        "updated_at": _iso(now),
        "sidebar": {
            "queues": [
                {"name": DEFAULT_QUEUE, "count": queue_total, "kind": "default"},
                {"name": "forecast.results", "count": len(completed), "kind": "results"},
                {"name": "forecast.dead", "count": recent_errors, "kind": "dead"},
            ],
            "workers": [
                {"name": "taskiq-pool", "status": "online" if processing_total else "idle", "active_tasks": processing_total},
            ],
            "quick_filters": {
                "active": queue_total,
                "queued": sum(1 for item in items if item["display_state"] == "start"),
                "errors_24h": recent_errors,
            },
            "broker": {
                "name": "Redis",
                "tasks_per_min": round(tasks_per_min, 1),
                "uptime_s": int((now - _STARTED_AT).total_seconds()),
            },
        },
        "available_models": sorted({item.get("model_type") or "unknown" for item in items}),
        "available_workers": sorted({item.get("worker") or "unassigned" for item in items}),
    }


def get_task(task_id: str) -> dict[str, Any] | None:
    with _LOCK:
        task = _TASKS.get(task_id)
        if not task:
            return None
        return _copy_task(task)


def get_models_analytics() -> dict[str, Any]:
    """
    Анализирует все задачи и генерирует статистику по моделям,
    включая MAPE, количество запусков, последний результат и т.д.
    """
    with _LOCK:
        now = _utc_now()
        
        # Группируем задачи по model_id
        models_stats: dict[str, Any] = {}
        
        for task in _TASKS.values():
            model_id = task.get("model_id") or "unknown"
            if model_id not in models_stats:
                models_stats[model_id] = {
                    "model_id": model_id,
                    "model_type": task.get("model_type") or "unknown",
                    "total_runs": 0,
                    "successful_runs": 0,
                    "failed_runs": 0,
                    "last_run_at": None,
                    "last_run_state": None,
                    "last_run_status_code": None,
                    "runtimes": [],
                    "mape_values": [],
                    "health_status": "ok",
                }
            
            stats = models_stats[model_id]
            
            # Подсчитываем общее количество запусков
            if task.get("state") == "done":
                stats["total_runs"] += 1
                status_code = task.get("status_code", 0)
                
                if status_code == 200:
                    stats["successful_runs"] += 1
                else:
                    stats["failed_runs"] += 1
                
                # Собираем информацию о последнем запуске
                completed_at = task.get("completed_at")
                if completed_at and (stats["last_run_at"] is None or completed_at > stats["last_run_at"]):
                    stats["last_run_at"] = completed_at
                    stats["last_run_state"] = task.get("display_state")
                    stats["last_run_status_code"] = status_code
                
                # Собираем runtime и MAPE
                runtime = task.get("runtime_s")
                if runtime is not None:
                    stats["runtimes"].append(runtime)
                
                quality = task.get("quality")
                if quality is not None and isinstance(quality, (int, float)):
                    stats["mape_values"].append(quality)
        
        # Рассчитываем итоговую статистику для каждой модели
        result = []
        for model_id, stats in models_stats.items():
            # Рассчитываем средние значения
            avg_runtime = sum(stats["runtimes"]) / len(stats["runtimes"]) if stats["runtimes"] else 0.0
            avg_mape = sum(stats["mape_values"]) / len(stats["mape_values"]) if stats["mape_values"] else None
            
            # Определяем health status
            last_state = stats["last_run_state"]
            if last_state and last_state == "done 200":
                # Проверяем MAPE
                if avg_mape is not None:
                    if avg_mape < 7:
                        health = "ok"
                    elif avg_mape < 12:
                        health = "warning"
                    else:
                        health = "error"
                else:
                    health = "ok"
            elif last_state and last_state.startswith("done ") and last_state != "done 200":
                health = "error"
            else:
                health = "ok"
            
            # Проверяем, как давно был последний запуск
            if stats["last_run_at"]:
                try:
                    last_run_dt = stats["last_run_at"] if isinstance(stats["last_run_at"], datetime) else datetime.fromisoformat(stats["last_run_at"])
                    hours_since = (now - last_run_dt).total_seconds() / 3600
                    if hours_since > 24 and health == "ok":
                        health = "warning"
                except (TypeError, ValueError):
                    pass
            
            result.append({
                "model_id": model_id,
                "model_type": stats["model_type"],
                "health_status": health,
                "total_runs": stats["total_runs"],
                "successful_runs": stats["successful_runs"],
                "failed_runs": stats["failed_runs"],
                "success_rate": round(
                    (stats["successful_runs"] / stats["total_runs"] * 100) if stats["total_runs"] > 0 else 0, 1
                ),
                "avg_runtime_s": round(avg_runtime, 1),
                "avg_mape": round(avg_mape, 1) if avg_mape is not None else None,
                "last_run_at": _iso(stats["last_run_at"]) if isinstance(stats["last_run_at"], datetime) else stats["last_run_at"],
                "last_run_state": stats["last_run_state"],
                "last_run_status_code": stats["last_run_status_code"],
            })
        
        # Сортируем по model_id
        result.sort(key=lambda x: x["model_id"])
        
        return {
            "status": 200,
            "models": result,
            "total_models": len(result),
            "updated_at": _iso(now),
        }


def get_model_runs(model_id: str, limit: int = 50) -> dict[str, Any]:
    """
    Получает историю запусков для конкретной модели.
    """
    with _LOCK:
        now = _utc_now()
        
        # Фильтруем все задачи по model_id
        runs = [
            _copy_task(task)
            for task in reversed(_TASKS.values())
            if task.get("model_id") == model_id and task.get("state") == "done"
        ]
        
        # Берем последние N запусков
        runs = runs[:limit]
        
        return {
            "status": 200,
            "model_id": model_id,
            "runs": runs,
            "total_runs": len(runs),
            "updated_at": _iso(now),
        }