# API

Подробные схемы с валидацией смотрите в [HTTP схемах](./schema/MAIN.md)\
Подробные выходящие данные смотрите в [HTTP сообщениях](./MESSAGES.md)

## Список запросов

- [predict](#1-predict) - **POST**

## 1. predict

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

- **fp_path** - путь к FP объекту
- **model_path** - модель, которая нужна из прогнозов
- **output_range** - диапазон для проноза (период)
- **step** - шаг в секундах
- **archives** - массив с полными FP путями (откуда брать данные архивов из НДЦ)
- **clip_negatives_to_0** - обрезать до 0 данные
- **use_dynamic_normalization** - использовать динамическую нормализацию

```json
{
  "fp_path": "root/FP/PROJECT/KAZ/AKMOLA/@regions/Akmola",
  "model_path": "prophet/watt/h/AKMOLA/@regions/Akmola/load",
  "output_range": 48,
  "step": 3600,
  "archives": [
    "root/FP/PROJECT/KAZ/@regions/AkmolaEU/Load/Pload_consume/archives/out_value",
    "root/FP/PROJECT/KAZ/AKMOLA/@regions/Akmola/weather/temperature/archives/out_value"
  ],
  "clip_negatives_to_0": true,
  "use_dynamic_normalization": false
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
