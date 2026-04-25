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

ML-сервер предназначен для обучения и эксплуатации моделей прогнозирования временных рядов (нагрузка, энергопотребление) по объектам энергосистемы. Система обслуживает запросы от внешней SCADA-системы и реализует полный ML-пайплайн: сбор данных → загрузку модели → получение прогноза. Обучение моеделй происходит отдельно, пока под управлением инженера.

### 1.2 Основные возможности

- Прогнозирование временных рядов по произвольному объекту (регион, подстанция и т.д.)
- Обучение моделей Prophet и XGBoost по запросу
- Хранение артефактов и метаданных моделей в MLflow
- Динамическое добавление новых объектов прогнозирования без изменения кода
- Сбор данных из нескольких внешних REST API в зависимости от конфигурации модели ("паспорт данных")

### 1.3 Потребитель системы

Внешняя SCADA-система взаимодействует с ML-сервером через REST API. Запросы инициируются SCADA-системой (pull-модель).

---

## 2. Архитектура системы

```
┌─────────────────────────────────────────────────────────┐
│                      SCADA-система                       │
└───────────────────────┬─────────────────────────────────┘
                        │ REST API (HTTP)
                        ▼
┌─────────────────────────────────────────────────────────┐
│                      ml-server                           │
│                                                          │
│   ┌─────────────┐   ┌──────────────┐  ┌─────────────┐  │
│   │  API Layer  │   │ Train Pipeline│  │  Predict    │  │
│   │  (FastAPI)  │──▶│  (по запросу)│  │  Pipeline   │  │
│   └──────┬──────┘   └──────┬───────┘  └──────┬──────┘  │
│          │                 │                  │          │
│          │          ┌──────▼──────────────────▼──────┐  │
│          │          │         Data Loader             │  │
│          │          │  (REST API внешних источников)  │  │
│          │          └─────────────────────────────────┘  │
│          │                                               │
│   ┌──────▼──────────────────────────────────────────┐   │
│   │                    MLflow                        │   │
│   │  Backend: SQLite  │  Artifacts: ./mlflow_data   │   │
│   └─────────────────────────────────────────────────┘   │
│                                                          │
│   ┌───────────┐                                          │
│   │   Redis   │  (кэш результатов / очередь задач)       │
│   └───────────┘                                          │
└─────────────────────────────────────────────────────────┘
```

### 2.1 Сервисы Docker Compose

| Сервис | Образ | Назначение |
|--------|-------|------------|
| `ml_model` | Собственный (Dockerfile) | Основной ML-сервер (FastAPI) |
| `mlflow` | `ghcr.io/mlflow/mlflow` | Трекинг экспериментов и хранение артефактов |
| `redis` | `redis:alpine` | Кэширование и опциональная очередь задач |

---

## 3. Компоненты инфраструктуры

### 3.1 ml_model (основной сервис)

**Функции:**
- Приём и обработка HTTP-запросов от SCADA
- Запуск пайплайна обучения по запросу
- Запуск пайплайна инференса
- Взаимодействие с MLflow (чтение/запись метаданных и артефактов)
- Взаимодействие с внешними REST API через `data_loader`

**Технологический стек:**
- Python 3.10+
- FastAPI + Uvicorn
- Prophet, XGBoost, scikit-learn
- MLflow client
- httpx / requests (для data_loader)

**Монтируемые тома:**
```
ml-server/src           → /workspace/server   (серверный код)
ml-server/local/models  → /workspace/models   (артефакты моделей)
fpforecast/             → /workspace/lib       (библиотека моделей)
```

**Переменные окружения:**
```
PYTHONPATH=/workspace/server:/workspace/lib
MLFLOW_TRACKING_URI=http://mlflow:5000
```

### 3.2 MLflow

**Схема хранения:**
- Backend Store (метаданные, теги, метрики, параметры): `sqlite:///mlflow_data/mlflow.db`
- Artifact Store (модели, датасеты, графики): `./mlflow_data/artifacts`

**Монтируемые тома:**
```
ml-server/mlflow_data  → /mlflow/mlflow_data
```

**Команда запуска:**
```bash
mlflow server \
  --host 0.0.0.0 \
  --port 5000 \
  --backend-store-uri sqlite:///mlflow_data/mlflow.db \
  --default-artifact-root ./mlflow_data/artifacts
```

### 3.3 Redis

Используется для:
- Кэширования результатов прогноза (опционально, TTL настраивается)
- Хранения промежуточных состояний долгих задач обучения

---

## 4. Пайплайн обучения (Train Pipeline)

### 4.1 Инициация

Обучение запускается **по явному запросу** через API. Параллельный фоновый запуск (Celery/cron) — **вне scope данного ТЗ**.

**Точка входа:** `POST /train`

### 4.2 Шаги пайплайна

```
1. Приём запроса (object_reference, model_type, data_source_config)
        │
        ▼
2. Сбор данных (data_loader)
   └── Запрос к внешним REST API согласно data_source_config
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
   └── mlflow.set_tag("object_reference", ...)
   └── mlflow.set_tag("model_type", ...)
   └── mlflow.<framework>.log_model(...)  — артефакт модели
        │
        ▼
6. Возврат run_id и метрик в ответе API
```

### 4.3 "Паспорт данных" (Data Passport)

Каждая обученная модель хранит в MLflow тег `data_source_config` — JSON-объект, описывающий источник данных:

```json
{
  "sources": [
    {
      "type": "rest_api",
      "url": "http://datasource1.example.com/api/timeseries",
      "params": {
        "object_id": "AKMOLA_LOAD",
        "interval": "1h"
      }
    }
  ],
  "date_column": "timestamp",
  "target_column": "value",
  "freq": "H"
}
```

Это позволяет системе при инференсе **автономно** знать, откуда брать данные, без дополнительной конфигурации.

### 4.4 Поддерживаемые типы моделей

| model_type | Библиотека | Назначение |
|------------|------------|------------|
| `prophet` | `prophet` | Временные ряды с сезонностью, праздниками |
| `xgboost` | `xgboost` | Табличные признаки, короткий горизонт |

---

## 5. Пайплайн инференса (Predict Pipeline)

### 5.1 Инициация

**Точка входа:** `POST /predict`

### 5.2 Шаги пайплайна

```
1. Приём запроса (object_reference, model_id, horizon)
        │
        ▼
2. Поиск модели в MLflow
   └── Получение run_id по model_id
   └── Чтение тега data_source_config ("паспорт данных")
        │
        ▼
3. Сбор данных (data_loader)
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
   └── Метаданные (model_id, run_id, горизонт, интервал)
```

### 5.3 Идентификация модели

Запрос к API содержит:

```json
{
  "object_reference": "/KAZ/AKMOLA/AKMOLA/@models/P_WATT",
  "model_id": "prophet_watt_h_AKMOLA_@regions_Akmola_load"
}
```

`model_id` — это имя зарегистрированной модели или `run_id` в MLflow.

---

## 6. Управление моделями (MLflow)

### 6.1 Структура эксперимента

Каждый объект прогнозирования — это отдельный **MLflow Experiment**. Имя эксперимента формируется из `object_reference`.

```
Experiment: /KAZ/AKMOLA/P_WATT
└── Run: prophet_watt_h_AKMOLA_load  (run_id: abc123)
    ├── Tags:
    │   ├── data_source_config: "{...}"
    │   ├── object_reference: "/KAZ/AKMOLA/..."
    │   └── model_type: "prophet"
    ├── Params: changepoint_prior_scale, seasonality_mode, ...
    ├── Metrics: mae, mape, rmse
    └── Artifacts:
        └── model/  (сериализованная модель)
```

### 6.2 Добавление нового объекта

Для добавления нового объекта прогнозирования **не требуется изменение кода**. Достаточно:

1. Отправить `POST /train` с новым `object_reference` и `data_source_config`
2. MLflow автоматически создаст новый эксперимент
3. Артефакт модели сохранится в `mlflow_data/artifacts`

### 6.3 Версионирование

Каждый запуск обучения создаёт новый `run` в рамках эксперимента. Для инференса используется последний успешный `run` (или явно указанный `model_id`).

---

## 7. API-интерфейс

### 7.1 Эндпоинты

#### `POST /predict` — Запрос прогноза

**Request Body:**
```json
{
  "object_reference": "/KAZ/AKMOLA/AKMOLA/@models/P_WATT",
  "model_id": "prophet_watt_h_AKMOLA_@regions_Akmola_load"
}
```

**Response `200`:**
```json
{
  "object_reference": "/KAZ/AKMOLA/AKMOLA/@models/P_WATT",
  "model_id": "prophet_watt_h_AKMOLA_@regions_Akmola_load",
  "run_id": "abc123def456",
  "forecast": [
    {"timestamp": "2026-04-17T00:00:00Z", "value": 1234.5},
    {"timestamp": "2026-04-17T01:00:00Z", "value": 1198.2}
  ],
  "freq": "H",
  "horizon": 24
}
```

---

#### `POST /train` — Запуск обучения

**Request Body:**
```json
{
  "object_reference": "/KAZ/AKMOLA/AKMOLA/@models/P_WATT",
  "model_type": "prophet",
  "data_source_config": {
    "sources": [
      {
        "type": "rest_api",
        "url": "http://datasource.example.com/api/timeseries",
        "params": {"object_id": "AKMOLA_LOAD", "interval": "1h"}
      }
    ],
    "date_column": "timestamp",
    "target_column": "value",
    "freq": "H"
  },
  "train_params": {
    "changepoint_prior_scale": 0.05,
    "seasonality_mode": "multiplicative"
  }
}
```

**Response `200`:**
```json
{
  "status": "success",
  "run_id": "abc123def456",
  "model_id": "prophet_watt_h_AKMOLA_@regions_Akmola_load",
  "metrics": {
    "mae": 45.2,
    "mape": 3.1,
    "rmse": 62.8
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
      "object_reference": "/KAZ/AKMOLA/...",
      "model_type": "prophet",
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
PORT=18888
REDIS_PORT=6379
MLFLOW_PORT=5000

# MLflow
MLFLOW_TRACKING_URI=http://mlflow:5000

# Внешние источники данных (опционально, базовый URL)
RZ_API_URL=http://external-datasource.example.com
```

### 8.2 Конфигурация модели (`config.yaml`)

Файл размещается в папке модели (`/workspace/models/<model_name>/config.yaml`):

```yaml
model_type: prophet
object_reference: /KAZ/AKMOLA/AKMOLA/@models/P_WATT
freq: H
horizon: 24

prophet:
  changepoint_prior_scale: 0.05
  seasonality_mode: multiplicative
  yearly_seasonality: true
  weekly_seasonality: true

xgboost:
  n_estimators: 200
  max_depth: 6
  learning_rate: 0.05
  lags: [1, 2, 3, 24, 48, 168]
```

### 8.3 Метаданные модели (`meta.json`)

```json
{
  "model_id": "prophet_watt_h_AKMOLA_@regions_Akmola_load",
  "model_type": "prophet",
  "object_reference": "/KAZ/AKMOLA/AKMOLA/@models/P_WATT",
  "run_id": "abc123def456",
  "trained_at": "2026-04-15T10:00:00Z",
  "metrics": {
    "mae": 45.2,
    "mape": 3.1,
    "rmse": 62.8
  },
  "freq": "H",
  "horizon": 24
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
├── fpforecast/                       # Библиотека моделей (→ /workspace/lib)
│   └── fpforecast/
│       ├── prophet_model.py
│       └── xgboost_model.py
│
├── local/
│   └── models/                       # Артефакты моделей (→ /workspace/models)
│       └── <model_name>/
│           ├── model.pkl
│           ├── meta.json
│           └── config.yaml
│
└── mlflow_data/                      # MLflow хранилище
    ├── mlflow.db                     # SQLite backend
    └── artifacts/                    # Артефакты моделей
```

---

## 10. Требования к развёртыванию

### 10.1 Docker Compose (целевая конфигурация)

```yaml
version: "3.9"

services:
  ml_model:
    build:
      context: .
      dockerfile: ./docker/Dockerfile
    ports:
      - "${PORT:-18888}:8000"
    volumes:
      - /abs/path/to/ml-server/src:/workspace/server
      - /abs/path/to/fpforecast:/workspace/lib
      - ../local/${MODEL:-models}:/workspace/models
    environment:
      - PYTHONUNBUFFERED=1
      - PYTHONPATH=/workspace/server:/workspace/lib
      - MLFLOW_TRACKING_URI=http://mlflow:5000
      - REDIS_URL=redis://redis:6379
    depends_on:
      - mlflow
      - redis

  mlflow:
    image: ghcr.io/mlflow/mlflow:latest
    ports:
      - "${MLFLOW_PORT:-5000}:5000"
    volumes:
      - ../mlflow_data:/mlflow/mlflow_data
    command: >
      mlflow server
      --host 0.0.0.0
      --port 5000
      --backend-store-uri sqlite:///mlflow_data/mlflow.db
      --default-artifact-root ./mlflow_data/artifacts

  redis:
    image: redis:alpine
    ports:
      - "${REDIS_PORT:-6379}:6379"
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
- `ml-server/local/` — артефакты обученных моделей
- `mlflow_data/` — база метаданных и артефакты MLflow

---

## 11. Нефункциональные требования

| Параметр | Требование |
|----------|------------|
| Время ответа `/predict` | ≤ 5 секунд (при загруженной модели) |
| Время обучения | ≤ 10 минут на одну модель (Prophet/XGBoost, до 3 лет данных) |
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
