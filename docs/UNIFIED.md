# ML Server — Сводная документация

> Автор сводки: сгенерировано автоматически на основе исходного кода и существующих MD-файлов.  
> Дата: 2026-04-16  

---

## Содержание

1. [Обзор архитектуры](#1-обзор-архитектуры)
2. [Структура проекта (FHS)](#2-структура-проекта-fhs)
3. [Установка и запуск](#3-установка-и-запуск)
4. [Конфигурация](#4-конфигурация)
5. [API: единственный эндпоинт `/predict`](#5-api-единственный-эндпоинт-predict)
   - [Схема запроса: создание (1-й запрос)](#51-схема-запроса-создание-1-й-запрос)
   - [Схема запроса: опрос результата (2-й запрос)](#52-схема-запроса-опрос-результата-2-й-запрос)
   - [HTTP ответы и сообщения](#53-http-ответы-и-сообщения)
6. [Брокер задач (TaskIQ + Redis)](#6-брокер-задач-taskiq--redis)
7. [Модели](#7-модели)
8. [Внешние зависимости](#8-внешние-зависимости)
9. [Хранение и MLflow](#9-хранение-и-mlflow)
10. [Противоречия — сводная таблица](#10-противоречия--сводная-таблица)

---

## 1. Обзор архитектуры

ML Server — сервис для запуска математических моделей прогнозирования временных рядов. Используется в связке с источниками данных, например SCADA-системой, провайдером данных прогноза погоды и тд.

**Компоненты:**

- **FastAPI** (`src/api/server.py`) — HTTP-сервер, порт 8000 (внутренний; внешний задаётся через `.env`)
- **TaskIQ** (`src/api/broker/`) — асинхронный брокер задач поверх Redis Streams
- **Redis** — очередь задач + результаты (TTL 1 час)
- **MLflow** — трекинг экспериментов, хранение метаданных моделей

**Поток выполнения:**

```
Клиент (1-й POST /predict)
    → FastAPI принимает, отправляет задачу в Redis Stream
    → Возвращает 202 START + task_id

Клиент (2-й POST /predict с task_id)
    → FastAPI проверяет результат в Redis
    → 202 PROCESSING (ещё не готово) ИЛИ 200 DONE (готово)

TaskIQ Worker (фоново)
    → Берёт задачу из Redis Stream
  → Разрешает model_id через MLflow Registry по alias/version и синхронизирует bundle в локальный cache
  → Загружает runtime-конфиг из bundle/configuration/cache_config.json и определяет параметры прогноза
    → Забирает историю из SCADA и при наличии координат дополнительно запрашивает погоду
  → Загружает модель из cached MLflow bundle/model (или работает в online-режиме для model_id = "none")
  → При отсутствии MLflow bundle/config для offline-модели возвращает 503; fallback к `/workspace/models` для offline не используется
    → Выполняет прогноз
    → Сохраняет результат в Redis
```

---

## 2. Структура проекта (FHS)

```
models/                  ← обученные модели (монтируется в /workspace/models)
mlruns/                  ← артефакты MLflow (в .gitignore)
lib/                     ← библиотеки, включая fpforecast (репозиторий)
ml-server/
├── docker/
│   ├── .dockerignore
│   ├── Dockerfile
│   └── docker-compose.yaml
├── docs/                    ← документация
├── fp/                      ← модуль прогнозирования к SCADA (модуль устарел и не используется)
└── src/
    └── api/
        ├── broker/
        │   ├── tasks/
        │   │   ├── __init__.py
        │   │   └── predict.py   ← логика задачи
        │   ├── __init__.py
        │   └── broker.py        ← определение брокера и task-декоратора
        ├── data/
        │   ├── __init__.py
        │   └── predict.py       ← Pydantic-схемы входных данных
        ├── forecast/
        │   ├── __init__.py
        │   ├── config.py        ← ModelConfig + load_model_config (MLflow bundle cache_config)
        │   ├── date.py
        │   ├── enums.py
        │   ├── evaluation.py
        │   ├── inference.py
        │   └── model.py         ← загрузка модели (init_model)
        ├── collector/
        │   ├── __init__.py
        │   ├── collector.py      ← получение данных из НДЦ
        ├── utils/
        │   ├── __init__.py
        │   ├── other.py
        │   ├── schema.py
        │   └── timestamps.py
        ├── __init__.py
        ├── config.py            ← все константы и переменные среды
        ├── message.py           ← формирование HTTP-ответов
        └── server.py            ← FastAPI приложение, /predict эндпоинт
```

**Пути в контейнере:**

| Хост                        | Контейнер          | Назначение              |
|-----------------------------|--------------------|-------------------------|
| `ml-server/src`             | `/workspace/server`| код API                 |
| `../local/${MODEL}`         | `/workspace/models`| обученные модели        |
| `../lib`                    | `/workspace/lib`   | библиотека моделей      |
| `../mlruns`                 | `/mlflow/mlruns`   | артефакты MLflow        |

---

## 3. Установка и запуск

### Первичная установка

```bash
# 1. Скопируйте .env.example → .env и заполните переменные
cp .env.example .env

# 2. Соберите Docker-образ (требуется SSH-доступ для приватных git-пакетов)
docker buildx build --ssh default --load -t fpcloud/ml:1.0.0 -f ./docker/Dockerfile .

# 3. Запустите контейнеры
docker compose -f docker/docker-compose.yaml up -d
```

> **Внимание:** Код `src/api/` монтируется в контейнер с хоста — не копируется внутрь образа.
> При изменении файлов API нужно перезапустить контейнер (`down` → `up`).

### Запустятся контейнеры

- **ml_model** — запускает одновременно TaskIQ worker и uvicorn API-сервер (порт 8000 внутренний)
- **redis** — брокер сообщений и хранилище результатов
- **mlflow** _(опционально)_ — UI на порту `${MLFLOW_PORT:-5050}`

### Локальная разработка (без Docker)

```bash
export PYTHONPATH=./src
python3.13 -m uvicorn api.server:app --reload --host 0.0.0.0 --port 8000

# В отдельном терминале — воркер:
taskiq worker api.broker:broker
```

### Перезапуск и диагностика

```bash
docker-compose down && docker-compose up -d --build
docker-compose logs -f ml_model
docker-compose ps
```

### Тесты

```bash
pytest -q
# Часть тестов требует запущенного Redis
```

---

## 4. Конфигурация

Файл: `src/api/config.py`. Значения могут быть переопределены через `.env`.

### Redis

| Переменная      | Описание                              | Значение по умолчанию   |
|-----------------|---------------------------------------|-------------------------|
| `REDIS_URL`     | URL Redis-сервера                     | `redis://redis:6379/0`  |
| `REDIS_TIMEOUT` | TTL результата в секундах             | `3600` (1 час)          |

### НДЦ (архивы данных)

| Переменная  | Описание                    | Значение по умолчанию                              |
|-------------|-----------------------------|----------------------------------------------------|
| `HISTORICAL_DATA_HOSTS` | Список хостов НДЦ | `["10.210.1.11", "10.210.1.13", "10.210.1.15"]`   |
| `HISTORICAL_DATA_URLS`  | URL-адреса API НДЦ | `http://{host}:7080/api/read/archive` для каждого  |

### Ремонты (CMMS)

| Переменная | Описание       | Источник              |
|------------|----------------|-----------------------|
| `CMMS_URL` | URL сервиса ремонтов | сервис CMMS; в текущем коде встречаются и исторические обозначения `RZ_URL` / `RZ_API_URL` |

### Общие

| Переменная            | Описание                             | Значение по умолчанию            |
|-----------------------|--------------------------------------|----------------------------------|
| `HEADERS`             | HTTP-заголовки для внешних запросов  | `{"Content-Type": "application/json"}` |
| `CLIENT_TIMEOUT_ONE`  | Таймаут одного запроса (сек)         | `30`                             |
| `CLIENT_TIMEOUT_ALL`  | Таймаут всех запросов (сек)          | `150` (30 × 5)                   |
| `GMT_TO_ASTANA_HOURS` | Смещение GMT → Астана (часы)         | `5`                              |

### .env (переменные Docker Compose)

| Переменная   | Описание                              | По умолчанию |
|--------------|---------------------------------------|--------------|
| `MODEL`      | Имя папки с моделями внутри `local/`  | `models`     |
| `PORT`       | Внешний порт хоста для API            | `18888`      |
| `REDIS_PORT` | Внешний порт Redis                    | `6379`       |
| `MLFLOW_PORT`| Внешний порт MLflow UI                | `5050`       |
| `CMMS_URL` | URL сервиса ремонтных данных          | —            |

---

## 5. API: единственный эндпоинт `/predict`

**URL:** `POST /predict`  
**Content-Type:** `application/json` (вход и выход)

Работает в два шага:

1. **Создание задачи** — передаёте параметры прогноза → получаете `task_id`
2. **Опрос результата** — передаёте `task_id` → получаете статус или готовый результат

Разграничение схем происходит автоматически: если в теле запроса есть поле `task_id` — используется схема опроса, иначе — схема создания.

---

### 5.1 Схема запроса: создание (1-й запрос)

> Pydantic-класс `PredictCreateSchema` (`src/api/data/predict.py`)

Клиент передаёт `object_reference`, опциональный `model_id` и опциональный `model_selection`.
Все runtime-параметры прогноза (`archives`, `step`, `output_range` и др.)
сервер читает самостоятельно из MLflow serving bundle `cache_config.json`.

#### Поля

| Поле               | Тип   | Обязательно | По умолчанию | Описание                                                        |
|--------------------|-------|-------------|--------------|------------------------------------------------------------------|
| `object_reference` | `str` | ✅           | —            | Путь к FP-объекту. Должен содержать `/` или `\`                 |
| `model_id`         | `str` | ❌           | `"none"`     | Путь к модели относительно `/workspace/models`. `"none"` = онлайн-обучение |

#### Внутреннее вычисляемое поле (нельзя передать извне)

| Поле     | Описание                          |
|----------|-----------------------------------|
| `online` | `true`, если `model_id == "none"` |

#### Валидация

- `object_reference` — не пустое, содержит `/` или `\`
- `model_id` — не пустое
- Схема строгая: лишние поля запрещены (`extra = "forbid"`)

#### Пример запроса

```json
{
  "object_reference": "/KAZ/AKMOLA/AKMOLA/@models/P_WATT",
  "model_id": "prophet/watt/h/AKMOLA/@regions/Akmola/load"
}
```

---

### 5.1.1 Конфигурация модели (`cache_config.json`)

Для offline serving runtime-конфиг лежит в MLflow bundle: `bundle/configuration/cache_config.json`.
Этот файл описывает, какие источники данных нужны модели и с какими параметрами их запрашивать.

**Логическая роль файла:**

- хранит описание источников данных для модели
- задаёт параметры запросов к historical_data, weather, CMMS и другим источникам
- используется сервером во время инференса; сервер сам этот файл не генерирует

**Пример структуры `cache_config.json`, который реально поддерживается текущим runtime:**

```json
{
  "short": {
    "input_range": 72,
    "output_range": 24,
    "step": 3600,
    "by-pass": false,
    "sources": [
      {
        "type": "historical_data",
        "pattern": "historic",
        "url": "http://127.0.0.1:7080/api/v1/read/archives",
        "request_body": {
          "archive": [
            "/root/FP/PROJECT/AKMOLA/@subjects/Kokshetau/purchase/archives/out_value"
          ],
          "step": 3600
        }
      },
      {
        "type": "weather",
        "pattern": "future",
        "url": "http://127.0.0.1:8050/api/v1/forecast",
        "request_body": {
          "measurements": [
            "pressure",
            "temperature",
            "wind_speed",
            "wind_direction",
            "humidity",
            "cloudiness",
            "precipitation"
          ]
        },
        "location": {
          "latitude": 51.1605,
          "longitude": 71.4704
        }
      },
      {
        "type": "cmms",
        "pattern": "planned",
        "url": "http://localhost:8000/api/v1/cmms",
        "request_body": {
          "state": "operational",
          "type": "generator"
        }
      }
    ]
  }
}
```

**Назначение секций:**

- `historical_data` описывает основной источник исторического ряда для прогноза
- `weather` описывает погодный источник, набор измерений и координаты точки
- `cmms` описывает сервис данных о ремонтах

**Нормализация, которую реально выполняет runtime:**

- `historic` sources используют `input_range`
- `future` и `planned` sources используют `output_range`
- для historical-data runtime нормализует `sources[*]` в `archives`, `historical_data_url` и `historical_data_request_overrides`
- для weather runtime нормализует `location` и рассчитывает `weather_hours`
- для CMMS runtime нормализует `cmms_request_overrides` и применяет planned-снижения на этапе postprocessing прогноза

**Плоский internal ModelConfig после нормализации:**

| Поле                          | Тип         | Описание                                           |
|-------------------------------|-------------|----------------------------------------------------|
| `archives`                    | `List[str]` | Пути FP-архивов (НДЦ) из historical_data source    |
| `step`                        | `int`       | Шаг прогноза в секундах, далее конвертируется в мс |
| `input_range`                 | `int?`      | Размер исторического окна                          |
| `output_range`                | `int`       | Горизонт прогноза                                  |
| `historical_data_url`         | `str?`      | Персональный URL historical_data для модели        |
| `historical_data_request_overrides` | `Dict` | Нормализованный request body для historical_data   |
| `weather_lat` / `weather_lon` | `float?`    | Координаты для weather source                      |
| `weather_hours`               | `int?`      | Горизонт weather source, выводится из `pattern`    |
| `cmms_url`                    | `str?`      | URL CMMS source                                    |
| `cmms_request_overrides`      | `Dict`      | Нормализованный request body для CMMS              |

**Режим прогноза** определяется автоматически из `step` (в мс после конвертации):

| Режим    | Условие на step_ms                      | Единица `output_range` |
|----------|-----------------------------------------|------------------------|
| `short`  | `step_ms < 86 400 000`                 | часы                   |
| `medium` | `86 400 000 ≤ step_ms < 2 419 200 000` | месяцы                 |
| `long`   | `step_ms ≥ 2 419 200 000`              | годы                   |

---

### 5.2 Схема запроса: опрос результата (2-й запрос)

> Pydantic-класс `PredictUpdateSchema`

| Поле      | Тип    | Обязательно | Описание                          |
|-----------|--------|-------------|-----------------------------------|
| `task_id` | `str`  | ✅           | UUID задачи, полученный из 1-го запроса |

#### Пример

```json
{
  "task_id": "5c852360dce04d399eeaaedd947459ba"
}
```

---

### 5.3 HTTP ответы и сообщения

#### 202 — Задача принята (START)

Возвращается сразу после 1-го запроса.

```json
{
  "status": 202,
  "state": "start",
  "task_id": "...",
  "object_reference": "..."
}
```

> ⚠️ **ПРОТИВОРЕЧИЕ #5** — `MESSAGES.md` показывает ключ `"fp_path"` в этом ответе. В коде (`message.py`) используется **`"object_reference"`**. Актуальный ключ — `object_reference`.

#### 202 — В обработке (PROCESSING)

Возвращается при опросе, если задача ещё выполняется или результат удалён из Redis.

```json
{
  "status": 202,
  "state": "processing",
  "task_id": "..."
}
```

#### 200 — Успешно (DONE)

```json
{
  "status": 200,
  "state": "done",
  "task_id": "...",
  "object_reference": "...",
  "data": {
    "message": "",
    "output": [
      [1774569600000, 660.2, 64],
      ...
    ],
    "quality": 64,
    "model_confidence": 1.0
  }
}
```

**Формат каждого элемента `output`:** `[timestamp_ms, value, qds]`

> ⚠️ **ПРОТИВОРЕЧИЕ #6** — `MAIN.md` показывает ключ `"fp_path"` на верхнем уровне 200-ответа. В коде (`broker.py`) добавляется **`"object_reference"`**. Актуальный ключ — `object_reference`.

> ⚠️ **ПРОТИВОРЕЧИЕ #7** — `model_confidence` в документации упоминается как значимая метрика. В коде **всегда захардкожено `1.0`** (`result.py`, строка `"model_confidence": 1.0`). Реальная логика не реализована.

#### 422 — Ошибка валидации входных данных

```json
{
  "status": 422,
  "message": "A valid JSON format was expected, but the data was not received or was invalid.",
  "details": {"predict_create": ["'step' : Value error, 'step' must be greater than 0"]}
}
```

#### 422 — Некорректные данные от НДЦ

```json
{
  "status": 422,
  "state": "done",
  "task_id": "...",
  "object_reference": "...",
  "message": "Incorrect data in the dataset from archives.",
  "quality": 12
}
```

#### 422 — Нет данных для запуска модели

Возникает, когда НДЦ вернул пустые данные. Модель не запускается.

```json
{
  "status": 422,
  "state": "done",
  "task_id": "...",
  "object_reference": "...",
  "message": "Model launch aborted: no input data received from archives."
}
```

#### 422 — Ошибка прогноза

```json
{
  "status": 422,
  "state": "done",
  "task_id": "...",
  "object_reference": "...",
  "message": "Forecast execution error: {текст ошибки}"
}
```

#### 500 — Внутренняя ошибка

```json
{
  "status": 500,
  "state": "done",
  "task_id": "...",
  "object_reference": "...",
  "message": "Internal server error: {текст ошибки}"
}
```

#### 503 — Внешний сервис недоступен

```json
{
  "status": 503,
  "state": "done",
  "task_id": "...",
  "object_reference": "...",
  "message": "HISTORICAL_DATA is not available, so it is impossible to take values ​​at this time."
}
```

Для сервиса ремонтов (CMMS) применяется тот же шаблон ошибки недоступности. В части текущего кода и старой документации этот источник ещё может называться `RZ`.

> ⚠️ **ПРОТИВОРЕЧИЕ #8** — `MESSAGES.md` для всех ответов типа 422/500/503 показывает ключ `"fp_path"`. В коде везде используется **`"object_reference"`**.

---

## 6. Брокер задач (TaskIQ + Redis)

Файлы: `src/api/broker/broker.py`, `src/api/broker/tasks/predict.py`

- Брокер: `RedisStreamBroker` (TaskIQ)
- Бэкенд результатов: `RedisAsyncResultBackend`, TTL = `REDIS_TIMEOUT` (3600 сек)
- Задача `api_predict` регистрируется декоратором `@broker.task`

**Жизненный цикл задачи:**

1. Клиент делает 1-й POST → `api_predict.kiq(data)` → задача в очереди Redis Stream
2. Worker подхватывает задачу → выполняет `predict_logic(...)` → записывает в Redis
3. Клиент делает 2-й POST → `is_result_ready(task_id)` → если готово → `get_result(task_id)`

> ⚠️ **ПРОТИВОРЕЧИЕ #9 (критическое)** — В `broker/tasks/predict.py` **вызов НДЦ закомментирован**:
> ```python
> # output = await get_data_from_arvhives(mode, archives, step, online)
> # if isinstance(output, dict): return output
> ```
> Вместо реальных данных используются **захардкоженные тестовые значения**.
> Это либо временная отладка, либо незавершённый рефакторинг. Сервис в таком виде не работает с реальными данными НДЦ — см. [вопрос №2](#вопросы).

---

## 7. Модели

Файл: `src/api/forecast/model.py` — функция `init_model`

### Типы моделей

| `model_id`     | Тип            | Файл модели               | Описание                                       |
|----------------|----------------|---------------------------|------------------------------------------------|
| `"none"`       | Prophet онлайн | —                         | Обучается на входных данных в момент запроса   |
| `"xgb/..."`    | XGBoost AR     | `xgb_model.json`          | Загружается из `/workspace/models/xgb/...`     |
| `"prophet/..."` | Prophet       | `prophet_model.json`      | Загружается из `/workspace/models/prophet/...` |

> ⚠️ **ПРОТИВОРЕЧИЕ #10** — Тип модели **`"sbre"`** реализован в коде, но нигде не задокументирован. Класс `SbreModel` пустой (`pass`). Назначение неизвестно — см. [вопрос №3](#вопросы).

### Структура папки модели

```
local/models/
└── {тип}/{путь}/
    ├── xgb_model.json      ← для XGBoost
    ├── prophet_model.json  ← для Prophet
    ├── meta.json           ← метаданные (версия, метрики, дата обучения)
    └── config.yaml         ← конфигурация источников данных
```

Внутри контейнера: `/workspace/models/{model_id}`.

### Как добавить новый тип модели

1. Добавить логику загрузки в `init_model` в `src/api/forecast/model.py`
2. Убедиться, что `predict()` в `inference.py` поддерживает новый класс и возвращает `(preds, pred_ts, is_matching)`
3. Добавить тесты в `src/tests/`

### Динамическая нормализация

Поддерживается только для `ModelWithMetaInfoAr` (XGBoost AR). Для остальных типов игнорируется без ошибки.

---

## 8. Внешние зависимости

### НДЦ (архивы временных рядов)

- Файл: `src/api/send/archives.py`
- Функции: `get_data_from_arvhives` (публичная), `send_ndc_url`, `extract_data`
- Адреса: `HISTORICAL_DATA_URLS` из `config.py`
- Формат ответа: `[timestamps_array, values_array, qds_array]`

### CMMS (ремонтные данные)

- Файл: `src/api/collector/cmms_client.py`
- Назначение: HTTP-клиент для сервиса-источника данных о ремонтах
- URL: `CMMS_URL` в новой схеме; в части текущего кода и старых документов ещё встречается историческое имя `RZ_URL`
- Статус: путь CMMS подключён в active predict pipeline как postprocessing
- Формат planned payload: объект вида `{equipment_code: [events...]}`
- Ключевые поля события: `p_descent`, `start_requested`, `end_requested`

---

## 9. Хранение и MLflow

### Структура хранения моделей

MLflow использует гибридный подход:

- **Backend Store (метаданные):** `sqlite:///mlflow_data/mlflow.db` — метрики, параметры, теги, run ID
- **Artifact Store (артефакты):** `./mlflow_data/artifacts` — бинарные файлы моделей, графики

### Концепция «Паспорт данных»

При обучении в MLflow артефакты должны публиковаться в serving-совместимом bundle. При запуске прогноза сервер разрешает `model_id` + selector в Registry, скачивает `bundle` и использует `bundle/configuration/cache_config.json` как runtime-конфиг.

### MLflow UI

```
http://localhost:${MLFLOW_PORT:-5050}
```

### Скачать артефакт модели из MLflow

```bash
mlflow artifacts download --run-id <run-id> --path <artifact-path> -d /tmp/model_artifacts
ls /tmp/model_artifacts/bundle
```

---

## 10. Противоречия — сводная таблица

| №  | Источник                      | Что написано в документации             | Что в коде / как есть                     | Статус        |
|----|-------------------------------|-----------------------------------------|-------------------------------------------|---------------|
| 1  | `MAIN.md`, `PREDICT.md`       | Поле `fp_path` в запросе                | Переименовано в `object_reference`        | ✅ Исправлено |
| 2  | `MAIN.md`, `PREDICT.md`       | Поле `model_path` в запросе             | Переименовано в `model_id`                | ✅ Исправлено |
| 3  | `PREDICT.md`, `MAIN.md`       | Поле `version` (обязательное)           | Публичный selector теперь вынесен в `model_selection.version` / `model_selection.version_alias` | ✅ Исправлено |
| 4  | `PREDICT.md`                  | `archives`, `step` и др. — в запросе   | Перенесены в MLflow runtime bundle config | ✅ Исправлено |
| 5  | `MESSAGES.md`                 | Ключ `"fp_path"` в ответах              | Ключ `"object_reference"`                 | ✅ Исправлено |
| 6  | `MAIN.md` (пример 200-ответа) | `model_confidence` — значимая метрика   | Всегда `1.0`, логика не реализована       | ⚠️ Открыто   |
| 7  | `broker/tasks/predict.py`     | Описан поток с НДЦ                      | Вызов НДЦ **временно** закомментирован    | ⏳ Временно   |
| 8  | Вся документация              | Режимы: `day` / `month` / `year`        | Переименованы: `short` / `medium` / `long`| ✅ Исправлено |
| 9  | Вся документация              | Тип модели `"sbre"` / класс `SbreModel` | Удалены из кода                           | ✅ Исправлено |

---

