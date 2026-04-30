# ToDo

## Current Tasks

1. **добавить поддержку манифеста для модели MultiOutputRegressor в адаптер XGBoostAdapter**
   - Location: src/api/forecast/adapters.py (XGBoostAdapter)
   - Context: Training refactored to use single XGBRegressor, but may need fallback to support legacy MultiOutputRegressor format
   - Status: pending



2. Замечания по ревизи кода относительно документации

- RZ/df_rz коллектор — явно отключён (df_rz = None). 
- predict.py — строки с df_rz = None и передачей weather_data
- Time-based TTL для кэша моделей — только лимит по количеству (MODEL_REGISTRY_CACHE_MAX=3), нет политики по времени
- inference.py — weather_data принимается, но не используется в адаптерах