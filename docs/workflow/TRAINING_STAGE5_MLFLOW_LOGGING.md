# TRAINING STAGE 5: Логирование в MLflow (MLflow Logging)

Цель этапа: зафиксировать результаты обучения в MLflow так, чтобы модель можно было найти, воспроизвести и использовать в инференсе.

---

## 1. Что делает этап

Stage 5 выполняет полный MLflow run lifecycle:
- открывает run;
- записывает теги (metadata);
- логирует параметры обучения;
- логирует quality-метрики;
- сохраняет bundle артефактов модели;
- получает `run_id` для возврата в API.

---

## 2. Логическая структура run

```text
Experiment
  -> Run
     -> Tags
     -> Params
     -> Metrics
  -> Artifacts/bundle/{model,configuration/cache_config.json,assets?}
```

Ключевые данные:
- Tags: `object_reference`, `model_type`, `data_source_config`, `run_date`;
- Params: гиперпараметры (`train_params`);
- Metrics: `mae`, `mape`, `rmse` и др.;
- Artifacts: `bundle/model` + `bundle/configuration/cache_config.json` (каноничный runtime config).

---

## 3. Почему data_source_config обязателен

`data_source_config` (паспорт данных) сохраняется как tag и критичен для инференса:
- позволяет восстановить источник данных модели;
- обеспечивает переносимость между train и inference;
- упрощает аудит и отладку run.

Именно поэтому в логировании обязательно хранить его в JSON-формате.

---

## 4. Вычисление и логирование метрик

Типовая группа:
- `MAE`
- `MAPE`
- `RMSE`

Формулы:

$$
\text{MAE}=\frac{1}{n}\sum_{i=1}^{n}|y_i-\hat{y}_i|
$$

$$
\text{MAPE}=\frac{100\%}{n}\sum_{i=1}^{n}\left|\frac{y_i-\hat{y}_i}{y_i}\right|
$$

$$
\text{RMSE}=\sqrt{\frac{1}{n}\sum_{i=1}^{n}(y_i-\hat{y}_i)^2}
$$

---

## 5. Ветка логирования artifacts

Для Prophet и XGBoost:
- модельный артефакт должен публиковаться в `bundle/model`;
- runtime-конфигурация должна публиковаться в `bundle/configuration/cache_config.json`;
- дополнительные служебные файлы могут публиковаться в `bundle/assets`.

Ожидаемый результат:
- в artifact store размещен единый bundle-каталог;
- run содержит совместимый с runtime layout для загрузки и инференса.

### 5.1 Dataset reproducibility: три уровня хранения данных

Хранить только метрики без возможности воспроизвести обучающую выборку — типовая ошибка. Рекомендуемая стратегия:

| Уровень | Что хранится | Где |
|---------|-------------|-----|
| **1. Источник истины** | Исторические данные остаются во внешнем источнике (SCADA/API). В обучении фиксируются только параметры выборки: период, объект, частота, фильтры. | Внешний API |
| **2. Снимок выборки** | Parquet-снимки train/val/test splits. | `bundle/assets/datasets/` |
| **3. Метаданные в MLflow** | Hash, row count, временной диапазон, версия схемы признаков. | MLflow tags/params |

**Canonic snapshot layout:**

```
bundle/assets/datasets/
├── train_snapshot.parquet
├── validation_snapshot.parquet
└── test_snapshot.parquet
```

**Обязательные dataset lineage tags/params в run:**

```python
mlflow.set_tag('dataset_uri',              '<url или путь к источнику>')
mlflow.set_tag('dataset_hash',             '<sha256 hex от raw_df.to_parquet()>')
mlflow.set_tag('dataset_start_ts',         '<ISO timestamp начала выборки>')
mlflow.set_tag('dataset_end_ts',           '<ISO timestamp конца выборки>')
mlflow.set_tag('feature_schema_version',   '1')  # бампать при изменении лагов/колонок
mlflow.log_param('dataset_rows',           15087)
```

**Политика retention:**
- Полный Parquet-snapshot хранить для Production-кандидатов и последних N экспериментальных run.
- Для остальных run достаточно метаданных + hash + profiling report.

Это позволяет ответить на вопрос «на каких данных обучена модель?» по тегам run, не открывая файлы, а при необходимости — загрузить точные splits из артефактов.

---

## 6. Выход этапа

В Stage 6 передается summary run:

```json
{
  "run_id": "abc123def456",
  "experiment": "/KAZ/AKMOLA/P_WATT",
  "metrics": {
    "mae": 45.2,
    "mape": 3.1,
    "rmse": 62.8
  },
  "model_id": "registered-model-or-name"
}
```

### 6.1 Notebook report outputs

Если обучение выполняется вручную через `TRAINING_MANUAL_WORKFLOW.ipynb`, до публикации в MLflow рекомендуется собрать companion report bundle:
- `data_quality_summary.csv`;
- `dataset_profile.csv`;
- `model_comparison.csv`;
- `recommendation.json`.

Этот bundle не заменяет MLflow run, а дает human-readable summary для review. После утверждения модели Stage 5 по-прежнему должен зафиксировать каноничные metrics и bundle artifacts в MLflow.

---

## 7. Ошибки этапа

Частые сценарии:
- MLflow endpoint недоступен;
- ошибка записи bundle artifact;
- недопустимые типы параметров/метрик;
- run стартовал, но завершился без нужных артефактов.

Практика:
- fail-fast при ошибке `start_run`;
- проверка целостности run (tags/params/metrics/bundle artifacts);
- логирование `run_id` и контекста в системные логи.

---

## 8. Проверка этапа

1. Run виден в MLflow UI.
2. У run присутствуют обязательные tags.
3. Параметры и метрики записаны.
4. Доступны `bundle/model` и `bundle/configuration/cache_config.json`.
5. `run_id` передан дальше в Stage 6.

---

## 9. Критерий готовности Stage 5

- MLflow run завершен успешно;
- все обязательные metadata/metrics/bundle artifacts сохранены;
- подготовлен валидный результат для возврата клиенту на Stage 6.
