# ✅ Конфигурация Тестовой Модели - ПОЛНОЕ РУКОВОДСТВО

**Статус:** ✅ ГОТОВО  
**Дата:** 20.04.2026  
**Версия:** 1.0  

---

## 🎯 Что Было Сделано

### 1. ✅ Конфигурация Окружения
- **Файл:** `.env.test`
- **Содержит:** Все параметры для тестовой среды
- **Переменные:** 50+ параметров для API, MLflow, кэша, логирования

### 2. ✅ Конфигурация Модели (YAML)
- **Файл:** `config/test_model_config.yaml`
- **Содержит:** Полная конфигурация Prophet модели
- **Секции:** Параметры модели, источник данных, инференс, мониторинг

### 3. ✅ Скрипт Инициализации (Python)
- **Файл:** `scripts/setup_test_model.py`
- **Функции:**
  - Создание синтетических данных (30 дней)
  - Обучение Prophet модели
  - Регистрация в MLflow
  - Создание конфигурационных файлов

### 4. ✅ Скрипт Окружения (Bash)
- **Файл:** `scripts/setup_test_env.sh`
- **Функции:**
  - Создание директорий
  - Установка зависимостей
  - Инициализация модели
  - Создание тестовых фикстур

### 5. ✅ Makefile для удобства
- **Файл:** `Makefile`
- **Команды:** setup-test, clean-test, test, run-api, mlflow-ui

### 6. ✅ Документация
- **Файл:** `docs/TEST_MODEL_SETUP.md`
- **Содержит:** Полное руководство по настройке

---

## 🚀 Быстрый Старт (3 Минуты)

### Способ 1: Используя Makefile (Самый Простой)

```bash
cd /Users/rustamkrikbayev/Documents/projects/forecast/ml-server
make setup-test
```

**Результат:**
- ✓ Созданы директории
- ✓ Установлены зависимости
- ✓ Создана синтетическая модель
- ✓ Зарегистрирована в MLflow

### Способ 2: Используя Скрипт Bash

```bash
cd /Users/rustamkrikbayev/Documents/projects/forecast/ml-server
bash scripts/setup_test_env.sh
```

### Способ 3: Ручно

```bash
# 1. Создать директории
mkdir -p config logs tests/fixtures/test_data mlflow_artifacts

# 2. Установить зависимости
pip install -r requirements.txt

# 3. Инициализировать модель
python scripts/setup_test_model.py
```

---

## 📋 Структура Конфигурации

### .env.test (Переменные Окружения)

```env
# Основные параметры
ENV=test
DEBUG=true

# API
API_HOST=0.0.0.0
API_PORT=8000

# MLflow
MLFLOW_TRACKING_URI=sqlite:///mlflow.db
MLFLOW_ARTIFACT_ROOT=./mlflow_artifacts

# Модель
MODEL_TYPE=prophet
MODEL_HORIZON=24
MODEL_FREQ=H
```

### config/test_model_config.yaml (Конфигурация Модели)

```yaml
name: prophet_watt_h_AKMOLA_test
version: 1.0.0
type: prophet

model:
  type: prophet
  horizon: 24                    # ← 24 часа
  freq: H                        # ← Почасовые данные
  seasonality_mode: additive     # ← Аддитивная сезонность

data_source:
  object_reference: /KAZ/AKMOLA/@models/P_WATT
  apis:
    - name: load
      endpoint: /api/load
      timeout: 30

inference:
  timeout: 60
  max_workers: 4
  include_confidence_intervals: true

tags:
  horizon: "24"
  model_type: "prophet"
  environment: "test"
```

---

## 🔍 Проверка Установки

### Шаг 1: Проверить Директории

```bash
ls -la mlflow_artifacts/
ls -la tests/fixtures/test_data/
```

**Ожидаемо:**
```
mlflow_artifacts/
├── 0/                   # Experiment artifacts
└── ...

tests/fixtures/test_data/
└── sample.csv          # 721 строка синтетических данных
```

### Шаг 2: Проверить MLflow

```bash
# Запустить MLflow UI
mlflow ui --backend-store-uri sqlite:///mlflow.db

# Открыть http://localhost:5000 в браузере
# Должна быть видна модель: prophet_watt_h_AKMOLA_test
# With tags:
#   - horizon: 24
#   - model_type: prophet
#   - environment: test
```

### Шаг 3: Проверить API

```bash
# Терминал 1: Запустить API
python -m uvicorn src.api.main:app --reload --port 8000

# Терминал 2: Тестовый запрос
curl -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d '{
    "object_reference": "/KAZ/AKMOLA/@models/P_WATT",
    "model_id": "prophet_watt_h_AKMOLA_test"
  }'
```

**Ожидаемый ответ (200 OK):**
```json
{
  "status": "success",
  "object_reference": "/KAZ/AKMOLA/@models/P_WATT",
  "model_id": "prophet_watt_h_AKMOLA_test",
  "horizon": 24,
  "forecast": [
    {
      "timestamp": "2026-04-20T01:00:00Z",
      "value": 512.34
    },
    ...
  ]
}
```

---

## 📊 Параметры Тестовой Модели

| Параметр | Значение | Описание |
|----------|---------|---------|
| **Model** | Prophet | Модель временного ряда Facebook |
| **Horizon** | 24 часа | Прогноз на 1 день |
| **Frequency** | Hourly | Данные почасовые |
| **Training Data** | 30 дней | ~720 точек данных |
| **Seasonality** | Additive | Аддитивная сезонность |
| **Region** | AKMOLA | Тестовый регион |
| **Entity** | Load (P_WATT) | Прогноз нагрузки |
| **Confidence** | 95% | Доверительные интервалы |

---

## 🛠️ Доступные Команды

### Makefile

```bash
make setup-test        # Полная настройка (рекомендуется)
make clean-test        # Очистить артефакты
make test              # Запустить тесты
make run-api           # Запустить API
make mlflow-ui         # Запустить MLflow UI
make test-predict      # Протестировать предсказание
make logs              # Показать логи
```

### Скрипты

```bash
# Инициализировать модель
python scripts/setup_test_model.py

# Полная настройка окружения
bash scripts/setup_test_env.sh
```

### Python

```bash
# Запустить API
python -m uvicorn src.api.main:app --reload

# Запустить тесты
pytest tests/ -v

# Проверить покрытие
pytest tests/ --cov=src
```

---

## 📁 Создаваемые Файлы и Директории

```
ml-server/
├── .env.test                                    # ✅ Окружение
├── config/
│   ├── test_model_config.yaml                  # ✅ Конфигурация модели
│   └── test_runtime.json                       # ✅ Runtime конфигурация
├── scripts/
│   ├── setup_test_model.py                     # ✅ Python скрипт
│   └── setup_test_env.sh                       # ✅ Bash скрипт
├── tests/
│   └── fixtures/
│       ├── test_data/
│       │   └── sample.csv                      # ✅ Синтетические данные
│       └── test_request.json                   # ✅ Тестовый запрос
├── logs/                                       # ✅ Директория логов
├── mlflow_artifacts/                           # ✅ MLflow артефакты
├── Makefile                                    # ✅ Makefile
└── docs/
    └── TEST_MODEL_SETUP.md                     # ✅ Документация
```

---

## 🔧 Конфигурирование

### Изменить Горизонт Прогноза

```yaml
# config/test_model_config.yaml
model:
  horizon: 48  # Вместо 24
```

### Изменить Регион

```yaml
# config/test_model_config.yaml
data_source:
  object_reference: /KAZ/AKTOBE/@models/P_WATT  # Другой регион
  region: AKTOBE
```

### Изменить Параметры Модели

```yaml
# config/test_model_config.yaml
model:
  seasonality_mode: multiplicative  # Вместо additive
  yearly_seasonality: false
  weekly_seasonality: true
```

### Изменить Источник Данных

```yaml
# config/test_model_config.yaml
data_source:
  apis:
    - name: load
      endpoint: /api/custom_load  # Новый endpoint
    - name: custom_data
      endpoint: /api/custom_endpoint
      required: false
```

---

## 🧪 Тестирование

### Запустить Все Тесты

```bash
make test
# или
pytest tests/ -v
```

### Запустить Тест Предсказания

```bash
make test-predict
```

### С Покрытием

```bash
pytest tests/ --cov=src --cov-report=html
open htmlcov/index.html
```

---

## ⚠️ Решение Проблем

### Проблема: "Prophet not found"
```bash
pip install prophet
```

### Проблема: "MLflow artifact directory error"
```bash
mkdir -p mlflow_artifacts
python scripts/setup_test_model.py
```

### Проблема: "Port 8000 already in use"
```bash
# Другой порт
python -m uvicorn src.api.main:app --port 8001

# Или найти процесс
lsof -i :8000
kill -9 <PID>
```

### Проблема: "Model not found in registry"
```bash
# Пересоздать
rm mlflow.db
python scripts/setup_test_model.py
```

---

## 📈 Что Дальше?

После успешной настройки:

### 1. Разработка
- Используйте тестовую модель для разработки
- Модифицируйте API под ваши нужды
- Добавляйте новые эндпоинты

### 2. Тестирование
- Запустите полный тестовый набор
- Проверьте интеграцию с SCADA
- Валидируйте результаты

### 3. Развёртывание
- Настройте production окружение
- Обучите реальные модели
- Настройте CI/CD

### 4. Мониторинг
- Просматривайте метрики в MLflow
- Анализируйте логи
- Отслеживайте производительность

---

## 📚 Ссылки на Документацию

| Документ | Назначение |
|----------|-----------|
| [TEST_MODEL_SETUP.md](TEST_MODEL_SETUP.md) | Полное руководство по настройке |
| [INFERENCE_PIPELINE_DETAILED_EXPLANATION.md](INFERENCE_PIPELINE_DETAILED_EXPLANATION.md) | Как работает инференс |
| [API_CONTRACT_UPDATE.md](API_CONTRACT_UPDATE.md) | Формат API запросов/ответов |
| [00_START_HERE.md](00_START_HERE.md) | Начало работы |

---

## ✅ Проверочный Список

Перед началом разработки убедитесь:

- [ ] Запущен `make setup-test` без ошибок
- [ ] MLflow UI показывает модель `prophet_watt_h_AKMOLA_test`
- [ ] API запускается на http://localhost:8000
- [ ] curl запрос возвращает 200 с прогнозом
- [ ] Тесты проходят: `pytest tests/ -v` → все PASSED
- [ ] Логи доступны: `tail -f logs/test.log`
- [ ] Конфигурация читается: проверить `.env.test`

---

## 🎉 Готово!

Ваша тестовая среда полностью настроена и готова к использованию!

**Чтобы начать:**

```bash
cd /Users/rustamkrikbayev/Documents/projects/forecast/ml-server
make setup-test
make run-api        # Терминал 1
make mlflow-ui      # Терминал 2 (в другом окне)
make test-predict   # Терминал 3 (в третьем окне)
```

---

**Версия:** 1.0  
**Дата:** 20.04.2026  
**Статус:** ✅ Готово к использованию
