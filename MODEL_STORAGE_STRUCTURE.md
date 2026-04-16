# Структура хранения модели и её конфигурация

Этот файл описывает, где и как хранятся модели в проекте, какие переменные конфигурации используются, и как запускать/переключать модели в окружении с Docker Compose (ml-server).

## Коротко
- Код сервера монтируется в контейнер как: `/workspace/server` (хост: `ml-server/src`).
- Папка с конкретными обученными моделями монтируется как: `/workspace/models` (хост: `ml-server/local/models` по умолчанию).
- MLflow хранит артефакты в `mlruns` (на хосте `ml-server/mlruns`), см. `docker-compose.yml`.

## Файловая организация (важные пути)
- ml-server серверный пакет: `ml-server`
  - Код сервера (монтируется в контейнер): `ml-server/src` -> `/workspace/server`
  - Dockerfile для сборки образа: `ml-server/docker/Dockerfile`
  - Compose файл: `ml-server/docker-compose.yml` (в нём описаны сервисы `ml_model`, `redis`, `mlflow`)
  - Локальная папка с моделями по умолчанию: `../local/models/` (внутри неё папки с именем моделей`, см. ниже)

- MLflow local runs: `mlruns/` (монтируется в контейнер mlflow как `/mlflow/mlruns`)

## Как устроена папка модели (пример: `ml-server/local/models`)
В папке каждой модели находятся:
- бинарные/файлы артефактов модели (pickle, joblib, ONNX, weights и т.д.)
- метаданные: `meta.json` или аналог (описание версии, метрик, дата обучения)
- конфигурация развёртывания (если требуется): `config.yaml`, `config.json`
- дополнительные файлы (например, словари, scaler'ы)

Пример структуры:

- ../local/`${MODEL}`
    - model.pkl
    - meta.json
    - config.yaml

В контейнере это будет доступно по пути `/workspace/models`.

## Переменные конфигурации (ключевые)
Файл `.env` в корне проекта (или в ml-server) используется Docker Compose и содержит переменные, которые применяются в `docker-compose.yml`.
Типичные переменные, используемые в проекте:

- MODEL — имя папки с моделями внутри `../local` (по умолчанию `models`).
  Пример: `MODEL=models` => на хосте `../local/models` монтируется в контейнер как `/workspace/models`.
- PORT — порт проброса хоста -> контейнера для сервиса `ml_model`. В compose: `${PORT:-18888}:8000`.
- REDIS_PORT — порт Redis на хосте (по умолчанию 6379).
- MLFLOW_PORT — порт MLflow UI на хосте (по умолчанию 5000 или 5050 в compose).
- RZ_API_URL — (опционально) внешний URL для RZ сервиса, читается в `api/config.py`.

Пример `.env` (минимум):
```
MODEL=models
PORT=18888
REDIS_PORT=6379
MLFLOW_PORT=5000
```

## Docker Compose — важные сопоставления томов и переменные
В `ml-server/docker-compose.yml` ключевые места:
- `ml_model.volumes`:
  - `../local/${MODEL:-models}:/workspace/models` — директория моделей
  - `/abs/path/to/ml-server/src:/workspace/server` — серверный код
  - `/abs/path/to/models:/workspace/lib` — общие библиотеки (fpforecast)
- `ml_model.environment`:
  - `PYTHONUNBUFFERED=1`
  - `PYTHONPATH=/workspace/server:/workspace/lib` — обязательно, чтобы Python внутри контейнера видел `api` и `fpforecast`
- `ml_model.build`:
  - `context: .` и `dockerfile: ./docker/Dockerfile` — Dockerfile ожидает `requirements.txt` в корне ml-server

Важно: в compose используются абсолютные пути для томов (на macOS/Windows), чтобы избежать проблем с относительными путями и разрешением.

## Как переключить модель
1. Скопировать/поместить новую модель в `../local/models/<имя_модели>` (например `../local/models/my_model`).
2. В запросе указать имя модели:
```json
{
    "object_reference": "/KAZ/AKMOLA/AKMOLA/@models/P_WATT",
    "model_id": "prophet_watt_h_AKMOLA_@regions_Akmola_load"
}
```
Сервер примонтирует нужную модель взяв необходимцю информацию из сервера MLFlow.

## Как модель загружается в коде
- В `api/forecast/model.py` (и смежных) есть функции/инициализаторы для загрузки модели, они ожидают найти модель в путях, см. `init_model`.
- Внутри контейнера код ожидает, что локальные модели доступны по `/workspace/models`.
- Модуль `fpforecast` (реализация моделей) загружается из `/workspace/lib/fpforecast`.

## MLflow (опционально)
- MLflow сервис в compose монтирует `../mlruns:/mlflow/mlruns` (хост -> контейнер)
- Если вы используете mlflow для хранения артефактов, убедитесь, что path `mlruns/` создан и доступен для записи.

## MLflow — схема хранения и "паспорт данных"

- Storage (гибридная схема):
  - Backend Store (метаданные): sqlite:///mlflow_data/mlflow.db — хранит метрики, параметры, теги и метаданные запусков.
  - Artifact Store (артефакты): ./mlflow_data/artifacts — хранит тяжёлые объекты (модели, сериализованные датасеты, графики).

- Концепция "Паспорта данных" (Data Passport / Tags):
  - Во время обучения в MLflow записывается тег, содержащий JSON-конфигурацию источника данных (тип БД, SQL-запрос, пути в S3 и т.д.).
  - При запуске прогноза код читает `run_id` модели и получает значение тега `data_source_config` из SQLite (backend store).
  - Полученный конфиг передаётся в модуль загрузки данных (`data_loader`), который формирует DataFrame для инференса.

- Пример запуска MLflow server (локально):
  ```bash
  mlflow server --host 0.0.0.0 --port 5000 \
    --backend-store-uri sqlite:///mlflow_data/mlflow.db \
    --default-artifact-root ./mlflow_data/artifacts
  ```

- Структура проекта (рекомендуемая для MLflow):
  - project_root/
    - mlflow_data/
      - mlflow.db
      - artifacts/

- Ключевые преимущества подхода:
  - Автономность: модель сама описывает, какие данные ей нужны при прогнозе (через тег).
  - Масштабируемость: SQLite даёт быстрый доступ к метаданным (фильтрация запусков и поиск по тегам).
  - Воспроизводимость: можно восстановить цепочку — какая модель обучалась на каких данных и с какими параметрами.

Если вы хотите, могу дополнительно:
- добавить в `docker-compose.yml` опцию для монтирования `mlflow_data` (если нужно отделить от `mlruns`),
- добавить пример кода для записи "паспорта данных" в MLflow (пример вызова `mlflow.set_tag("data_source_config", json.dumps(cfg))`).

## Рекомендации по бэкапу и правам
- Регулярно бэкапьте `ml-server/local` и `mlruns/` (если используется MLflow).
- Проверьте права доступа на каталоги, чтобы контейнер мог читать/писать (в macOS обычно права root<->user переводятся автоматически, но в Linux может потребоваться chown).

## Частые ошибки и как их решать
- ModuleNotFoundError: No module named 'api' — обычно из-за неправильного тома `src` (монтируется не туда). Проверьте, что `ml-server/src` реально содержит `api/`.
- ModuleNotFoundError: No module named 'fpforecast' — проверьте, что монтируется `models/` (в котором есть `fpforecast/`), и что `PYTHONPATH` включает `/workspace/lib`.
- Docker build failed: `/requirements.txt: not found` — убедитесь, что в контексте сборки (`context: .`) есть `requirements.txt` (в `ml-server/requirements.txt`).
- Ошибки с приватными git: см. раздел SSH выше.

## Быстрые команды
```bash
# Перезапустить сервисы (ml-server folder)
cd ml-server
docker-compose down
docker-compose up -d --build

# Посмотреть логи сервиса ml_model
docker-compose logs -f ml_model

# Проверить статус контейнеров
docker-compose ps
```

## Заключение
- Источники правд: серверный код в `ml-server/src`, библиотеки/модели в `models/`, конкретные артефакты обученных моделей в `ml-server/local/${MODEL}`.
- Для корректной работы контейнера важно правильно смонтировать директории и настроить `PYTHONPATH`.
- Если нужно — могу дополнить этот документ примерами `meta.json` формата, шаблоном `config.yaml` для модели или автоматическими скриптами обновления модели.
