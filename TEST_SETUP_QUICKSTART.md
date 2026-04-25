# 🚀 Быстрый старт тестовой модели

## ✅ Статус: ГОТОВО К ИСПОЛЬЗОВАНИЮ

Все компоненты тестовой модели (конфигурация, скрипты, документация) успешно созданы и готовы к развертыванию.

---

## 📦 Что было создано

### 1. **Конфигурация окружения** (`.env.test`)
- 50+ параметров для тестовой среды
- API, MLflow, logging настройки
- Модель параметры (horizon=24, freq=H)

### 2. **Конфигурация модели** (`config/test_model_config.yaml`)
- Полная конфигурация Prophet модели
- Параметры обучения и инференса
- Метрики и SLA пороги
- MLflow теги

### 3. **Python скрипты** (`scripts/`)
- `setup_test_model.py` - инициализация и обучение модели
- `setup_test_env.sh` - автоматизация настройки окружения
- `test_model_interface.py` - интерфейс для тестирования

### 4. **Makefile** для управления
- `make setup-test` - полная настройка
- `make run-api` - запуск API
- `make mlflow-ui` - MLflow интерфейс
- `make test` - запуск тестов
- Еще 5+ команд

### 5. **Документация** (`docs/`)
- `TEST_MODEL_SETUP.md` - подробное руководство
- `TEST_MODEL_CONFIGURATION.md` - полная конфигурация
- Встроенные примеры и решение проблем

---

## 🚀 Как начать

### Способ 1: Используя Makefile (Рекомендуется)

```bash
cd /Users/rustamkrikbayev/Documents/projects/forecast/ml-server
make setup-test
```

**Результат:**
- ✓ Созданы директории (config, logs, tests/fixtures, mlflow_artifacts)
- ✓ Установлены зависимости
- ✓ Созданы синтетические данные (30 дней)
- ✓ Обучена Prophet модель
- ✓ Модель зарегистрирована в MLflow
- ✓ Готово к использованию!

### Способ 2: Прямой запуск скриптов

```bash
mkdir -p config logs tests/fixtures/test_data mlflow_artifacts
pip install -r requirements.txt
python scripts/setup_test_model.py
```

---

## ✅ Проверка установки

После успешного запуска `make setup-test`:

```bash
# 1. Проверить MLflow
mlflow ui --backend-store-uri sqlite:///mlflow.db
# Открыть http://localhost:5000
# Должна быть видна модель: prophet_watt_h_AKMOLA_test

# 2. Запустить API (Терминал 1)
make run-api

# 3. Протестировать предсказание (Терминал 2)
make test-predict
```

---

## 📋 Параметры тестовой модели

| Параметр | Значение |
|----------|----------|
| Тип модели | Prophet |
| Горизонт прогноза | 24 часа |
| Частота данных | Hourly (почасовые) |
| Данные для обучения | 30 дней (~720 точек) |
| Регион | AKMOLA |
| Сущность | Load (P_WATT) |
| Интервал доверия | 95% |

---

## 🎯 Доступные команды

```bash
# Основные команды
make setup-test          # Полная настройка и инициализация
make clean-test          # Очистить все артефакты
make test                # Запустить тесты

# Запуск сервисов
make run-api             # Запустить API на порту 8000
make mlflow-ui           # Запустить MLflow UI на порту 5000
make test-predict        # Протестировать predict endpoint

# Управление
make logs                # Показать логи
make status              # Проверить статус
```

---

## 🧪 Тестирование API

После запуска API (`make run-api`), можно тестировать:

```bash
curl -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d '{
    "object_reference": "/KAZ/AKMOLA/@models/P_WATT",
    "model_id": "prophet_watt_h_AKMOLA_test"
  }'
```

Ожидаемый ответ (200 OK):
```json
{
  "status": "success",
  "horizon": 24,
  "forecast": [
    {"timestamp": "2026-04-20T01:00:00Z", "value": 512.34},
    {"timestamp": "2026-04-20T02:00:00Z", "value": 518.92},
    ...
  ]
}
```

---

## 📚 Документация

| Документ | Назначение |
|----------|-----------|
| `TEST_MODEL_SETUP.md` | Пошаговое руководство по настройке |
| `TEST_MODEL_CONFIGURATION.md` | Полная конфигурация и параметры |
| `INFERENCE_PIPELINE_DETAILED_EXPLANATION.md` | Как работает инференс |
| `API_CONTRACT_UPDATE.md` | Формат API запросов |

---

## ⚙️ Конфигурирование

### Изменить горизонт прогноза

```yaml
# config/test_model_config.yaml
model:
  horizon: 48  # Вместо 24
```

### Изменить регион

```yaml
# config/test_model_config.yaml
data_source:
  object_reference: /KAZ/AKTOBE/@models/P_WATT
```

### Изменить параметры MLflow

```bash
# .env.test
MLFLOW_TRACKING_URI=sqlite:///custom_mlflow.db
```

---

## ⚠️ Решение проблем

### Prophet не установлен
```bash
pip install prophet
```

### MLflow artifact директория не найдена
```bash
mkdir -p mlflow_artifacts
python scripts/setup_test_model.py
```

### Модель не найдена в registry
```bash
rm mlflow.db
python scripts/setup_test_model.py
```

### Порт 8000 уже занят
```bash
python -m uvicorn src.api.main:app --port 8001
```

---

## ✅ Проверочный список

Перед началом разработки убедитесь:

- [ ] Запущен `make setup-test` без ошибок
- [ ] MLflow UI показывает модель `prophet_watt_h_AKMOLA_test`
- [ ] API запускается на http://localhost:8000 без ошибок
- [ ] curl запрос возвращает 200 с прогнозом
- [ ] Тесты проходят: `pytest tests/ -v` → все PASSED
- [ ] Логи доступны: `tail -f logs/test.log`

---

## 📊 Структура файлов

```
ml-server/
├── .env.test                          ← Окружение для тестов
├── config/
│   ├── test_model_config.yaml         ← Конфигурация модели
│   └── test_runtime.json              ← Runtime конфигурация
├── scripts/
│   ├── setup_test_model.py            ← Python инициализация
│   └── setup_test_env.sh              ← Bash настройка
├── tests/
│   └── fixtures/
│       ├── test_data/
│       │   └── sample.csv             ← Синтетические данные
│       └── test_request.json           ← Пример запроса
├── logs/                              ← Логи (создаётся)
├── mlflow_artifacts/                  ← MLflow артефакты (создаётся)
├── Makefile                           ← Команды
├── TEST_MODEL_SETUP_SUMMARY.txt       ← Полный summary
└── docs/
    ├── TEST_MODEL_SETUP.md            ← Подробное руководство
    └── TEST_MODEL_CONFIGURATION.md    ← Полная конфигурация
```

---

## 🎉 Готово к использованию!

Все компоненты созданы и настроены. Начните с:

```bash
make setup-test
```

Затем запустите в разных терминалах:
```bash
# Терминал 1: API
make run-api

# Терминал 2: MLflow (опционально)
make mlflow-ui

# Терминал 3: Тестовый запрос
make test-predict
```

---

**Версия:** 1.0  
**Дата:** 20.04.2026  
**Статус:** ✅ ГОТОВО К ИСПОЛЬЗОВАНИЮ
