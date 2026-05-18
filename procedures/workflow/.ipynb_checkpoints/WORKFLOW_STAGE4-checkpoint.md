# WORKFLOW STAGE 4: Сбор входных данных

## 1. Цель этапа

Собрать входные данные для инференса на основе runtime-конфига из Stage3:

- загрузить historical series для model input,
- опционально загрузить weather payload,
- опционально загрузить CMMS planned adjustments,
- вернуть управляемую ошибку при недоступности обязательного источника historical data.

Граница этапа: завершается, когда получены и проверены `timestamp`, `value`, `health_flag`, а также подготовлены опциональные `weather_data` и `planned_adjustments`.

Важно: на этом этапе используется только набор параметров `step` (мс), `input_range`, `output_range` из runtime-конфига. Отдельный параметр `mode` не используется.

Вход Stage4: `config` (`ModelConfig`) уже нормализован из единого сырого формата `cache_config.json` с объектом `sources` (см. Stage3).

## 2. Точки входа в коде

- `src/api/broker/tasks/predict.py` -> `_get_historical_data_payload(...)`
- `src/api/broker/tasks/predict.py` -> `_get_weather_payload(...)`
- `src/api/broker/tasks/predict.py` -> `_get_planned_adjustments(...)`
- `src/api/collector/historical_client.py` -> `fetch_model_data(...)`
- `src/api/collector/cmms_client.py` -> `fetch_planned_series(...)`

## 3. Пошаговая логика на уровне кода

### Шаг 1. Сбор historical data

Внутри `logic(...)` вызывается:

```python
output = await _get_historical_data_payload(config, step, input_range, output_range, online)
if isinstance(output, dict):
    return output
```

`_get_historical_data_payload(...)` прокидывает параметры в historical client:

```python
return await get_historical_data_client().fetch_model_data(
    archives=config.archives,
    step=step,
    input_range=input_range,
    output_range=output_range,
    online=online,
    historical_data_url=config.historical_data_url,
    request_overrides=config.historical_data_request_overrides,
)
```

На этом шаге используются нормализованные поля `ModelConfig`:

- `config.archives`
- `config.historical_data_url`
- `config.historical_data_request_overrides`
- `step`, `input_range`, `output_range`

Если вместо кортежа данных вернулся dict с ошибкой (`status >= 400`) или `JSONResponse`, задача завершается на этом месте с соответствующим payload.

### Шаг 2. Построение historical request window

В `HistoricalDataClient.build_request(...)` окно вычисляется из `step`, `input_range`, `output_range`:

- `to` = текущий час UTC,
- `from` = `to - history_points * step`,
- `history_points = input_range`, если задан и `> 0`, иначе `output_range`.

Базовый payload:

```json
{
  "from": 1714412400000,
  "to": 1714585200000,
  "archive": ["..."],
  "step": 3600
}
```

Правила валидации:

- `archives` не пустой,
- `step > 0`,
- `output_range > 0`.

`request_overrides` может переопределить `from`/`to`/`step`.

### Шаг 3. Нормализация historical response

После HTTP-вызова historical client:

- валидирует структуру `{archive_name: [[timestamp, value], ...]}`,
- преобразует series в numpy-массивы,
- при `online == false` интерполирует пропуски,
- возвращает `ModelData = (timestamps_list, values_list, qds_list)`.

В `logic(...)` сразу выполняется guard:

```python
if not timestamp or not value or len(timestamp[0]) == 0:
    return HTTPMessages.model_launch_aborted_no_data()
```

### Шаг 4. Опциональная загрузка weather

Погодные данные загружаются только если в конфиге заданы `weather_lat` и `weather_lon`:

```python
weather_data = await _get_weather_payload(config, output_range)
```

Внутри используется `hours = config.weather_hours or max(output_range, 1)`.

Источник значений: `config.weather_lat`, `config.weather_lon`, `config.weather_url`, `config.weather_units`, `config.weather_hours`.

Если weather недоступен или падает исключение, возвращается `None`, этап не прерывается.

### Шаг 5. Опциональная загрузка CMMS planned adjustments

После получения прогноза вызывается:

```python
planned_adjustments = await _get_planned_adjustments(config, step, output_range)
```

В `CMMSClient.build_request(...)` окно строится как future horizon:

- `from` = текущий час UTC,
- `to` = `from + output_range * step`.

Базовый payload:

```json
{
  "from": 1714585200000,
  "to": 1714758000000,
  "step": 3600
}
```

`request_overrides.range_size` может переопределить длину окна, `from/to` также можно задать явно.

Источник значений: `config.cmms_url` и `config.cmms_request_overrides`.

Если CMMS недоступен, этап деградирует мягко: возвращается `None` и прогноз продолжается без planned-корректировок.

## 4. Ошибки и защитные поведения

### 4.1 Невалидные параметры historical request

- Источник: `HistoricalDataClient.build_request(...)`
- Условия: пустой `archives`, `step <= 0`, `output_range <= 0`
- Результат: `unprocessable_entity_historical_data(...)`

### 4.2 Historical source недоступен

- Источник: сетевой сбой/ошибка historical API
- Результат:
  - если включен `HISTORICAL_DATA_STUB_ENABLED` -> синтетические данные,
  - иначе возвращается ошибка (`service_unavailable_historical_data` или `unprocessable_entity_historical_data`).

### 4.3 Historical payload пустой

- Источник: после нормализации `timestamp/value` пустые
- Результат: `model_launch_aborted_no_data()`

### 4.4 Weather/CMMS недоступны

- Источник: ошибка weather/CMMS вызова
- Результат: лог warning + продолжение pipeline без соответствующего источника.

## 5. Как проверить этап

### Проверка 1. Базовый predict с рабочей offline-моделью

```bash
cd ml-server
make test-predict PREDICT_MODEL_ID=model3
```

Ожидание:

- historical данные успешно получены,
- этап доходит до инференса,
- итоговый статус `DONE`.

### Проверка 2. Ошибка historical API

```bash
curl -sS -X POST http://localhost:8030/predict \
  -H "Content-Type: application/json" \
  -d '{"object_reference":"/root/FP/PROJECT/AKMOLA/@regions/does-not-exist","model_id":"model3"}'
```

Ожидание:

- при недоступном historical source задача завершается с ошибкой источника данных,
- при включенном historical stub задача продолжает выполнение.

### Проверка 3. Проверка деградации weather/CMMS

- Отключить/исказить `weather_url` или `cmms_url` в runtime-конфиге модели.
- Выполнить predict.

Ожидание:

- прогноз не падает только из-за weather/CMMS,
- в логах есть предупреждения о недоступности источника.

## 6. Операционный чеклист

- [ ] Historical запрос сформирован из `step`, `input_range`, `output_range`.
- [ ] `archives` и `step` присутствуют в payload historical client.
- [ ] Исторические данные преобразованы в `timestamp/value/health_flag`.
- [ ] Пустой historical input отсекается через `model_launch_aborted_no_data`.
- [ ] Weather загружен опционально и не блокирует этап при ошибке.
- [ ] CMMS planned payload загружен опционально и не блокирует этап при ошибке.
- [ ] Контекст (`timestamp`, `value`, `health_flag`, `weather_data`, `planned_adjustments`) готов для следующего этапа.

## 7. Связь с соседними этапами

- Предыдущий файл: `docs/workflow/WORKFLOW_STAGE3.md`
- Следующий файл: `docs/workflow/WORKFLOW_STAGE5.md`
- Что передаётся дальше:
  - `timestamp`, `value`, `health_flag`
  - `weather_data`
  - `planned_adjustments`
  - `step`, `input_range`, `output_range`
  - `model`, `model_id`, `online`
