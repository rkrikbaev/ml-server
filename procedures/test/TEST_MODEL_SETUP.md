# Настройка Тестовой Модели и Конфигурации

**Дата:** 20.04.2026  
**Версия:** 1.0  
**Статус:** ✅ Готово  

---

## 📋 Оглавление

1. [Обзор](#обзор)
2. [Требования](#требования)
3. [Быстрый старт](#быстрый-старт)
    "sources": [
5. [Конфигурация моделей](#конфигурация-моделей)
        "type": "historical_data",
7. [Решение проблем](#решение-проблем)

---

## Обзор

Тестовая модель - это полностью настроенная Prophet модель для прогнозирования нагрузки в регионе AKMOLA. Она используется для:

- ✅ Разработки и отладки API
- ✅ Интеграционного тестирования
- ✅ Проверки пайплайна инференса
- ✅ Демонстрации возможностей системы

### Компоненты

| Компонент | Назначение | Местоположение |
|-----------|-----------|-------------------|
| **Конфигурация окружения** | Переменные среды для тестов | `.env.test` |
| **Runtime-конфигурация модели** | Активный `cache_config.json` в MLflow bundle cache | `/tmp/local_models_cache/.../bundle/configuration/cache_config.json` |
| **Скрипт инициализации** | Python скрипт настройки | `scripts/setup_test_model.py` |
| **Скрипт окружения** | Bash скрипт для полной настройки | `scripts/setup_test_env.sh` |
| **Синтетические данные** | Тестовые данные для обучения | `tests/fixtures/test_data/` |

---

## Требования

### Системные требования
- Python 3.9+
- macOS, Linux или WSL2
- ~500 МБ свободного места на диске

### Зависимости Python
```
prophet>=1.2.1        # Forecasting library
mlflow>=2.0.0         # Model registry and tracking
pandas>=2.3.3         # Data manipulation
fastapi>=0.110.0      # API framework
scikit-learn>=1.7.2   # Machine learning utilities
```

### Установка зависимостей
```bash
pip install -r requirements.txt
```

---

## Быстрый Старт

### Вариант 1: Автоматизированная настройка (Рекомендуется)

```bash
# 1. Перейти в директорию проекта
cd /Users/rustamkrikbayev/Documents/projects/forecast/ml-server

# 2. Сделать скрипты исполняемыми
chmod +x scripts/setup_test_env.sh
chmod +x scripts/setup_test_model.py

# 3. Запустить скрипт настройки
bash scripts/setup_test_env.sh
```

**Что происходит:**
- ✓ Создаются директории
- ✓ Проверяется Python окружение
- ✓ Устанавливаются зависимости
- ✓ Создаётся синтетический датасет
- ✓ Тренируется модель
- ✓ Модель регистрируется в MLflow
- ✓ Создаются конфигурации

### Вариант 2: Пошаговая ручная настройка

```bash
# 1. Создать директории
mkdir -p config logs tests/fixtures/test_data mlflow_artifacts

# 2. Создать окружение
cp .env.test .env
export $(cat .env | xargs)

# 3. Обучить модель
python scripts/setup_test_model.py

# 4. Проверить регистрацию в MLflow
mlflow ui --backend-store-uri sqlite:///mlflow.db
# Открыть http://localhost:5000 в браузере
```

---

## Подробная Настройка

### Конфигурация Окружения (.env.test)

```env
# Основные параметры
ENV=test
DEBUG=true

# API
API_HOST=0.0.0.0
API_PORT=8000
API_LOG_LEVEL=INFO

# MLflow
MLFLOW_TRACKING_URI=sqlite:///mlflow.db
MLFLOW_ARTIFACT_ROOT=./mlflow_artifacts

# Модель
MODEL_TYPE=prophet
MODEL_HORIZON=24
MODEL_FREQ=H

# Cache (опционально)
REDIS_HOST=localhost
REDIS_PORT=6379
CACHE_ENABLED=false

# Historical-data stub for integration smoke tests
HISTORICAL_DATA_STUB_ENABLED=true
```

### Использование конфигурации

```bash
# Загрузить конфигурацию
export $(cat .env.test | xargs)

# Или используйте в Python
from dotenv import load_dotenv
load_dotenv('.env.test')
```

---

## Конфигурация Моделей

Текущий offline runtime читает конфигурацию инференса из MLflow serving bundle:

```text
/tmp/local_models_cache/.../bundle/configuration/cache_config.json
```

Для online flow (`model_id == "none"`) registry bundle не требуется.

### Актуальный формат `cache_config.json`

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

### Семантика полей

- `input_range` задаёт размер исторического окна
- `output_range` задаёт горизонт прогноза и размер future/planned окна
- `pattern = historic` использует `input_range`
- `pattern = future` использует `output_range`
- `pattern = planned` использует `output_range`
- `step` задаётся в секундах

### Что реально использует runtime сейчас

- SCADA source: да, используется активно
- weather source: да, запрашивается как optional payload
- CMMS source: участвует в active predict flow как postprocessing planned-снижения

Поддерживаемый формат planned payload:

```json
{
  "0704011504": [
    {
      "p_station": 1688,
      "p_descent": 325,
      "start_requested": 1771095600000,
      "end_requested": 1778871540000
    }
  ]
}
```

### Legacy helper config

Скрипты настройки всё ещё могут создавать вспомогательный файл `config/test_runtime.json` для локальных экспериментов, но активный offline `/predict` использует именно MLflow bundle `cache_config.json`.

Пример legacy helper-файла:

```json
{
  "environment": "test",
  "model": {
    "type": "prophet",
    "horizon": 24,
    "freq": "H"
  },
  "data_source": {
    "object_reference": "/KAZ/AKMOLA/@models/P_WATT",
    "apis": [...]
  }
}
```

---

## Проверка и Тестирование

### 1. Проверка регистрации модели в MLflow

```bash
# Запустить MLflow UI
mlflow ui --backend-store-uri sqlite:///mlflow.db

# Открыть http://localhost:5000
# Должна быть видна модель: prophet_watt_h_AKMOLA_test
```

### 2. Проверка синтетических данных

```bash
# Проверить созданные данные
head -5 tests/fixtures/test_data/sample.csv
wc -l tests/fixtures/test_data/sample.csv
```

**Ожидаемый результат:**
```
timestamp,ds,y,load
2026-03-21 12:34:56.789123,2026-03-21 12:34:56.789123,512.34,512.34
...
721 total rows (30 дней × 24 часов + 1 заголовок)
```

### 3. Тест API предсказания

Текущий `/predict` работает в два шага:

1. Первый `POST /predict` создаёт задачу и возвращает `202 start` и `task_id`
2. Повторные `POST /predict` с тем же `task_id` возвращают `202 processing` или финальный `200 done`

```bash
# Запустить сервисы
docker compose up -d

# 1-й запрос: старт задачи
curl -X POST http://localhost:18888/predict \
  -H "Content-Type: application/json" \
  -d '{
    "object_reference": "/KAZ/AKMOLA/@models/P_WATT",
    "model_id": "prophet_watt_h_AKMOLA_test"
  }'

# 2-й запрос: опрос результата
curl -X POST http://localhost:18888/predict \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "<task_id_from_first_response>"
  }'
```

**Ожидаемые ответы:**

Первый запрос:

```json
{
  "status": 202,
  "object_reference": "/KAZ/AKMOLA/@models/P_WATT",
  "task_id": "...",
  "state": "start"
}
```

Повторный запрос во время обработки:

```json
{
  "status": 202,
  "task_id": "...",
  "state": "processing"
}
```

Финальный ответ:

```json
{
  "status": 200,
  "object_reference": "/KAZ/AKMOLA/@models/P_WATT",
  "task_id": "...",
  "state": "done",
  "data": {
    "message": "",
    "output": [
      [1776733200000, 451.2, 0],
      [1776736800000, 451.1, 0]
    ],
    "quality": 0,
    "model_confidence": 1.0
  }
}
```

### 4. Запуск тестов

```bash
# Запустить smoke-тест двухшагового /predict
pytest tests/test_predict_smoke.py -v

# Запустить smoke-тест через Makefile
make smoke-positive

# Запустить негативный smoke-тест без SCADA stub
make smoke-negative

# Запустить все тесты
pytest tests/ -v

# С покрытием
pytest tests/ --cov=src --cov-report=html
```

---

## Структура Файлов

```
ml-server/
├── .env.test                           # Конфигурация окружения для тестов
├── config/
│   └── test_runtime.json              # Legacy helper-конфигурация (опционально)
├── scripts/
│   ├── setup_test_env.sh              # Bash скрипт полной настройки
│   ├── setup_test_model.py            # Python скрипт инициализации модели
│   └── ...
├── tests/
│   ├── fixtures/
│   │   ├── test_data/
│   │   │   └── sample.csv             # Синтетические данные (создаётся)
│   │   └── test_request.json          # Тестовый запрос (создаётся)
│   ├── test_predict_smoke.py          # Smoke-тест start -> processing -> done
│   └── ...
├── logs/                              # Логи (создаётся)
├── mlflow_artifacts/                  # MLflow артефакты (создаётся)
└── ...

local/
└── models/
  └── prophet_watt_h_AKMOLA_test/
    └── bundle/configuration/cache_config.json   # Активная runtime-конфигурация модели
```

---

## Параметры Тестовой Модели

| Параметр | Значение | Назначение |
|----------|----------|-----------|
| **Model Type** | Prophet | Модель временного ряда |
| **Horizon** | 24 часа | Прогноз на 1 день вперёд |
| **Frequency** | Hourly | Почасовые данные |
| **Seasonality** | Additive | Аддитивная сезонность |
| **Training Data** | 30 дней | ~720 точек данных |
| **Region** | AKMOLA | Тестовый регион |
| **Entity** | P_WATT (Load) | Прогноз нагрузки |

### Метрики модели

Модель создаётся с синтетическими данными специально для тестирования:
- ✓ Детерминированные результаты
- ✓ Воспроизводимые данные
- ✓ Известный горизонт прогноза
- ✓ Быстрое обучение (~30 сек)

---

## Окружение Разработки

### Для локальной разработки

```bash
# 1. Установить зависимости
pip install -r requirements.txt

# 2. Загрузить конфигурацию для разработки
export $(cat .env.test | xargs)

# 3. Запустить MLflow
mlflow ui --backend-store-uri sqlite:///mlflow.db &

# 4. Инициализировать модель
python scripts/setup_test_model.py

# 5. Запустить API в режиме разработки
PYTHONPATH=./src python -m uvicorn api.server:app --reload --log-level debug --port 8000

# 6. В другом терминале запустить тесты
pytest tests/test_predict_smoke.py -v
```

### Docker (опционально)

```bash
# Собрать образ
docker build -t ml-server:test -f docker/Dockerfile .

# Запустить контейнеры
docker compose up -d

# Проверить логи
docker compose logs -f ml_model
```

---

## Решение Проблем

### Проблема: "Prophet not installed"

```bash
# Решение
pip install prophet
```

### Проблема: "MLflow artifact directory not found"

```bash
# Решение
mkdir -p mlflow_artifacts
python scripts/setup_test_model.py
```

### Проблема: "Model not found in registry"

```bash
# Проверить регистрацию
mlflow models list

# Пересоздать модель
rm mlflow.db
python scripts/setup_test_model.py
```

### Проблема: "Timeout при запросе к API"

```bash
# Увеличить timeout в .env.test
INFERENCE_TIMEOUT=120

# Или через legacy helper-конфигурацию
python -c "
import json
with open('config/test_runtime.json') as f:
    config = json.load(f)
config['inference']['timeout'] = 120
with open('config/test_runtime.json', 'w') as f:
    json.dump(config, f)
"
```

### Проблема: "SCADA недоступна во время smoke-теста"

```bash
# Для интеграционного тестового сценария включить synthetic fallback
SCADA_STUB_ENABLED=true
```

### Негативный сценарий проверки без stub

```bash
# Явно выключить stub и проверить, что /predict завершится 503 done
SCADA_STUB_ENABLED=false docker compose up -d --force-recreate ml_model
/Users/rustamkrikbayev/Documents/projects/forecast/.venv/bin/python -m pytest tests/test_predict_negative_smoke.py -v
```

### Проблема: "Port 8000 already in use"

```bash
# Найти процесс
lsof -i :8000

# Или использовать другой порт
python -m uvicorn src.api.main:app --port 8001
```

---

## Проверочный Список

После настройки проверить:

- [ ] Директории созданы: `config`, `logs`, `tests/fixtures/test_data`, `mlflow_artifacts`
- [ ] Активный runtime-config доступен: `bundle/configuration/cache_config.json`
- [ ] MLflow запущен: `mlflow ui` доступен на http://localhost:5000
- [ ] Модель зарегистрирована: `prophet_watt_h_AKMOLA_test` видна в MLflow UI
- [ ] Синтетические данные созданы: `tests/fixtures/test_data/sample.csv` имеет 721 строку
- [ ] API запускается: `docker compose up -d` или `PYTHONPATH=./src python -m uvicorn api.server:app`
- [ ] Предсказание работает: первый curl возвращает `202 start`, повторный запрос доходит до `200 done`
- [ ] Smoke-тест проходит: `pytest tests/test_predict_smoke.py -v` показывает PASSED
- [ ] Негативный smoke-тест проходит: `make smoke-negative` подтверждает `503 done` без SCADA stub

---

## Что Дальше?

После успешной настройки тестовой модели:

1. **Развёртывание**
   - Следуйте guide-у в документации
   - Настройте реальные модели для production

2. **Интеграция SCADA**
   - Используйте примеры запросов из тестов
   - Тестируйте с реальными данными

3. **Мониторинг**
   - Просмотрите логи: `tail -f logs/test.log`
   - Мониторьте метрики в MLflow UI

4. **Оптимизация**
   - Тюнинг параметров модели
   - Оптимизация производительности

---

## Ссылки

- 📖 [Документация инференса](INFERENCE_PIPELINE_DETAILED_EXPLANATION.md)
- 📖 [API контракт](API_CONTRACT_UPDATE.md)
- 🚀 [Быстрый старт](00_START_HERE.md)
- 🔧 [Конфигурация](API_DOCUMENTATION_INDEX.md)

---

**Версия:** 1.0  
**Дата:** 20.04.2026  
**Статус:** ✅ Готово к использованию
