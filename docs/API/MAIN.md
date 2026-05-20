# API

Подробные схемы с валидацией смотрите в [HTTP схемах](./schema/MAIN.md)\
Подробные выходящие данные смотрите в [HTTP сообщениях](./MESSAGES.md)

## Список запросов

- [predict/{model_id}](#1-predict) - **GET**
- [tasks/{task_id}](#2-taskstask_id) - **GET**

## 1. predict

Запрос регистрируется в брокере и отправляется в очередь worker. Для offline-модели worker разрешает `model_id` через MLflow Registry по alias/version. В ответ сервер возвращает статус `START` и `task_id`. Дальнейший опрос результата выполняется отдельным endpoint `GET /tasks/{task_id}`.

<img alt="Date of Creation" src="https://img.shields.io/badge/Date%20of%20Creation-20%3F%3F.%3F%3F.%3F%3F,%20%3F%3F:%3F%3F%20%3FM-1565c0?style=for-the-badge" />
<img alt="URL" src="https://img.shields.io/badge/URL-/predict/{model_id}-a00069?style=for-the-badge" />
<img alt="Method" src="https://img.shields.io/badge/Method-GET-00695c?style=for-the-badge" />

### Query параметры

- `model_id` (path, required)
- `version_alias` (query, optional, default: `Production`)
- `object_ref` (query, optional)

### HTTP статусы, которые могут быть возвращены

- 202 - запрос принят и поставлен в обработку
- 422 - некорректный запрос

### Параметры запроса

> Подробнее об [ключах и валидации](./schema/PREDICT.md) API

#### Пример GET-запроса

- **object_ref** - путь к FP объекту клиента
- **model_id** - модель, которая нужна из прогнозов

```http
GET /predict/prophet_watt_h_AKMOLA_@regions_Akmola_load?version_alias=Production&object_ref=/KAZ/AKMOLA/AKMOLA/@models/P_WATT
```

Пояснение к примеру:

- `model_id` передается в path (`/predict/{model_id}`)
- `version_alias` передается в query
- `object_ref` передается в query

### Выходящие данные

> Остальные выходящие данные найдёте в [здесь](./MESSAGES.md)

#### Пример ответа

Для данного примера напичкали данные от фонаря, поэтому в серьёз не принимайте за чистую монету, пожалуйста
```json
{
  "status": 202,
  "object_ref": "/KAZ/AKMOLA/AKMOLA/@models/P_WATT",
  "task_id": "f3b44ac9720f40108ad16def9f300b4e",
  "state": "start"
}
```

## 2. tasks/{task_id}

Опрос статуса и результата ранее созданной задачи по `task_id`.

<img alt="URL" src="https://img.shields.io/badge/URL-/tasks/{task_id}-a00069?style=for-the-badge" />
<img alt="Method" src="https://img.shields.io/badge/Method-GET-00695c?style=for-the-badge" />

### Content-Type

- <img alt="output" src="https://img.shields.io/badge/output-application/json;-4527a0?style=flat-square" />

### HTTP статусы, которые могут быть возвращены

- 202 - задача еще обрабатывается
- 200 - задача успешно завершена
- 422 - ошибка данных/прогноза
- 500 - внутренняя ошибка сервера
- 503 - недоступен внешний сервис

### Параметры

- **task_id** - UUID задачи из ответа `GET /predict/{model_id}`

### Пример ответа при обработке

```json
{
  "status": 202,
  "task_id": "f3b44ac9720f40108ad16def9f300b4e",
  "state": "processing"
}
```

### Пример финального успешного ответа

```json
{
  "status": 200,
  "state": "done",
  "task_id": "f3b44ac9720f40108ad16def9f300b4e",
  "object_ref": "/KAZ/AKMOLA/AKMOLA/@models/P_WATT",
  "data": {
    "message": "...",
    "output": [
      [1746900000, 312.4],
      [1746903600, 314.1]
    ],
    "model_confidence": 1.0
  }
}
```

Примечание по `model_confidence`:
- Поле вычисляется в диапазоне `[0.0, 1.0]`.
- На confidence влияют `is_matching`, доступность модели и доля валидных (не `NaN`) прогнозных точек.
