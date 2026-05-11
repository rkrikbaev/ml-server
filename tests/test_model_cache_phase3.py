"""
Unit tests for model instance caching - Phase 3 validation
"""
import pytest
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from api.forecast import model as model_module  # type: ignore[import-not-found]


def test_cache_infrastructure_exists():
    """Verify cache infrastructure is properly initialized."""
    assert hasattr(model_module, '_MODEL_CACHE')
    assert hasattr(model_module, '_MODEL_CACHE_LOCK')
    assert hasattr(model_module, '_CACHE_STATS')
    assert isinstance(model_module._MODEL_CACHE, dict)
    assert 'hits' in model_module._CACHE_STATS
    assert 'misses' in model_module._CACHE_STATS
    assert 'evictions' in model_module._CACHE_STATS


def test_cache_key_builder():
    """Test cache key builder produces stable identifiers."""
    k1 = model_module._build_cache_key("none", "prophet")
    k2 = model_module._build_cache_key("none", "prophet")
    assert k1 == k2
    assert k1 == ("none", "prophet")
    
    k3 = model_module._build_cache_key("/tmp/model", "xgb")
    assert k3 == ("/tmp/model", "xgb")
    
    k4 = model_module._build_cache_key("relative/path", "prophet")
    assert k4[0] == str(Path("/workspace/models") / "relative/path")
    assert k4[1] == "prophet"


def test_cache_hit_on_repeated_prophet_calls():
    """Verify cache hit occurs when requesting same Prophet model twice."""
    model_module._MODEL_CACHE.clear()
    model_module._CACHE_STATS["hits"] = 0
    model_module._CACHE_STATS["misses"] = 0
    
    with patch('api.forecast.model.ProphetAdapter') as mock_prophet:
        mock_instance = MagicMock()
        mock_prophet.return_value = mock_instance
        
        # First call
        result1 = model_module.init_model("none", 3600000, fallback="none", model_type="prophet")
        initial_misses = model_module._CACHE_STATS["misses"]
        assert initial_misses == 1
        
        # Second call with same params
        result2 = model_module.init_model("none", 3600000, fallback="none", model_type="prophet")
        assert model_module._CACHE_STATS["hits"] == 1
        assert result1 is result2, "Cache should return same instance"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
