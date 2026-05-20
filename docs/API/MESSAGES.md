# Сообщения

<img alt="Author" src="https://img.shields.io/badge/Author-Мария%20Полковникова-ffc107?style=for-the-badge" />
<img alt="Date of Creation" src="https://img.shields.io/badge/Date%20of%20Creation-2026.03.12,%2011:21%20AM-1565c0?style=for-the-badge" />

## Список сообщений

- **200**: Хорошо
- **202**: Принято (_2 варианта_)
- **404**: Не найдено
- **422**: Необрабатываемый экземпляр (_7 вариантов_)
- **500**: Внутренняя ошибка сервера
- **503**: Сервис недоступен (_2 формата, 5 источников_)

---

## 200: Хорошо

`data` любой тип данных

Для predict-flow в успешном `data` может присутствовать поле `model_confidence`.
Текущее поведение: значение вычисляется в диапазоне `[0.0, 1.0]` на основе `is_matching` и полноты выходного ряда.

```json
{
  "status": 200,
  "state": "done",
  "task_id": "...",
  "data": ...
}
```

---

## 202: Принято

### 1-ый вариант

Применяется, когда начали обработку задачи

```json
{
  "status": 202,
  "state": "start",
  "task_id": "...",
  "object_ref": "..."
}
```

### 2-ой вариант

Применяется, когда задача в процессе или удалена

```json
{
  "status": 202,
  "state": "processing",
  "task_id": "..."
}
```

---

## 404: Не найдено

```json
{
  "status": 404,
  "message": "API not found"
}
```

---

## 422: Необрабатываемый экземпляр

### [Вариант 1](./schema/MAIN.md)

`details` содержит ключ дескриминатора названия tag из схемы, а значение - список ошибок валидации

Возникает, когда входные данные не соответствуют действительности

```json
{
  "status": 422,
  "message": "A valid JSON format was expected, but the data was not received or was invalid.",
  "details": {"...": ["..."]}
}
```

### Вариант 2

Возникнет, когда данные не понравились при обработки исходящих от НДЦ

```json
{
  "status": 422,
  "state": "done",
  "task_id": "...",
  "object_ref": "...",
  "message": "Incorrect data in the dataset from archives."
}
```

### Вариант 3

Возникнет, когда данные не понравились при обработке данных у модели

```json
{
  "status": 422,
  "state": "done",
  "task_id": "...",
  "object_ref": "...",
  "message": "Forecast execution error: {сообщение от ошибки из кода}"
}
```

### Вариант 4

Возникнет, когда данные не понравились при обработке данных погоды

```json
{
  "status": 422,
  "state": "done",
  "task_id": "...",
  "object_ref": "...",
  "message": "Incorrect data in the dataset from weather service.",
  "details": "{опционально: сообщение от ошибки из кода}"
}
```

### Вариант 5

Возникнет, когда данные не понравились при обработке historical_data

```json
{
  "status": 422,
  "state": "done",
  "task_id": "...",
  "object_ref": "...",
  "message": "Incorrect data in the dataset from HISTORICAL_DATA.",
  "details": "{опционально: сообщение от ошибки из кода}"
}
```

### Вариант 6

Возникнет, когда отсутствует `config.json` для `model_id`

```json
{
  "status": 422,
  "state": "done",
  "task_id": "...",
  "object_ref": "...",
  "message": "Model launch aborted: config.json not found for model '{model_id}'."
}
```

### Вариант 7

Возникнет, когда модель не получила входные данные из архивов

```json
{
  "status": 422,
  "state": "done",
  "task_id": "...",
  "object_ref": "...",
  "message": "Model launch aborted: no input data received from archives."
}
```

---

## 500: Внутренняя ошибка сервера

```json
{
  "status": 500,
  "state": "done",
  "task_id": "...",
  "object_ref": "...",
  "message": "Internal server error: {сообщение от ошибки из кода}"
}
```

---

## 503: Сервис недоступен

### Вариант 1

Не связался с внешним сервисом (NDC, RZ, WEATHER, HISTORICAL_DATA, MLFLOW)

```json
{
  "status": 503,
  "state": "done",
  "task_id": "...",
  "object_ref": "...",
  "message": "{NDC, RZ, WEATHER, HISTORICAL_DATA или MLFLOW} is not available, so it is impossible to take values at this time."
}
```

### Вариант 2

Не связался с внешним сервисом (NDC, RZ, WEATHER, HISTORICAL_DATA, MLFLOW) и добавил сообщение из кода

```json
{
  "status": 503,
  "state": "done",
  "task_id": "...",
  "object_ref": "...",
  "message": "{NDC, RZ, WEATHER, HISTORICAL_DATA или MLFLOW} is not available, so it is impossible to take values at this time. Error: {сообщение от ошибки из кода}"
}
```

---
