# Data Quality Assessment

Оценка качества входных данных встроена в пайплайн прогнозирования и доступна как отдельный эндпоинт.

---

## 1. Автоматически при прогнозе

Каждый вызов `GET /predict/{model_id}` автоматически запускает оценку качества исторических данных.  
Результат возвращается в теле ответа внутри `data.data_quality`.

```json
{
  "status": 200,
  "data": {
    "output": [[ts, value, null], ...],
    "data_quality": {
      "overall_quality_score": 94.5,
      "window_start": "2026-05-28T00:00:00Z",
      "window_end":   "2026-05-29T12:00:00Z",
      "elapsed_seconds": 0.003,
      "anomalies_count": 4,
      "tags": {
        "/path/to/archive": {
          "quality_score": 94.5,
          "total_expected_points": 360,
          "missing_points_count": 3,
          "duplicates_count": 0,
          "outliers_count": 1,
          "stuck_sequences_count": 0,
          "rate_of_change_count": 0,
          "long_gaps_count": 0
        }
      }
    }
  }
}
```

**Логирование:**
- `INFO`  — общий счёт, число аномалий, число тегов, время выполнения
- `DEBUG` — детальная статистика по каждому тегу

Ошибка пайплайна оценки не прерывает прогноз — логируется как `WARNING`, ключ `data_quality` в ответ не попадает.

---

## 2. Отдельный эндпоинт

```http
POST /data-quality/assess
Content-Type: application/json

{
  "object_ref": "/path/to/archive",
  "from":       "2026-05-01T00:00:00Z",
  "to":         "2026-05-28T00:00:00Z",
  "step":       3600
}
```

| Поле | Тип | Описание |
|------|-----|----------|
| `object_ref` | string \| array | Путь к архиву (или список путей) |
| `from` | ISO-8601 \| Unix ms \| `""` | Начало окна (пусто → `to` − 24 шага) |
| `to` | ISO-8601 \| Unix ms \| `""` | Конец окна (пусто → текущий час UTC) |
| `step` | int | Шаг в секундах (например, `3600`) |

Опциональные параметры:

| Поле | По умолчанию | Описание |
|------|-------------|----------|
| `allow_look_ahead` | `true` | `false` → только forward-fill (для онлайн-режима) |
| `z_score_window` | `48` | Скользящее окно детекции спайков |
| `z_score_threshold` | `3.0` | Порог \|Z\| для спайка |
| `stuck_window` | `10` | Минимальное число одинаковых значений подряд → stuck signal |
| `scada_url` | — | Переопределить URL SCADA для этого запроса |

Ответ содержит `metadata`, `metrics_scoring`, `anomalies_log`, `cleaned_data`.

---

## 3. Пайплайн валидации (4 шага)

| Шаг | Что делает |
|-----|-----------|
| **Chronological** | Дедупликация (mean), сортировка, выравнивание на регулярную сетку |
| **Static bounds** | ±inf → NaN; rolling Z-score → NaN |
| **Dynamic control** | Скачки (99.9-й перцентиль diff) → NaN; stuck signal → NaN |
| **Imputation** | Пропуски ≤ 3 → линейная; 4–30 → кубический сплайн; > 30 → не заполняется |

**Формула счёта:**
```
Score = 100 × (1 − (w_missing×N_miss + w_dup×N_dup + w_spike×N_spike + w_stuck×N_stuck) / N_total)
```
Зажат в [0, 100].

---

## 4. Локальное тестирование (Jupyter)

```
procedures/workflow/TEST_DATA_QUALITY.ipynb       # требует ml-server (src/ в PYTHONPATH)
procedures/workflow/DATA_QUALITY_STANDALONE.ipynb # полностью автономный, только pip-пакеты
```

Зависимости автономного ноутбука:
```
pip install pydantic numpy scipy pandas requests plotly
```

---

## 5. Структура кода

```
lib/pipeline.py                        ← единственный источник логики (схемы + пайплайн)
src/api/data_quality/
    models.py                          ← re-export из lib/pipeline.py
    pipeline.py                        ← re-export из lib/pipeline.py
    router.py                          ← POST /data-quality/assess
src/api/broker/tasks/predict.py        ← _assess_data_quality() вызывается при прогнозе
```
