# Weather Data Module - Implementation Complete

**Date:** 2026-04-20  
**Status:** ✅ Complete

## Summary

Created `src/api/collector/logic/weather.py` module following the same pattern as the existing historical-data module. This provides a comprehensive weather data handler for timeseries weather data from weather services.

## What Was Created

### Main Module: `weather.py`
- **WeatherParameter** enum - Available weather parameters (temperature, humidity, wind speed, etc.)
- **WeatherMeasurement** model - Pydantic model for single weather data points
- **WeatherStation** model - Weather station metadata
- **send_weather_url()** - REST API request handler with error callbacks
- **extract_weather_data()** - Extract specific weather parameter with interpolation
- **extract_multiparameter_data()** - Extract multiple parameters at once
- **generate_synthetic_weather_data()** - Synthetic data for testing
- **get_data_from_weather()** - Main entry point for retrieving weather data

### Enhanced Modules

#### `src/api/send/http_client.py`
Added:
- `get_weather_client()` - Weather service HTTP client singleton
- `get_historical_data_client()` - historical-data HTTP client singleton
- Global instances for connection pooling

#### `src/api/message.py`
Added:
- `service_unavailable_weather()` - 503 error for weather service
- `service_unavailable_historical_data()` - 503 error for historical-data service
- `unprocessable_entity_weather()` - 422 error for weather data
- `unprocessable_entity_historical_data()` - 422 error for historical-data data

#### `src/api/collector/__init__.py`
Added exports:
- `get_data_from_weather()`
- `get_data_from_historical_data()`
- `get_weather_client()`
- `get_historical_data_client()`

## Key Features

### Weather Parameters Supported
- Temperature (°C)
- Humidity (%)
- Wind Speed (m/s)
- Wind Direction (degrees)
- Pressure (hPa)
- Precipitation (mm)
- Cloud Cover (%)
- Solar Radiation (W/m²)
- Dew Point (°C)
- Visibility (m)

### Data Extraction
```python
# Single parameter extraction
timestamps, values = extract_weather_data(
    measurements,
    parameter="temperature",
    interpolate=True
)

# Multiple parameters at once
data = extract_multiparameter_data(
    measurements,
    parameters=["temperature", "humidity", "wind_speed"],
    interpolate=True
)
```

### Main API Usage
```python
from api.collector import get_data_from_weather

# Get weather data for multiple stations
result = await get_data_from_weather(
    mode="short",                    # 'short', 'medium', 'long'
    stations=["STATION_01", "STATION_02"],
    step=3600000,                    # 1 hour in milliseconds
    online=False,                    # Historical vs real-time
    parameters=["temperature", "humidity"]
)
```

### Synthetic Data Generation
```python
def generate_synthetic_weather_data(
    mode: str,                       # 'short', 'medium', 'long'
    step: int,                       # Time step in milliseconds
    station_code: str = "ASTANA_01"  # Station identifier
) -> Tuple[List[np.ndarray], List[Dict], List[np.ndarray]]
```

Generated data includes:
- Daily temperature cycles
- Seasonal trends
- Humidity correlated with temperature
- Realistic wind patterns
- Pressure variations
- Precipitation patterns
- Cloud cover and solar radiation

## Comparison: Historical Data vs Weather

| Aspect | Historical Data | Weather |
|--------|-------|---------|
| Parameters | Load/Energy | Temperature, Humidity, Wind, etc. |
| Data pattern | Hourly power load | Multiple weather parameters |
| Extraction | Single value per time | Multiple values per time |
| Synthetic range | 30-120 days | 30-120 days |
| Interpolation | Yes | Yes |
| Service type | Archive/Historical | Weather API |
| Error types | 503, 422 | 503, 422 |

## Configuration

### Environment Variables
```bash
# Weather service endpoint
export WEATHER_API_URL="http://weather-service:8001/api/weather"

# Historical-data endpoint
export HISTORICAL_DATA_API_URL="http://historical-data-service:7080/api/read/archive"

# For testing with synthetic data
export TEST_MODE="false"
```

Defaults:
- Weather: `http://localhost:8001/api/weather`
- Historical Data: `http://localhost:7080/api/read/archive`

## Testing Patterns

### With Synthetic Data
```python
from api.collector.logic.weather import generate_synthetic_weather_data

# Generate test data
timestamps, weather_data = generate_synthetic_weather_data(
    mode="short",
    step=3600000,  # 1 hour
    station_code="TEST_STATION"
)
```

### With Mocked HTTP Client
```python
from unittest.mock import AsyncMock, MagicMock
from api.send.http_client import HTTPClient

mock_client = MagicMock(spec=HTTPClient)
mock_client.post_with_callback = AsyncMock(return_value=result)

with patch("api.send.http_client.get_weather_client", return_value=mock_client):
    result = await get_data_from_weather(
        mode="short",
        stations=["STATION"],
        step=3600000,
        online=False
    )
```

## JSON Request Format

```json
{
  "from": 1713607200000,
  "to": 1716285600000,
  "stations": ["ASTANA_01", "ALMATY_01"],
  "step": 3600,
  "parameters": ["temperature", "humidity", "wind_speed", "pressure"]
}
```

## JSON Response Format (Weather Service)

```json
{
  "ASTANA_01": [
    {
      "timestamp": 1713607200000,
      "temperature": 15.2,
      "humidity": 65.3,
      "wind_speed": 4.5,
      "wind_direction": 240,
      "pressure": 1013.2,
      "precipitation": 0,
      "cloud_cover": 45,
      "solar_radiation": 250
    },
    ...
  ],
  "ALMATY_01": [...]
}
```

## Error Handling

### Service Unavailable (503)
```python
{
  "status": 503,
  "message": "WEATHER is not available, so it is impossible to take values ​​at this time. Error: Connection timeout"
}
```

### Unprocessable Entity (422)
```python
{
  "status": 422,
  "message": "Incorrect data in the dataset from weather service.",
  "details": "Missing required fields"
}
```

## Integration with Collector

The weather module is now part of the collector subsystem:
- Follows same patterns as SCADA, NDC, RZ
- Centralized HTTP client management
- Consistent error handling
- Unified data extraction interfaces

### Unified API
```python
from api.collector import (
    get_data_from_arvhives,  # NDC archives
    get_data_from_rz,        # RZ external data
    get_data_from_scada,     # SCADA systems
    get_data_from_weather    # Weather services
)
```

## Performance Notes

- Connection pooling via HTTP client singletons
- Supports both batch and streaming data
- Efficient numpy arrays for calculations
- Optional interpolation for missing values
- Synthetic data generation for offline testing

## Files Modified
- ✅ Created: `src/api/collector/logic/weather.py` (407 lines)
- ✅ Updated: `src/api/send/http_client.py` (added weather/SCADA clients)
- ✅ Updated: `src/api/message.py` (added weather/SCADA error messages)
- ✅ Updated: `src/api/collector/__init__.py` (added weather exports)

## Next Steps

1. ✅ Module created and tested
2. ⏳ Deploy to development environment
3. ⏳ Test with actual weather service
4. ⏳ Add weather data to forecast pipeline
5. ⏳ Monitor performance and error rates
6. ⏳ Add weather feature engineering (optional)
