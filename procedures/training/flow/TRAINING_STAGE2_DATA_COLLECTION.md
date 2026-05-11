# TRAINING STAGE 2: Сбор данных (Data Collection)

Цель этапа: получить исторический ряд (и при необходимости дополнительные источники) по `data_source_config` для последующего обучения.

---

## 1. Что делает этап

На этом шаге pipeline:
- читает `data_source_config` из Stage 1;
- строит запросы к внешним источникам;
- выгружает исторические значения за нужный период;
- объединяет данные в единый DataFrame;
- валидирует минимальную пригодность набора.

Граница этапа:
- успех: сформирован raw DataFrame для препроцессинга;
- ошибка: этап завершает pipeline с сообщением о недоступности/некорректности данных.

---

## 2. Входной контракт

Вход:
- `object_reference`
- `model_type`
- `data_source_config`
- временные границы выборки (`start_date`, `end_date`) или их вычисление по правилам pipeline

Пример источника в `data_source_config`:

```json
{
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
}
```

---

## 3. Типовой алгоритм

```text
for each source in data_source_config.sources:
  1) build request params
  2) call external API
  3) parse response JSON
  4) convert to DataFrame
merge all DataFrames
return combined raw DataFrame
```

---

## 4. Пример внешнего API

Запрос:

```text
GET /api/timeseries?object_id=AKMOLA_LOAD&interval=1h&start_date=...&end_date=...
```

Ответ:

```json
[
  {"timestamp": "2025-01-01T00:00:00Z", "value": 1234.5},
  {"timestamp": "2025-01-01T01:00:00Z", "value": 1198.2}
]
```

Результат на выходе Stage 2:

```text
timestamp                value
2025-01-01T00:00:00Z     1234.5
2025-01-01T01:00:00Z     1198.2
...
```

---

## 5. Ошибки и деградации

Критичные ошибки:
- source недоступен (`ConnectError`, timeout);
- ответ API некорректный или пустой;
- отсутствуют ожидаемые поля (`timestamp`, `value`);
- невозможна агрегация нескольких источников.

Рекомендуемые действия:
- логировать полный контекст: URL, params, код ответа;
- использовать retry/backoff для временных сбоев;
- явно различать «источник пустой» vs «источник недоступен».

---

## 6. Выход этапа

На Stage 3 передается raw dataset:

```json
{
  "rows": "N > 0",
  "columns": ["timestamp", "value", "...optional features..."],
  "source_meta": {
    "sources_used": 1,
    "period": "[start_date, end_date]"
  }
}
```

---

## 7. Проверка этапа

1. Убедиться, что endpoint источника доступен.
2. Проверить, что дата-диапазон возвращает данные.
3. Сверить колонки ответа с `date_column` и `target_column`.
4. Подтвердить, что итоговый DataFrame не пуст.

---

## 8. Критерий готовности Stage 2

- данные успешно загружены;
- структура данных соответствует ожиданиям следующего этапа;
- pipeline может перейти в Stage 3 (предобработка).
