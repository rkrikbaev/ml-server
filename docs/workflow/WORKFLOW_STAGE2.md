# WORKFLOW STAGE 2: Постановка задачи в очередь

## 1. Цель этапа

Принять прошедший валидацию `PredictCreateSchema` и:

- поставить задачу в TaskIQ-очередь через broker,
- зафиксировать начальное состояние задачи в task monitor,
- вернуть клиенту немедленный ответ `202 START` с `task_id`.

Граница этапа: этап завершается после отправки HTTP `202` клиенту. Сама задача продолжает выполняться асинхронно (этап 3+).

## 2. Точки входа в коде

- `src/api/server.py` -> `process_data`, 1st run (create-ветка)
- `src/api/broker/broker.py` -> `api_predict`
- `src/api/task_monitor.py` -> `record_task_created`
- `src/api/message.py` -> `accepted_start`, `to_json_response`

## 3. Пошаговая логика на уровне кода

### Шаг 1. Вызов enqueue через `api_predict.kiq(...)`

После проверки `isinstance(data, PredictCreateSchema)` вызывается:

```python
task = await api_predict.kiq(data)
```

- `api_predict` — это TaskIQ-задача, декорированная `@broker.task`.
- `.kiq(data)` — ставит задачу в очередь и **не ждет** её выполнения.
- Возвращаемый `task` содержит `task.task_id` (UUID).

Фактически вызов `.kiq()` публикует сообщение в Redis Stream. Worker берёт его асинхронно.

### Шаг 2. Структура задачи `api_predict`

В `src/api/broker/broker.py`:

```python
@broker.task
async def api_predict(data: Dict[str, Any]) -> Dict[str, Any]:
    output = await predict_logic(
        model_id=data["model_id"],
        online=data["online"],
    selector=data.get("selector"),
    )
    output["object_reference"] = data["object_reference"]
    return output
```

Задача принимает:
- `model_id`, `online`, `object_reference` из deserialized payload,
- опциональный `selector` (`data.get("selector")`) для MLflow resolution.

Задача возвращает финальный payload (обрабатывается в этапе 7 при polling).

### Шаг 3. Регистрация задачи в task monitor

```python
record_task_created(task.task_id, data.object_reference, data.model_id)
```

Что делает `record_task_created` (в `src/api/task_monitor.py`):

- создает структуру задачи через `_make_task(...)`,
- записывает начальный `state = "start"` и `status_code = 202`,
- добавляет первую запись в `poll_history`,
- сохраняет задачу в in-memory `OrderedDict` со thread-safe `RLock`,
- обрезает лог если задач больше `_MAX_TASKS = 500`.

Структура записи в task monitor:

```json
{
  "task_id": "...",
  "task_name": "forecasting.run_forecast",
  "queue": "forecast.default",
  "priority": "normal",
  "object_reference": "...",
  "model_id": "...",
  "model_type": "...",
  "state": "start",
  "status_code": 202,
  "received_at": "2026-04-29T...",
  "updated_at": "2026-04-29T...",
  "started_at": null,
  "completed_at": null,
  "expires_at": null,
  "worker": null,
  "sources": { "scada": {...}, "weather": {...}, "cmms": {...} },
  "quality": null,
  "model_confidence": null,
  "result_preview": [],
  "result": null,
  "error": null,
  "poll_history": [
    {"timestamp": "...", "status": 202, "state": "start"}
  ]
}
```

`model_type` в task monitor определяется через `_infer_model_type(model_id)`, который читает локальный `config_unified.yaml` из `/workspace/models/{model_id}/` только для UI/analytics metadata. Это не serving source для offline MLflow inference.

### Шаг 4. Формирование ответа `202 START`

```python
return messages.to_json_response(
    messages.accepted_start(task.task_id, data.object_reference),
    task.task_id,
    HTTPState.START
)
```

`accepted_start(...)` формирует тело:

```python
content = {"status": 202}
content["task_id"] = task_id
content["object_reference"] = fp_path
```

Здесь `fp_path` — только внутреннее имя параметра функции `accepted_start(...)`; во внешнем JSON используется ключ `object_reference`.

`to_json_response(...)` добавляет к нему `state = "start"`:

```python
case HTTPState.START:
    HTTPState.state_start(data)  # data["state"] = "start"
```

И возвращает `JSONResponse(status_code=202)`.

## 4. Выход этапа

HTTP-ответ клиенту:

- HTTP статус: `202`
- Body:

```json
{
  "status": 202,
  "task_id": "5c852360dce04d399eeaaedd947459ba",
  "object_reference": "/root/FP/PROJECT/AKMOLA/@regions/KOKSHETAU/Load/P_load/archives/out_value",
  "state": "start"
}
```

Одновременно:
- задача поставлена в Redis Stream,
- задача зафиксирована в task monitor,
- worker начнёт выполнение (этап 3) независимо от клиента.

## 5. Режимы broker

Режим определяется при старте приложения через переменные окружения:

| Переменная | Значение | Режим |
|---|---|---|
| `USE_IN_MEMORY_BROKER` | `false` (default) | `RedisStreamBroker` + `RedisAsyncResultBackend` |
| `USE_IN_MEMORY_BROKER` | `true` + `TEST_MODE` = `true` | `InMemoryBroker` + `DummyResultBackend` |

В Docker-окружении по умолчанию используется Redis. В тестовом `InMemoryBroker` задача также сразу выполняется, но без Redis.

Источники конфигурации:
- `src/api/broker/broker.py`
- `src/api/config.py` -> `REDIS_URL`, `REDIS_TIMEOUT`

## 6. Ошибки и защитные поведения

### 6.1 Ошибка при постановке в очередь (`.kiq()` упал)

- Broker не смог поставить задачу (Redis недоступен).
- Исключение всплывет из `await api_predict.kiq(data)`.
- Обработчик: глобально-необработанное исключение -> HTTP `500`.
- `record_task_created` вызвана не будет в этом случае.

### 6.2 Overflow task monitor

- `_trim_tasks()` автоматически удаляет самые старые задачи при превышении `_MAX_TASKS = 500`.
- Данные хранятся in-memory, не персистируются между рестартами.

## 7. Как проверить этап вручную

### Проверка 1. Получить task_id после create-запроса

```bash
curl -sS -X POST http://localhost:8030/predict \
  -H "Content-Type: application/json" \
  -d '{"object_reference":"/root/FP/PROJECT/AKMOLA/@regions/KOKSHETAU/Load/P_load/archives/out_value","model_id":"model3","model_selection":{"version_alias":"Production"}}'
```

Ожидание:

```json
{
  "status": 202,
  "task_id": "<uuid>",
  "object_reference": "/root/FP/PROJECT/AKMOLA/@regions/KOKSHETAU/Load/P_load/archives/out_value",
  "state": "start"
}
```

### Проверка 2. Убедиться, что задача появилась в task monitor

```bash
curl -sS http://localhost:8030/ui/tasks
```

Задача с `task_id` должна быть видна в первых позициях с `state = "start"` или уже переходящая в `"processing"`.

### Проверка 3. End-to-end через make

```bash
cd ml-server
make test-predict PREDICT_MODEL_ID=model3
```

Выполняет full cycle: create -> poll до DONE.

## 8. Операционный чеклист

Используйте этот список как быстрый контроль выполнения Stage2:

- [ ] Create-request к `/predict` принят без ошибок валидации (`422` нет).
- [ ] Сервер вернул `202` и непустой `task_id`.
- [ ] В ответе есть `state = "start"` и `object_reference`.
- [ ] В `GET /ui/tasks` есть запись с тем же `task_id`.
- [ ] У записи в monitor начальный `status_code = 202` и `state = "start"`.
- [ ] Для create payload с `model_selection` в worker ушёл вычисленный `selector`.
- [ ] Этап завершён, можно переходить к Stage3 (worker execution).

## 9. Связь с соседними этапами

- Предыдущий файл: `docs/workflow/WORKFLOW_STAGE1.md`
- Следующий файл: `docs/workflow/WORKFLOW_STAGE3.md`
- Что передается в следующий этап:
  - worker получает из очереди payload: `model_id`, `object_reference`, `online`, опционально `selector`,
  - начинается `predict_logic(model_id, online, selector)`.
