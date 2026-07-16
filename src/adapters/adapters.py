"""
adapters.py

Адаптеры для моделей прогнозирования используя base_interface.
Примеры реализации ARAdapter и ProphetAdapter для интеграции старых моделей.

Deprecated flow:
  - fpforecast.models.ar.ModelWithMetaInfoAr
  - fpforecast.models.prophet.ModelWithMetaInfoProphet
  
New flow:
  - ARAdapter(BaseModel)
  - ProphetAdapter(BaseModel)
"""
from datetime import datetime, timezone
import logging
from typing import Any, Dict, Optional, List
import pandas as pd
import numpy as np

from adapters.base_interface import BaseModel, PredictionInput, PredictionOutput

logger = logging.getLogger(__name__)


class ARAdapter(BaseModel):
    """
    Адаптер для модели авторегрессии (AR).

    Обеспечивает совместимость со старым интерфейсом ModelWithMetaInfoAr
    через новый base_interface.

    Пример использования:
        model = ARAdapter(model_name="ar_model_v1")
        prediction = model.predict(PredictionInput(features=[1, 2, 3, ...]))
    """

    def __init__(self, model_name: str = "ar_model", legacy_model: Optional[Any] = None):
        """
        Инициализация AR адаптера.

        Args:
            model_name: Имя модели
            legacy_model: Существующая ModelWithMetaInfoAr для обратной совместимости
        """
        super().__init__(model_name)
        self.legacy_model = legacy_model
        self.model = legacy_model if legacy_model is not None else self
        self.W_past = getattr(legacy_model, 'W_past', 24) if legacy_model else 24
        self.W_future = getattr(legacy_model, 'W_future', 12) if legacy_model else 12

    def load(self) -> None:
        """Mark adapter as loaded for the simplified adapter flow."""
        self.model = self.legacy_model if self.legacy_model is not None else self

    def predict(self, input_data: PredictionInput) -> PredictionOutput:
        """
        Выполнить прогноз используя AR модель.

        Args:
            input_data: PredictionInput с features (исторические значения)

        Returns:
            PredictionOutput с predictions и метаданными
        """
        self.validate_input(input_data)

        try:
            if self.legacy_model is not None:
                # Использование старой модели через адаптер
                y_pred, is_matching = self._predict_with_legacy_model(input_data)
            else:
                # Простой AR прогноз (placeholder для демонстрации)
                y_pred = self._predict_ar_simple(input_data)
                is_matching = True

            logger.info(f"AR prediction: {len(y_pred)} values, matching={is_matching}")

            return PredictionOutput(
                predictions=y_pred.tolist(),
                metadata={
                    "is_matching": is_matching,
                    "w_past": self.W_past,
                    "w_future": self.W_future,
                    "model_type": "autoregression"
                }
            )
        except Exception as e:
            logger.error(f"AR prediction failed: {e}")
            raise ValueError(f"AR prediction error: {str(e)}")

    def train(self, train_data: List[float], timestamps: Optional[List[str]] = None) -> None:
        """
        Подготовка AR модели к использованию.

        Args:
            train_data: Исторические данные для обучения
            timestamps: Опциональные метки времени
        """
        if not train_data or len(train_data) < self.W_past + self.W_future:
            raise ValueError(f"Need at least {self.W_past + self.W_future} data points")

        logger.info(f"AR model prepared with {len(train_data)} data points")

    def _predict_with_legacy_model(self, input_data: PredictionInput) -> tuple:
        """Использование старой ModelWithMetaInfoAr через адаптер."""
        try:
            # Конвертация в формат старой модели
            df = pd.DataFrame({"value": input_data.features})

            # Вызов старой модели
            _, y_pred, is_matching = self.legacy_model.predict(df)
            y_pred = np.asarray(y_pred).reshape(-1)

            return y_pred, is_matching
        except Exception as e:
            logger.error(f"Legacy AR model failed: {e}")
            raise

    def _predict_ar_simple(self, input_data: PredictionInput) -> np.ndarray:
        """Простой AR прогноз (демонстрация)."""
        features = np.asarray(input_data.features)

        # Простая AR(1) модель: y_t = 0.8 * y_{t-1}
        if len(features) > 0:
            last_value = features[-1]
            predictions = np.full(self.W_future, last_value * 0.8)
        else:
            predictions = np.full(self.W_future, np.nan)

        return predictions


class ProphetAdapter(BaseModel):
    """
    Адаптер для Facebook Prophet модели.
    
    Обеспечивает совместимость со старым интерфейсом ModelWithMetaInfoProphet
    через новый base_interface.
    
    Пример использования:
        model = ProphetAdapter(model_name="prophet_v1", legacy_model=prophet_instance)
        prediction = model.predict(PredictionInput(features=[1, 2, 3, ...]))
    """
    
    def __init__(self, model_name: str = "prophet_model", legacy_model: Optional[Any] = None):
        """
        Инициализация Prophet адаптера.
        
        Args:
            model_name: Имя модели
            legacy_model: Существующая Prophet модель для обратной совместимости
        """
        super().__init__(model_name)
        self.legacy_model = legacy_model
        self.model = legacy_model if legacy_model is not None else self
        self.forecast_periods = 12

    def load(self) -> None:
        """Mark adapter as loaded for the simplified adapter flow."""
        self.model = self.legacy_model if self.legacy_model is not None else self
    
    def predict(self, input_data: PredictionInput) -> PredictionOutput:
        """
        Выполнить прогноз используя Prophet модель.
        
        Args:
            input_data: PredictionInput с features (исторические значения)
            
        Returns:
            PredictionOutput с predictions и метаданными
        """
        self.validate_input(input_data)

        requested_output_range = self.forecast_periods
        if input_data.metadata:
            requested_output_range = int(input_data.metadata.get("output_range", self.forecast_periods))
        self.forecast_periods = max(requested_output_range, 1)
        
        try:
            if self.legacy_model is not None:
                # Использование старой Prophet модели через адаптер
                y_pred = self._predict_with_legacy_prophet(input_data)
            else:
                # Простой Prophet прогноз (placeholder)
                y_pred = self._predict_prophet_simple(input_data)
            
            logger.info(f"Prophet prediction: {len(y_pred)} values")
            
            return PredictionOutput(
                predictions=y_pred.tolist(),
                metadata={
                    "forecast_periods": self.forecast_periods,
                    "model_type": "prophet"
                }
            )
        except Exception as e:
            logger.error(f"Prophet prediction failed: {e}")
            raise ValueError(f"Prophet prediction error: {str(e)}")
    
    def train(self, train_data: List[float], timestamps: Optional[List[str]] = None) -> None:
        """
        Подготовка Prophet модели к использованию.
        
        Args:
            train_data: Исторические данные для обучения
            timestamps: Опциональные метки времени
        """
        if not train_data or len(train_data) < 10:
            raise ValueError("Prophet requires at least 10 data points")
        
        logger.info(f"Prophet model prepared with {len(train_data)} data points")
    
    def _predict_with_legacy_prophet(self, input_data: PredictionInput) -> np.ndarray:
        """Использование старой Prophet модели через адаптер."""
        try:
            # Создание future DataFrame
            future = pd.DataFrame({
                "ds": pd.date_range(periods=self.forecast_periods, freq="D")
            })
            
            # Вызов старой Prophet модели
            forecast = self.legacy_model.predict(future)
            y_pred = forecast["yhat"].values[:self.forecast_periods]
            
            return y_pred
        except Exception as e:
            logger.error(f"Legacy Prophet model failed: {e}")
            raise
    
    def _predict_prophet_simple(self, input_data: PredictionInput) -> np.ndarray:
        """Простой Prophet-подобный прогноз (демонстрация)."""
        features = np.asarray(input_data.features)
        
        # Простой тренд: линейная регрессия
        if len(features) > 1:
            x = np.arange(len(features))
            z = np.polyfit(x, features, 1)
            p = np.poly1d(z)
            
            future_x = np.arange(len(features), len(features) + self.forecast_periods)
            predictions = p(future_x)
        else:
            predictions = np.full(self.forecast_periods, features[0] if len(features) > 0 else 0)
        
        return predictions


class XGBoostAdapter(BaseModel):
    """
    Адаптер для XGBoost модели.
    
    Пример использования:
        model = XGBoostAdapter(model_name="xgb_v1", legacy_model=xgb_model)
        prediction = model.predict(PredictionInput(features=[...]))
    """
    
    def __init__(self, model_name: str = "xgboost_model", legacy_model: Optional[Any] = None):
        super().__init__(model_name)
        self.legacy_model = legacy_model
        self.model = legacy_model if legacy_model is not None else self

    def load(self) -> None:
        """Mark adapter as loaded for the simplified adapter flow."""
        self.model = self.legacy_model if self.legacy_model is not None else self

    @staticmethod
    def _build_feature_vector_for_inference(
        series: np.ndarray,
        expected_features: int,
        metadata: Optional[Dict[str, Any]],
    ) -> np.ndarray:
        """Build a feature vector aligned with training (lags + 4 cyclic time features)."""
        if expected_features <= 0:
            return series.reshape(1, -1)

        if series.size >= expected_features and expected_features < 8:
            return series[-expected_features:].reshape(1, -1)

        # Train pipeline appends 4 cyclic time features.
        lags = max(expected_features - 4, 1)

        if series.size >= lags:
            lag_values = series[-lags:]
        elif series.size > 0:
            pad_value = float(series[-1])
            lag_values = np.concatenate([series, np.full(lags - series.size, pad_value, dtype=float)])
        else:
            lag_values = np.zeros(lags, dtype=float)

        step_ms = 3_600_000
        ts_next = None
        if isinstance(metadata, dict):
            try:
                step_ms = int(metadata.get("step", step_ms))
            except Exception:
                step_ms = 3_600_000

            raw_ts = metadata.get("timestamps")
            if isinstance(raw_ts, list) and raw_ts:
                try:
                    ts_next = int(raw_ts[-1]) + step_ms
                except Exception:
                    ts_next = None

        if ts_next is None:
            ts_next = int(datetime.now(tz=timezone.utc).timestamp() * 1000)

        dt = datetime.fromtimestamp(ts_next / 1000, tz=timezone.utc)
        hour = float(dt.hour)
        dow = float(dt.weekday())

        sin_h = np.sin(2 * np.pi * hour / 24.0)
        cos_h = np.cos(2 * np.pi * hour / 24.0)
        sin_d = np.sin(2 * np.pi * dow / 7.0)
        cos_d = np.cos(2 * np.pi * dow / 7.0)

        full_features = np.concatenate([lag_values.astype(float), np.array([sin_h, cos_h, sin_d, cos_d])])

        if full_features.size > expected_features:
            full_features = full_features[-expected_features:]
        elif full_features.size < expected_features:
            pad_value = float(full_features[-1]) if full_features.size else 0.0
            full_features = np.concatenate([
                full_features,
                np.full(expected_features - full_features.size, pad_value, dtype=float),
            ])

        return full_features.reshape(1, -1)
    
    def predict(self, input_data: PredictionInput) -> PredictionOutput:
        """Выполнить прогноз используя XGBoost."""
        self.validate_input(input_data)
        
        try:
            raw_series = np.asarray(input_data.features, dtype=float).reshape(-1)
            features = raw_series.reshape(1, -1)
            
            if self.legacy_model is not None:
                import xgboost as xgb
                
                # Check if model is a dict of step-wise boosters (multi-output)
                if isinstance(self.legacy_model, dict):
                    first_step = sorted(self.legacy_model.keys())[0]
                    expected_features = int(self.legacy_model[first_step].num_features())
                    if features.shape[1] != expected_features:
                        features = self._build_feature_vector_for_inference(
                            raw_series,
                            expected_features,
                            input_data.metadata,
                        )

                    # Multi-step forecast: predict for each step
                    dmatrix = xgb.DMatrix(features)
                    predictions = []
                    for step in sorted(self.legacy_model.keys()):
                        y_pred_step = self.legacy_model[step].predict(dmatrix)
                        predictions.append(float(y_pred_step[0]))
                    y_pred = np.array(predictions)
                # Single booster
                elif isinstance(self.legacy_model, xgb.Booster):
                    expected_features = int(self.legacy_model.num_features())
                    if features.shape[1] != expected_features:
                        features = self._build_feature_vector_for_inference(
                            raw_series,
                            expected_features,
                            input_data.metadata,
                        )

                    dmatrix = xgb.DMatrix(features)
                    y_pred = self.legacy_model.predict(dmatrix)
                # XGBRegressor
                else:
                    expected_features = getattr(self.legacy_model, "n_features_in_", None)
                    if expected_features is not None and features.shape[1] != int(expected_features):
                        features = self._build_feature_vector_for_inference(
                            raw_series,
                            int(expected_features),
                            input_data.metadata,
                        )

                    y_pred = self.legacy_model.predict(features)
            else:
                # Placeholder
                y_pred = np.mean(features) * np.ones(1)
            
            return PredictionOutput(
                predictions=y_pred.tolist(),
                metadata={"model_type": "xgboost"}
            )
        except Exception as e:
            logger.error(f"XGBoost prediction failed: {e}")
            raise ValueError(f"XGBoost prediction error: {str(e)}")
    
    def train(self, train_data: List[float], timestamps: Optional[List[str]] = None) -> None:
        """Подготовка XGBoost модели."""
        if not train_data:
            raise ValueError("Training data cannot be empty")
        
        logger.info(f"XGBoost model prepared with {len(train_data)} data points")


class SolarAdapter(BaseModel):
    """
    Адаптер для прогнозирования генерации солнечной электростанции.

    Использует XGBoost-модель (тот же формат бандла, что и XGBoostAdapter:
    манифест ``xgb_model.json`` + пошаговые бустеры), но строит вектор
    признаков с учётом метеорологических данных из источника ``weather``.

    Структура вектора признаков (должна совпадать с обучением):
        [lag_1, ..., lag_k,
         solar_radiation, temperature, cloud_cover,   ← weather (CWS field names)
         sin_hour, cos_hour, sin_doy, cos_doy]        ← cyclic time

    Количество лагов вычисляется как:
        k = booster.num_features() - N_WEATHER_FEATURES - N_TIME_FEATURES

    Если модель не загружена, используется нативный fallback на основе
    масштабирования последнего ненулевого значения по относительной
    инсоляции (``solar_radiation / 1000``).

    Пример cache_config.json:
        см. docs/examples/solar_cache_config.json
    """

    # Weather feature order must match training pipeline.
    # Field names align with the weather service's SCADA-compatible response format.
    _WEATHER_KEYS: tuple = ("solar_radiation", "temperature", "cloud_cover")
    N_WEATHER_FEATURES: int = 3
    N_TIME_FEATURES: int = 4  # sin_h, cos_h, sin_doy, cos_doy

    def __init__(self, model_name: str = "solar_model", legacy_model: Optional[Any] = None):
        """
        Args:
            model_name: Имя модели.
            legacy_model: Загруженный dict[int, xgb.Booster] или одиночный Booster.
        """
        super().__init__(model_name)
        self.legacy_model = legacy_model
        self.model = legacy_model if legacy_model is not None else self

    def load(self) -> None:
        self.model = self.legacy_model if self.legacy_model is not None else self

    # ------------------------------------------------------------------
    # Feature engineering
    # ------------------------------------------------------------------

    def _extract_weather_at_step(
        self,
        weather_data: Optional[Dict[str, Any]],
        step_index: int,
    ) -> np.ndarray:
        """Return weather feature array [solar_radiation, temperature, cloud_cover] for forecast step *i*."""
        defaults = np.zeros(self.N_WEATHER_FEATURES, dtype=float)
        if not isinstance(weather_data, dict):
            return defaults
        hourly = weather_data.get("hourly")
        if not isinstance(hourly, list) or step_index >= len(hourly):
            return defaults
        entry = hourly[step_index]
        if not isinstance(entry, dict):
            return defaults
        return np.array(
            [float(entry.get(k) or 0.0) for k in self._WEATHER_KEYS],
            dtype=float,
        )

    @staticmethod
    def _cyclic_time_features(forecast_ts_ms: int) -> np.ndarray:
        """Return [sin_hour, cos_hour, sin_doy, cos_doy] for the given ms timestamp."""
        dt = datetime.fromtimestamp(forecast_ts_ms / 1000, tz=timezone.utc)
        hour = float(dt.hour) + float(dt.minute) / 60.0
        doy = float(dt.timetuple().tm_yday)
        return np.array(
            [
                np.sin(2 * np.pi * hour / 24.0),
                np.cos(2 * np.pi * hour / 24.0),
                np.sin(2 * np.pi * doy / 365.0),
                np.cos(2 * np.pi * doy / 365.0),
            ],
            dtype=float,
        )

    def _build_feature_row(
        self,
        series: np.ndarray,
        step_index: int,
        forecast_ts_ms: int,
        weather_data: Optional[Dict[str, Any]],
        expected_features: int,
    ) -> np.ndarray:
        """
        Build one feature row for a single forecast step.

        Layout: [lags..., weather(3), time(4)]
        """
        n_fixed = self.N_WEATHER_FEATURES + self.N_TIME_FEATURES
        lags = max(expected_features - n_fixed, 1)

        if series.size >= lags:
            lag_values = series[-lags:].astype(float)
        elif series.size > 0:
            pad_val = float(series[-1])
            lag_values = np.concatenate(
                [series.astype(float), np.full(lags - series.size, pad_val)]
            )
        else:
            lag_values = np.zeros(lags, dtype=float)

        weather_vec = self._extract_weather_at_step(weather_data, step_index)
        time_vec = self._cyclic_time_features(forecast_ts_ms)

        row = np.concatenate([lag_values, weather_vec, time_vec])

        # Align to exact expected_features (safety pad/trim)
        if row.size > expected_features:
            row = row[-expected_features:]
        elif row.size < expected_features:
            row = np.concatenate([row, np.zeros(expected_features - row.size)])

        return row.reshape(1, -1)

    # ------------------------------------------------------------------
    # Predict
    # ------------------------------------------------------------------

    def predict(self, input_data: PredictionInput) -> PredictionOutput:
        """
        Run solar generation forecast.

        Extracts weather features from ``input_data.metadata["weather_data"]``
        (list of hourly dicts from the weather source) and combines them with
        historical generation lags and cyclic time features.
        """
        self.validate_input(input_data)

        raw_series = np.asarray(input_data.features, dtype=float).reshape(-1)
        metadata = input_data.metadata or {}
        weather_data: Optional[Dict[str, Any]] = metadata.get("weather_data")
        step_ms = int(metadata.get("step", 3_600_000))
        output_range = int(metadata.get("output_range", 24))

        raw_ts = metadata.get("timestamps")
        if isinstance(raw_ts, list) and raw_ts:
            base_ts = int(raw_ts[-1]) + step_ms
        else:
            base_ts = int(datetime.now(tz=timezone.utc).timestamp() * 1000)

        try:
            if self.legacy_model is not None:
                import xgboost as xgb

                if isinstance(self.legacy_model, dict):
                    step_keys = sorted(self.legacy_model.keys())
                    first_booster = self.legacy_model[step_keys[0]]
                    expected_features = int(first_booster.num_features())

                    predictions: List[float] = []
                    for i, step_key in enumerate(step_keys):
                        forecast_ts = base_ts + i * step_ms
                        row = self._build_feature_row(
                            raw_series, i, forecast_ts, weather_data, expected_features
                        )
                        dmatrix = xgb.DMatrix(row)
                        val = float(self.legacy_model[step_key].predict(dmatrix)[0])
                        predictions.append(max(val, 0.0))
                    y_pred = np.array(predictions)

                elif isinstance(self.legacy_model, xgb.Booster):
                    expected_features = int(self.legacy_model.num_features())
                    predictions = []
                    for i in range(output_range):
                        forecast_ts = base_ts + i * step_ms
                        row = self._build_feature_row(
                            raw_series, i, forecast_ts, weather_data, expected_features
                        )
                        dmatrix = xgb.DMatrix(row)
                        val = float(self.legacy_model.predict(dmatrix)[0])
                        predictions.append(max(val, 0.0))
                    y_pred = np.array(predictions)

                else:
                    # XGBRegressor / sklearn pipeline
                    n_feat = int(getattr(self.legacy_model, "n_features_in_", len(raw_series)))
                    predictions = []
                    for i in range(output_range):
                        forecast_ts = base_ts + i * step_ms
                        row = self._build_feature_row(
                            raw_series, i, forecast_ts, weather_data, n_feat
                        )
                        val = float(self.legacy_model.predict(row)[0])
                        predictions.append(max(val, 0.0))
                    y_pred = np.array(predictions)

            else:
                # No model file — irradiance-scaled naive fallback
                y_pred = self._irradiance_naive(raw_series, weather_data, output_range)

            logger.info(
                "Solar prediction: %d values, weather=%s",
                len(y_pred),
                "yes" if weather_data is not None else "no",
            )

            return PredictionOutput(
                predictions=y_pred.tolist(),
                metadata={
                    "model_type": "solar",
                    "weather_used": weather_data is not None,
                    "output_range": output_range,
                },
            )

        except Exception as exc:
            logger.error("Solar prediction failed: %s", exc)
            raise ValueError(f"Solar prediction error: {exc}")

    def _irradiance_naive(
        self,
        series: np.ndarray,
        weather_data: Optional[Dict[str, Any]],
        output_range: int,
    ) -> np.ndarray:
        """
        Fallback when no model is loaded.

        Scales the last known non-zero generation value by relative GHI
        (solar_radiation / 1000 W/m²) at each forecast step.
        """
        nonzero = series[series > 0]
        last_val = float(nonzero[-1]) if nonzero.size > 0 else 0.0

        predictions: List[float] = []
        for i in range(output_range):
            if isinstance(weather_data, dict):
                hourly = weather_data.get("hourly")
                if isinstance(hourly, list) and i < len(hourly):
                    entry = hourly[i]
                    ghi = float((entry or {}).get("solar_radiation", 0.0) or 0.0)
                    scale = min(ghi / 1000.0, 1.0)
                    predictions.append(last_val * scale)
                    continue
            predictions.append(np.nan)

        return np.array(predictions, dtype=float)

    def train(self, train_data: List[float], timestamps: Optional[List[str]] = None) -> None:
        """Solar models are trained offline in notebooks; this is a no-op."""
        logger.info("SolarAdapter: training is offline-only (%d pts provided)", len(train_data))


class LinearRegressionAdapter(BaseModel):
    """
    Адаптер для линейной регрессии (sklearn LinearRegression или совместимых estimators).

    Поддерживает два формата сохранённых моделей:

    1. **Пошаговый (multi-step)** — ``dict[int, estimator]``, где ключ — номер шага
       прогноза (0-based).  Загружается из ``lr_model.pkl`` как ``{"steps": [estimator_0, ...]}``.

    2. **Одиночный** — один scikit-learn estimator, возвращающий скаляр или вектор.

    Вектор признаков строится по той же схеме, что и в ``XGBoostAdapter``:
    ``[lag_1, ..., lag_k, sin_hour, cos_hour, sin_dow, cos_dow]``
    (4 цикличных временны́х признака).  Количество лагов вычисляется как
    ``n_features_in_ - 4``; при отсутствии атрибута берутся все исторические значения.

    Если модель не загружена, используется линейный тренд по последним точкам истории
    (простой fallback, аналогичный ``_predict_prophet_simple``).

    Пример cache_config.json::

        "model_type": "lr"

    Файл модели ожидается по пути ``bundle/model/lr_model.pkl``.
    """

    def __init__(self, model_name: str = "lr_model", legacy_model: Optional[Any] = None):
        """
        Args:
            model_name: Имя модели.
            legacy_model: Загруженный dict[int, estimator] или одиночный sklearn estimator.
        """
        super().__init__(model_name)
        self.legacy_model = legacy_model
        self.model = legacy_model if legacy_model is not None else self

    def load(self) -> None:
        """Mark adapter as loaded."""
        self.model = self.legacy_model if self.legacy_model is not None else self

    # ------------------------------------------------------------------
    # Feature engineering (mirrors XGBoostAdapter logic)
    # ------------------------------------------------------------------

    @staticmethod
    def _build_feature_vector(
        series: np.ndarray,
        expected_features: int,
        metadata: Optional[Dict[str, Any]],
    ) -> np.ndarray:
        """Build [lags..., sin_h, cos_h, sin_dow, cos_dow] feature vector."""
        if expected_features <= 0:
            return series.reshape(1, -1)

        # Plain raw features when small enough to skip time encoding
        if expected_features <= 4 or series.size >= expected_features:
            if series.size >= expected_features:
                return series[-expected_features:].reshape(1, -1)

        lags = max(expected_features - 4, 1)

        if series.size >= lags:
            lag_values = series[-lags:].astype(float)
        elif series.size > 0:
            pad_val = float(series[-1])
            lag_values = np.concatenate([series.astype(float), np.full(lags - series.size, pad_val)])
        else:
            lag_values = np.zeros(lags, dtype=float)

        # Determine timestamp of the next forecast step
        step_ms = 3_600_000
        ts_next = None
        if isinstance(metadata, dict):
            try:
                step_ms = int(metadata.get("step", step_ms))
            except Exception:
                step_ms = 3_600_000
            raw_ts = metadata.get("timestamps")
            if isinstance(raw_ts, list) and raw_ts:
                try:
                    ts_next = int(raw_ts[-1]) + step_ms
                except Exception:
                    ts_next = None

        if ts_next is None:
            ts_next = int(datetime.now(tz=timezone.utc).timestamp() * 1000)

        dt = datetime.fromtimestamp(ts_next / 1000, tz=timezone.utc)
        hour = float(dt.hour)
        dow = float(dt.weekday())
        sin_h = np.sin(2 * np.pi * hour / 24.0)
        cos_h = np.cos(2 * np.pi * hour / 24.0)
        sin_d = np.sin(2 * np.pi * dow / 7.0)
        cos_d = np.cos(2 * np.pi * dow / 7.0)

        full = np.concatenate([lag_values, np.array([sin_h, cos_h, sin_d, cos_d])])

        if full.size > expected_features:
            full = full[-expected_features:]
        elif full.size < expected_features:
            full = np.concatenate([full, np.zeros(expected_features - full.size)])

        return full.reshape(1, -1)

    # ------------------------------------------------------------------
    # Predict
    # ------------------------------------------------------------------

    def predict(self, input_data: PredictionInput) -> PredictionOutput:
        """
        Run linear regression forecast.

        Supports multi-step dict models (one estimator per horizon step)
        and single sklearn estimators (single-output or multi-output).
        """
        self.validate_input(input_data)

        raw_series = np.asarray(input_data.features, dtype=float).reshape(-1)
        metadata = input_data.metadata or {}

        try:
            if self.legacy_model is not None:
                if isinstance(self.legacy_model, dict):
                    # Multi-step: dict[int, estimator] keyed by step index
                    step_keys = sorted(self.legacy_model.keys())
                    first_est = self.legacy_model[step_keys[0]]
                    expected_features = int(getattr(first_est, "n_features_in_", raw_series.size))

                    predictions: List[float] = []
                    for step_key in step_keys:
                        features = self._build_feature_vector(raw_series, expected_features, metadata)
                        val = float(np.asarray(self.legacy_model[step_key].predict(features)).ravel()[0])
                        predictions.append(val)
                    y_pred = np.array(predictions)

                else:
                    # Single estimator — may return scalar or vector
                    expected_features = int(getattr(self.legacy_model, "n_features_in_", raw_series.size))
                    features = self._build_feature_vector(raw_series, expected_features, metadata)
                    y_pred = np.asarray(self.legacy_model.predict(features), dtype=float).ravel()

            else:
                # Fallback: linear trend extrapolation
                output_range = int(metadata.get("output_range", 24))
                y_pred = self._linear_trend_forecast(raw_series, output_range)

            logger.info("LinearRegression prediction: %d values", len(y_pred))

            return PredictionOutput(
                predictions=y_pred.tolist(),
                metadata={"model_type": "lr"},
            )

        except Exception as exc:
            logger.error("LinearRegression prediction failed: %s", exc)
            raise ValueError(f"LinearRegression prediction error: {exc}")

    @staticmethod
    def _linear_trend_forecast(series: np.ndarray, output_range: int) -> np.ndarray:
        """Simple linear-trend extrapolation used when no model file is present."""
        if series.size < 2:
            last = float(series[-1]) if series.size else 0.0
            return np.full(output_range, last)

        x = np.arange(series.size, dtype=float)
        coeffs = np.polyfit(x, series, 1)
        p = np.poly1d(coeffs)
        future_x = np.arange(series.size, series.size + output_range, dtype=float)
        return p(future_x)

    def train(self, train_data: List[float], timestamps: Optional[List[str]] = None) -> None:
        """Linear regression models are trained offline in notebooks; this is a no-op."""
        logger.info("LinearRegressionAdapter: training is offline-only (%d pts provided)", len(train_data))


class WindAdapter(BaseModel):
    """
    Адаптер для прогнозирования генерации ветровой электростанции.

    Использует XGBoost-модель (тот же формат бандла, что и SolarAdapter:
    манифест ``xgb_model.json`` + пошаговые бустеры), но строит вектор
    признаков с учётом метеорологических данных ветра из источника ``weather``.

    Структура вектора признаков (должна совпадать с обучением):
        [lag_1, ..., lag_k,
         wind_speed,                        ← скорость ветра (км/ч или м/с — как в обучении)
         wind_dir_sin, wind_dir_cos,        ← круговое кодирование направления ветра (°)
         temperature,                       ← температура воздуха (°C)
         sin_hour, cos_hour,                ← цикличное время суток
         sin_doy,  cos_doy]                 ← цикличный день года

    Количество лагов вычисляется как:
        k = booster.num_features() - N_WEATHER_FEATURES - N_TIME_FEATURES

    Если модель не загружена, используется нативный fallback:
    масштабирование последнего ненулевого значения генерации по кубическому
    закону мощности ветра (P ∝ v³) относительно среднего ветра в истории.

    Пример cache_config.json:
        см. docs/examples/wind_cache_config.json
    """

    # Weather feature order must match training pipeline.
    # wind_direction is encoded as (sin, cos) → 2 values, so N_WEATHER_FEATURES = 4.
    _WIND_SPEED_KEY: str = "wind_speed"
    _WIND_DIR_KEY: str = "wind_direction"
    _TEMPERATURE_KEY: str = "temperature"
    N_WEATHER_FEATURES: int = 4   # wind_speed, wind_dir_sin, wind_dir_cos, temperature
    N_TIME_FEATURES: int = 4      # sin_h, cos_h, sin_doy, cos_doy

    def __init__(self, model_name: str = "wind_model", legacy_model: Optional[Any] = None):
        """
        Args:
            model_name: Имя модели.
            legacy_model: Загруженный dict[int, xgb.Booster] или одиночный Booster.
        """
        super().__init__(model_name)
        self.legacy_model = legacy_model
        self.model = legacy_model if legacy_model is not None else self

    def load(self) -> None:
        self.model = self.legacy_model if self.legacy_model is not None else self

    # ------------------------------------------------------------------
    # Feature engineering
    # ------------------------------------------------------------------

    def _extract_weather_at_step(
        self,
        weather_data: Optional[Dict[str, Any]],
        step_index: int,
    ) -> np.ndarray:
        """
        Return weather feature array
        [wind_speed, wind_dir_sin, wind_dir_cos, temperature]
        for forecast step *i*.

        wind_direction (degrees 0-360) is encoded as sin/cos so that
        the boundary 0°/360° is handled correctly.
        """
        defaults = np.zeros(self.N_WEATHER_FEATURES, dtype=float)
        if not isinstance(weather_data, dict):
            return defaults
        hourly = weather_data.get("hourly")
        if not isinstance(hourly, list) or step_index >= len(hourly):
            return defaults
        entry = hourly[step_index]
        if not isinstance(entry, dict):
            return defaults

        wind_speed = float(entry.get(self._WIND_SPEED_KEY) or 0.0)
        wind_dir_deg = float(entry.get(self._WIND_DIR_KEY) or 0.0)
        temperature = float(entry.get(self._TEMPERATURE_KEY) or 0.0)

        wind_rad = np.deg2rad(wind_dir_deg)
        wind_dir_sin = np.sin(wind_rad)
        wind_dir_cos = np.cos(wind_rad)

        return np.array(
            [wind_speed, wind_dir_sin, wind_dir_cos, temperature],
            dtype=float,
        )

    @staticmethod
    def _cyclic_time_features(forecast_ts_ms: int) -> np.ndarray:
        """Return [sin_hour, cos_hour, sin_doy, cos_doy] for the given ms timestamp."""
        dt = datetime.fromtimestamp(forecast_ts_ms / 1000, tz=timezone.utc)
        hour = float(dt.hour) + float(dt.minute) / 60.0
        doy = float(dt.timetuple().tm_yday)
        return np.array(
            [
                np.sin(2 * np.pi * hour / 24.0),
                np.cos(2 * np.pi * hour / 24.0),
                np.sin(2 * np.pi * doy / 365.0),
                np.cos(2 * np.pi * doy / 365.0),
            ],
            dtype=float,
        )

    def _build_feature_row(
        self,
        series: np.ndarray,
        step_index: int,
        forecast_ts_ms: int,
        weather_data: Optional[Dict[str, Any]],
        expected_features: int,
    ) -> np.ndarray:
        """
        Build one feature row for a single forecast step.

        Layout: [lags..., weather(4), time(4)]
        """
        n_fixed = self.N_WEATHER_FEATURES + self.N_TIME_FEATURES
        lags = max(expected_features - n_fixed, 1)

        if series.size >= lags:
            lag_values = series[-lags:].astype(float)
        elif series.size > 0:
            pad_val = float(series[-1])
            lag_values = np.concatenate(
                [series.astype(float), np.full(lags - series.size, pad_val)]
            )
        else:
            lag_values = np.zeros(lags, dtype=float)

        weather_vec = self._extract_weather_at_step(weather_data, step_index)
        time_vec = self._cyclic_time_features(forecast_ts_ms)

        row = np.concatenate([lag_values, weather_vec, time_vec])

        # Align to exact expected_features (safety pad/trim)
        if row.size > expected_features:
            row = row[-expected_features:]
        elif row.size < expected_features:
            row = np.concatenate([row, np.zeros(expected_features - row.size)])

        return row.reshape(1, -1)

    # ------------------------------------------------------------------
    # Predict
    # ------------------------------------------------------------------

    def predict(self, input_data: PredictionInput) -> PredictionOutput:
        """
        Run wind generation forecast.

        Extracts weather features from ``input_data.metadata["weather_data"]``
        (list of hourly dicts from the weather source) and combines them with
        historical generation lags and cyclic time features.
        """
        self.validate_input(input_data)

        raw_series = np.asarray(input_data.features, dtype=float).reshape(-1)
        metadata = input_data.metadata or {}
        weather_data: Optional[Dict[str, Any]] = metadata.get("weather_data")
        step_ms = int(metadata.get("step", 3_600_000))
        output_range = int(metadata.get("output_range", 24))

        raw_ts = metadata.get("timestamps")
        if isinstance(raw_ts, list) and raw_ts:
            base_ts = int(raw_ts[-1]) + step_ms
        else:
            base_ts = int(datetime.now(tz=timezone.utc).timestamp() * 1000)

        try:
            if self.legacy_model is not None:
                import xgboost as xgb

                if isinstance(self.legacy_model, dict):
                    step_keys = sorted(self.legacy_model.keys())
                    first_booster = self.legacy_model[step_keys[0]]
                    expected_features = int(first_booster.num_features())

                    predictions: List[float] = []
                    for i, step_key in enumerate(step_keys):
                        forecast_ts = base_ts + i * step_ms
                        row = self._build_feature_row(
                            raw_series, i, forecast_ts, weather_data, expected_features
                        )
                        dmatrix = xgb.DMatrix(row)
                        val = float(self.legacy_model[step_key].predict(dmatrix)[0])
                        predictions.append(max(val, 0.0))
                    y_pred = np.array(predictions)

                elif isinstance(self.legacy_model, xgb.Booster):
                    expected_features = int(self.legacy_model.num_features())
                    predictions = []
                    for i in range(output_range):
                        forecast_ts = base_ts + i * step_ms
                        row = self._build_feature_row(
                            raw_series, i, forecast_ts, weather_data, expected_features
                        )
                        dmatrix = xgb.DMatrix(row)
                        val = float(self.legacy_model.predict(dmatrix)[0])
                        predictions.append(max(val, 0.0))
                    y_pred = np.array(predictions)

                else:
                    # XGBRegressor / sklearn pipeline
                    n_feat = int(getattr(self.legacy_model, "n_features_in_", len(raw_series)))
                    predictions = []
                    for i in range(output_range):
                        forecast_ts = base_ts + i * step_ms
                        row = self._build_feature_row(
                            raw_series, i, forecast_ts, weather_data, n_feat
                        )
                        val = float(self.legacy_model.predict(row)[0])
                        predictions.append(max(val, 0.0))
                    y_pred = np.array(predictions)

            else:
                # No model file — wind-speed-scaled naive fallback
                y_pred = self._wind_power_naive(raw_series, weather_data, output_range)

            logger.info(
                "Wind prediction: %d values, weather=%s",
                len(y_pred),
                "yes" if weather_data is not None else "no",
            )

            return PredictionOutput(
                predictions=y_pred.tolist(),
                metadata={
                    "model_type": "wind",
                    "weather_used": weather_data is not None,
                    "output_range": output_range,
                },
            )

        except Exception as exc:
            logger.error("Wind prediction failed: %s", exc)
            raise ValueError(f"Wind prediction error: {exc}")

    def _wind_power_naive(
        self,
        series: np.ndarray,
        weather_data: Optional[Dict[str, Any]],
        output_range: int,
    ) -> np.ndarray:
        """
        Fallback when no model is loaded.

        Estimates generation using the cubic wind power law:
            P_forecast ≈ P_ref × (v_forecast / v_ref)³

        where P_ref is the last non-zero observed generation value and
        v_ref is the mean wind speed over the recent history from the
        weather payload (or 1.0 if unavailable, yielding a naive repeat).

        Predictions are clipped to [0, max_observed] to avoid extrapolation.
        """
        nonzero = series[series > 0]
        last_gen = float(nonzero[-1]) if nonzero.size > 0 else 0.0
        max_gen = float(series.max()) if series.size > 0 else 0.0

        # Estimate reference wind speed from the tail of historical hourly data
        # (the weather payload's hourly list starts at the current hour, so we
        # can't directly read "past" wind — use last_gen as the reference instead
        # and scale relative to forecast wind speed with a nominal reference of 10 m/s).
        NOMINAL_WIND_REF_KPH = 10.0

        predictions: List[float] = []
        for i in range(output_range):
            if isinstance(weather_data, dict):
                hourly = weather_data.get("hourly")
                if isinstance(hourly, list) and i < len(hourly):
                    entry = hourly[i]
                    v_forecast = float((entry or {}).get(self._WIND_SPEED_KEY, 0.0) or 0.0)
                    # Cubic law, capped at max observed generation
                    scale = min((v_forecast / NOMINAL_WIND_REF_KPH) ** 3, 1.0)
                    predictions.append(min(last_gen * scale, max_gen))
                    continue
            predictions.append(np.nan)

        return np.array(predictions, dtype=float)

    def train(self, train_data: List[float], timestamps: Optional[List[str]] = None) -> None:
        """Wind models are trained offline in notebooks; this is a no-op."""
        logger.info("WindAdapter: training is offline-only (%d pts provided)", len(train_data))


class NaiveAdapter(BaseModel):
    """
    Наивный алгоритм прогнозирования.

    Использует исторические данные напрямую в качестве прогноза:
    берёт последние ``horizon`` значений из входного ряда и возвращает
    их как предсказание на следующий горизонт.

    Если исторических данных меньше, чем ``horizon``, оставшиеся точки
    заполняются последним известным значением.

    Пример использования::

        model = NaiveAdapter(model_name="naive", horizon=24)
        prediction = model.predict(PredictionInput(features=[...]))
    """

    def __init__(
        self,
        model_name: str = "naive_model",
        horizon: int = 24,
    ):
        """
        Args:
            model_name: Имя модели.
            horizon: Количество шагов прогноза (по умолчанию 24 часа).
        """
        super().__init__(model_name)
        self.horizon = horizon
        # Наивная модель не требует файла — помечаем как «загруженную» сразу.
        self.model = self

    def load(self) -> None:
        """Наивная модель не требует загрузки из файла."""
        self.model = self

    def predict(self, input_data: PredictionInput) -> PredictionOutput:
        """
        Вернуть последние ``horizon`` значений истории как прогноз.

        Args:
            input_data: PredictionInput с полем features (массив исторических значений).

        Returns:
            PredictionOutput с predictions длиной ``horizon``.
        """
        self.validate_input(input_data)

        horizon = self.horizon
        if input_data.metadata:
            horizon = int(input_data.metadata.get("output_range", horizon))

        features = np.asarray(input_data.features, dtype=float).reshape(-1)

        if len(features) == 0:
            predictions = np.full(horizon, np.nan)
        elif len(features) >= horizon:
            # Берём последние horizon значений (один период назад)
            predictions = features[-horizon:].copy()
        else:
            # Данных меньше горизонта — дополняем последним значением
            pad_value = features[-1]
            predictions = np.concatenate(
                [features, np.full(horizon - len(features), pad_value)]
            )

        logger.info(f"Naive prediction: {horizon} values from {len(features)} history points")

        return PredictionOutput(
            predictions=predictions.tolist(),
            metadata={
                "model_type": "naive",
                "horizon": horizon,
                "history_length": len(features),
            },
        )

    def train(self, train_data: List[float], timestamps: Optional[List[str]] = None) -> None:
        """Наивная модель не требует обучения."""
        logger.info("NaiveAdapter: no training required")
