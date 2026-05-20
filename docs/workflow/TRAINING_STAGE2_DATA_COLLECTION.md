# TRAINING STAGE 2: Сбор данных (Data Collection)

Цель этапа: получить исторический ряд (и при необходимости дополнительные источники) по `data_config` для последующего обучения.

---

## 1. Что делает этап

На этом шаге pipeline:
- читает `data_config` из Stage 1 (pre-flight + валидация запроса);
- строит запросы к внешним источникам;
- выгружает исторические значения за нужный период;
- объединяет данные в единый DataFrame;
- валидирует минимальную пригодность набора.

Граница этапа:
- успех: сформирован raw DataFrame для препроцессинга;
- ошибка: этап завершает pipeline с сообщением о недоступности/некорректности данных.

---

## 2. Входной контракт (data_config) - описание окружения модели

Схема представления данных:

```json
{
  "object_ref": "/root/FP/PROJECT/AKMOLA/@regions/North Kazakhstan/load/@models/P_watt",
  "input_range": 72,
  "output_range": 24,
  "step": 3600,
  "pattern": "historical[forecast,plan]",
  "sources": [
    {
      "url": "http://127.0.0.1:7080/api/v1/read/archives",
      "parameters": [
        "/root/FP/PROJECT/AKMOLA/@regions/SevKaz/Load/P_Load/archives/out_value"
      ],
      "pattern": "historical"
    }
  ]
}
```

1. `object_ref` - идентификатор объекта - модели
2. `input_range` - диапазон для получения входных данных (часы)
3. `output_range` - диапазон для получения выходных данных (часы)
4. `step` - шаг грануляции (секунды) указанных диапазонов
5. `pattern` - принцип формирования периода для получения данных относительно горизонта
6. `sources` - настройки источников данных:
  - адрес URL источника данных (`url`)
  - список параметров `parameters` данные по которым надо получить
  - шаг в секундах `step`
  - `pattern` - параметр определяет из какого временного диапазона исходных данных запрашивать данные. Существуют три паттерна:
    1. historical - данные в прошлом.
    2. future - данные в будущем

Предпологается, что на стороне источника данных реализован REST API который реализует описанную ниже модель обмена данными.

### Получение исторических данных (historical)

Для получения данных полность находящихся в прошлом относительно настоящего соответсвтуют паттерну - `historical`

Формирование временных границы выборки (`from`, `to`) вычисляются по правилу:

from = now - input_range * step

to = now

`now` - время в формате UNIXTIME (sec)

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

Тогда запрос для получения данных будет выглядет так:

```bash
  curl --location 'http://127.0.0.1:7080/api/v1/read/archives' \
  --header 'Content-Type: application/json' \
  --data-raw '{
      "from": "2026-05-10T0:00:00.000+5",
      "to": "2026-05-10T23:00:00.000+5",
      "archive": [
          "/root/FP/PROJECT/AKMOLA/@regions/KOKSHETAU/Load/P_load/archives/out_value"
      ],
      "step": 3600
  }'
```

Ответ:

```json
{
  "metadata": {
        "source": "mock",
        "timestamp": "2026-05-16T11:02:02Z"
    },
  "parameters": {
      "/root/FP/PROJECT/AKMOLA/@regions/KOKSHETAU/Load/P_load/archives/out_value":[
        [
          1778353200000,
          267.9830287285199
        ],
      
        ...

        [
          1778432400000,
          363.98691685413587
        ]
      ]
  }
}
```

`metadata` - метаданные, содержат вспомогательную информацию
`parameters` - список парметров запрашиваемыми с сервиса

### Получение данных прогноза погоды (forecast)

Запрос:

```bash
curl --location 'http://127.0.0.1:8050/forecast?lat=43.25&lon=76.92'
```

Ответ:

```json
{
    "metadata": {
        "source": "mock",
        "timestamp": "2026-05-16T11:02:02Z",
        "lat": 43.25,
        "lon": 76.92
    },
    "parameters": {
        "temp": [...],
        "pressure": [...],
        "wind_speed": [...],
        "wind_direction": [...],
        "wind_gust":[...],
        "clouds": [...],
        "humidity": [...],
        "light_intensity": [...]
      }
}
```

### Пример запроса планновых данных (plan)

Запрос:

todo.

Ответ:

todo.

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
    "period": "[from, to]"
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
