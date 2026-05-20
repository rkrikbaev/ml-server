# Конфигурация

Документ синхронизирован с runtime-логикой в [ml-server/src/api/config.py](ml-server/src/api/config.py).

## Redis

| Canonical name | Legacy alias | Описание | Значение по умолчанию |
| --- | --- | --- | --- |
| **REDIS_URL** | - | URL Redis сервера | `redis://redis:6379/0` в Docker, `redis://127.0.0.1:6379/0` локально |
| **REDIS_TIMEOUT** | - | TTL/таймаут хранения результатов в Redis (сек.) | `3600` |

## Historical Data

Приоритет чтения: `HISTORICAL_DATA_URLS` -> `HISTORICAL_DATA_URL` -> `SCADA_URL`.

| Canonical name | Legacy alias | Описание | Значение по умолчанию |
| --- | --- | --- | --- |
| **HISTORICAL_DATA_URLS** | `HISTORICAL_DATA_URL`, `SCADA_URL` | URL(ы) API исторических архивов, список через запятую | `http://127.0.0.1:7080/api/v1/read/archives` |

## CMMS

Приоритет чтения: `CMMS_URL` -> `CMMS_API_URL`.

| Canonical name | Legacy alias | Описание | Значение по умолчанию |
| --- | --- | --- | --- |
| **CMMS_URL** | `CMMS_API_URL` | URL API ремонтов (CMMS) | `http://localhost:8000/api/v1/cmms` |
| **RZ_URL** | - | Runtime-алиас в коде, если env `RZ_URL` не задан, берется `CMMS_URL` | равно `CMMS_URL` |

## Weather

Приоритет чтения: `WEATHER_URL` -> `WEATHER_API_URL`.

| Canonical name | Legacy alias | Описание | Значение по умолчанию |
| --- | --- | --- | --- |
| **WEATHER_URL** | `WEATHER_API_URL` | URL API погоды | пустая строка |

## General

| Canonical name | Legacy alias | Описание | Значение по умолчанию |
| --- | --- | --- | --- |
| **HEADERS** | - | Базовые HTTP-заголовки (`accept`, `Content-Type`) | `{"accept": "application/json", "Content-Type": "application/json"}` |
| **CLIENT_TIMEOUT_ONE** | - | Таймаут одного внешнего запроса (сек.) | `30` |
| **CLIENT_TIMEOUT_ALL** | - | Общий таймаут серии внешних запросов (сек.) | `120` |
| **GMT_TO_ASTANA_HOURS** | - | Смещение времени GMT -> Astana (часы) | `5` |

## Tag

| Canonical name | Legacy alias | Описание | Значение по умолчанию |
| --- | --- | --- | --- |
| **TAG_PREDICT_CREATE** | - | Тег create-схемы predict | `predict_create` |
| **TAG_PREDICT_UPDATE** | - | Тег update-схемы predict | `predict_update` |
