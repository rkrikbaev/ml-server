"""
integration_example.py

Пример интеграции единого интерфейса модели с FastAPI сервером.
Демонстрирует, как использовать BaseModel, PredictionInput и PredictionOutput.
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel as PydanticModel
from typing import Optional, Dict, Any, List
import json

from api.forecast.base_interface import PredictionInput, PredictionOutput
from api.forecast.adapters import get_model_adapter


app = FastAPI()

# Глобальное хранилище загруженных моделей (в реальном приложении — Redis)
loaded_models: Dict[str, Any] = {}


# Pydantic модели для HTTP запросов/ответов
class ForecastRequest(PydanticModel):
    """Запрос на прогноз"""
    model_id: str
    features: Dict[str, Any]
    metadata: Optional[Dict[str, Any]] = None
    config: Optional[Dict[str, Any]] = None


class ForecastResponse(PydanticModel):
    """Ответ сервера"""
    model_id: str
    predictions: List[Any]
    confidence: Optional[List[float]] = None
    metadata: Optional[Dict[str, Any]] = None


@app.post("/forecast")
async def forecast_endpoint(request: ForecastRequest) -> ForecastResponse:
    """
    Endpoint для получения прогноза.
    
    Пример запроса:
    ```
    POST /forecast
    {
        "model_id": "prophet_watt_AKMOLA",
        "features": {"ds": ["2024-01-01", "2024-01-02"]},
        "metadata": {"region": "AKMOLA"},
        "config": {"batch_size": 32}
    }
    ```
    """
    try:
        # 1. Загрузить модель (если ещё не загружена)
        if request.model_id not in loaded_models:
            loaded_models[request.model_id] = _load_model(request.model_id)
        
        model = loaded_models[request.model_id]
        
        # 2. Создать входной объект (соответствует единому интерфейсу)
        inp = PredictionInput(
            features=request.features,
            metadata=request.metadata or {},
            config=request.config or {}
        )
        
        # 3. Выполнить прогноз
        output: PredictionOutput = model.predict(inp)
        
        # 4. Вернуть результат в формате Pydantic
        return ForecastResponse(
            model_id=request.model_id,
            predictions=output.predictions,
            confidence=output.confidence,
            metadata=output.metadata
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/load_model")
async def load_model_endpoint(model_id: str, model_path: str, model_type: str) -> Dict[str, str]:
    """
    Явно загрузить модель.
    
    Пример:
    ```
    POST /load_model?model_id=prophet_watt_AKMOLA&model_path=/workspace/models/model.pkl&model_type=prophet
    ```
    """
    try:
        adapter = get_model_adapter(model_type, model_path, config={})
        adapter.load()
        loaded_models[model_id] = adapter
        return {"status": "success", "model_id": model_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health_check() -> Dict[str, Any]:
    """Проверка здоровья сервера"""
    return {
        "status": "healthy",
        "loaded_models": list(loaded_models.keys())
    }


def _load_model(model_id: str):
    """
    Вспомогательная функция для загрузки модели по ID.
    
    В реальном приложении здесь должна быть логика:
    - чтения конфига из MLflow по model_id
    - определения типа модели
    - загрузки артефактов
    """
    # Пример: читаем из meta.json или запрашиваем MLflow
    import os
    model_dir = f"/workspace/models/{model_id}"
    
    if not os.path.exists(model_dir):
        raise FileNotFoundError(f"Model directory not found: {model_dir}")
    
    # Предположим, что есть meta.json с описанием модели
    meta_path = os.path.join(model_dir, "meta.json")
    if os.path.exists(meta_path):
        with open(meta_path, 'r') as f:
            meta = json.load(f)
        model_type = meta.get('framework', 'sklearn')
        model_file = os.path.join(model_dir, meta.get('artifacts', {}).get('model', 'model.pkl'))
    else:
        # Fallback: предполагаем sklearn
        model_type = 'sklearn'
        model_file = os.path.join(model_dir, "model.pkl")
    
    if not os.path.exists(model_file):
        raise FileNotFoundError(f"Model file not found: {model_file}")
    
    # Создать и загрузить адаптер
    adapter = get_model_adapter(model_type, model_file, config={})
    adapter.load()
    
    return adapter


# Пример использования в стиле sync (если нужно)
def predict_sync(model_id: str, features: Dict[str, Any]) -> Dict[str, Any]:
    """
    Синхронный вспомогательный метод для прогноза.
    
    Использование:
    ```python
    result = predict_sync("prophet_watt_AKMOLA", {"ds": ["2024-01-01"]})
    print(result)
    ```
    """
    # Загрузить модель
    if model_id not in loaded_models:
        loaded_models[model_id] = _load_model(model_id)
    
    model = loaded_models[model_id]
    
    # Прогноз
    inp = PredictionInput(features=features)
    output = model.predict(inp)
    
    # Вернуть как словарь
    return output.to_dict()


if __name__ == "__main__":
    import uvicorn
    
    # Запустить сервер
    uvicorn.run(app, host="0.0.0.0", port=8000)
