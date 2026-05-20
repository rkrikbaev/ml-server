# Техническое задание: ML-инфраструктура для прогнозирования временных рядов

**Версия:** 1.0  
**Дата:** 16.04.2026  
**Статус:** На согласовании

---

## Содержание

1. [Общее описание системы](#1-общее-описание-системы)
2. [Архитектура системы](#2-архитектура-системы)
3. [Компоненты инфраструктуры](#3-компоненты-инфраструктуры)
4. [Пайплайн обучения (Train Pipeline)](#4-пайплайн-обучения-train-pipeline)
5. [Пайплайн инференса (Predict Pipeline)](#5-пайплайн-инференса-predict-pipeline)
6. [Управление моделями (MLflow)](#6-управление-моделями-mlflow)
7. [API-интерфейс](#7-api-интерфейс)
8. [Конфигурация и окружение](#8-конфигурация-и-окружение)
9. [Структура проекта](#9-структура-проекта)
10. [Требования к развёртыванию](#10-требования-к-развёртыванию)
11. [Нефункциональные требования](#11-нефункциональные-требования)
12. [Открытые вопросы](#12-открытые-вопросы)

---

## 1. Общее описание системы

### 1.1 Назначение

ML-сервер (далее Runner) обученных моделей предназначен для эксплуатации моделей прогнозирования временных рядов (нагрузка, энергопотребление) по объектам энергосистемы. Система обслуживает запросы от внешней SCADA-системы и реализует полный ML-пайплайн: сбор данных → загрузку модели → получение прогноза. Обучение моеделй происходит отдельно, пока под управлением инженера в тетрадках (Jupyter Notebook).

### 1.2 Основные возможности

- Прогнозирование временных рядов по произвольному объекту (регион, подстанция и т.д.)
- Хранение артефактов и метаданных моделей в MLflow
- Динамическое добавление новых объектов прогнозирования без изменения кода
- Сбор данных из нескольких внешних REST API в зависимости от конфигурации модели ("паспорт данных")

### 1.3 Потребитель системы

Внешняя pull-система (например SCADA система) взаимодействует с Runner через REST API интерфейс по протоколу HTTP. Запросы инициируются внешней системой (pull-система).

---

## 2. Архитектура системы

```
┌─────────────────────────────────────────────────────────┐
│                      pull-система                       │
└───────────────────────┬─────────────────────────────────┘
                        │ REST API (HTTP)
                        ▼
┌──────────────────────────────────────────────────────────┐
│                      Runner                              │
│                                                          │
│                      ┌─────────────┐                     │
│                      │  Predict    │                     │
│                      │  Pipeline   │                     │
│                      └──────┬──────┘                     │
│                             │                            │
│           ┌─────────────────▼───────────────┐            │
│           │         Data Loader             │            │
│           │  (REST API внешних источников)  │            │
│           └─────────────────────────────────┘            │
│                                                          │
│   ┌──────────────────────────────────────────────────┐   │
│   │                       MLflow                     │   │
│   │        Backend: SQLite  │  Artifacts: ./mlruns   │   │
│   └──────────────────────────────────────────────────┘   │
│                                                          │
│   ┌───────────┐                                          │
│   │   Redis   │  (кэш результатов / очередь задач)       │
│   └───────────┘                                          │
└──────────────────────────────────────────────────────────┘
```

### 2.1 Сервисы Docker Compose

| Сервис | Образ | Назначение |
|--------|-------|------------|
| `ml_model` | Собственный (Dockerfile) | Основной ML-сервер (FastAPI) |
| `mlflow` | `ghcr.io/mlflow/mlflow` | Трекинг экспериментов и хранение артефактов |
| `redis` | `redis:alpine` | Кэширование и опциональная очередь задач |

---

## 3. Компоненты инфраструктуры

### 3.1 Runner (основной сервис)

**Функции:**
- Приём и обработка HTTP-запросов от pull-системы
- Запуск пайплайна инференса
- Взаимодействие с MLflow (чтение/запись метаданных и артефактов)
- Взаимодействие с внешними REST API

**Технологический стек:**
- Python 3.10+
- FastAPI + Uvicorn
- Prophet, XGBoost, scikit-learn
- MLflow client
- httpx / requests (для data_loader)

**Монтируемые тома:**
```
./src                → /workspace/server   (серверный код)
/local_models_cache  → /workspace/models   (артефакты моделей)
```

**Переменные окружения:**
```
MLFLOW_TRACKING_URI=http://mlflow:5000
```

### 3.2 MLflow

**Схема хранения:**
- Backend Store (метаданные, теги, метрики, параметры): `sqlite:///mlflow_data/mlflow.db`
- Artifact Store (модели, датасеты, графики): `../locals/mlruns/<Experiment ID>/<Run ID>/artifacts`

**Монтируемые тома:**
```
../local/mlruns   → /mlflow/mlruns
mlflow_data       → /mlflow
```

**Команда запуска:**
```bash
mlflow server \
  --host 0.0.0.0 \
  --port 5000 \
  --backend-store-uri sqlite:///mlflow_data/mlflow.db \
  --default-artifact-root /mlflow/mlruns
```

### 3.3 Redis

Используется для:
- Кэширования результатов прогноза (опционально, TTL настраивается)
- Хранения промежуточных состояний долгих задач обучения

---

## 4. Пайплайн обучения (Train Pipeline)

### 4.1 Инициация

Обучение проводиться дата-инженером вручную в отдельной тетради `MODEL_DATA_COLLECTION.ipynb`.

**Точка входа:** Тетрадь в которой инженер готовит данные. Здесь согласно подготовленным конфигурационным файлам система собирает необходимые данные.

### 4.2 Шаги пайплайна

```
1. Загрузка и формирование файла data_config.json для описания модели из двух файлов подготовлнных дата-инженером: 1. параметры модели - файл `models.csv`, 2. источники данных - файл `inputs.csv`.
        │
        ▼
2. Сбор данных
   └── Запрос к внешним REST API согласно data_config.json
   └── Формирование DataFrame
        │
        ▼
3. Предобработка данных
   └── Валидация, очистка, feature engineering
        │
        ▼
4. Обучение модели
   └── Prophet или XGBoost (определяется параметром model_type)
        │
        ▼
5. Логирование в MLflow
   └── mlflow.start_run()
   └── mlflow.log_params(...)        — гиперпараметры
   └── mlflow.log_metrics(...)       — метрики качества (MAE, MAPE, RMSE)
   └── mlflow.set_tag("data_source_config", json.dumps(cfg))  — "паспорт данных"
  └── mlflow.set_tag("object_ref", ...)
   └── mlflow.set_tag("model_type", ...)
   └── mlflow.<framework>.log_model(...)  — артефакт модели
   
```

### 4.3 "Паспорт данных" (Data Passport)

Каждая модель должна иметь `data_config` — JSON-объект, содержащий информацию об конфигурации модели, например:

```json
{
  "object_ref": "/root/FP/PROJECT/AKMOLA/@regions/North Kazakhstan/load/@models/P_watt",
  "input_range": 72,
  "output_range": 24,
  "step": 3600,
  "sources": [
    {
      "url": "http://127.0.0.1:7080/api/v1/read/archives",
      "parameters": [
        "/root/FP/PROJECT/AKMOLA/@regions/SevKaz/Load/P_Load/archives/out_value"
      ],
      "pattern": "historical[forecast,plan]"
    }
  ]
}
```

Это позволяет системе при инференсе **автономно** знать, откуда и как брать данные.

### 4.4 Поддерживаемые типы моделей

| model_type | Библиотека | Назначение |
|------------|------------|------------|
| `prophet` | `prophet` | Временные ряды с сезонностью, праздниками |
| `xgboost` | `xgboost` | Табличные признаки, короткий горизонт |

---

## 5. Пайплайн инференса (Predict Pipeline)

### 5.1 Инициация

**Точка входа:** `GET /predict/{model_id}?version_alias=Production`

### 5.2 Шаги пайплайна

```
1. Приём запроса (object_ref, model_id, version_alias)
        │
        ▼
2. Поиск модели в MLflow
  └── Получение run_id по model_id и version_alias
   └── Чтение тега data_source_config ("паспорт данных")
        │
        ▼
3. Сбор данных
   └── Запрос к внешним REST API согласно data_source_config
   └── Формирование DataFrame для инференса
        │
        ▼
4. Загрузка артефакта модели
   └── mlflow.<framework>.load_model(model_uri)
        │
        ▼
5. Генерация прогноза
        │
        ▼
6. Формирование и возврат ответа
   └── Временной ряд прогноза (timestamp + value)
   └── Метаданные (model_id, run_id)
```

### 5.3 Идентификация модели

Идентификация модели проходит по следующим параметрам:

`model_id` — это имя зарегистрированной модели в MLflow.
`version_alias` — alias версии модели `model_id` (например, `Production`).

---

## 6. Управление моделями (MLflow)

### 6.1 Структура эксперимента

Каждый объект прогнозирования — это отдельный **MLflow Experiment**. Имя эксперимента формируется из `object_ref`.

```
Experiment: /KAZ/AKMOLA/P_WATT
└── Run: prophet_watt_h_AKMOLA_load  (run_id: abc123)
    ├── Tags:
    │   ├── data_source_config: "{...}"
    │   ├── object_ref: "/KAZ/AKMOLA/..."
    │   └── model_type: "prophet"
    ├── Params: changepoint_prior_scale, seasonality_mode, ...
    ├── Metrics: mae, mape, rmse
    └── Artifacts:
        └── model/  (сериализованная модель)
```

### 6.2 Добавление нового объекта

Для добавления нового объекта прогнозирования **не требуется изменение кода**. Достаточно:

1. Добавить в файлы параметры нового объекта: 1. параметры модели - файл `models.csv`, 2. источники данных - файл `inputs.csv` с новым `object_ref`.
2. Запустить тетрадь `./procedures/training/MODEL_DATA_COLLECTION.ipynb`; по завершению в `../local/models/` будет сформирована директория с именем модели (преобразованный `object_ref` + `_` + `output_range` + `hour`) и сформирован новый `data_config.json`.
3. Запустить тетрадь `ml-server/procedures/training/MODEL_TRAINING_MANUAL_WORKFLOW.ipynb` для обучения новой модели согласно данным из `data_config.json`.
2. По завершению MLflow автоматически создаст новый эксперимент.
3. Артефакт модели сохранится в `../local/mlruns/artifacts`

### 6.3 Версионирование

Каждый запуск обучения создаёт новый `run` в рамках эксперимента. Для инференса используется последний успешный `run` (или явно указанный `model_id`).

---

## 7. API-интерфейс

Подробная API-документация: [ml-server/docs/API/MAIN.md](API/MAIN.md)

### 7.1 Эндпоинты

#### `GET /predict/{model_id}?version_alias=Production&object_ref={object_ref}` — Запрос на вызов модели

где `object_ref` - идентификатор объекта на стороне клиента (опционально), `model_id` - идентификатор модели (обязательно), `version_alias` - версия модели (обязательно). 

**Response `200`:**
```json
{
    "status": 202,
    "task_id": "516c2ffaccfa4be285ec1b944ae6c4de",
  "object_ref": "/root/FP/PROJECT/AKMOLA/@regions/North Kazakhstan/load/@models/P_watt",
    "state": "start"
}
```

### `GET /tasks/{task_id}` - запрос на получение ответа от модели

где `task_id` - индентификатор задачи полученной на предыдущем этапе

**Response `200`:**
```json
{
    "status": 202,
    "task_id": "516c2ffaccfa4be285ec1b944ae6c4de",
    "state": "processing"
}
```

когда прогноз еще не готов, 

или при успешном получении результата:

```json
{
  "status": 200,
  "state": "done",
  "task_id": "f3b44ac9720f40108ad16def9f300b4e",
  "object_ref": "/KAZ/AKMOLA/AKMOLA/@models/P_WATT",
  "data": {
    "message": "...",
    "output": [
      [1746900000, 312.4, 0],
      [1746903600, 314.1, 0]
    ]
  }
}
```

---

#### `GET /models` — Список доступных моделей

**Response `200`:**
```json
{
  "models": [
    {
      "model_id": "prophet_watt_h_AKMOLA_@regions_Akmola_load",
      "object_ref": "/KAZ/AKMOLA/...",
      "type": "prophet",
      "run_id": "abc123",
      "created_at": "2026-04-15T10:00:00Z",
      "metrics": {"mae": 45.2, "mape": 3.1}
    }
  ]
}
```

---

#### `GET /health` — Проверка состояния сервиса

**Response `200`:**
```json
{
  "status": "ok",
  "mlflow": "connected",
  "redis": "connected"
}
```

---

### 7.2 Коды ответов

| Код | Значение |
|-----|----------|
| `200` | Успешно |
| `400` | Некорректный запрос (невалидные параметры) |
| `404` | Модель не найдена |
| `422` | Ошибка валидации тела запроса |
| `500` | Внутренняя ошибка сервера |
| `503` | MLflow недоступен |

---

## 8. Конфигурация и окружение

### 8.1 Файл `.env`

```env
# Модель (имя папки в ../local/)
MODEL=models

# Порты
PORT=8030
REDIS_PORT=6379
MLFLOW_PORT=5000

# MLflow
MLFLOW_TRACKING_URI=http://mlflow:5000

# Внешние источники данных (опционально, базовый URL)
RZ_API_URL=http://external-datasource.example.com
```

### 8.2 Конфигурация модели (`cache_config.json`)

Файл размещается в папке модели (`../local/mlruns/<Experiment id>/<Run id>/artifacts/bundle/configuration/cache_config.json`):

```yaml
{
  "step": 3600,
  "input_range": null,
  "output_range": 36,
  "model_type": "prophet",
  "fallback": "none",
  "config": {},
  "sources": {
    "historical_data": {
      "type": "historical_data",
      "url": "http://127.0.0.1:7080/api/v1/read/archives",
      "request": {
        "archive": [
          "/root/FP/PROJECT/AKMOLA/@regions/SevKaz/Load/P_Load/archives/out_value"
        ],
        "step": 3600,
        "pattern": "historic"
      }
    }
  }
}
```

### 8.3 Метаданные модели (`meta.json`)

```json
{
  "model_id": "prophet_watt_h_AKMOLA_@regions_Akmola_load",
  "type": "prophet",
  "object_ref": "/KAZ/AKMOLA/AKMOLA/@models/P_WATT",
  "run_id": "abc123def456",
  "trained_at": "2026-04-15T10:00:00Z",
  "metrics": {
    "mae": 45.2,
    "mape": 3.1,
    "rmse": 62.8,
    "wape": 3.1
  }
}
```

---

## 9. Структура проекта

```
project_root/
│
├── ml-server/
│   ├── src/                          # Серверный код (→ /workspace/server)
│   │   └── api/
│   │       ├── main.py               # FastAPI app, роутеры
│   │       ├── config.py             # Настройки (env vars)
│   │       ├── forecast/
│   │       │   ├── model.py          # Загрузка/инициализация модели
│   │       │   ├── predict.py        # Пайплайн инференса
│   │       │   └── train.py          # Пайплайн обучения
│   │       ├── data/
│   │       │   └── loader.py         # data_loader (REST API клиент)
│   │       └── mlflow_client.py      # Обёртка над MLflow API
│   │
│   ├── docker/
│   │   └── Dockerfile
│   ├── docker-compose.yml
│   ├── requirements.txt
│   └── .env
│
├── /tmp/
│   └── local_models_cache/                       # Артефакты моделей (→ /workspace/models)
│       └── <model_name>/
│           ├── model.pkl
│           ├── meta.json
│           └── config.yaml
│
└── local/                          # Локальное хранилище
    ├── mlflow.db                   # SQLite backend
    └── mlruns/                     # Артефакты моделей
```

---

## 10. Требования к развёртыванию

### 10.1 Docker Compose (целевая конфигурация)

```yaml
services:
  model-server:
    image: fpcloud/ml:1.0.0
    build:
      context: .
      dockerfile: ./docker/Dockerfile
    extra_hosts:
      - "host.docker.internal:host-gateway"
    container_name: models_${MODEL:-models}
    restart: unless-stopped
    command: >
      bash -c "
        taskiq worker api.broker:broker --workers 8 &
        python -u -m uvicorn api.server:app --host 0.0.0.0 --port 8030 &
        wait -n
      "
    ports:
      - "${PORT:-8030}:8030"
    environment:
      - PYTHONUNBUFFERED=1
      - TEST_MODE=true
      - SCADA_STUB_ENABLED=${SCADA_STUB_ENABLED:-false}
      - HISTORICAL_DATA_STUB_ENABLED=${HISTORICAL_DATA_STUB_ENABLED:-false}
      - MLFLOW_TRACKING_URI=http://mlflow:5000
      - MLFLOW_REGISTRY_URI=http://mlflow:5000
      - MLFLOW_DEFAULT_ALIAS=Production
      - MODEL_REGISTRY_CACHE_MAX=3
      - MODEL_REGISTRY_CACHE_DIR=/tmp/local_models_cache
    volumes:
      - "./src:/workspace/server"
      - "model_registry_cache:/tmp/local_models_cache"
    depends_on:
      - redis
      - mlflow
    deploy:
      resources:
        limits:
          cpus: '8'
          memory: 1024M
    tty: true
    stdin_open: true
    networks:
      - ml

  redis:
    image: redis:7
    container_name: redis
    restart: unless-stopped
    ports:
      - "${REDIS_PORT:-6379}:6379"
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD-SHELL", "redis-cli ping"]
      interval: 5s
      timeout: 5s
      retries: 5
    networks:
      - ml

  mlflow:
    image: ghcr.io/mlflow/mlflow:latest
    container_name: mlflow
    restart: unless-stopped
    # Run the MLflow tracking server explicitly. The upstream image's default
    # CMD may not start the server (it can default to `python3`), causing the
    # container to exit with code 0. Provide an explicit command so the
    # container stays running and serves the UI on the mapped port.
    command: mlflow server --host 0.0.0.0 --port 5000 --backend-store-uri sqlite:////mlflow/mlflow.db --serve-artifacts --artifacts-destination /mlflow/mlruns --allowed-hosts mlflow,mlflow:5000,localhost,localhost:5050,127.0.0.1,127.0.0.1:5050,host.docker.internal
    ports:
      - "${MLFLOW_PORT:-5050}:5000"
    volumes:
      - "../local/mlruns:/mlflow/mlruns"
      - "mlflow_data:/mlflow"
    networks:
      - ml
```

### 10.2 Минимальные требования к серверу

| Ресурс | Минимум | Рекомендуется |
|--------|---------|---------------|
| CPU | 4 ядра | 8 ядер |
| RAM | 8 ГБ | 16 ГБ |
| Диск | 50 ГБ | 200 ГБ |
| ОС | Ubuntu 22.04 | Ubuntu 22.04 |
| Docker | 24.x | 24.x+ |

### 10.3 Бэкап

Регулярному бэкапу подлежат:
- `../local/` — артефакты обученных моделей

---

## 11. Нефункциональные требования

| Параметр | Требование |
|----------|------------|
| Время ответа `/predict` | ≤ 5 секунд (при загруженной модели) |
| Доступность | 95% (плановые работы допустимы) |
| Логирование | Все запросы и ошибки пишутся в stdout (docker logs) |
| Версионирование моделей | Все версии хранятся в MLflow, старые не удаляются автоматически |
| Безопасность | Сервис работает в закрытой сети, авторизация API — вне scope |

---

## 12. Открытые вопросы

| # | Вопрос | Влияние |
|---|--------|---------|
| 1 | Формат временных меток от внешних REST API (UTC? локальное время?) | Обработка в data_loader |
| 2 | Нужна ли авторизация для API ml-server со стороны SCADA? | Безопасность |
| 3 | Какова максимальная глубина исторических данных для обучения? | Ресурсы, время обучения |
| 4 | Нужен ли мониторинг качества модели после деплоя (model drift)? | Архитектура, scope |
| 5 | Обработка ошибок внешних API: retry-политика, timeout? | Надёжность data_loader |
| 6 | Нужно ли хранить сырые данные обучающей выборки как артефакт MLflow? | Воспроизводимость |

---

*Документ подготовлен для согласования. После утверждения и предоставления текущей версии ПО будет составлен план доработки с разбивкой по задачам.*
