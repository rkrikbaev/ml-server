# TRAINING STAGE 6: Возврат результатов (Return Results)

Цель этапа: вернуть клиенту (SCADA/внешнему API-потребителю) итог обучения в едином контракте ответа.

---

## 1. Что делает этап

Stage 6:
- собирает итоговый payload из Stage 5;
- добавляет идентификаторы run/model;
- включает метрики качества;
- возвращает статус выполнения и диагностическое сообщение;
- завершает training pipeline transaction.

---

## 2. Типовой контракт ответа

Пример успешного ответа:

```json
{
  "status": "success",
  "run_id": "abc123def456",
  "model_id": "prophet_watt_h_AKMOLA_@regions_Akmola_load",
  "metrics": {
    "mae": 45.2,
    "mape": 3.1,
    "rmse": 62.8
  },
  "timestamp": "2026-04-17T14:30:00Z",
  "message": "Model trained successfully"
}
```

Поля:
- `status`: `success` или `error`;
- `run_id`: идентификатор MLflow run;
- `model_id`: идентификатор/имя модели;
- `metrics`: ключевые показатели качества;
- `timestamp`: время завершения;
- `message`: человекочитаемый итог.

---

## 3. Ошибочный ответ

Пример:

```json
{
  "status": "error",
  "run_id": null,
  "model_id": null,
  "metrics": null,
  "timestamp": "2026-04-17T14:30:00Z",
  "message": "Training failed at Stage 2: data source timeout"
}
```

Рекомендация:
- в сообщении фиксировать точку отказа (Stage N) для ускорения triage.

---

## 4. Семантика завершения

Stage 6 считается завершенным, когда:
- клиент получил ответ по HTTP;
- ответ соответствует контракту;
- в случае успеха содержит `run_id` и `metrics`;
- в случае ошибки содержит диагностику причины.

---

## 5. Интеграция с внешней системой

Внешний клиент (например SCADA) обычно делает:
1. POST `/train`;
2. получает TrainResponse;
3. сохраняет `run_id` и `model_id`;
4. использует их для аудита и последующего контроля inference-пайплайна.

---

## 6. Что важно для downstream

Минимум для последующих процессов:
- `run_id` — ссылка на полный MLflow контекст;
- `model_id` — ссылка на обученный артефакт/версию;
- `metrics` — принятие решения о пригодности модели.

---

## 7. Проверка этапа

1. Успешный сценарий возвращает полный payload с `run_id`.
2. Ошибочный сценарий возвращает единый error contract.
3. Поле `timestamp` соответствует UTC/согласованной TZ политике.
4. `metrics` присутствуют и имеют числовые типы.

---

## 8. Критерий готовности Stage 6

- API-ответ сформирован и отдан клиенту;
- контракт соблюден для success/error веток;
- training pipeline считается полностью завершенным.

---

## 9. Мини-схема потока

```text
Stage 5 (MLflow run complete)
  -> collect run_id/model_id/metrics
  -> build TrainResponse
  -> return HTTP response to caller
  -> end of training pipeline
```
