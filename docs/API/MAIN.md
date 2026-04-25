# API

Подробные схемы с валидацией смотрите в [HTTP схемах](./schema/MAIN.md)\
Подробные выходящие данные смотрите в [HTTP сообщениях](./MESSAGES.md)

## Список запросов

- [predict](#1-predict) - **POST**

## 1. predict

Первый запрос регистрируется в брокере и отправляется в очередь worker. В ответ сервер возвращает статус `START` и `task_id`. Пока worker не завершил обработку, повторный запрос с этим `task_id` будет возвращать статус `PROCESSING`. После завершения задачи сервер возвращает результат со статусом `DONE`.

<img alt="Date of Creation" src="https://img.shields.io/badge/Date%20of%20Creation-20%3F%3F.%3F%3F.%3F%3F,%20%3F%3F:%3F%3F%20%3FM-1565c0?style=for-the-badge" />
<img alt="URL" src="https://img.shields.io/badge/URL-/predict-a00069?style=for-the-badge" />
<img alt="Method" src="https://img.shields.io/badge/Method-POST-00695c?style=for-the-badge" />

### Content-Type

- <img alt="input" src="https://img.shields.io/badge/input-application/json;-4527a0?style=flat-square" />
- <img alt="output" src="https://img.shields.io/badge/output-application/json;-4527a0?style=flat-square" />

### HTTP статусы, которые могут быть возвращены

- 200 - успешный ответ
- 202 - запрос принят, но ещё не обработан; запрос в процессе обработки; ответ удалён
- 422 - некорректный запрос или ответ
- 500 - что-то пошло не так
- 503 - сервис откуда берём дополнительные данные не может достучаться

### Входящие данные

> Подробнее об [ключах и валидации](./schema/PREDICT.md) API

#### Пример 1-ого запроса

- **object_reference** - путь к FP объекту
- **model_id** - модель, которая нужна из прогнозов

```json
{
    "object_reference": "/KAZ/AKMOLA/AKMOLA/@models/P_WATT",
    "model_id": "prophet/watt/h/AKMOLA/@regions/Akmola/load"
}
```

#### Пример 2-ого запроса

- **task_id** - UUID задачи (сам генерируется после запроса 1)

```json
{
  "task_id": "5c852360dce04d399eeaaedd947459ba"
}
```

### Выходящие данные

> Остальные выходящие данные найдёте в [здесь](./MESSAGES.md)

#### Пример ответа

Для данного примера напичкали данные от фонаря, поэтому в серьёз не принимайте за чистую монету, пожалуйста
```json
{
  "status": 200,
  "data": {
    "message": "...",
    "output": [
      [0, 0.0, 0],
      ...
    ],
    "quality": 0,
    "model_confidence": 1.0
  },
  "fp_path": "root/FP/PROJECT/KAZ/AKMOLA/@regions/Akmola",
  "task_id": "f3b44ac9720f40108ad16def9f300b4e",
  "state": "done"
}
```
