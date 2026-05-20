# Common Model Interface Implementation — Summary

## Overview

Реализован единый интерфейс для всех библиотечных модулей прогнозирования, который позволяет подключить любую модель к серверу прогнозирования без изменения серверного кода.

**Главная идея**: все модели (Prophet, XGBoost, scikit-learn и др.) должны принимать одинаковые входные данные и возвращать одинаковые выходные данные, соответствуя контракту `BaseModel`.

---

## 📂 Созданные/Обновленные файлы

### 1. **`ml-server/src/api/forecast/base_interface.py`** (NEW)
Основной модуль, определяющий контракт для всех моделей.

**Содержит**:
- `PredictionInput` (dataclass) — единый входной формат
  - `features: Dict` — признаки/входные данные
  - `metadata: Dict` — опциональные метаданные (регион, источник и т.д.)
  - `config: Dict` — опциональная конфигурация (batch_size, device и т.д.)
  - Методы: `to_dict()`, `to_json()`, `from_dict()`, `from_json()`

- `PredictionOutput` (dataclass) — единый выходной формат
  - `predictions: Any` — основные прогнозы
  - `confidence: Optional[List[float]]` — опциональная уверенность
  - `metadata: Optional[Dict]` — опциональные метаданные результата
  - Методы: `to_dict()`, `to_json()`, `from_dict()`, `from_json()`

- `BaseModel` (abstract class) — базовый класс для всех моделей
  - Абстрактные методы: `load()`, `predict(input_data)`
  - Вспомогательные методы: `validate_input()`, `is_loaded()`

**Использование**:
```python
from api.forecast.base_interface import BaseModel, PredictionInput, PredictionOutput

class MyModel(BaseModel):
    def load(self):
        # загрузить модель
        pass
    
    def predict(self, input_data: PredictionInput) -> PredictionOutput:
        # выполнить прогноз
        pass
```

---

### 2. **`ml-server/src/api/forecast/adapters.py`** (NEW)
Примеры готовых адаптеров для популярных типов моделей.

**Содержит**:
- `ProphetModelAdapter` — для Facebook Prophet
- `XGBoostModelAdapter` — для XGBoost
- `ScikitLearnModelAdapter` — для scikit-learn (LinearRegression, RandomForest и т.д.)
- `get_model_adapter(model_type, model_path, config)` — фабрика для создания адаптеров

**Особенности**:
- Каждый адаптер наследует `BaseModel` и реализует `load()` и `predict()`
- Обработка специфики каждого типа модели (например, Prophet работает с датами в формате 'ds')
- Сериализация результатов в `PredictionOutput` с дополнительными метаданными (доверительные интервалы, количество образцов и т.д.)

**Использование**:
```python
from api.forecast.adapters import get_model_adapter

adapter = get_model_adapter('prophet', 'path/to/model.pkl')
adapter.load()

inp = PredictionInput(features={'ds': ['2024-01-01', '2024-01-02']})
output = adapter.predict(inp)
print(output.predictions)  # [1.5, 2.3]
print(output.metadata['intervals'])  # {'lower': [...], 'upper': [...]}
```

---

### 3. **`ml-server/scripts/test_model_interface.py`** (NEW)
Примеры и автоматические тесты для проверки интерфейса.

**Содержит**:
- `test_prediction_input_serialization()` — тест сериализации/десериализации входа
- `test_prediction_output_serialization()` — тест сериализации/десериализации выхода
- `test_dict_conversion()` — тест преобразования в/из словарей
- `test_custom_model_adapter()` — пример создания собственного адаптера
- `test_input_validation()` — проверка валидации входных данных
- `test_metadata_preservation()` — проверка сохранения метаданных
- `print_demo()` — демонстрационные примеры

**Запуск**:
```bash
cd ml-server
python scripts/test_model_interface.py
```

---

### 5. **`ml-server/docs/MODEL_STORAGE_STRUCTURE.md`** (UPDATED)
Обновлена с новым разделом "Общий интерфейс модели (Common Model Interface)".

**Добавлено**:
- Описание компонентов интерфейса (`PredictionInput`, `PredictionOutput`, `BaseModel`)
- Примеры использования адаптеров (Prophet, XGBoost, scikit-learn, фабрика)
- Инструкция по добавлению собственного адаптера
- Пример интеграции с сервером
- Ссылки на файлы реализации

---

## 🔄 Рабочий процесс

### Для использования существующей модели:

```python
from api.forecast.adapters import get_model_adapter
from api.forecast.base_interface import PredictionInput

# 1. Создать адаптер
adapter = get_model_adapter(
    model_type='prophet',
    model_path='/workspace/models/prophet_model.pkl',
    config={}
)

# 2. Загрузить модель
adapter.load()

# 3. Подготовить входные данные
inp = PredictionInput(
    features={'ds': ['2024-01-01', '2024-01-02', '2024-01-03']},
    metadata={'region': 'AKMOLA'}
)

# 4. Выполнить прогноз
output = adapter.predict(inp)

# 5. Получить результаты
print(output.predictions)  # [1.5, 2.3, 1.8]
print(output.confidence)   # [0.92, 0.85, 0.88]
print(output.metadata)     # {'model_type': 'prophet', 'intervals': {...}}
```

### Для добавления новой модели:

1. **Создать адаптер** (в `adapters.py` или отдельном файле):
```python
from api.forecast.base_interface import BaseModel

class CustomModelAdapter(BaseModel):
    def load(self):
        # загрузить модель
        pass
    
    def predict(self, input_data):
        # выполнить прогноз
        pass
```

2. **Зарегистрировать в фабрике** (опционально):
```python
# в get_model_adapter()
adapters['custom'] = CustomModelAdapter
```

3. **Использовать**:
```python
adapter = get_model_adapter('custom', 'path/to/model')
adapter.load()
output = adapter.predict(inp)
```

### Для интеграции с FastAPI сервером:

```python
# В api/forecast/model.py или смежном модуле
from api.forecast.adapters import get_model_adapter
from api.forecast.base_interface import PredictionInput, PredictionOutput

# Загрузить модель
model_adapter = get_model_adapter(model_type, model_path, config)
model_adapter.load()

# В endpoint'е
@app.post("/forecast")
async def forecast(request_data: dict) -> dict:
    # Преобразовать в единый формат
    inp = PredictionInput.from_dict(request_data)
    
    # Выполнить прогноз
    output = model_adapter.predict(inp)
    
    # Вернуть результат
    return output.to_dict()
```

---

## ✅ Преимущества

1. **Однородность кода** — все модели используют один и тот же интерфейс
2. **Расширяемость** — добавление новых типов моделей не требует изменений серверного кода
3. **Переносимость** — модели можно менять без перезагрузки сервера (горячая замена)
4. **Тестируемость** — каждый адаптер можно тестировать независимо
5. **Типизация** — используются dataclasses и type hints для безопасности типов
6. **Сериализация** — встроенная поддержка JSON и dict преобразований

---

## 📋 Чек-лист для интеграции существующих моделей

- [ ] Проверить, есть ли адаптер для типа вашей модели в `adapters.py`
- [ ] Если нет, создать собственный адаптер (см. примеры в `adapters.py`)
- [ ] Убедиться, что модель загружается через `adapter.load()`
- [ ] Подготовить входные данные в формате `PredictionInput`
- [ ] Проверить, что прогноз возвращает `PredictionOutput`
- [ ] Протестировать интеграцию с использованием `scripts/test_model_interface.py`
- [ ] Обновить `MODEL_STORAGE_STRUCTURE.md` с информацией о новом адаптере (если создан)

---

## 🐛 Примеры ошибок и как их решать

### Ошибка: `ModuleNotFoundError: No module named 'api'`
**Решение**: убедиться, что `PYTHONPATH` включает `/workspace/server`
```bash
export PYTHONPATH=/workspace/server:/workspace/lib
```

### Ошибка: `Model not loaded. Call load() first.`
**Решение**: всегда вызывать `adapter.load()` перед `adapter.predict()`
```python
adapter = get_model_adapter(...)
adapter.load()  # <— не забыть
output = adapter.predict(inp)
```

### Ошибка: `ValueError: features must contain 'ds' for Prophet`
**Решение**: для Prophet входные данные должны содержать колонку 'ds' с датами
```python
inp = PredictionInput(features={'ds': ['2024-01-01', '2024-01-02']})
```

---

## 📖 Дополнительная документация

- **`ml-server/docs/MODEL_STORAGE_STRUCTURE.md`** — полное описание структуры хранения и интеграции
- **`ml-server/src/api/forecast/base_interface.py`** — документация в docstrings
- **`ml-server/src/api/forecast/adapters.py`** — примеры адаптеров с комментариями
- **`ml-server/scripts/test_model_interface.py`** — примеры использования и тесты

---

## 🚀 Следующие шаги

1. **Обновить `api/forecast/model.py`** для использования новых адаптеров
2. **Мигрировать существующие модели** (Prophet, XGBoost) на новый интерфейс
3. **Добавить обработку ошибок** для production-среды
4. **Создать CI/CD тесты** для валидации новых адаптеров
5. **Документировать процесс** добавления новых моделей для команды

---

**Дата создания**: 2024
**Версия**: 1.0
**Статус**: ✅ Готово к интеграции
