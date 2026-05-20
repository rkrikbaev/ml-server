# WORKFLOW STAGE 3: Выполнение worker-задачи

## 1. Цель этапа

Принять задачу из очереди и подготовить контекст для последующего сбора данных и инференса:

- разрешить offline-модель через MLflow Registry по `model_id` и selector,
- загрузить и провалидировать runtime-конфиг модели, определить наличие обязательных полей,
- подготовить базовую структуру ответа для возврата в случае ошибок.

Граница этапа: завершается, когда обязательные параметры определены. Если конфиг не найден, задача завершается здесь с ошибкой.

Важно: фактический горизонт прогнозирования задаётся выбранным runtime-конфигом модели (`input_range`, `output_range`, `step`).

## 2. Точки входа в коде

- `src/api/broker/broker.py` -> `api_predict` (точка запуска worker)
- `src/api/broker/tasks/predict.py` -> `logic(model_id, online, selector)` 
- `src/adapters/config.py` -> `load_model_config(model_id)`
- `src/adapters/provider.py` -> `sync_with_registry(model_id, selector)`

## 3. Пошаговая логика на уровне кода

### Шаг 1. Worker берёт задачу из очереди

TaskIQ-worker запущен как отдельный процесс:

```bash
taskiq worker api.broker:broker --workers 8
```

При получении сообщения из Redis Stream worker вызывает:

```python
@broker.task
async def api_predict(data: Dict[str, Any]) -> Dict[str, Any]:
    output = await predict_logic(
        model_id=data["model_id"],
        online=data["online"],
        selector=data.get("selector"),
    )
    output["object_ref"] = data["object_ref"]
    return output
```

`predict_logic` — это алиас для `logic` из `src/api/broker/tasks/predict.py`.

### Шаг 2. Вход в `logic(model_id, online, selector)`

Функция `logic` обёрнута в глобальный `try/except`:

```python
async def logic(model_id: str, online: bool, selector: Optional[str] = None) -> Dict[str, Any]:
    try:
        ...
    except Exception as e:
        return HTTPMessages.internal_server_error(str(e))
```

Любое непойманное исключение внутри возвращает `500` как payload задачи.

### Шаг 3. Разрешение модели через MLflow Registry

Для offline-моделей (`model_id != "none"`) worker сначала вызывает:

```python
sync_result = get_model_provider().sync_with_registry(model_id, selector)
```

Что делает `sync_with_registry(...)`:

- определяет selector (`version_alias` или `version`, по умолчанию `Production`),
- разрешает `run_id` в MLflow Registry,
- скачивает artifact `bundle`,
- кеширует его в `/tmp/local_models_cache`,
- возвращает `bundle_path`, `model_path`, `config_path`, `run_id`.

Если registry недоступен:

- для offline-модели допустим только fallback к последнему успешно закешированному MLflow bundle того же `model_id`,
- fallback к `/workspace/models` для offline serving не используется,
- если закешированного bundle нет, worker завершает задачу с `503 MLFLOW`.

### Шаг 4. Загрузка runtime-конфига модели

```python
try:
    config = load_model_config(model_id, bundle_path=bundle_path, require_bundle=(model_id != "none"))
except Exception:
    ...
```

`load_model_config(model_id)` в `src/adapters/config.py`:

- Для offline serving читает `bundle/configuration/cache_config.json` из cached MLflow bundle
- Для online flow (`model_id == "none"`) fallback path допустим без registry bundle
- Нормализует raw config через `_parse_model_config_payload(...)`
- Создаёт и возвращает объект `ModelConfig` (pydantic-модель).

В проекте фиксируется один формат сырого `cache_config.json`:

```json
{
    "model_type": "xgb/prophet",
    "fallback": "none",
    "sources": {
        "step": 3600,
        "input_range": 168,
        "output_range": 24,
        "historical": {
            "type": "rest_api",
            "pattern": "historic",
            "archives": ["/root/FP/.../archives/out_value"],
            "url": "http://host.docker.internal:7080/api/v1/read/archives",
            "request_overrides": {
                "archive": ["/root/FP/.../archives/out_value"]
            }
        },
        "weather": {
            "type": "rest_api",
            "pattern": "forecast",
            "lat": 43.25,
            "lon": 76.92,
            "url": "http://127.0.0.1:8050/api/v1/forecast",
            "units": "metric",
            "hours": 24
        },
        "cmms": {
            "type": "rest_api",
            "pattern": "planned",
            "url": null,
            "request_overrides": {}
        }
    }
}
```

Если bundle/config не найден для offline-модели -> `service_unavailable_mlflow` -> `503`.

### Шаг 5. Структура `ModelConfig`

После нормализации `sources` в runtime используется плоский `ModelConfig`.

Ключевые поля с дефолтами:

| Поле | Тип | Дефолт | Описание |
|---|---|---|---|
| `step` | `int` | `3600` | Шаг прогноза в секундах |
| `output_range` | `int` | `48` | Количество шагов на выходе |
| `input_range` | `Optional[int]` | `None` | Глубина истории (None = авто) |
| `model_type` | `str` | `"prophet"` | Тип модели: `xgb/prophet/naive/ar` |
| `fallback` | `str` | `"none"` | Fallback-модель при ошибке |
| `archives` | `List[str]` | обязательно | Адреса архивов SCADA/historical |
| `historical_data_url` | `Optional[str]` | `None` | URL для historical data |
| `historical_data_request_overrides` | `Dict[str, Any]` | `{}` | Переопределения запроса historical source |
| `weather_lat/lon` | `Optional[float]` | `None` | Координаты для weather |
| `weather_url` | `Optional[str]` | `None` | URL weather-сервиса |
| `weather_units` | `str` | `"metric"` | Единицы погоды: `metric/imperial` |
| `weather_hours` | `Optional[int]` | `None` | Горизонт weather source в часах |
| `cmms_url` | `Optional[str]` | `None` | URL CMMS-сервиса |
| `cmms_request_overrides` | `Dict[str, Any]` | `{}` | Переопределения запроса CMMS source |
| `clip_negatives_to_0` | `bool` | `True` | Обрезать отрицательные прогнозы |

Связь с сырым `sources`:

- `sources.step` -> `config.step`
- `sources.input_range` -> `config.input_range`
- `sources.output_range` -> `config.output_range`
- `sources.historical.archives/url/request_overrides` -> historical поля `ModelConfig`
- `sources.weather.lat/lon/url/units/hours` -> weather поля `ModelConfig`
- `sources.cmms.url/request_overrides` -> cmms поля `ModelConfig`

Ограничения:
- `step > 0`
- `output_range > 0`
- `archives` не пустой
- `weather_lat` и `weather_lon` только в паре
- `weather_units` из множества `{metric, imperial}`
- `weather_hours > 0` (если задан)
- `model_type` из множества `{xgb, prophet, naive, ar}`
- `fallback` из множества `{none, naive, ar, prophet, xgb}`

### Шаг 6. Подготовка рабочих параметров из runtime-конфига

```python
step = config.step * 1000                                  # seconds → ms
input_range = config.input_range
output_range = config.output_range
```

Пояснение по смыслу параметров:

- `step` задаёт дискретность временной сетки (в мс внутри pipeline),
- `input_range` задаёт глубину входной истории (в точках),
- `output_range` задаёт горизонт прогноза (в точках).

Примеры:

| `config.step` (сек) | `config.input_range` (точек на входе) | `config.output_range` (точек на выходе) |
|---|---|---|
| 3600 (1 час) | 48 | 48 |
| 1800 (30 мин) | 96 | 96 |

`input_range` также трактуется как количество входных точек истории. Если в конфиге `input_range = None`, рабочее окно входа определяется логикой сборщика.

Итог: горизонт и окно данных задаются конфигом модели через `step`, `input_range`, `output_range`.

### Шаг 7. Загрузка файла модели с диска

Файл модели хранится в cached MLflow bundle рядом с runtime configuration:

```
/tmp/local_models_cache/<model>/<selector>/<version>/bundle/
├── model/
│   ├── prophet_model.json   # для model_type = "prophet"
│   └── xgb_model.json       # для model_type = "xgb"
└── configuration/
    └── cache_config.json
```

Вызывается в `src/adapters/model.py` -> `init_model(...)`, который строит адаптер по `model_type`:

| `model_type` | Файл модели | Адаптер |
|---|---|---|
| `prophet` | `prophet_model.json` | `ProphetAdapter` |
| `xgb` | `xgb_model.json` | `XGBoostAdapter` |
| `naive` | файл не нужен | `NaiveAdapter` |
| `ar` | файл не нужен | `ARAdapter` |

Если файл модели указан (`prophet`/`xgb`) но не найден:

- Проверяется поле `config.fallback`.
- Если `fallback != "none"` — создаётся fallback-адаптер и выдаётся предупреждение в лог.
- Если `fallback == "none"` — выбрасывается `FileNotFoundError`, которое всплывает в глобальный `except` -> `500`.

Онлайн-режим (`model_id == "none"`) создаёт новую Prophet-модель без registry bundle.

### Шаг 8. Контекст готов для следующих этапов

После успешного выполнения шагов 1–7 у worker есть:

- `config` — объект `ModelConfig`,
- `step` — шаг в миллисекундах,
- `input_range` — глубина входной истории в точках,
- `output_range` — количество точек прогноза,
- `model_id`, `online` — переданы из очереди.
- `model` — инициализированный адаптер (или fallback).

Эти значения используются во всех последующих этапах (4–6).

## 4. Ошибки и защитные поведения

### 4.1 MLflow bundle/config не найден

- Источник: исключение внутри `load_model_config`
- Результат: `503` + MLflow unavailable/config unavailable message как payload задачи
- Worker завершает задачу, пишет payload в result backend

### 4.2 Невалидные поля конфига

- Источник: pydantic-валидация `ModelConfig`
- Результат: исключение всплывает в `load_model_config`; для offline serving возвращается `503 MLFLOW`, для online flow возможно `422`

### 4.3 Файл модели не найден и fallback отключён

- Источник: `FileNotFoundError` в `init_model` при `fallback == "none"`
- Результат: `500` из глобального `except Exception as e`
- Файлы: `src/adapters/model.py` -> `init_model`

### 4.4 Непойманное исключение

- Источник: любое необработанное исключение в `logic`
- Результат: `500` из глобального `except Exception as e`

## 5. Как проверить этап

### Проверка 1. Просмотр конфига модели через UI

```bash
curl -sS "http://localhost:8030/ui/model-config?model_id=model3"
```

Ожидание:
- `200` с `raw_config` (то, что в файле) и `normalized_config` (то, что загружает `ModelConfig`).

### Проверка 2. Несуществующая offline-модель

```bash
curl -sS "http://localhost:8030/predict/nonexistent_model?object_ref=/root/FP/PROJECT/AKMOLA/@regions/does-not-exist"
```

Получить `task_id` из ответа, затем опросить `GET /tasks/{task_id}`. Ожидание:

- финальный ответ с `status: 503` и сообщением о недоступном MLflow bundle/config.

### Проверка 3. Корректная модель

```bash
cd ml-server
make test-predict PREDICT_MODEL_ID=model3
```

Ожидание: задача доходит до этапа 4 (сбор данных) без ошибки на этапе 3.

## 6. Операционный чеклист

Используйте этот список как быстрый контроль прохождения Stage3:

- [ ] Worker получил payload с `model_id`, `online` и опциональным `selector`.
- [ ] Для offline-модели выполнен `sync_with_registry(model_id, selector)`.
- [ ] Получен `bundle_path`; при промахе registry применён fallback только к cached MLflow bundle.
- [ ] Runtime config успешно загружен из `bundle/configuration/cache_config.json`.
- [ ] Подготовлены `step` (мс), `input_range`, `output_range` (в шагах).
- [ ] Модель инициализирована из `bundle/model` или через допустимый fallback.
- [ ] При ошибке bundle/config для offline возвращается `503 MLFLOW`.
- [ ] Контекст готов для Stage4 (сбор данных).

## 7. Связь с соседними этапами

- Предыдущий файл: `docs/workflow/WORKFLOW_STAGE2.md`
- Следующий файл: `docs/workflow/WORKFLOW_STAGE4.md`
- Что передаётся дальше:
  - `config` (`ModelConfig`)
    - `selector` (alias/version для MLflow Registry)
  - `step` (мс)
  - `input_range` (точек)
  - `output_range` (шагов)
  - `model` (инициализированный адаптер или fallback)
  - `model_id`, `online`
