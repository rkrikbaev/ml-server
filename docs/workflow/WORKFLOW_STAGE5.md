# WORKFLOW STAGE 5: Инициализация модели и инференс

## 1. Цель этапа

Инициализировать model adapter и выполнить прогноз на подготовленных данных:

- создать модель на основе `model_type` и runtime-конфига,
- выполнить `predict(...)` на `timestamp/value`,
- получить `preds`, `pred_ts`, `is_matching` для следующего этапа.

Граница этапа: завершается после успешного вызова `predict(...)` или возврата управляемой ошибки `422` при ошибке инференса.

Вход Stage5: используются параметры из `config` (`ModelConfig`), который получен в Stage3 из единого сырого формата `cache_config.json` с объектом `sources`.

## 2. Точки входа в коде

- `src/api/broker/tasks/predict.py` -> `logic(...)`
- `src/api/forecast/model.py` -> `init_model(...)`
- `src/api/forecast/inference.py` -> `predict(...)`
- `src/api/utils/timestamps.py` -> `get_pred_timestamps(...)`

## 3. Пошаговая логика на уровне кода

### Шаг 1. Инициализация адаптера модели

В `logic(...)`:

```python
model = init_model(model_source, step, config.use_dynamic_normalization, config.fallback, config.model_type)
```

Используемые поля `ModelConfig` на этом шаге:

- `model_type`
- `fallback`
- `use_dynamic_normalization` (передаётся в `init_model`)

Источник `model_source`:

- offline: путь к `bundle/model` из MLflow cache,
- online (`model_id == "none"`): создаётся новая Prophet-модель без registry bundle.

Поддерживаемые типы `model_type`:

- `prophet`
- `xgb`
- `naive`
- `ar`

Если файл модели для `prophet/xgb` отсутствует:

- при `fallback != "none"` используется fallback adapter,
- при `fallback == "none"` выбрасывается исключение.

### Шаг 2. Подготовка входов для инференса

На вход `predict(...)` передаются:

- `y=value`,
- `timestamps=timestamp`,
- `model=model`,
- `step` (мс),
- `output_range` (точек),
- `online`,
- `df_rz_melt` (сейчас `None`),
- `weather_data` (опционально).

Вызов из `logic(...)`:

```python
preds, pred_ts, is_matching = predict(
    y=value,
    timestamps=timestamp,
    model=model,
    step=step,
    output_range=output_range,
    online=online,
    df_rz_melt=df_rz,
    weather_data=weather_data,
)
```

Для функции `predict(...)` используется именованный вызов (kwargs), поэтому фактический порядок аргументов в call-site не критичен.

### Шаг 3. Формирование сетки `pred_ts`

В `inference.predict(...)` вызывается:

```python
_, pred_timestamps = get_pred_timestamps(timestamps[0], step, output_range)
```

Это формирует временную сетку прогноза на `output_range` точек с шагом `step`.

### Шаг 4. Вызов model adapter

`predict(...)` собирает `PredictionInput` и вызывает:

```python
prediction_output = model.predict(prediction_input)
```

Далее:

- `predictions` приводятся к numpy,
- обрезаются до `output_range`,
- если точек меньше, паддятся `NaN` до длины `output_range`.

### Шаг 5. Обработка ошибки инференса

Если внутри `predict(...)` произошло исключение:

- логируется ошибка,
- возвращаются `NaN`-предсказания длины `output_range`,
- `is_matching = False`.

Важно: в текущей реализации `src/api/forecast/inference.py::predict(...)` ловит исключения внутри себя и обычно не пробрасывает их наружу.

Поэтому основной runtime-путь при ошибке инференса:

- `predict(...)` возвращает `NaN`-массив и `is_matching=False`,
- дальнейшая обработка выполняется в Stage6 (через `quality/status` логику `_build_result`).

Внешний `try/except` в `logic(...)` вернёт:

- `HTTPMessages.unprocessable_entity_forecast(...)` (`422`).

только если исключение возникло на уровне вызова (до/вне внутреннего `except` функции `predict(...)`).

## 4. Ошибки и защитные поведения

### 4.1 Ошибка инициализации модели

- Источник: `init_model(...)`
- Причины: unsupported `model_type`, отсутствующий model file без fallback, ошибка загрузки артефакта
- Результат: исключение уходит в глобальный `except` -> `500 internal_server_error`

### 4.2 Ошибка в прогнозе

- Источник: `predict(...)`/adapter
- Базовый результат: `predict(...)` возвращает `NaN`-прогноз и `is_matching=False`, pipeline продолжается
- `unprocessable_entity_forecast(...)` (`422`) возможен при исключении на уровне вызова `predict(...)` в `logic(...)`

### 4.3 Частично заполненный прогноз

- Источник: модель вернула меньше точек, чем `output_range`
- Результат: массив дополняется `NaN`, pipeline продолжается

## 5. Как проверить этап

### Проверка 1. Базовый offline-инференс

```bash
cd ml-server
make test-predict PREDICT_MODEL_ID=xgb
```

Ожидание:

- модель успешно инициализируется,
- формируются `preds` и `pred_ts`,
- запрос переходит на Stage6.

### Проверка 2. Ошибка model file (без fallback)

- Настроить модель с `model_type=xgb` или `prophet`, удалить соответствующий файл в bundle/cache и выставить `fallback=none`.
- Выполнить predict.

Ожидание:

- возврат `500` (internal_server_error) из worker payload.

### Проверка 3. Fallback model

- Для той же ошибки model file выставить `fallback=naive` (или другой поддерживаемый).

Ожидание:

- модель инициализируется через fallback,
- pipeline не падает на Stage5.

## 6. Операционный чеклист

- [ ] `init_model(...)` вызван с `step`, `fallback`, `model_type` из runtime-конфига.
- [ ] `predict(...)` получил `step` и `output_range` из конфига.
- [ ] Сетка `pred_ts` построена через `get_pred_timestamps(...)`.
- [ ] Результат прогноза нормализован до длины `output_range`.
- [ ] Ошибки инференса возвращаются как `422`, а не скрыто.
- [ ] Контекст (`preds`, `pred_ts`, `is_matching`) готов для Stage6.

## 7. Связь с соседними этапами

- Предыдущий файл: `docs/workflow/WORKFLOW_STAGE4.md`
- Следующий файл: `docs/workflow/WORKFLOW_STAGE6.md`
- Что передаётся дальше:
  - `preds`, `pred_ts`, `is_matching`
  - `timestamp`, `value`, `qds`
  - `config.clip_negatives_to_0`
  - `planned_adjustments` (если есть)
