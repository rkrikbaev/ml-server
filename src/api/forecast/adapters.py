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

import logging
from typing import Any, Dict, Optional, List
import pandas as pd
import numpy as np

from api.forecast.base_interface import BaseModel, PredictionInput, PredictionOutput

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
    
    def predict(self, input_data: PredictionInput) -> PredictionOutput:
        """Выполнить прогноз используя XGBoost."""
        self.validate_input(input_data)
        
        try:
            features = np.asarray(input_data.features).reshape(1, -1)
            
            if self.legacy_model is not None:
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
