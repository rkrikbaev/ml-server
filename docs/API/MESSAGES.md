# Сообщения

<img alt="Author" src="https://img.shields.io/badge/Author-Мария%20Полковникова-ffc107?style=for-the-badge" />
<img alt="Date of Creation" src="https://img.shields.io/badge/Date%20of%20Creation-2026.03.12,%2011:21%20AM-1565c0?style=for-the-badge" />

## Список сообщений

- **200**: Хорошо
- **202**: Принято (_2 варианта_)
- **404**: Не найдено
- **422**: Необрабатываемый экземпляр (_3 варианта_)
- **500**: Внутренняя ошибка сервера
- **503**: Сервис недоступен (_2 варианта_)

---

## 200: Хорошо

`data` любой тип данных

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
  "object_reference": "..."
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
  "object_reference": "...",
  "message": "Incorrect data in the dataset from archives.",
  "quality": ...
}
```

### Вариант 3

Возникнет, когда данные не понравились при обработке данных у модели

```json
{
  "status": 422,
  "state": "done",
  "task_id": "...",
  "object_reference": "...",
  "message": "Forecast execution error: {сообщение от ошибки из кода}"
}
```

---

## 500: Внутренняя ошибка сервера

```json
{
  "status": 500,
  "state": "done",
  "task_id": "...",
  "object_reference": "...",
  "message": "Internal server error: {сообщение от ошибки из кода}"
}
```

---

## 503: Сервис недоступен

### Вариант 1

Не связался с сервисом НДЦ, ремонтных заявок или MLflow

```json
{
  "status": 503,
  "state": "done",
  "task_id": "...",
  "object_reference": "...",
  "message": "{NDC, RZ или MLFLOW} is not available, so it is impossible to take values at this time."
}
```

### Вариант 2

Не связался с сервисом НДЦ, ремонтных заявок или MLflow и добавил сообщение из кода

```json
{
  "status": 503,
  "state": "done",
  "task_id": "...",
  "object_reference": "...",
  "message": "{NDC, RZ или MLFLOW} is not available, so it is impossible to take values at this time. Error: {сообщение от ошибки из кода}"
}
```

---
