# Схема для Predict

Для [API predict](../MAIN.md#1-predict) публично используется двухшаговый GET-контракт:
1. Создание задачи - запрос `GET /predict/{model_id}`
2. Опрос результата - запрос `GET /tasks/{task_id}`

## Создание задачи: `GET /predict/{model_id}`

| Локация | Поле | Тип | Обязательность | Описание |
| --- | --- | --- | --- | --- |
| path | `model_id` | `string` | обязательно | бизнес-идентификатор модели |
| query | `version_alias` | `string` | необязательно | alias в MLflow Registry, по умолчанию `Production` |
| query | `object_ref` | `string` | необязательно | путь к FP-объекту клиента |

### Поле `object_ref`

- не может быть пустым;
- должно содержать `/` или `\\`.

### Поле `model_id`

- не может быть пустым.

### Поле `version_alias`

- если не передано, сервер использует alias `Production`.

Пример create-запроса:

```http
GET /predict/prophet_watt_h_AKMOLA_@regions_Akmola_load?version_alias=Production&object_ref=/KAZ/AKMOLA/@models/P_WATT
```

## Внутренняя модель в коде

В коде может сохраняться внутренняя Pydantic-модель (`PredictCreateSchema`) и вычисляемые поля (`online`, `selector`), но публичный HTTP-контракт для клиента — только GET path/query-параметры, указанные выше.

## Опрос результата

Опрос результата не использует JSON-body схему. Используется endpoint `GET /tasks/{task_id}`.

Параметр:

- `task_id` - идентификатор ранее созданной задачи

Пример:

```http
GET /tasks/f3b44ac9720f40108ad16def9f300b4e
```

## Внутренняя схема `PredictUpdateSchema`

Схема `PredictUpdateSchema` сохранена в коде как внутренний тип с полем `task_id` (используется внутренне, не как публичный body-контракт).

| Обязательность | Поле | Тип | Описание |
| --- | --- | --- | --- |
| обязательно | `task_id` | `string` | идентификатор ранее созданной задачи |
