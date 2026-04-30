# WORKFLOW STAGE 6: Постобработка и формирование результата

## 1. Цель этапа

Сформировать финальный payload задачи после инференса:

- применить planned корректировки CMMS к прогнозу,
- оценить качество входных данных (QDS),
- собрать финальный объект `data.output` и статистику,
- вернуть `DONE`-payload с финальными `message/quality` и статистикой.

Граница этапа: завершается, когда сформирован ответ `HTTPMessages.ok_done(...)` либо возвращена ошибка из общего `try/except`.

## 2. Точки входа в коде

- `src/api/broker/tasks/predict.py` -> `_get_planned_adjustments(...)`
- `src/api/broker/tasks/predict.py` -> `_apply_planned_adjustments(...)`
- `src/api/broker/tasks/predict.py` -> `_build_result(...)`
- `src/api/forecast/evaluation.py` -> `count_input_qds(...)`
- `src/api/forecast/evaluation.py` -> `evaluate_input_quality(...)`

## 3. Пошаговая логика на уровне кода

### Шаг 1. Загрузка planned adjustments

После инференса вызывается:

```python
planned_adjustments = await _get_planned_adjustments(config, step, output_range)
```

Если CMMS недоступен или вернул ошибку источника:

- функция возвращает `None`,
- pipeline продолжается без planned-корректировок.

### Шаг 2. Применение planned adjustments к прогнозу

```python
preds, planned_applied_count = _apply_planned_adjustments(preds, pred_ts, planned_adjustments)
```

Правило применения:

- ключ planned-словаря = timestamp в мс,
- для каждого `pred_ts` при точном совпадении вычитается `reduction`.

### Шаг 3. Оценка качества входных данных

```python
critical_freq, non_critical_freq = count_input_qds(timestamp, value, qds)
input_qds, input_reason = evaluate_input_quality(critical_freq, non_critical_freq)
```

Результат:

- `input_qds` определяет уровень качества входа,
- `input_reason` содержит человекочитаемое объяснение.

### Шаг 4. Сбор финального результата

`logic(...)` возвращает:

```python
return HTTPMessages.ok_done(
    _build_result(...)
)
```

В `_build_result(...)`:

- рассчитывается внутренний `status/message` по правилам качества,
- при `clip_negatives_to_0=True` отрицательные значения `preds` обрезаются до `0`,
- собирается `output` в формате `[[timestamp, value, qds], ...]`,
- добавляются `input_statistics`, `output_statistics`, `planned_adjustments_applied`.

Важно: успешный путь Stage6 всегда оборачивается в `HTTPMessages.ok_done(...)`, то есть HTTP-статус ответа задачи = `200`.
Внутренний `status` в `_build_result(...)` используется для формирования `message` и финального `quality`.

## 4. Правила определения финального статуса

Порядок приоритета в `_build_result(...)`:

1. Базовый статус = `200`, качество = `QDS.BASE`.
2. Если `model is None` -> `422`.
3. Если `is_matching == False` и пока `200` -> `422`.
4. Если `status` еще `200` и `input_qds != BASE` -> статус становится `input_qds`.
5. Итоговый `quality = max(base_pred_qds, input_qds)`.

Примечание по контракту:

- этот `status` является внутренней переменной `_build_result(...)`,
- наружу в успешном DONE-ответе отдается `HTTP 200` + `data` c полями `message`, `quality`, `output`.

## 5. Ошибки и защитные поведения

### 5.1 Ошибка CMMS

- Источник: ошибка запроса/парсинга planned payload
- Результат: warning в лог, продолжение без planned-коррекций

### 5.2 Ошибка в постобработке

- Источник: непойманное исключение в `logic(...)` после инференса
- Результат: `internal_server_error(...)` (`500`)

### 5.3 Низкое качество входа

- Источник: частота критичных/некритичных QDS выше порогов
- Результат: финальный `quality` повышается до `NOT_TOPICAL` или `INVALID`, а `message` заполняется причиной.

## 6. Как проверить этап

### Проверка 1. Стандартный успешный путь

```bash
cd ml-server
make test-predict PREDICT_MODEL_ID=xgb
```

Ожидание:

- финальный payload содержит `data.output`,
- есть `input_statistics` и `output_statistics`,
- поле `planned_adjustments_applied` присутствует.

### Проверка 2. Проверка обрезки отрицательных значений

- Установить в runtime-конфиге `clip_negatives_to_0=true`.
- Выполнить predict на наборе, где модель генерирует отрицательные значения.

Ожидание:

- в `data.output` значения ниже 0 отсутствуют.

### Проверка 3. Проверка влияния planned adjustments

- Подать planned payload из CMMS с ненулевыми `p_descent` в диапазоне прогноза.

Ожидание:

- `planned_adjustments_applied > 0`,
- соответствующие точки прогноза уменьшены.

## 7. Операционный чеклист

- [ ] Planned-корректировки запрошены и обработаны без фатального влияния на pipeline.
- [ ] Применение planned adjustments выполняется по timestamp в мс.
- [ ] QDS входа посчитан через `count_input_qds` и `evaluate_input_quality`.
- [ ] Финальный `quality` и `status` сформированы по правилам `_build_result`.
- [ ] Итоговый payload содержит `output`, статистику входа/выхода и счетчик applied planned points.

## 8. Связь с соседними этапами

- Предыдущий файл: `docs/workflow/WORKFLOW_STAGE5.md`
- Следующий файл: `docs/workflow/WORKFLOW_STAGE7.md`
- Что передаётся дальше:
  - `data.output`
  - `quality`, `message`
  - `input_statistics`, `output_statistics`
  - `planned_adjustments_applied`
