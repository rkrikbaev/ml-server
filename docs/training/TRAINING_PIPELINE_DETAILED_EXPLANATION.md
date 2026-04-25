# Training Pipeline (4.2) - Detailed Step-by-Step Explanation

**Document:** Explaining section 4.2 from ТЗ_ML_Infrastructure.md  
**Date:** April 19, 2026  
**Purpose:** Deep dive into train pipeline architecture and flow

---

## Overview

The training pipeline is a 6-step process that takes a request to train a model on a specific object and produces a trained model artifact with metrics logged in MLflow.

```
Request → Collect Data → Preprocess → Train → Log → Return Results
```

---

## Step 1: Приём запроса (Request Reception)

### What Happens

The training pipeline begins when the external SCADA system sends an HTTP POST request to the `/train` endpoint.

### Request Format

```json
{
  "object_reference": "/KAZ/AKMOLA/AKMOLA/@models/P_WATT",
  "model_type": "prophet",
  "data_source_config": {
    "sources": [
      {
        "type": "rest_api",
        "url": "http://datasource.example.com/api/timeseries",
        "params": {
          "object_id": "AKMOLA_LOAD",
          "interval": "1h"
        }
      }
    ],
    "date_column": "timestamp",
    "target_column": "value",
    "freq": "H"
  },
  "train_params": {
    "changepoint_prior_scale": 0.05,
    "seasonality_mode": "multiplicative"
  }
}
```

### Key Parameters Explained

| Parameter | Type | Purpose | Example |
|-----------|------|---------|---------|
| `object_reference` | String | Unique identifier for the forecasting object | `/KAZ/AKMOLA/AKMOLA/@models/P_WATT` |
| `model_type` | String | Type of model to train | `"prophet"` or `"xgboost"` |
| `data_source_config` | Object | **"Data Passport"** - tells system where to get data | See below |
| `train_params` | Object | Model-specific hyperparameters | Varies by model type |

### Understanding "Data Passport" (data_source_config)

The `data_source_config` is crucial - it's **stored with the model** so the system knows where to get data during inference without reconfiguration.

```json
{
  "sources": [
    {
      "type": "rest_api",
      "url": "http://datasource.example.com/api/timeseries",
      "params": {
        "object_id": "AKMOLA_LOAD",
        "interval": "1h"
      }
    }
  ],
  "date_column": "timestamp",
  "target_column": "value",
  "freq": "H"
}
```

**Breakdown:**
- `sources[]` - Array of data sources (can be multiple)
  - `type` - "rest_api", "database", etc.
  - `url` - Where to fetch data from
  - `params` - Query parameters for the API
- `date_column` - Which column contains timestamps
- `target_column` - Which column contains the values to predict
- `freq` - Frequency of data ("H" = hourly, "D" = daily, etc.)

### Processing in API Layer

```python
# In main.py - POST /train endpoint
@app.post("/train")
async def train_model(request: TrainRequest) -> TrainResponse:
    # 1. Validate request schema
    # 2. Pass to pipeline
    # 3. Return results
    
    result = await train_pipeline.run(
        object_reference=request.object_reference,
        model_type=request.model_type,
        data_source_config=request.data_source_config,
        train_params=request.train_params
    )
    
    return TrainResponse(
        status="success",
        run_id=result.run_id,
        metrics=result.metrics
    )
```

---

## Step 2: Сбор данных (Data Collection)

### What Happens

Once the request is received, the system uses the `data_source_config` to fetch historical data from external REST APIs.

### The Data Loader Component

**Purpose:** Implements the logic to fetch data from external sources based on configuration.

**Key Points:**
- Works with the `data_source_config` (the "data passport")
- Can fetch from multiple sources
- Handles API authentication and retries
- Returns a pandas DataFrame

### Data Collection Flow

```python
# In api/data/loader.py

class DataLoader:
    def load(self, config: DataSourceConfig, 
             start_date: datetime, 
             end_date: datetime) -> pd.DataFrame:
        """
        Load data for training based on config
        
        config: The "data passport" telling us where to get data
        start_date: Historical data starts from
        end_date: Historical data ends at
        """
        
        all_data = []
        
        # Step 2.1: Iterate through configured data sources
        for source in config.sources:
            
            if source["type"] == "rest_api":
                # Step 2.2: Build API request
                url = source["url"]
                params = {
                    **source["params"],
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat()
                }
                
                # Step 2.3: Make HTTP request to external API
                response = httpx.get(url, params=params, timeout=30)
                response.raise_for_status()
                
                # Step 2.4: Parse response
                data = response.json()
                
                # Step 2.5: Convert to DataFrame
                df = pd.DataFrame(data)
                all_data.append(df)
        
        # Step 2.6: Combine all data sources
        combined_df = pd.concat(all_data, axis=1)
        
        return combined_df
```

### Example: What External API Returns

**Request:**
```
GET http://datasource.example.com/api/timeseries?
    object_id=AKMOLA_LOAD&
    interval=1h&
    start_date=2025-01-01&
    end_date=2026-04-01
```

**Response:**
```json
[
  {
    "timestamp": "2025-01-01T00:00:00Z",
    "value": 1234.5
  },
  {
    "timestamp": "2025-01-01T01:00:00Z",
    "value": 1198.2
  },
  ...
  {
    "timestamp": "2026-04-01T23:00:00Z",
    "value": 1456.8
  }
]
```

### Resulting DataFrame

After data collection, you have:

```
        timestamp      value
0 2025-01-01 00:00  1234.5
1 2025-01-01 01:00  1198.2
2 2025-01-01 02:00  1201.3
...
N 2026-04-01 23:00  1456.8
```

**Total rows:** ~15,000 hours (365 days × 24 hours + training period)

### Error Handling

```python
# Handle various failure scenarios
try:
    response = httpx.get(url, params=params, timeout=30)
except httpx.ConnectError:
    logger.error(f"Cannot connect to {url}")
    raise
except httpx.TimeoutException:
    logger.error(f"Request to {url} timed out")
    raise
except httpx.HTTPStatusError as e:
    logger.error(f"API returned {e.response.status_code}: {e.response.text}")
    raise
```

---

## Step 3: Предобработка данных (Data Preprocessing)

### What Happens

Raw data is cleaned, validated, and prepared for model training.

### Preprocessing Steps

```python
# In api/forecast/preprocess.py

def preprocess_data(df: pd.DataFrame, config: DataSourceConfig) -> pd.DataFrame:
    """
    Preprocess training data
    """
    
    # Step 3.1: Extract relevant columns
    df = df[[config.date_column, config.target_column]].copy()
    print("✓ Extracted columns")
    
    # Step 3.2: Sort by date (ensure chronological order)
    df = df.sort_values(config.date_column)
    print("✓ Sorted by date")
    
    # Step 3.3: Remove duplicates
    df = df.drop_duplicates(subset=[config.date_column])
    print("✓ Removed duplicates")
    
    # Step 3.4: Validate timestamps
    df[config.date_column] = pd.to_datetime(df[config.date_column])
    print("✓ Validated timestamps")
    
    # Step 3.5: Check for missing values
    missing_count = df.isnull().sum().sum()
    if missing_count > 0:
        logger.warning(f"Found {missing_count} missing values")
        # Handle missing values
        df = df.fillna(method='ffill')  # Forward fill
        df = df.fillna(method='bfill')  # Backward fill
    print(f"✓ Handled {missing_count} missing values")
    
    # Step 3.6: Remove outliers (optional)
    Q1 = df[config.target_column].quantile(0.25)
    Q3 = df[config.target_column].quantile(0.75)
    IQR = Q3 - Q1
    df = df[
        (df[config.target_column] >= Q1 - 1.5*IQR) &
        (df[config.target_column] <= Q3 + 1.5*IQR)
    ]
    print("✓ Removed outliers")
    
    # Step 3.7: Feature engineering (if needed)
    # For Prophet: rename to required format
    if config.model_type == "prophet":
        df = df.rename(columns={
            config.date_column: 'ds',
            config.target_column: 'y'
        })
    print("✓ Applied feature engineering")
    
    # Step 3.8: Validate final dataset
    assert len(df) > 100, "Not enough data for training"
    assert df.isnull().sum().sum() == 0, "Still has missing values"
    print("✓ Final validation passed")
    
    return df
```

### Preprocessing Checks

| Check | Purpose | Example |
|-------|---------|---------|
| Column extraction | Keep only needed columns | Keep only `timestamp` and `value` |
| Sort by date | Ensure chronological order | Dates from oldest to newest |
| Remove duplicates | Handle API errors | If same timestamp appears twice |
| Validate timestamps | Ensure correct format | Convert to ISO format |
| Handle missing values | Fill gaps | Forward-fill then backward-fill |
| Outlier detection | Remove anomalies | Use IQR method |
| Rename columns | Format for model | Prophet expects `ds` and `y` |

### Example Transformation

**Before:**
```
timestamp               value    extra_col
2025-01-01 00:00      1234.5   "info"
2025-01-01 00:00      1234.5   "duplicate"
2025-01-01 02:00      NaN      None        ← Missing
2025-01-01 03:00      999999.0 "outlier"
2025-01-01 04:00      1201.3   "info"
```

**After:**
```
ds                   y
2025-01-01 00:00    1234.5
2025-01-01 01:00    1234.5   ← Forward-filled missing
2025-01-01 02:00    1234.5   ← Forward-filled missing
2025-01-01 03:00    1234.5   ← Outlier removed/imputed
2025-01-01 04:00    1201.3
```

---

## Step 4: Обучение модели (Model Training)

### What Happens

The cleaned data is used to train the specified model type (Prophet or XGBoost).

### Training by Model Type

#### Option A: Prophet Model

```python
# In api/forecast/train.py

from prophet import Prophet

def train_prophet_model(df: pd.DataFrame, 
                       train_params: dict) -> Prophet:
    """
    Train Prophet model
    
    df: Preprocessed DataFrame with 'ds' and 'y' columns
    train_params: Hyperparameters from request
    """
    
    # Step 4.1.1: Create Prophet instance with parameters
    model = Prophet(
        changepoint_prior_scale=train_params.get('changepoint_prior_scale', 0.05),
        seasonality_mode=train_params.get('seasonality_mode', 'multiplicative'),
        yearly_seasonality=train_params.get('yearly_seasonality', True),
        weekly_seasonality=train_params.get('weekly_seasonality', True),
        daily_seasonality=train_params.get('daily_seasonality', False),
        interval_width=train_params.get('interval_width', 0.95)
    )
    print("✓ Created Prophet instance")
    
    # Step 4.1.2: Fit model to historical data
    # This is where the actual learning happens
    with suppress_prophet_warnings():
        model.fit(df)
    print("✓ Fitted model to data")
    
    # Step 4.1.3: Generate future dataframe for validation
    future = model.make_future_dataframe(periods=336)  # 2 weeks
    print("✓ Created future dataframe")
    
    # Step 4.1.4: Make predictions on future
    forecast = model.predict(future)
    print("✓ Generated forecast")
    
    return model, forecast
```

**What Prophet Does Internally:**
- Decomposes time series into trend, seasonality, and holidays
- Estimates trend changepoints
- Learns seasonal patterns
- Creates confidence intervals

#### Option B: XGBoost Model

```python
# In api/forecast/train.py

import xgboost as xgb
from sklearn.preprocessing import StandardScaler

def train_xgboost_model(df: pd.DataFrame, 
                       train_params: dict) -> xgb.XGBRegressor:
    """
    Train XGBoost model
    
    df: Preprocessed DataFrame with 'y' column (already renamed from target_column)
    train_params: Hyperparameters from request
    """
    
    # Step 4.2.1: Create lagged features
    lags = train_params.get('lags', [1, 2, 3, 24, 48, 168])
    X_list = []
    
    for lag in lags:
        # Create feature: y(t-lag)
        X_list.append(df['y'].shift(lag).values)
    
    X = np.column_stack(X_list)
    y = df['y'].values[max(lags):]  # Remove NaN rows
    X = X[max(lags):]
    print(f"✓ Created lagged features (shape: {X.shape})")
    
    # Step 4.2.2: Split into train/test
    split_idx = int(len(X) * 0.8)
    X_train, X_test = X[:split_idx], X[split_idx:]
    y_train, y_test = y[:split_idx], y[split_idx:]
    print(f"✓ Train: {len(X_train)} samples, Test: {len(X_test)} samples")
    
    # Step 4.2.3: Create and configure XGBoost model
    model = xgb.XGBRegressor(
        n_estimators=train_params.get('n_estimators', 200),
        max_depth=train_params.get('max_depth', 6),
        learning_rate=train_params.get('learning_rate', 0.05),
        subsample=train_params.get('subsample', 0.8),
        colsample_bytree=train_params.get('colsample_bytree', 0.8)
    )
    print("✓ Created XGBoost model")
    
    # Step 4.2.4: Train the model
    model.fit(
        X_train, y_train,
        eval_set=[(X_test, y_test)],
        verbose=False
    )
    print("✓ Trained model")
    
    return model
```

**What XGBoost Does:**
- Uses historical values as features (lag features)
- Builds ensemble of decision trees
- Learns non-linear patterns
- Optimizes for regression loss

### Model Training Outputs

**Prophet returns:**
- Fitted model object (with trend, seasonality, changepoints)
- Forecast dataframe (with predictions and confidence intervals)

**XGBoost returns:**
- Fitted model object (with trained trees)
- Feature importance scores

---

## Step 5: Логирование в MLflow (MLflow Logging)

### What Happens

All model metadata, parameters, metrics, and the model artifact are logged to MLflow.

### MLflow Structure

```
Experiment: /KAZ/AKMOLA/P_WATT
    └── Run: prophet_watt_h_AKMOLA_load (run_id: abc123def456)
        ├── Tags:
        │   ├── data_source_config: "{...}"
        │   ├── object_reference: "/KAZ/AKMOLA/..."
        │   └── model_type: "prophet"
        ├── Params:
        │   ├── changepoint_prior_scale: 0.05
        │   ├── seasonality_mode: "multiplicative"
        │   └── ...
        ├── Metrics:
        │   ├── mae: 45.2
        │   ├── mape: 3.1
        │   └── rmse: 62.8
        └── Artifacts:
            └── model/  ← Serialized model file
```

### MLflow Logging Code

```python
# In api/forecast/train.py

import mlflow
import json

def log_to_mlflow(model, 
                  model_type: str,
                  object_reference: str,
                  data_source_config: dict,
                  train_params: dict,
                  metrics: dict):
    """
    Log training run to MLflow
    """
    
    # Step 5.1: Start MLflow run
    with mlflow.start_run(run_name=f"{model_type}_run_{datetime.now().isoformat()}"):
        
        print("✓ Started MLflow run")
        
        # Step 5.2: Set tags (metadata)
        # Tags are searchable strings that describe the run
        mlflow.set_tag("object_reference", object_reference)
        mlflow.set_tag("model_type", model_type)
        mlflow.set_tag("data_source_config", json.dumps(data_source_config))
        mlflow.set_tag("run_date", datetime.now().isoformat())
        print("✓ Set tags")
        
        # Step 5.3: Log parameters
        # Parameters are the inputs to the training (hyperparameters)
        for param_name, param_value in train_params.items():
            mlflow.log_param(param_name, param_value)
        print(f"✓ Logged {len(train_params)} parameters")
        
        # Step 5.4: Log metrics
        # Metrics are numbers measuring model quality
        for metric_name, metric_value in metrics.items():
            mlflow.log_metric(metric_name, metric_value)
        print(f"✓ Logged {len(metrics)} metrics")
        
        # Step 5.5: Log model artifact
        # The model artifact is the serialized trained model
        if model_type == "prophet":
            mlflow.prophet.log_model(
                model,
                artifact_path="model",
                registered_model_name=f"{object_reference}_prophet"
            )
            print("✓ Logged Prophet model artifact")
            
        elif model_type == "xgboost":
            mlflow.xgboost.log_model(
                model,
                artifact_path="model",
                registered_model_name=f"{object_reference}_xgboost"
            )
            print("✓ Logged XGBoost model artifact")
        
        # Step 5.6: Get run ID
        run_id = mlflow.active_run().info.run_id
        print(f"✓ Run ID: {run_id}")
        
        return run_id
```

### Metrics Calculation

Before logging, we calculate model quality metrics:

```python
def calculate_metrics(y_actual: np.array, 
                     y_predicted: np.array) -> dict:
    """
    Calculate model quality metrics
    """
    
    mae = np.mean(np.abs(y_actual - y_predicted))
    mape = np.mean(np.abs((y_actual - y_predicted) / y_actual)) * 100
    rmse = np.sqrt(np.mean((y_actual - y_predicted) ** 2))
    
    return {
        "mae": mae,      # Mean Absolute Error
        "mape": mape,    # Mean Absolute Percentage Error
        "rmse": rmse     # Root Mean Squared Error
    }
```

### Data Passport Storage (Critical!)

Notice that `data_source_config` is stored as a **tag** in MLflow:

```python
mlflow.set_tag("data_source_config", json.dumps(data_source_config))
```

**Why this matters:** During inference, the system retrieves this tag and knows where to get data WITHOUT needing new configuration!

---

## Step 6: Возврат результатов (Return Results)

### What Happens

The training pipeline returns the results to the API, which sends them back to the SCADA system.

### Return Data Structure

```python
# In api/forecast/train.py

@dataclass
class TrainResponse:
    """Response from training pipeline"""
    status: str          # "success" or "error"
    run_id: str         # MLflow run ID (e.g., "abc123def456")
    model_id: str       # Registered model name
    metrics: dict       # {"mae": 45.2, "mape": 3.1, "rmse": 62.8}
    timestamp: str      # ISO format datetime
    message: str        # Success/error message
```

### API Response Example

```json
{
  "status": "success",
  "run_id": "abc123def456",
  "model_id": "prophet_watt_h_AKMOLA_@regions_Akmola_load",
  "metrics": {
    "mae": 45.2,
    "mape": 3.1,
    "rmse": 62.8
  },
  "timestamp": "2026-04-17T14:30:00Z",
  "message": "Model trained successfully"
}
```

### Complete Request/Response Cycle

```
SCADA System                              ml-server
    │
    ├─ POST /train                        FastAPI endpoint receives
    │  (with config) ─────────────────────────►│
    │                                         │
    │                                         ├─ Data collection
    │                                         │  (REST API calls)
    │                                         │
    │                                         ├─ Preprocessing
    │                                         │
    │                                         ├─ Training
    │                                         │
    │                                         ├─ MLflow logging
    │                                         │
    │◄─────────────────────── TrainResponse
    │  (run_id + metrics)                    │
    │
```

---

## Complete Pipeline Flow Diagram

```
╔════════════════════════════════════════════════════════════════════════╗
║                        TRAIN PIPELINE COMPLETE FLOW                    ║
╚════════════════════════════════════════════════════════════════════════╝

┌──────────────────────────────────────────────────────────────────────┐
│ STEP 1: REQUEST RECEPTION                                            │
│ Input: POST /train with                                              │
│   • object_reference: "/KAZ/AKMOLA/AKMOLA/@models/P_WATT"          │
│   • model_type: "prophet"                                            │
│   • data_source_config: {...}  ← "Data Passport"                    │
│   • train_params: {...}                                              │
└──────────────────────┬───────────────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────────────┐
│ STEP 2: DATA COLLECTION                                              │
│ • Parse data_source_config                                           │
│ • Make HTTP requests to external APIs                                │
│ • Example: GET http://datasource/api/timeseries?object_id=...      │
│ • Collect: {"timestamp": "2025-01-01...", "value": 1234.5}         │
│ • Result: Raw DataFrame with 15,000+ rows                           │
└──────────────────────┬───────────────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────────────┐
│ STEP 3: PREPROCESSING                                                │
│ • Extract columns (timestamp, value)                                 │
│ • Sort chronologically                                               │
│ • Remove duplicates                                                  │
│ • Handle missing values (forward/backward fill)                      │
│ • Remove outliers (IQR method)                                       │
│ • Rename columns for model (e.g., → "ds", "y" for Prophet)          │
│ • Result: Clean DataFrame ready for training                        │
└──────────────────────┬───────────────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────────────┐
│ STEP 4: MODEL TRAINING                                               │
│                                                                       │
│ If model_type = "prophet":                                           │
│   • Create Prophet(seasonality_mode='multiplicative', ...)          │
│   • Call model.fit(df)  ← Learn trend, seasonality                  │
│   • Create future dataframe                                          │
│   • Call model.predict(future)  ← Generate forecast                 │
│                                                                       │
│ If model_type = "xgboost":                                           │
│   • Create lag features (t-1, t-2, t-3, t-24, ...)                 │
│   • Split train/test (80/20)                                        │
│   • Train XGBRegressor with parameters                              │
│   • Calculate predictions on test set                               │
│                                                                       │
│ Result: Trained model object in memory                              │
└──────────────────────┬───────────────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────────────┐
│ STEP 5: MLflow LOGGING                                               │
│ • Create MLflow run for experiment "/KAZ/AKMOLA/P_WATT"            │
│ • Set tags:                                                          │
│   - object_reference: "/KAZ/AKMOLA/..."                             │
│   - model_type: "prophet"                                            │
│   - data_source_config: "{...}"  ← STORES DATA PASSPORT!            │
│ • Log parameters: changepoint_prior_scale=0.05, ...                 │
│ • Calculate metrics: MAE=45.2, MAPE=3.1, RMSE=62.8                  │
│ • Log metrics to MLflow                                              │
│ • Serialize model → .pkl or .joblib file                            │
│ • Upload model artifact to mlflow_data/artifacts/                   │
│ • Get run_id: "abc123def456"                                         │
│                                                                       │
│ MLflow Storage Structure:                                            │
│ mlflow_data/                                                         │
│ ├── mlflow.db  ← SQLite database with all metadata                   │
│ └── artifacts/                                                       │
│     └── <experiment>/<run_id>/artifacts/model  ← Model file         │
└──────────────────────┬───────────────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────────────┐
│ STEP 6: RETURN RESULTS                                               │
│ Return TrainResponse:                                                │
│ {                                                                    │
│   "status": "success",                                               │
│   "run_id": "abc123def456",                                          │
│   "model_id": "prophet_watt_h_AKMOLA_@regions_Akmola_load",         │
│   "metrics": {                                                       │
│     "mae": 45.2,                                                     │
│     "mape": 3.1,                                                     │
│     "rmse": 62.8                                                     │
│   },                                                                 │
│   "timestamp": "2026-04-17T14:30:00Z"                                │
│ }                                                                    │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Key Concepts Summary

### 1. Data Passport (data_source_config)

**Most important insight:** The `data_source_config` is stored in MLflow as a tag. This means:

- **At Training Time:** "Here's where to get the training data from"
- **At Inference Time:** System retrieves this config and knows where to get prediction data
- **No Reconfiguration Needed:** Same config used for both training and inference

### 2. Why MLflow is Used

```python
# Without MLflow
model.pkl → Saved locally
# Later: Where did this model come from? What were the parameters? What's the data source?
# UNKNOWN! ❌

# With MLflow
Run abc123 {
    tags: {object_reference, model_type, data_source_config},
    params: {changepoint_prior_scale, seasonality_mode, ...},
    metrics: {mae: 45.2, mape: 3.1, ...},
    artifacts: {model.pkl}
}
# Now we know EVERYTHING! ✅
```

### 3. Data Flow

```
External REST API
        │
        ▼
   Raw Data (15,000+ rows)
        │
        ▼
  Preprocessing (clean, validate, fill)
        │
        ▼
  Clean Data (ready for training)
        │
        ├────────────────────┬──────────────────┐
        │                    │                  │
        ▼                    ▼                  ▼
    Prophet           XGBoost            Custom Model
   (seasonal)      (tabular features)     (adapters)
        │                    │                  │
        └────────────────────┴──────────────────┘
                       │
                       ▼
            MLflow Logging (all metadata)
                       │
                       ▼
            Return success + run_id + metrics
```

---

## Practical Example: Training AKMOLA Load Forecast

### Step by Step Walkthrough

**Request arrives:**
```json
{
  "object_reference": "/KAZ/AKMOLA/AKMOLA/@models/P_WATT",
  "model_type": "prophet",
  "data_source_config": {
    "sources": [{
      "type": "rest_api",
      "url": "http://data.example.com/api/timeseries",
      "params": {"object_id": "AKMOLA_LOAD", "interval": "1h"}
    }],
    "date_column": "timestamp",
    "target_column": "value",
    "freq": "H"
  },
  "train_params": {
    "changepoint_prior_scale": 0.05,
    "seasonality_mode": "multiplicative"
  }
}
```

**Step 1-2: Data Collection**
```
GET http://data.example.com/api/timeseries?object_id=AKMOLA_LOAD&interval=1h
Response: 15,104 rows of data from 2024-01-01 to 2026-04-17
```

**Step 3: Preprocessing**
```
15,104 rows → Validated → Cleaned → 15,087 clean rows
```

**Step 4: Training**
```
Prophet learns:
  - Trend: Gradual increase in load
  - Weekly seasonality: Lower on weekends
  - Yearly seasonality: Higher in winter/summer
  - Changepoints: Major changes at specific dates
```

**Step 5: MLflow Logging**
```
Experiment: /KAZ/AKMOLA/P_WATT
  Run: prophet_watt_h_AKMOLA_load_20260417_143000
    Tags:
      - object_reference: /KAZ/AKMOLA/AKMOLA/@models/P_WATT
      - model_type: prophet
      - data_source_config: {sources: [...]}  ← STORED FOR LATER!
    Params:
      - changepoint_prior_scale: 0.05
      - seasonality_mode: multiplicative
    Metrics:
      - mae: 45.2
      - mape: 3.1
      - rmse: 62.8
    Artifacts:
      - model.pkl (2.3 MB)
```

**Step 6: Response**
```json
{
  "status": "success",
  "run_id": "abc123def456",
  "model_id": "prophet_watt_h_AKMOLA_@regions_Akmola_load",
  "metrics": {"mae": 45.2, "mape": 3.1, "rmse": 62.8},
  "timestamp": "2026-04-17T14:30:00Z"
}
```

---

## Connection to Inference Pipeline

Once a model is trained and stored in MLflow, it can be used for predictions:

```
PREDICT REQUEST arrives:
  "model_id": "prophet_watt_h_AKMOLA_@regions_Akmola_load"
        │
        ▼
  Find run in MLflow with this model_id
        │
        ▼
  Retrieve tag: "data_source_config" (the data passport!)
        │
        ▼
  Use data_source_config to collect PREDICTION DATA
  (from same external API, no reconfiguration needed!)
        │
        ▼
  Load trained model artifact from MLflow
        │
        ▼
  Generate forecast
        │
        ▼
  Return results
```

---

## Error Handling Scenarios

### Scenario 1: Data Source Unavailable

```
Step 2 Fails: Cannot connect to external API
│
└─► Exception caught
│
└─► Log error: "Data source unreachable: timeout after 30s"
│
└─► Return 503 Service Unavailable
    {
      "status": "error",
      "message": "Failed to collect training data",
      "details": "Connection to http://data.example.com timed out"
    }
```

### Scenario 2: Insufficient Data

```
Step 3 Fails: Only 50 rows of data (less than 100 minimum)
│
└─► Exception caught
│
└─► Log error: "Insufficient data for training"
│
└─► Return 400 Bad Request
    {
      "status": "error",
      "message": "Cannot train model",
      "details": "Need at least 100 data points, got 50"
    }
```

### Scenario 3: Model Training Fails

```
Step 4 Fails: Prophet fails to converge
│
└─► Exception caught
│
└─► Log error: "Prophet failed to fit model"
│
└─► Return 500 Internal Server Error
    {
      "status": "error",
      "message": "Model training failed",
      "details": "Prophet: failed to converge after 1000 iterations"
    }
```

---

## Performance Characteristics

| Step | Typical Duration | Bottleneck | Notes |
|------|------------------|-----------|-------|
| 1. Request | < 1ms | Network | Fast |
| 2. Data Collection | 5-30s | External API | Main bottleneck |
| 3. Preprocessing | < 5s | CPU (pandas) | Linear with data size |
| 4. Training | 1-10 min | CPU/RAM | Depends on data volume |
| 5. MLflow Logging | 5-30s | Disk I/O | Artifact upload |
| 6. Return Results | < 1ms | Network | Fast |
| **Total** | **10-15 min** | Step 4 | For 1+ year of hourly data |

---

## Summary

The training pipeline (Section 4.2) is a carefully orchestrated 6-step process that:

1. **Receives a request** with configuration specifying which object and where to get data
2. **Collects historical data** from external REST APIs (the "data passport" determines this)
3. **Cleans and validates** data to ensure quality
4. **Trains a model** (Prophet or XGBoost) on the historical data
5. **Logs everything** to MLflow (metadata, parameters, metrics, and model artifact)
6. **Returns success** with run_id and metrics to the SCADA system

The most important insight: **The data_source_config (data passport) is stored in MLflow**, so during inference, the system automatically knows where to get prediction data without any reconfiguration!

