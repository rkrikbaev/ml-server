# TRAINING STAGE 1: Прием запроса /train (Request Reception)

Цель этапа: принять и провалидировать входной training-запрос, после чего передать нормализованные параметры в pipeline.

---

## 1. Что делает этап

На этом шаге сервис:
- принимает HTTP POST запрос на endpoint обучения;
- валидирует структуру JSON и обязательные поля;
- проверяет семантику параметров (`model_type`, `object_reference`, `data_source_config`, `train_params`);
- формирует входной контракт для Stage 2.

Граница этапа:
- успех: запрос принят и преобразован в внутреннюю структуру pipeline;
- ошибка: возвращается валидирующий ответ (обычно 4xx) без перехода к сбору данных.

---

## 2. Входной контракт

Ожидаемый payload (минимальный пример):

```json
{
  "object_reference": "/KAZ/AKMOLA/AKMOLA/@models/P_WATT",
  "model_type": "prophet",
  "data_source_config": {
    "sources": [
      {
        "type": "rest_api",
        "url": "http://datasource.example.com/api/timeseries",
        "params": {
          "object_id": "AKMOLA_LOAD",
          "interval": "1h"
        }
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

Ключевые поля:
- `object_reference`: уникальный идентификатор объекта/сигнала для обучения.
- `model_type`: тип модели (`prophet` или `xgboost`).
- `data_source_config`: «паспорт данных» (где и как брать исторический ряд).
- `train_params`: гиперпараметры выбранной модели.

---

## 3. Data Passport (критичный смысл поля)

`data_source_config` хранит источник и формат данных, и затем сохраняется в MLflow на этапе Stage 5.

Зачем это нужно:
- инференс может автоматически восстановить откуда брать входные данные;
- повторный запуск/репродукция обучения возможны без ручной переконфигурации;
- один и тот же `object_reference` можно обучать на разных data-source стратегиях.

---

## 4. Валидация на этапе

Типовые проверки:
- JSON корректен и парсится;
- обязательные поля присутствуют;
- `model_type` поддерживается;
- `data_source_config.sources` не пуст;
- `date_column`, `target_column`, `freq` заданы;
- `train_params` соответствует выбранной модели.

Типовые ошибки:
- пустой `object_reference`;
- неподдерживаемый `model_type`;
- некорректный `url` источника;
- отсутствуют колонки в конфиге (`date_column`/`target_column`).

---

## 5. Выход этапа

В Stage 2 передается нормализованный набор:

```json
{
  "object_reference": "...",
  "model_type": "prophet|xgboost",
  "data_source_config": {"...": "..."},
  "train_params": {"...": "..."}
}
```

Если проверка не пройдена, pipeline останавливается и возвращает ошибку в API-ответе.

---

## 6. Псевдопоток вызовов

```text
POST /train
  -> parse JSON
  -> validate schema
  -> validate semantic rules
  -> build internal TrainRequest
  -> pass to Stage 2 (Data Collection)
```

---

## 7. Что проверять при отладке

1. Поля в payload соответствуют ожидаемой схеме.
2. `model_type` совпадает с доступными тренерами.
3. В `data_source_config` указан рабочий endpoint.
4. Конфиг содержит правильные названия колонок (`timestamp/value` или эквиваленты).

---

## 8. Критерий готовности Stage 1

- запрос успешно прошел синтаксическую и семантическую валидацию;
- сформирован внутренний training-request;
- pipeline готов перейти к Stage 2 (сбор данных).
