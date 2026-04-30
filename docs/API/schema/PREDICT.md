# Схема для Predict

Для [API predict](../MAIN.md#1-predict) используется две схемы:
1. Создание задачи (`PredictCreateSchema`) - первый запрос
2. Опрос результата (`PredictUpdateSchema`) - повторный запрос

Для обеих схем действует строгий режим: лишние поля запрещены.

## Создание `PredictCreateSchema`

| Обязательность | Поле | Тип | Описание |
| --- | --- | --- | --- |
| обязательно | `object_reference` | `string` | путь к FP-объекту |
| необязательно | `model_id` | `string` | бизнес-идентификатор модели, по умолчанию `none` |
| необязательно | `model_selection` | `object` | селектор модели в MLflow Registry |
| внутреннее | `online` | `boolean` | вычисляется автоматически |
| внутреннее | `selector` | `string` | вычисляется автоматически |

### Поле `object_reference`

- не может быть пустым;
- должно содержать `/` или `\\`.

### Поле `model_id`

- не может быть пустым;
- значение `none` включает online-режим.

### Поле `model_selection`

Поддерживаются два взаимоисключающих поля:

| Поле | Тип | Описание |
| --- | --- | --- |
| `version_alias` | `string` | alias в MLflow Registry, например `Production` |
| `version` | `string` | конкретная версия модели в MLflow Registry |

Правила:

- `version_alias` и `version` нельзя передавать одновременно;
- пустые строки запрещены;
- если `model_selection` не передан, сервер использует alias `Production`.

Пример create-запроса:

```json
{
	"object_reference": "/KAZ/AKMOLA/@models/P_WATT",
	"model_id": "prophet/watt/h/AKMOLA/@regions/Akmola/load",
	"model_selection": {
		"version_alias": "Production"
	}
}
```

## Внутренние вычисляемые поля

### `online`

| Значение | Условие |
| --- | --- |
| `true` | `model_id == "none"` |
| `false` | `model_id != "none"` |

### `selector`

| Ситуация | Значение |
| --- | --- |
| указан `model_selection.version` | значение `version` |
| указан `model_selection.version_alias` | значение `version_alias` |
| `model_selection` не указан | `Production` |

## Обновление `PredictUpdateSchema`

| Обязательность | Поле | Тип | Описание |
| --- | --- | --- | --- |
| обязательно | `task_id` | `string` | идентификатор ранее созданной задачи |
