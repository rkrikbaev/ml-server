# WORKFLOW STAGE 6: Постобработка и формирование результата

## 1. Цель этапа

Сформировать финальный payload задачи после инференса:

- применить опциональное клиппирование отрицательных значений,
- собрать финальный объект `data.output` и статистику,
- вернуть `DONE`-payload с финальными `message`, `model_confidence` и статистикой.

Граница этапа: завершается, когда сформирован ответ `HTTPMessages.ok_done(...)` либо возвращена ошибка из общего `try/except`.

## 2. Точки входа в коде

- `src/api/broker/tasks/predict.py` -> `_build_result(...)`
- `src/api/broker/tasks/predict.py` -> `_compute_model_confidence(...)`
- `src/api/broker/tasks/predict.py` -> `_build_input_statistics(...)`
- `src/api/broker/tasks/predict.py` -> `_build_output_statistics(...)`

> **Примечание (CMMS):** Функции `_get_planned_adjustments(...)` и `_apply_planned_adjustments(...)` существуют в коде, но **закомментированы** и не вызываются в активном pipeline. Поле `planned_adjustments_applied` в ответе не формируется.

> **Примечание (health_flag):** Функции `count_input_health(...)` и `evaluate_input_health(...)` существуют в `src/adapters/evaluation.py`, но **не подключены** к активному predict pipeline.

## 3. Пошаговая логика на уровне кода

### Шаг 1. Опциональное клиппирование отрицательных значений

В `_build_result(...)`:

```python
if clip_negatives_to_0:
    preds = maximum(preds, 0)
```

Управляется полем `clip_negatives_to_0` из `ModelConfig` (по умолчанию `True`).

### Шаг 2. Сборка массива вывода

```python
output = [
    [int(ts), None if isnan(p) else round(float(p), 1), None]
    for ts, p in zip(pred_ts, preds)
]
```

Формат каждого элемента: `[timestamp_ms, value_or_null, null]`.

- Первый элемент: временная метка в мс (unix).
- Второй элемент: значение прогноза (float, округлённый до 1 знака) или `null` при `NaN`.
- Третий элемент: зарезервирован, всегда `null`.

### Шаг 3. Расчёт model_confidence

```python
model_confidence = _compute_model_confidence(preds, is_matching, model)
```

Логика:
- base confidence = 1.0
- если `model is None` → `-0.35`
- если `is_matching == False` → `-0.30`
- вычитается `(1 - valid_ratio) * 0.50`, где `valid_ratio` = доля конечных значений в `preds`
- результат зажимается в `[0.0, 1.0]`

### Шаг 4. Сборка статистики входа/выхода

```python
input_statistics = _build_input_statistics(timestamps, values)
output_statistics = _build_output_statistics(pred_ts, preds)
```

Обе функции возвращают `point_count`, `valid_point_count`, `start_timestamp`, `end_timestamp`, `min`, `max`, `mean`, `std`.

### Шаг 5. Формирование сообщения

```python
if model is None:
    message = "Model loading warning: fallback inference path was used."
elif not is_matching:
    message = "Input data does not match training distribution."
else:
    message = ""
```

### Шаг 6. Сборка финального результата

`logic(...)` возвращает:

```python
return HTTPMessages.ok_done(
    _build_result(...)
)
```

Структура payload задачи при успешном завершении:

```json
{
  "message": "...",
  "output": [[timestamp_ms, value_or_null, null], ...],
  "model_confidence": 0.95,
  "input_statistics": {"point_count": ..., "valid_point_count": ..., "min": ..., ...},
  "output_statistics": {"point_count": ..., "valid_point_count": ..., "min": ..., ...},
  "mlflow": {"name": "model_name", "version": "1"}
}
```

Поле `mlflow` присутствует только для offline-режима (`model_id != "none"`).

Важно: успешный путь Stage6 всегда оборачивается в `HTTPMessages.ok_done(...)`, то есть HTTP-статус ответа задачи = `200`.

## 4. Ошибки и защитные поведения

### 4.1 Ошибка в постобработке

- Источник: непойманное исключение в `logic(...)` после инференса
- Результат: `internal_server_error(...)` (`500`)

### 4.2 Все прогнозы NaN

- Источник: модель вернула только `NaN` (ошибка инференса без исключения)
- Результат: `output` содержит `[ts, null, null]` для каждой точки; `model_confidence` снижается; pipeline не падает

## 5. Как проверить этап

### Проверка 1. Стандартный успешный путь

```bash
cd ml-server
make test-predict PREDICT_MODEL_ID=xgb
```

Ожидание:

- финальный payload содержит `data.output` в формате `[[ts, val, null], ...]`,
- есть `input_statistics` и `output_statistics`,
- поле `model_confidence` присутствует в диапазоне `[0.0, 1.0]`.

### Проверка 2. Проверка клиппирования отрицательных значений

- Установить в runtime-конфиге `clip_negatives_to_0=true`.
- Выполнить predict на наборе, где модель генерирует отрицательные значения.

Ожидание:

- в `data.output` значения ниже 0 отсутствуют.

## 6. Операционный чеклист

- [ ] Клиппирование отрицательных значений выполнено (если `clip_negatives_to_0=True`).
- [ ] Каждый элемент `output` имеет три компонента: `[timestamp_ms, value_or_null, null]`.
- [ ] `model_confidence` рассчитан через `_compute_model_confidence`.
- [ ] `input_statistics` и `output_statistics` присутствуют в payload.
- [ ] `message` заполнен при наличии предупреждений (fallback или несовпадение распределения).
- [ ] Итоговый payload обёрнут в `HTTPMessages.ok_done(...)`.

## 7. Связь с соседними этапами

- Предыдущий файл: `docs/workflow/WORKFLOW_STAGE5.md`
- Следующий файл: `docs/workflow/WORKFLOW_STAGE7.md`
- Что передаётся в ответ:
  - `data.output`
  - `model_confidence`, `message`
  - `input_statistics`, `output_statistics`
  - `mlflow` (опционально)
