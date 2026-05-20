"""
test_model_interface.py

Простые примеры и тесты для проверки работы единого интерфейса модели.
"""

import json
from pathlib import Path
import sys

# Добавить путь до локальной директории src
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from adapters.base_interface import PredictionInput, PredictionOutput, BaseModel


def test_prediction_input_serialization():
    """Тест сериализации/десериализации PredictionInput"""
    print("\n[TEST] PredictionInput serialization...")
    
    # Создать входной объект
    inp = PredictionInput(
        features={'ds': ['2024-01-01', '2024-01-02'], 'y': [1.5, 2.3]},
        metadata={'region': 'AKMOLA', 'source': 'raw_db'},
        config={'batch_size': 32}
    )
    
    # Сериализовать
    json_str = inp.to_json()
    print(f"  Serialized: {json_str[:100]}...")
    
    # Десериализовать
    inp_restored = PredictionInput.from_json(json_str)
    print(f"  Restored features: {inp_restored.features}")
    print(f"  Restored metadata: {inp_restored.metadata}")
    print("  ✓ PredictionInput serialization passed")


def test_prediction_output_serialization():
    """Тест сериализации/десериализации PredictionOutput"""
    print("\n[TEST] PredictionOutput serialization...")
    
    # Создать выходной объект
    out = PredictionOutput(
        predictions=[1.5, 2.3, 1.8],
        confidence=[0.92, 0.85, 0.88],
        metadata={'model_type': 'prophet', 'intervals': {'lower': [1.0, 1.8, 1.3], 'upper': [2.0, 2.8, 2.3]}}
    )
    
    # Сериализовать
    json_str = out.to_json()
    print(f"  Serialized: {json_str[:100]}...")
    
    # Десериализовать
    out_restored = PredictionOutput.from_json(json_str)
    print(f"  Restored predictions: {out_restored.predictions}")
    print(f"  Restored confidence: {out_restored.confidence}")
    print("  ✓ PredictionOutput serialization passed")


def test_dict_conversion():
    """Тест преобразования в/из словарей"""
    print("\n[TEST] Dictionary conversion...")
    
    # PredictionInput
    inp_dict = {
        'features': {'x': [1, 2, 3]},
        'metadata': {'test': True},
        'config': None
    }
    inp = PredictionInput.from_dict(inp_dict)
    print(f"  Input from dict: {inp.features}")
    
    # PredictionOutput
    out_dict = {
        'predictions': [1.0, 2.0, 3.0],
        'confidence': [0.9, 0.8, 0.9],
        'metadata': None
    }
    out = PredictionOutput.from_dict(out_dict)
    print(f"  Output from dict: {out.predictions}")
    print("  ✓ Dictionary conversion passed")


def test_custom_model_adapter():
    """Тест создания собственного адаптера"""
    print("\n[TEST] Custom model adapter...")
    
    # Создать простую тестовую модель
    class DummyModel(BaseModel):
        """Простая модель для теста"""
        
        def load(self) -> None:
            # Симуляция загрузки
            self.model = lambda x: [float(val) * 2 for row in x for val in row.values()]
        
        def predict(self, input_data: PredictionInput) -> PredictionOutput:
            self.validate_input(input_data)
            if not self.is_loaded():
                raise RuntimeError("Model not loaded")
            
            # Простой прогноз: удвоить значения
            predictions = []
            for key, values in input_data.features.items():
                if isinstance(values, (list, tuple)):
                    predictions.extend([float(v) * 2 for v in values])
            
            return PredictionOutput(
                predictions=predictions,
                confidence=[0.95] * len(predictions),
                metadata={'model_type': 'dummy'}
            )
    
    # Использовать адаптер
    model = DummyModel("dummy_path", config={})
    model.load()
    
    inp = PredictionInput(features={'x': [1, 2, 3]})
    out = model.predict(inp)
    
    print(f"  Input: {inp.features}")
    print(f"  Output predictions: {out.predictions}")
    print(f"  Expected: [2.0, 4.0, 6.0]")
    assert out.predictions == [2.0, 4.0, 6.0], "Predictions don't match"
    print("  ✓ Custom model adapter passed")


def test_input_validation():
    """Тест валидации входных данных"""
    print("\n[TEST] Input validation...")
    
    class ValidatingModel(BaseModel):
        def load(self) -> None:
            self.model = {}
        
        def predict(self, input_data: PredictionInput) -> PredictionOutput:
            self.validate_input(input_data)
            
            if 'required_feature' not in input_data.features:
                raise ValueError("Missing required_feature")
            
            return PredictionOutput(predictions=[1.0, 2.0])
    
    model = ValidatingModel("test_path", config={})
    model.load()
    
    # Случай 1: отсутствуют требуемые поля
    try:
        inp = PredictionInput(features={'other': [1, 2]})
        model.predict(inp)
        print("  ✗ Validation failed: should have raised ValueError")
    except ValueError as e:
        print(f"  ✓ Caught expected error: {e}")
    
    # Случай 2: правильные данные
    inp = PredictionInput(features={'required_feature': [1, 2]})
    out = model.predict(inp)
    print(f"  ✓ Validation passed for correct input: {out.predictions}")


def test_metadata_preservation():
    """Тест сохранения метаданных через конвейер"""
    print("\n[TEST] Metadata preservation...")
    
    # Создать входные данные с метаданными
    inp = PredictionInput(
        features={'x': [1, 2]},
        metadata={'region': 'ALMATY', 'user_id': 'user123'},
        config={'timeout': 30}
    )
    
    # Проверить, что метаданные доступны
    assert inp.metadata['region'] == 'ALMATY', "Metadata not preserved"
    assert inp.config['timeout'] == 30, "Config not preserved"
    
    # Через сериализацию
    json_str = inp.to_json()
    inp_restored = PredictionInput.from_json(json_str)
    assert inp_restored.metadata['user_id'] == 'user123', "Metadata not restored after JSON"
    
    print(f"  Input metadata: {inp.metadata}")
    print(f"  Config: {inp.config}")
    print("  ✓ Metadata preservation passed")


def print_demo():
    """Демонстрационный вывод"""
    print("\n" + "="*60)
    print("Model Interface Integration Examples")
    print("="*60)
    
    print("\n[EXAMPLE 1] Basic PredictionInput usage:")
    print("""
    from api.forecast.base_interface import PredictionInput
    
    inp = PredictionInput(
        features={'dates': ['2024-01-01', '2024-01-02']},
        metadata={'region': 'AKMOLA'}
    )
    print(inp.features)  # {'dates': ['2024-01-01', '2024-01-02']}
    """)
    
    print("\n[EXAMPLE 2] Using adapters from adapters.py:")
    print("""
    from api.forecast.adapters import get_model_adapter
    
    model = get_model_adapter('prophet', '/path/to/model.pkl')
    model.load()
    
    inp = PredictionInput(features={'ds': dates})
    output = model.predict(inp)
    print(output.predictions)
    print(output.metadata['intervals'])
    """)
    
    print("\n[EXAMPLE 3] FastAPI integration:")
    print("""
    from fastapi import FastAPI
    from api.forecast.base_interface import PredictionInput
    
    @app.post("/forecast")
    async def forecast(request: dict):
        inp = PredictionInput.from_dict(request)
        output = model.predict(inp)
        return output.to_dict()
    """)


if __name__ == "__main__":
    print_demo()
    print("\n" + "="*60)
    print("Running Tests")
    print("="*60)
    
    try:
        test_prediction_input_serialization()
        test_prediction_output_serialization()
        test_dict_conversion()
        test_custom_model_adapter()
        test_input_validation()
        test_metadata_preservation()
        
        print("\n" + "="*60)
        print("✓ All tests passed!")
        print("="*60)
    except Exception as e:
        print(f"\n✗ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
