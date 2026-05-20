
1. Схема хранения (Storage)
Мы используем MLflow Registry + локальный bundle cache для serving:
Backend Store: MLflow tracking/registry store — хранит метрики, параметры, теги, alias/version и run_id.
Artifact Store: `mlruns/` — хранит bundle-артефакты моделей.

2. Serving flow
Offline prediction работает так:
- клиент передаёт `model_id` и опционально `model_selection.version_alias` или `model_selection.version`;
- runtime разрешает selector в MLflow Registry;
- скачивает `bundle` и кеширует его в `/tmp/local_models_cache`;
- читает runtime-конфиг из `bundle/configuration/cache_config.json`;
- читает модель из `bundle/model`.

Fallback policy:
- для offline serving допустим только fallback к последнему успешно закешированному MLflow bundle того же `model_id`;
- fallback к `/workspace/models` для offline serving не используется;
- online flow (`model_id == "none"`) не требует registry bundle.

3. Структура serving bundle

```text
bundle/
├── model/
│   └── ... model artifacts ...
├── configuration/
│   └── cache_config.json
└── assets/
    └── ... optional files ...
```

4. Ключевые преимущества
Повторяемость: serving всегда использует артефакты, привязанные к конкретному `run_id`.
Управляемость: alias/version становятся публичным selector'ом для `/predict`.
Надёжность: при сбое MLflow можно использовать последний успешно закешированный bundle.