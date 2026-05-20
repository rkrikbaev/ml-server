# Model Configuration Standard: One Config per Model
## Based on cache_config.json Structure

**Principle**: Each model in MLflow has exactly ONE cache_config.json describing its complete runtime behavior.

---

## Template: Model Configuration Structure

```json
{
  "model_type": "string",
  "model_name": "string",
  "version": "semver",
  "fallback": "strategy",
  "sources": {
    "step": 3600,
    "input_range": 168,
    "output_range": 24,
    "historical": { ... },
    "weather": { ... },
    "cmms": { ... }
  }
}
```

---

## Current Model: XGBoost AKMOLA

### Model Identity
```json
{
  "model_type": "xgb",
  "model_name": "prophet_watt_h_AKMOLA_test",
  "version": "1.0.0",
  "fallback": "none",
```

### STAGE 4 Data Sources Configuration
```json
  "sources": {
    "step": 3600,
    "input_range": 168,
    "output_range": 24,
    
    "historical": {
      "type": "archive",
      "url": "http://host.docker.internal:7080/api/v1/read/archives",
      "archives": [
        "/root/FP/PROJECT/AKMOLA/@regions/KOKSHETAU/Load/P_load/archives/out_value"
      ],
      "request_overrides": {
        "archive": ["/root/FP/PROJECT/AKMOLA/@regions/KOKSHETAU/Load/P_load/archives/out_value"],
        "step": 3600,
        "range_size": 168,
        "pattern": "historic"
      },
      "timeout": 30,
      "retry_count": 3,
      "required": true
    },
    
    "weather": {
      "type": "forecast",
      "url": null,
      "lat": null,
      "lon": null,
      "units": "metric",
      "hours": null,
      "timeout": 30,
      "retry_count": 3,
      "required": false
    },
    
    "cmms": {
      "type": "maintenance",
      "url": null,
      "request_overrides": {},
      "timeout": 30,
      "retry_count": 3,
      "required": false
    }
  }
}
```

---

## MLflow Storage: One Config per Model Version

```
mlruns/
├── 1/                                    # Experiment
│   └── manual_reg/
│       └── 848387cc60dd48ef8abec7a643493bde/  # RUN ID for XGBoost model
│           └── artifacts/
│               └── bundle/
│                   ├── configuration/
│                   │   └── cache_config.json      ◄─ THIS MODEL'S CONFIG
│                   ├── models/
│                   │   └── model.pkl
│
│
└── prophet_watt_h_AKMOLA_test/           # Model Registry
    ├── version/1/
    │   ├── run_id: 848387cc60dd48ef8abec7a643493bde
    │   ├── config_file: cache_config.json (XGBoost variant)
    │   └── model.pkl
    │
    ├── version/2/
    │   ├── run_id: <another_run_id>
    │   ├── config_file: cache_config.json (Prophet variant)
    │   └── model.pkl
    │
    └── version/3/
        ├── run_id: <third_run_id>
        ├── config_file: cache_config.json (Ensemble variant)
        └── model.pkl
```

**Key Point**: Each version has its own cache_config.json artifact. The config describes ONLY that version's behavior.

---

## Model Loading Flow

When MLflow loads a specific model version:

```
mlflow.pyfunc.load_model('prophet_watt_h_AKMOLA_test/1')
  │
  ├─ Retrieves Run ID: 848387cc60dd48ef8abec7a643493bde
  │
  ├─ Loads artifacts:
  │  ├─ model.pkl (model weights)
  │  └─ cache_config.json ◄─ THIS CONFIG DESCRIBES THIS MODEL
  │
  └─ model.config = cache_config.json
     ├─ model_type = "xgb"
     ├─ step = 3600
     ├─ sources = {...}  ◄─ For STAGE 4 data collection
```

---

## Multi-Model Registry Example

### Scenario: Three model versions in production

**Model Version 1: XGBoost** (Current production)
```json
{
  "model_type": "xgb",
  "model_name": "prophet_watt_h_AKMOLA_test",
  "version": "1.0.0",
  "sources": {
    "step": 3600,
    "input_range": 168,
    "output_range": 24,
    "historical": { "url": "http://host.docker.internal:7080/...", ... },
    "weather": { "url": null, ... },
    "cmms": { "url": null, ... }
  }
}
```

**Model Version 2: Prophet** (Experimental)
```json
{
  "model_type": "prophet",
  "model_name": "prophet_watt_h_AKMOLA_test",
  "version": "2.0.0",
  "sources": {
    "step": 3600,
    "input_range": 336,                   ◄─ Longer lookback
    "output_range": 24,
    "historical": { "url": "http://host.docker.internal:7080/...", ... },
    "weather": { "url": "http://127.0.0.1:8050/...", ... },  ◄─ Weather enabled
    "cmms": { "url": null, ... }
  }
}
```

**Model Version 3: Ensemble** (Testing)
```json
{
  "model_type": "ensemble",
  "model_name": "prophet_watt_h_AKMOLA_test",
  "version": "3.0.0",
  "sources": {
    "step": 3600,
    "input_range": 168,
    "output_range": 48,                   ◄─ Longer forecast
    "historical": { "url": "http://host.docker.internal:7080/...", ... },
    "weather": { "url": "http://127.0.0.1:8050/...", ... },  ◄─ Weather enabled
    "cmms": { "url": "http://localhost:8000/...", ... }       ◄─ CMMS enabled
  }
}
```

Each has its OWN cache_config.json with its own parameters!

---

## Configuration Scope & Responsibility

### What cache_config.json DOES describe:
✓ Model type and version  
✓ Data sources for STAGE 4 collection  
✓ Time series parameters (step, input_range, output_range)  
✓ API endpoints for data fetching  
✓ Fallback/error handling strategy  
✓ Runtime behavior of THIS model ONLY  

### What cache_config.json does NOT describe:
✗ Training parameters (in separate model_config.yaml)  
✗ Inference hyperparameters (in model wrapper)  
✗ General system configuration (in infrastructure config)  
✗ Other models' behavior  

---

## MLflow Artifact Hierarchy

```
Single Model = Single cache_config.json = Single RunID

  mlruns/manual_reg/848387cc60dd48ef8abec7a643493bde/
  ├── artifacts/bundle/
  │   ├── configuration/
  │   │   └── cache_config.json          ◄─ MODEL CONFIGURATION
  │   │                                     Describes XGBoost model v1.0.0
  │   │                                     STAGE 4 sources
  │   │                                     Data collection parameters
  │   │
  │   ├── models/
  │   │   └── model.pkl                  ◄─ MODEL WEIGHTS
  │   │                                     Serialized model binary
  │   │
  │   └── [other artifacts]
  │
  └── [metrics, params, tags]
```

---

## Operational Model: One Config Rule

### When Adding a New Model:

1. **Create** - New model in training pipeline
2. **Register** - Create MLflow Run with unique Run ID
3. **Artifact** - Store model.pkl + **cache_config.json**
4. **Configure** - cache_config.json describes ONLY this model's behavior
5. **Deploy** - MLflow loads model + its own cache_config.json
6. **Query** - Model uses its cache_config for data collection

### When Updating a Model:

1. **Modify** - Model code / parameters
2. **Retrain** - Create new Run with new Run ID
3. **Update** - Create new cache_config.json for new behavior
4. **Register** - New version in MLflow Registry
5. **Test** - Version-specific cache_config.json
6. **Promote** - Each production version has its config snapshot

---

## Current Model: cache_config.json Analysis

**File Location in MLflow**:
```
Run ID: 848387cc60dd48ef8abec7a643493bde
Path: artifacts/bundle/configuration/cache_config.json
Size: ~500 bytes
```

**Model Described**:
```
Name:      prophet_watt_h_AKMOLA_test
Type:      XGBoost (xgb)
Version:   1.0.0
Status:    Active
Framework: XGBoost
```

**Data Collection (STAGE 4) Configured**:
```
Active Sources:   1/3 (historical only)
Sampling:         3600 seconds (hourly)
Lookback:         168 hours (7 days)
Forecast:         24 hours ahead
Timeout:          30 seconds per API call
Retry Strategy:   3 attempts on failure
```

**Inactive Sources**:
```
Weather:  URL not configured
CMMS:     URL not configured
```

**Ready for Production**: ✓ YES
- Primary data source fully configured
- Fallback strategy defined
- Timeout and retry logic in place

---

## One Config, One Model: Benefits

```
✓ Clear Ownership        Each model owns its config
✓ Version Control        Config versioned with model
✓ Isolation             No cross-model contamination
✓ Easy Debugging        Find config specific to model
✓ Reproducibility       Config snapshot with model
✓ Rollback Support      Old model = old config behavior
✓ A/B Testing           Different models = different configs
✓ Multiple Experiments  Each experiment has own config
```

---

## Summary

**One Configuration File = One Model in MLflow**

The `cache_config.json` file:
- Lives in MLflow artifacts for a specific run
- Describes ONLY that model's runtime behavior
- Used during STAGE 4 data collection
- Version-controlled with model weights
- Loaded automatically when model is retrieved

Each model version = separate cache_config.json with its own parameters.

This ensures clarity, isolation, and reproducibility in the ML pipeline.
