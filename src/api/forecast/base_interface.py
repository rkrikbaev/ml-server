"""
base_interface.py

Абстрактный интерфейс для моделей прогнозирования.
Все модели, подключённые к серверу, должны реализовать этот интерфейс.

Это обеспечивает единообразный способ передачи данных на вход и получения результатов.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, asdict
import json


@dataclass
class PredictionInput:
    """
    Стандартный объект для передачи входных данных на вход модели.
    
    Атрибуты:
        features: Dict[str, Any] — признаки (ключ -> значение). Может быть DataFrame, 
                  преобразованный в dict с методом to_dict('list').
        metadata: Dict[str, Any] — опциональные метаданные (дата, регион, версия модели и т.д.).
        config: Dict[str, Any] — опциональные параметры инференса (batch_size, timeout и т.д.).
    """
    features: Any
    metadata: Optional[Dict[str, Any]] = None
    config: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Преобразовать в словарь."""
        return asdict(self)

    def to_json(self) -> str:
        """Преобразовать в JSON строку."""
        return json.dumps(self.to_dict(), default=str)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PredictionInput":
        """Создать из словаря."""
        return cls(**data)

    @classmethod
    def from_json(cls, json_str: str) -> "PredictionInput":
        """Создать из JSON строки."""
        return cls.from_dict(json.loads(json_str))


@dataclass
class PredictionOutput:
    """
    Стандартный объект для возврата результатов прогнозирования.
    
    Атрибуты:
        predictions: List[float] или Dict[str, Any] — основной результат прогноза.
        confidence: Optional[List[float]] — доверие/вероятность для каждого прогноза (опционально).
        metadata: Optional[Dict[str, Any]] — метаданные результата 
                  (время выполнения, версия модели, условия запроса и т.д.).
    """
    predictions: Any  # List[float], List[Dict], DataFrame и т.д.
    confidence: Optional[List[float]] = None
    metadata: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Преобразовать в словарь."""
        # predictions может быть не-сериализуемым, поэтому конвертируем
        pred_serializable = predictions = self.predictions
        if hasattr(self.predictions, 'tolist'):  # numpy array, pandas Series
            pred_serializable = self.predictions.tolist()
        elif hasattr(self.predictions, 'to_dict'):  # pandas DataFrame
            pred_serializable = self.predictions.to_dict(orient='list')
        
        return {
            'predictions': pred_serializable,
            'confidence': self.confidence,
            'metadata': self.metadata,
        }

    def to_json(self) -> str:
        """Преобразовать в JSON строку."""
        return json.dumps(self.to_dict(), default=str)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PredictionOutput":
        """Создать из словаря."""
        return cls(
            predictions=data.get('predictions'),
            confidence=data.get('confidence'),
            metadata=data.get('metadata'),
        )

    @classmethod
    def from_json(cls, json_str: str) -> "PredictionOutput":
        """Создать из JSON строки."""
        return cls.from_dict(json.loads(json_str))


class BaseModel(ABC):
    """
    Абстрактный базовый класс для всех моделей прогнозирования.
    
    Каждая модель (Prophet, XGBoost, AR и т.д.) должна наследовать этот класс 
    и реализовать методы load() и predict().
    """

    def __init__(self, model_path: str, config: Optional[Dict[str, Any]] = None):
        """
        Инициализация модели.
        
        Args:
            model_path: путь к файлу/директории с моделью (pkl, h5, pth и т.д.).
            config: опциональная конфигурация модели (может быть загружена из config.yaml).
        """
        self.model_path = model_path
        self.config = config or {}
        self.model = None

    @abstractmethod
    def load(self) -> None:
        """
        Загрузить модель из файла.
        
        Реализация зависит от формата хранения (pickle, joblib, keras и т.д.).
        """
        pass

    @abstractmethod
    def predict(self, input_data: PredictionInput) -> PredictionOutput:
        """
        Выполнить прогноз на основе входных данных.
        
        Args:
            input_data: объект PredictionInput с признаками и метаданными.
            
        Returns:
            объект PredictionOutput с результатами прогноза.
            
        Raises:
            ValueError: если input_data некорректен.
            RuntimeError: если модель не загружена.
        """
        pass

    def validate_input(self, input_data: PredictionInput) -> bool:
        """
        Валидировать входные данные (опционально переопределить в подклассе).
        
        Args:
            input_data: объект PredictionInput.
            
        Returns:
            True если входные данные корректны.
            
        Raises:
            ValueError если входные данные некорректны.
        """
        if not isinstance(input_data, PredictionInput):
            raise ValueError(f"Expected PredictionInput, got {type(input_data)}")
        features = input_data.features
        if features is None:
            raise ValueError("features cannot be empty")
        if hasattr(features, "size"):
            if int(features.size) == 0:
                raise ValueError("features cannot be empty")
        elif hasattr(features, "__len__"):
            if len(features) == 0:
                raise ValueError("features cannot be empty")
        return True

    def is_loaded(self) -> bool:
        """Проверить, загружена ли модель."""
        return self.model is not None
