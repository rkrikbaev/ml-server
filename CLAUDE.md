# ML Forecast Platform — контекст проекта для Claude

## Что это за проект

Серверная платформа для краткосрочного, среднесрочного (месяц) и долгосрочного (год) прогнозирования электрической нагрузки по объектам энергосистемы Казахстана.

Основной потребитель — SCADA-система. Любой HTTP-клиент может подключиться напрямую.

---

## Стек и архитектура

- **API**: FastAPI + uvicorn, основной business endpoint `POST /predict` (дополнительно есть `/ui/*` endpoints для мониторинга)
- **Брокер задач**: `taskiq` + `RedisStreamBroker` — **не Celery**
- **Result backend**: Redis, TTL результатов 1 час
- **Модели**: Prophet, AR/XGBoost через единый `BaseModel` интерфейс (адаптеры)
- **Хранение моделей**: диск `/workspace/models/{model_id}/config.json` + файл модели
- **MLflow**: каталог (SQLite + artifact store), в инференсе **не участвует**
- **Docker Compose**: контейнер `ml_model` (8 CPU, 1 GB RAM) + `redis:7` + `mlflow`
- **Воркеров**: 8, запускаются в одном контейнере командой `taskiq worker api.broker:broker --workers 8`

---

## Ключевые решения проекта

### model_id — двойная роль
`model_id` — это одновременно **уникальный идентификатор модели** и **относительный путь** к её директории под `/workspace/models/`. Первый сегмент пути = тип модели (`prophet`, `xgb`). Все параметры инференса берутся из `config.json` в этой директории — клиент ничего не передаёт кроме `model_id` и `object_reference`.

### API-контракт: двухшаговый асинхронный
```
POST /predict { object_reference, model_id }
→ 202 { task_id, state: "start" }

POST /predict { task_id }
→ 202 { state: "processing" }  — пока выполняется
→ 200/422/500/503 { data.output, state: "done" }  — по завершении
```

### Lifecycle задачи в брокере
`start` → `processing` → `done` (200/422/500/503) → `expired` (после TTL)

Это точные состояния брокера taskiq — **не** Celery-термины (PENDING/STARTED/SUCCESS/FAILURE).

### Горизонт определяется автоматически по `step`
```python
step < 86_400_000 ms  →  "short"   (часовой / суточный)
step >= 2_419_200_000 →  "long"    (месячный → годовой)
иначе                 →  "medium"
```

### Онлайн-режим
`model_id = "none"` — Prophet обучается прямо на входных данных SCADA без предзагрузки модели с диска.

### Источники данных (из config.json модели)
- **SCADA** (`historical_data`) — критический, при недоступности → 503
- **Weather API** — опциональный, ошибка не прерывает pipeline
- **CMMS** — опциональный, плановые снижения применяются постобработкой

---

## Структура файлов проекта

```
src/api/
  server.py          — FastAPI app, lifespan, /predict endpoint, /ui/* endpoints
  broker/
    broker.py        — taskiq broker (RedisStreamBroker или InMemoryBroker)
    tasks/predict.py — predict_logic: загрузка конфига → SCADA → модель → CMMS
  forecast/
    config.py        — ModelConfig (Pydantic), load_model_config(), нормализация секций
    model.py         — init_model(): определение типа по пути, загрузка, fallback
    inference.py     — predict(): BaseModel → PredictionInput → PredictionOutput
    base_interface.py — BaseModel (abstract), PredictionInput, PredictionOutput
    adapters.py      — ProphetAdapter, ARAdapter, XGBoostAdapter
    evaluation.py    — QDS оценка входных данных
  data/predict.py    — Pydantic схемы: PredictCreateSchema / PredictUpdateSchema
```

---

## Экраны веб-интерфейса (UI/UX)

Два основных экрана в навигации: **Tasks** и **Models**.

### Tasks Monitor (мониторинг задач)
- Таблица задач с колонками: `task_id`, `object_reference`, `model_id`, `state`, `received`, `runtime`, иконки источников S/W/C, `worker`, действие
- Фильтры: по state (`start` / `processing` / `done ✓` / `done ✗` / `expired`), поиск, воркер, модель
- **Detail panel** — три вкладки:
  - **Детали**: task_id, state, worker, TTL, исходный POST-запрос, timing, источники S/W/C, poll history, результат/ошибка
  - **Данные модели**: конфигурация из `config.json` — параметры ModelConfig, архивы SCADA, источники. Экспорт ↓ JSON / ↓ CSV
  - **Источники**: сырые данные SCADA [timestamp, value, qds], Weather (temp/pressure/wind), CMMS (p_station, p_descent, окна). Кнопка **↓ Скачать всё (ZIP)** → `scada.csv + weather.json + cmms.csv`
- **Ручной запуск** («+ Запустить прогноз») — три вкладки формы:
  - *Модель и период*: `model_id` из списка, `object_reference`, `from`/`to` datetime (если не заданы — воркер считает из config), переключатель онлайн-режима
  - *Архив SCADA*: чеклист архивов из config.json + возможность добавить вручную
  - *Источники*: URL SCADA, Weather (lat/lon + toggle), CMMS (toggle)

### Models (каталог моделей)
- Список всех моделей с диска `/workspace/models/`
- Колонки: health dot, `model_id`, тип (badge), горизонт (badge), MAPE (цвет: <7% зел, 7–12% янт, ≥12% красн), последний запуск (rel time + ✗ если fail), runtime, источники S/W/C, кол-во запусков, кнопка ▶
- Два вида: таблица / карточки grid
- Sidebar-фильтры по типу (prophet/arima/xgb/ets), горизонту (short/medium/long), региону
- **Detail panel** — три вкладки:
  - **Обзор**: health dot + статус, 4 метрики (MAPE/запуски/avg runtime/последний), тренд MAPE (mini bar chart), **блок «Последний прогон»** (task_id + статус из брокера + worker + received + object_reference), атрибуты (region/step/output_range/config updated/mlflow run_id)
  - **Конфигурация**: ModelConfig параметры, архивы SCADA, источники S/W/C, путь на диске. Экспорт ↓ JSON / ↓ CSV
  - **История**: таблица runs с колонками task_id (кликабельная ссылка в Tasks) / статус HTTP-кодом / runtime / MAPE. Последний run — голубой фон. Агрегат: всего/avg MAPE/avg runtime/успешность %
- Footer: кнопка **▶ Запустить прогноз** (форма с предзаполненным model_id), **→ Tasks** (фильтр по model_id), **MLflow ↗**

---

## Важные связи между экранами

- `task_id` в описании модели (экран Models) — прямая ссылка на запись в Tasks Monitor
- Кнопка «→ Tasks» из detail panel Models открывает Tasks с фильтром по `model_id`
- Кнопка ▶ из любой строки Models открывает форму запуска с предзаполненным `model_id`
- «Данные модели» = конфигурация `config.json`, **а не** исторические данные SCADA

---

## Логика здоровья модели (health)

| Статус | Условие |
|--------|---------|
| ok (зелёный) | MAPE < 7% и последний запуск успешен |
| warn (янтарный) | MAPE 7–12% или последний запуск > 24ч назад |
| err (красный) | Последний запуск завершился с ошибкой (done 4xx/5xx) |

---

## Цвета состояний задачи

| Состояние | Фон | Текст |
|-----------|-----|-------|
| start | #EEEDFE | #5B21B6 (фиолетовый) |
| processing | #E6F1FB | #0C447C (синий) |
| done 200 | #EAF3DE | #27500A (зелёный) |
| done 4xx/5xx | #FCEBEB | #791F1F (красный) |
| expired | #ECEAE4 | #5A5850 (серый) |

---

## Иконки источников данных

- **S** (SCADA) — #185FA5, синий, критический
- **W** (Weather) — #0284C7, голубой, опциональный
- **C** (CMMS) — #534AB7, фиолетовый, опциональный
- Серая (opacity 0.3) = источник не настроен или недоступен

---

## Документы проекта

- `ML_Forecast_Platform_Description_v2.docx` — техническое описание платформы (12 разделов)
- `Tasks_Monitor_UIUX_Spec_v2.docx` — UI/UX спецификация (23 раздела, 2 части: Tasks Monitor + Models)

---

## Что ещё не реализовано (технический долг)

- Active inference через MLflow Model Registry (запланировано)
- Кеш моделей в памяти воркера
- Горизонтальное масштабирование (> 1 контейнера)
- RZ-коллектор в pipeline
- Погодные данные как явные признаки модели (сейчас передаются в metadata)
- График throughput, экспорт списка задач в CSV, streaming лог воркера
