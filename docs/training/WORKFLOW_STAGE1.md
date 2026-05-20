# WORKFLOW STAGE 1: Прием запроса `/predict` (create-ветка)

## 1. Цель этапа

Подготовить валидный create-запрос к постановке в очередь:

- распознать тип payload (create или update),
- провалидировать поля create-запроса,
- определить режим `online/offline` для следующего этапа.

Граница этапа: этап завершается в момент, когда запрос определен как `PredictCreateSchema` и готов к передаче в этап 2 (enqueue).

## 2. Точки входа в коде

- `src/api/server.py` -> `process_data(data: PredictSchema = Body(...))`
- `src/api/data/predict.py` -> `PredictSchema`, `predict_discriminator`, `PredictCreateSchema`

## 3. Входные данные

HTTP запрос:

- Method: `POST`
- URL: `/predict`
- Content-Type: `application/json`

Create-payload (ожидаемый минимум):

```json
{
  "object_reference": "/KAZ/AKMOLA/@models/P_WATT",
  "model_id": "prophet/watt/h/AKMOLA/@regions/Akmola/load",
  "model_selection": {
    "version_alias": "Production"
  }
}
```

Допустим также `model_id: "none"` для online-режима.

## 4. Пошаговая логика на уровне кода

### Шаг 1. FastAPI читает body и применяет тип `PredictSchema`

В `process_data` параметр `data` типизирован как `PredictSchema` (discriminated union), поэтому до входа в бизнес-логику выполняется pydantic-парсинг.

Результат шага:

- если JSON невалиден/не соответствует схеме -> переход в обработчик 422,
- если валиден -> объект одной из схем (`PredictCreateSchema` или `PredictUpdateSchema`).

### Шаг 2. Дискриминация create/update

Функция `predict_discriminator(v)` в `src/api/data/predict.py`:

- если в payload есть ключ `task_id` -> это update-ветка,
- иначе -> это create-ветка.

Критично:

- отсутствие `task_id` автоматически направляет запрос в create-ветку,
- наличие `task_id` переводит запрос в polling-ветку (этап 7, не в scope этого файла).

### Шаг 3. Валидация `PredictCreateSchema`

Ограничения схемы:

- `ConfigDict(strict=True, extra="forbid")`
- лишние поля запрещены,
- типы не приводятся "мягко" (строгая проверка).

Поля:

- `model_id: str = "none"`
- `object_reference: str`
- `model_selection: ModelSelectionSchema | None = None`

Структура `model_selection`:

- `version_alias: str | None` — alias в MLflow Registry (например `Production`)
- `version: str | None` — конкретная версия модели в MLflow Registry

Правила для `model_selection`:

- `version_alias` и `version` взаимоисключающие
- пустые строки запрещены
- если `model_selection` не передан, вычисляемый `selector` получает значение `Production`

Валидаторы:

- `check_model_id`:
  - строка не должна быть пустой,
- `check_object_reference`:
  - строка не должна быть пустой,
  - должна содержать `/` или `\\`.

### Шаг 4. Вычисление режима online/offline

`PredictCreateSchema.online` (computed field):

- `online = (model_id == "none")`

Это значение не передается явно клиентом, а вычисляется на сервере и будет использовано на следующих этапах.

`PredictCreateSchema.selector` (computed field):

- если передан `model_selection.version` -> `selector = version`
- иначе если передан `model_selection.version_alias` -> `selector = version_alias`
- иначе -> `selector = "Production"`

`selector` используется дальше для разрешения модели в MLflow Registry.

### Шаг 5. Ветвление в обработчике `process_data`

Условие:

- `if isinstance(data, PredictCreateSchema): ...`

Если условие истинно, запрос считается корректным create-запросом и передается в этап 2 (постановка задачи в очередь).

## 5. Выход этапа

Технический выход этапа 1:

- сформирован валидный объект `PredictCreateSchema`,
- определен флаг `online`,
- выбрана create-ветка `process_data`.

Внешне это проявляется переходом к следующему шагу (enqueue), который уже возвращает HTTP `202 START` с `task_id`.

## 6. Ошибки и защитные проверки

### 6.1 Невалидный JSON / несовместимая схема

- источник: pydantic/FastAPI validation,
- результат: HTTP `422`,
- обработчик: `validation_exception_handler` в `src/api/server.py`.

### 6.2 Пустой `model_id`

- источник: `check_model_id`,
- результат: HTTP `422`.

### 6.3 Пустой `object_reference`

- источник: `check_object_reference`,
- результат: HTTP `422`.

### 6.4 `object_reference` без `/` и `\\`

- источник: `check_object_reference`,
- результат: HTTP `422`.

### 6.5 Лишние поля

- источник: `extra="forbid"`,
- результат: HTTP `422`.

## 7. Как проверить этап вручную

### Проверка 1. Валидный create-запрос

```bash
curl -sS -X POST http://localhost:8030/predict \
  -H "Content-Type: application/json" \
  -d '{"object_reference":"/root/FP/PROJECT/AKMOLA/@regions/KOKSHETAU/Load/P_load/archives/out_value","model_id":"model3","model_selection":{"version_alias":"Production"}}'
```

Ожидание:

- запрос проходит в create-ветку,
- дальше обрабатывается этапом 2,
- приходит `202` и `task_id`.

### Проверка 2. Невалидный `object_reference`

```bash
curl -sS -X POST http://localhost:8030/predict \
  -H "Content-Type: application/json" \
  -d '{"object_reference":"INVALID_PATH","model_id":"model3","model_selection":{"version_alias":"Production"}}'
```

Ожидание:

- `422` с описанием ошибки валидации.

### Проверка 3. Лишнее поле

```bash
curl -sS -X POST http://localhost:8030/predict \
  -H "Content-Type: application/json" \
  -d '{"object_reference":"/root/FP/PROJECT/AKMOLA/@regions/KOKSHETAU/Load/P_load/archives/out_value","model_id":"model3","model_selection":{"version_alias":"Production"},"extra_field":123}'
```

Ожидание:

- `422` из-за `extra="forbid"`.

## 8. Связь со следующими этапами

- Следующий файл: `docs/workflow/WORKFLOW_STAGE2.md`
- Что передается дальше:
  - `model_id`,
  - `object_reference`,
  - опциональный `model_selection`,
  - вычисленный `online`,
  - вычисленный `selector` (по умолчанию `Production`).
