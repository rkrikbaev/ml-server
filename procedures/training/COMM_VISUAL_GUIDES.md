# Training Pipeline - Visual Guides & Diagrams

**Purpose:** Visual reference for understanding the training pipeline flow  
**Format:** ASCII diagrams, flowcharts, and structured visualizations

> Implementation note: `POST /train` in this guide is a target workflow and is currently **not implemented** in the active codebase.

---

## 1. Overall Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                           SCADA SYSTEM                              │
│                                                                     │
│  ┌────────────────────────────────────────────────────────────┐     │
│  │ POST /train with:                                          │     │
│  │  • object_reference: "/KAZ/AKMOLA/AKMOLA/@models/P_WATT"   │     │
│  │  • model_type: "prophet"                                   │     │
│  │  • data_source_config: {...}                               │     │
│  │  • train_params: {...}                                     │     │
│  └────────────────────────────────────────────────────────────┘     │
└──────────────────────────┬──────────────────────────────────────────┘
                           │ HTTP Request
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                           ML-SERVER                                 │
│                                                                      │
│ ┌────────────────────────────────────────────────────────────────┐ │
│ │  API Layer (FastAPI)                                           │ │
│ │  POST /train endpoint                                          │ │
│ └────────────┬─────────────────────────────────────────────────┘ │
│              │                                                    │
│              ▼                                                    │
│ ┌────────────────────────────────────────────────────────────────┐ │
│ │  Train Pipeline Manager                                        │ │
│ │  1. Request reception ✓                                        │ │
│ │  2. Data collection → Data Loader → External REST APIs        │ │
│ │  3. Preprocessing → Validation & Cleaning                     │ │
│ │  4. Model Training → Prophet/XGBoost                          │ │
│ │  5. MLflow Logging → Store metadata & artifacts               │ │
│ │  6. Return Results → TrainResponse                            │ │
│ └────────────┬─────────────────────────────────────────────────┘ │
│              │                                                    │
│              ├───────────────────┬────────────────────┐           │
│              │                   │                    │           │
│              ▼                   ▼                    ▼           │
│        ┌──────────┐        ┌──────────┐      ┌────────────────┐ │
│        │ External │        │ MLflow   │      │   Redis        │ │
│        │REST APIs │        │ (tracks) │      │   (optional)   │ │
│        └──────────┘        └──────────┘      └────────────────┘ │
│                                                                   │
│ Storage:                                                          │
│ ├── mlflow_data/mlflow.db (metadata)                             │
│ └── mlflow_data/artifacts/ (model files)                         │
└──────────────────────────────────────────────────────────────────┘
                           │ HTTP Response
                           ▼
┌──────────────────────────────────────────────────────────────────────┐
│                      SCADA SYSTEM (Response)                         │
│                                                                       │
│  {                                                                    │
│    "status": "success",                                              │
│    "run_id": "abc123def456",                                        │
│    "metrics": {"mae": 45.2, "mape": 3.1, "rmse": 62.8}             │
│  }                                                                    │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 2. Request/Response Flow

```
SCADA SYSTEM                           ML-SERVER (Train Pipeline)
│                                      │
├──────► POST /train                   │
│        (object_reference             │
│         model_type                   │
│         data_source_config)          │
│                                      ├─► [STEP 1] Request Reception
│                                      │   ✓ Parse JSON
│                                      │   ✓ Validate schema
│                                      │
│                                      ├─► [STEP 2] Data Collection
│                                      │   ├─ Get data_source_config
│                                      │   ├─ For each source in config:
│                                      │   │  ├─ Parse URL
│                                      │   │  ├─ Build params
│                                      │   │  └─ HTTP GET request
│                                      │   └─ Combine all data
│                                      │
│                                      ├─► [STEP 3] Preprocessing
│                                      │   ├─ Extract columns
│                                      │   ├─ Sort by date
│                                      │   ├─ Remove duplicates
│                                      │   ├─ Handle missing values
│                                      │   ├─ Remove outliers
│                                      │   └─ Rename columns
│                                      │
│                                      ├─► [STEP 4] Training
│                                      │   ├─ If prophet:
│                                      │   │  ├─ Create Prophet()
│                                      │   │  ├─ model.fit(df)
│                                      │   │  └─ model.predict()
│                                      │   ├─ If xgboost:
│                                      │   │  ├─ Create lags
│                                      │   │  ├─ Split train/test
│                                      │   │  └─ model.fit()
│                                      │
│                                      ├─► [STEP 5] MLflow Logging
│                                      │   ├─ mlflow.start_run()
│                                      │   ├─ mlflow.set_tag()
│                                      │   ├─ mlflow.log_param()
│                                      │   ├─ mlflow.log_metric()
│                                      │   ├─ mlflow.<model>.log_model()
│                                      │   └─ Get run_id
│                                      │
│                                      ├─► [STEP 6] Return Results
│                                      │   └─ TrainResponse
│                                      │
│◄─────── Return Response              │
│         (run_id + metrics)           │
```

---

## 3. Data Passport (data_source_config) Structure

```
data_source_config
│
├─ sources[] (array of data sources)
│  │
│  ├─ [0] First source
│  │  ├─ type: "rest_api"
│  │  ├─ url: "http://datasource.example.com/api/timeseries"
│  │  └─ params:
│  │     ├─ object_id: "AKMOLA_LOAD"
│  │     └─ interval: "1h"
│  │
│  ├─ [1] Second source (optional)
│  │  ├─ type: "rest_api"
│  │  ├─ url: "http://other-source.com/api"
│  │  └─ params: {...}
│  │
│  └─ [n] ...
│
├─ date_column: "timestamp"  ← Which column has dates
├─ target_column: "value"    ← Which column to predict
└─ freq: "H"                 ← Data frequency (H=hourly, D=daily)

Purpose:
┌─────────────────────────────────────────────────────────┐
│ "Data Passport" tells the system:                       │
│ • WHERE to get data (REST API endpoints)               │
│ • WHAT data to extract (column names)                  │
│ • HOW OFTEN the data comes (frequency)                 │
│                                                         │
│ Stored in MLflow during training, so during inference  │
│ the system KNOWS WHERE TO GET DATA automatically! ✓   │
└─────────────────────────────────────────────────────────┘
```

---

## 4. Step-by-Step Data Transformation

```
STEP 2: DATA COLLECTION
═══════════════════════════════════════════════════════════

External API                      Collected Data (DataFrame)
────────────────────────────────────────────────────────────
GET /api/timeseries        ────►   timestamp           value
  object_id=AKMOLA_LOAD           2025-01-01 00:00    1234.5
  interval=1h                     2025-01-01 01:00    1198.2
  start_date=2025-01-01           2025-01-01 02:00    1201.3
  end_date=2026-04-17             ...
                                  2026-04-17 23:00    1456.8
Response: JSON array                (15,104 rows)


STEP 3: PREPROCESSING
═══════════════════════════════════════════════════════════

Raw Data                      Clean Data (Ready for Model)
────────────────────────────────────────────────────────────
timestamp        value         ds                   y
2025-01-01...    1234.5   ──►  2025-01-01 00:00    1234.5
2025-01-01...    1198.2   ──►  2025-01-01 01:00    1198.2
2025-01-01...    NaN      ──►  2025-01-01 02:00    1198.2  ← filled
2025-01-01...    1234.5   ──►  2025-01-01 03:00    1234.5  ← removed dup
2025-01-01...    999999   ──►  2025-01-01 04:00    1201.3  ← fixed outlier
...

Changes Applied:
✓ Extracted: [timestamp, value]
✓ Sorted: By date (oldest → newest)
✓ Duplicates: Removed
✓ Missing: Forward-filled then backward-filled
✓ Outliers: Detected and imputed
✓ Renamed: timestamp→ds, value→y
✓ Validated: No nulls remain (15,087 rows)


STEP 4: MODEL TRAINING
═══════════════════════════════════════════════════════════

Prophet Model              XGBoost Model
────────────────────────────────────────────────────────────

Clean Data                 Clean Data
    │                           │
    ▼                           ▼
Prophet()              Create Lag Features
    │                       │
    ├─ Trend                ├─ y(t-1), y(t-2)
    │  (gradual increase)   ├─ y(t-3), y(t-24)
    │                       ├─ y(t-48), y(t-168)
    ├─ Seasonality          │
    │  (weekly, yearly)     ├─ Split: 80% train / 20% test
    │                       │
    ├─ Changepoints         ├─ Create XGBRegressor
    │  (major changes)      │
    │                       ├─ Fit on training data
    └─ model.fit()          │
       │                    └─ model.fit()
       ▼                       │
    Fitted Model           Fitted Model
    (learned patterns)     (learned tree ensemble)


STEP 5: MLFLOW LOGGING
═══════════════════════════════════════════════════════════

Trained Model          MLflow Run            MLflow Storage
──────────────────────────────────────────────────────────
Model object    ──►    Run: abc123def456     Backend DB:
  + params             │                     sqlite:///mlflow.db
  + metrics            ├─ Tags:              │
                       │  • object_ref       └─ Stores all metadata
                       │  • model_type
                       │  • data_source_cfg  Artifact Storage:
                       │
                       ├─ Params:            mlflow_data/artifacts/
                       │  • changepoint: 0.05│
                       │  • seasonality: mult│ ├─ abc123def456/
                       │                     │ │  └─ bundle/
                       ├─ Metrics:           │ │     ├─ model/ (serialized payload)
                       │  • mae: 45.2        │ │     ├─ metadata.yaml
                       │                     │ │     ├─ configuration/cache_config.json
                       │  • mape: 3.1        │ │     └─ ...
                       │  • rmse: 62.8       │ │
                       │                     │ └─ other-runs/
                       ├─ Artifacts:
                       │  • bundle/model
                       │  • bundle/configuration/cache_config.json
                       │
                       └─ Stored until retrieved

KEY POINT: data_source_config STORED AS TAG
This means during inference, system knows where to get data! ✓
```

---

## 5. Data Flow During Training

```
┌────────────────────────────────────────────────────────────────┐
│                        TRAINING PIPELINE                        │
│                        DATA FLOW DIAGRAM                        │
└────────────────────────────────────────────────────────────────┘

                    External REST APIs
                           │
                    (configured in          
                     data_source_config)
                           │
                           ▼
                    ┌──────────────┐
         ┌──────────┤ Data Loader  ├──────────┐
         │          └──────────────┘          │
         │                                    │
         ▼                                    ▼
    ┌─────────────┐                   ┌─────────────┐
    │   Request   │                   │   Response  │
    │   Handler   │                   │   Builder   │
    └──────┬──────┘                   └────▲────────┘
           │                                │
    [STEP 1]                           [STEP 6]
  Request                           Return Results
 Reception                               │
           │                            │
           ├────────────────────────────┤
           │                            │
           ▼                            │
    ┌──────────────────┐                │
    │ Validate Request │                │
    │  & Schema        │                │
    └────────┬─────────┘                │
             │                          │
    [STEP 2] │                          │
 Data        │                          │
Collection  │                          │
             ▼                          │
    ┌──────────────────┐                │
    │  Data Collector  │                │
    │  (from APIs)     │                │
    └────────┬─────────┘                │
             │                          │
    [STEP 3] │                          │
Preprocessing│                          │
             ▼                          │
    ┌──────────────────┐                │
    │  Preprocessor    │                │
    │  • Clean         │                │
    │  • Validate      │                │
    │  • Rename        │                │
    └────────┬─────────┘                │
             │                          │
    [STEP 4] │                          │
Training     │                          │
             ▼                          │
    ┌──────────────────┐                │
    │ Model Trainer    │◄───────────────┤
    │ • Prophet        │                │
    │ • XGBoost        │                │
    └────────┬─────────┘                │
             │                          │
    [STEP 5] │                          │
MLflow       │                          │
Logging      ▼                          │
    ┌──────────────────┐                │
    │  MLflow Client   │                │
    │  • start_run()   │                │
    │  • set_tag()     │                │
    │  • log_metric()  │                │
    │  • log_model()   │                │
    └────────┬─────────┘                │
             │                          │
             ├──────────────────────────┘
             │
             ▼
    ┌──────────────────────┐
    │ MLflow Backend Store │
    │ (SQLite DB)          │
    │ mlflow_data/         │
    │  └─ mlflow.db        │
    └──────────────────────┘
             │
             ├─────────────────────────┐
             │                         │
             ▼                         ▼
    ┌──────────────────┐    ┌──────────────────┐
    │ Artifact Storage │    │  Get run_id &    │
    │ mlflow_data/     │    │  Return Results  │
    │  artifacts/      │    │  to API Response │
    │   ├─ abc123/     │    │                  │
    │   │  └─ model/   │    └──────────────────┘
    │   │     (model files)        │
    │   │  └─ configuration/cache_config.json
    │   │                          │
    │   └─ ...         │           │
    └──────────────────┘           │
                                  [STEP 6]
                                 Response
                                  Sent to
                                  SCADA
```

---

## 6. State Transitions During Training

```
REQUEST RECEIVED
       │
       ▼
    ╔═══════════════════════════════════════╗
    ║ State: VALIDATING                     ║
    ║ - Parse JSON                          ║
    ║ - Check schema                        ║
    ║ Status: 🟡 In Progress                ║
    ╚═══════════════════════════════════════╝
       │
       ├─ Validation Failed? → Return 422 ❌
       │
       ▼
    ╔═══════════════════════════════════════╗
    ║ State: COLLECTING DATA                ║
    ║ - Call external APIs                  ║
    ║ - Parse responses                     ║
    ║ Status: 🟡 In Progress                ║
    ║ Duration: 5-30 seconds                ║
    ╚═══════════════════════════════════════╝
       │
      ├─ Connection Failed? → Return 503 ❌
      ├─ Timeout? → Return 503 ❌
       │
       ▼
    ╔═══════════════════════════════════════╗
    ║ State: PREPROCESSING                  ║
    ║ - Clean data                          ║
    ║ - Validate columns                    ║
    ║ - Handle missing values               ║
    ║ Status: 🟡 In Progress                ║
    ║ Duration: < 5 seconds                 ║
    ╚═══════════════════════════════════════╝
       │
       ├─ Insufficient data? → Return 400 ❌
       ├─ Invalid format? → Return 422 ❌
       │
       ▼
    ╔═══════════════════════════════════════╗
    ║ State: TRAINING                       ║
    ║ - Initialize model                    ║
    ║ - Fit to data                         ║
    ║ - Generate predictions                ║
    ║ Status: 🟡 In Progress                ║
    ║ Duration: 1-10 minutes                ║
    ╚═══════════════════════════════════════╝
       │
       ├─ Out of memory? → Return 500 ❌
       ├─ Convergence failed? → Return 500 ❌
       │
       ▼
    ╔═══════════════════════════════════════╗
    ║ State: LOGGING TO MLFLOW              ║
    ║ - Connect to MLflow                   ║
    ║ - Start run                           ║
    ║ - Log all metadata                    ║
    ║ - Upload artifacts                    ║
    ║ Status: 🟡 In Progress                ║
    ║ Duration: 5-30 seconds                ║
    ╚═══════════════════════════════════════╝
       │
       ├─ MLflow unavailable? → Return 503 ❌
       ├─ Disk full? → Return 500 ❌
       │
       ▼
    ╔═══════════════════════════════════════╗
    ║ State: SUCCESS ✅                      ║
    ║ - Got run_id from MLflow              ║
    ║ - Calculated metrics                  ║
    ║ - Built response                      ║
    ║ Status: 🟢 Complete                    ║
    ║ Return: 200 OK                        ║
    ║ Response: {run_id, metrics}           ║
    ╚═══════════════════════════════════════╝
```

---

## 7. MLflow Storage Organization

```
┌─────────────────────────────────────────────────────────────┐
│                    MLflow Organization                      │
└─────────────────────────────────────────────────────────────┘

mlflow_data/
│
├─ mlflow.db ← SQLite Database (Backend Store)
│  │
│  └─ Contains:
│     ├─ Experiments
│     │  └─ Experiment: /KAZ/AKMOLA/P_WATT
│     │     ├─ Name: "/KAZ/AKMOLA/P_WATT"
│     │     └─ Experiment_id: 1
│     │
│     ├─ Runs
│     │  └─ Run: abc123def456
│     │     ├─ run_id: "abc123def456"
│     │     ├─ experiment_id: 1
│     │     ├─ status: "FINISHED"
│     │     ├─ start_time: 1713353400000
│     │     ├─ end_time: 1713354000000
│     │     └─ ...
│     │
│     ├─ Tags
│     │  └─ Run: abc123def456
│     │     ├─ key: "object_reference"
│     │     │  value: "/KAZ/AKMOLA/AKMOLA/@models/P_WATT"
│     │     │
│     │     ├─ key: "model_type"
│     │     │  value: "prophet"
│     │     │
│     │     └─ key: "data_source_config"
│     │        value: "{\"sources\": [...], \"freq\": \"H\"}"
│     │
│     ├─ Parameters
│     │  └─ Run: abc123def456
│     │     ├─ key: "changepoint_prior_scale"
│     │     │  value: "0.05"
│     │     ├─ key: "seasonality_mode"
│     │     │  value: "multiplicative"
│     │     └─ ...
│     │
│     └─ Metrics
│        └─ Run: abc123def456
│           ├─ key: "mae"
│           │  value: 45.2
│           │  timestamp: 1713354000000
│           ├─ key: "mape"
│           │  value: 3.1
│           │  timestamp: 1713354000000
│           └─ ...
│
└─ artifacts/ ← Artifact Store (Filesystem)
   │
   ├─ 1/  ← Experiment_id 1 (/KAZ/AKMOLA/P_WATT)
   │  │
   │  ├─ abc123def456/  ← Run_id (first run)
   │  │  │
   │  │  └─ artifacts/
   │  │     └─ bundle/
   │  │        ├─ model/  ← Trained model payload
   │  │        ├─ configuration/
   │  │        │  └─ cache_config.json
   │  │        └─ assets/ (optional)
   │  │
   │  ├─ xyz789abc123/  ← Run_id (second run - retrain)
   │  │  │
   │  │  └─ artifacts/
   │  │     └─ bundle/
   │  │        ├─ model/ ← Updated model payload
   │  │        ├─ configuration/cache_config.json
   │  │        └─ ...
   │  │
   │  └─ ...
   │
   └─ 2/  ← Experiment_id 2 (another object)
      │
      ├─ def456xyz789/
      │  └─ ...
      │
      └─ ...

KEY INSIGHTS:
═════════════
1. SQLite DB stores all metadata efficiently
2. Artifacts stored on disk (can be large)
3. Each run creates new directory in artifacts
4. Tags stored as text (searchable)
5. data_source_config stored as JSON string in tags
6. Can query: "Find all runs with model_type=prophet"
7. Can retrieve: Run abc123def456's config during inference ✓
```

---

## 8. Error Handling Flow

```
EXCEPTION HANDLING DURING TRAINING
════════════════════════════════════

┌─────────────────────────────────────┐
│ Exception Occurs                    │
│ (at any step)                       │
└──────────────┬──────────────────────┘
               │
               ▼
        ┌──────────────────┐
        │ Catch Exception  │
        │ logger.error()   │
        └────────┬─────────┘
                 │
                 ▼
        ┌──────────────────────────────┐
        │ Determine Error Type         │
        └────────┬─────────────────────┘
                 │
      ┌──────────┼──────────┬──────────┬─────────────┐
      │          │          │          │             │
      ▼          ▼          ▼          ▼             ▼
   Network   Insufficient Data Format  Training  MLflow
   Error     Data Error     Error      Error      Error
   │         │             │          │          │
   │         │             │          │          │
   Return    Return        Return     Return     Return
   503       400           422        500        503
   │         │             │          │          │
   └────────┬┴────────┬────┴──────┬───┴──────┬───┘
            │         │          │          │
            ▼         ▼          ▼          ▼
       {               {         {          {
       "status":     "status": "status":   "status":
       "error",      "error", "error",    "error",
       "message":    "msg":   "msg":      "msg":
       "Cannot      "Insuff  "Invalid   "MLflow
       collect      data"    format"    unavail"
       data"       }         }          }
            │         │          │          │
            └────────┴──────┬────┴──────┬───┘
                            │          │
                            ▼          ▼
                        SCADA System receives error
                        Training NOT logged to MLflow
                        No model created
```

---

## 9. Timeline Example: AKMOLA Load Training

```
14:25:00  SCADA sends POST /train for AKMOLA load
          │
          ├─ payload:
          │  {
          │    "object_reference": "/KAZ/AKMOLA/P_WATT",
          │    "model_type": "prophet",
          │    "data_source_config": {
          │      "sources": [{
          │        "url": "http://data.example.com/...",
          │        "params": {...}
          │      }],
          │      "freq": "H"
          │    }
          │  }
          │
14:25:01  API receives request
          ├─ [STEP 1] Request validation: ✓
          │
14:25:02  Data collection starts
          ├─ Request to external API with 15,000+ hourly data points
          │  (1 year + historical data)
          │
14:25:20  Data collection complete
          ├─ Received 15,104 rows from external API
          │
14:25:21  Preprocessing starts
          ├─ Sort, validate, clean, rename columns
          │
14:25:23  Preprocessing complete
          ├─ Clean data: 15,087 rows ready
          │
14:25:24  Model training starts
          ├─ Prophet creates model instance
          ├─ prophet.fit(df) - Learning begins
          │  • Decomposes time series
          │  • Finds trend
          │  • Learns weekly seasonality
          │  • Learns yearly seasonality
          │  • Detects changepoints
          │
14:33:45  Model training complete
          ├─ Took ~8 minutes
          ├─ Model is ready
          │
14:33:46  Calculate metrics
          ├─ Forecast on test set
          ├─ MAE: 45.2
          ├─ MAPE: 3.1%
          ├─ RMSE: 62.8
          │
14:33:47  MLflow logging starts
          ├─ mlflow.start_run()
          ├─ mlflow.set_tag("object_reference", "...")
          ├─ mlflow.set_tag("model_type", "prophet")
          ├─ mlflow.set_tag("data_source_config", "{...}")  ← KEY!
          ├─ mlflow.log_param("changepoint_prior_scale", 0.05)
          ├─ mlflow.log_metric("mae", 45.2)
          ├─ mlflow.log_metric("mape", 3.1)
          ├─ mlflow.log_metric("rmse", 62.8)
          ├─ mlflow.prophet.log_model(model, "model")
          │  (Serializes model to pickle, uploads ~2.3MB)
          │
14:34:12  MLflow logging complete
          ├─ Registered model in MLflow
          ├─ Got run_id: "abc123def456"
          │
14:34:13  Return response to SCADA
          ├─ {
          │    "status": "success",
          │    "run_id": "abc123def456",
          │    "model_id": "prophet_watt_h_AKMOLA",
          │    "metrics": {
          │      "mae": 45.2,
          │      "mape": 3.1,
          │      "rmse": 62.8
          │    }
          │  }
          │
14:34:14  SCADA receives response
          ├─ Training COMPLETE ✓
          │
          TOTAL TIME: 9 minutes 14 seconds

BREAKDOWN:
──────────
- Data collection: ~18 seconds
- Preprocessing:   ~2 seconds
- Training:        ~8 minutes
- MLflow logging:  ~25 seconds
- Response:        ~1 second
────────────────────────────────
  TOTAL:           ~8 minutes 47 seconds
```

---

## 10. Comparison: Prophet vs XGBoost Training

```
┌────────────────────────────────────────────────────────────────┐
│              PROPHET vs XGBOOST TRAINING PIPELINE              │
└────────────────────────────────────────────────────────────────┘

PROPHET                           XGBOOST
════════════════════════════════════════════════════════════════

Data Preparation:                Data Preparation:
 Input: df with 'ds', 'y'       Input: df with 'y'
 └─ Requires two columns          └─ Can use one column

Create Model:                    Create Features:
 └─ Prophet(...)                 ├─ Lag y(t-1)
                                 ├─ Lag y(t-2)
                                 ├─ Lag y(t-3)
                                 ├─ Lag y(t-24)
                                 ├─ Lag y(t-48)
                                 └─ Lag y(t-168)
                                    Result: 2D array [N, 6]

Fitting:                         Data Split:
 └─ model.fit(df)                ├─ Train: 80% of data
    • Decomposes into             ├─ Test: 20% of data
      trend, season, holidays
    • Estimates changepoints
    • Learns seasonal patterns

Prediction:                       Create Model:
 └─ future_df = make_future...   └─ XGBRegressor(...)
    forecast = predict(future)
    Returns df with:              Fitting:
    - yhat (prediction)           └─ model.fit(X_train, y_train)
    - yhat_lower (CI lower)          • Builds decision trees
    - yhat_upper (CI upper)          • Ensemble learning
    - trend                          • Learns non-linear patterns
    - yearly
    - weekly

OUTPUTS                          Prediction:
════════════════════════════════════════════════════════════════
Forecast:                        Predictions:
 [                                np.array([
   {                               1234.5,
     "timestamp": "...",           1198.2,
     "yhat": 1234.5,              1201.3,
     "yhat_lower": 1200.1,         ...
     "yhat_upper": 1269.0,        ])
     "trend": 1234.0,
     "yearly": 0.5,
     "weekly": -0.0
   },
   ...
 ]

METRICS                          Feature Importance:
════════════════════════════════════════════════════════════════
• MAE: 45.2                      • y(t-1): 0.45
• MAPE: 3.1%                     • y(t-24): 0.32
• RMSE: 62.8                     • y(t-2): 0.15
                                 • y(t-48): 0.08


ADVANTAGES                       ADVANTAGES
════════════════════════════════════════════════════════════════
✓ Handles seasonality well       ✓ Great for multiple features
✓ Decomposable (trend, season)   ✓ Non-linear patterns
✓ Built-in confidence intervals  ✓ Feature importance
✓ Fast inference                 ✓ Robust to outliers
✓ Works with little data         ✓ Can use external features


LIMITATIONS                      LIMITATIONS
════════════════════════════════════════════════════════════════
✗ Assumes additive/multiplicative ✗ Less interpretable
✗ May struggle with trend changes ✗ Needs more training data
✗ Limited to time series         ✗ Requires feature engineering
✗ No feature importance           ✗ Slower inference


TYPICAL USE CASE                 TYPICAL USE CASE
════════════════════════════════════════════════════════════════
Energy load with strong         Energy load with external
seasonal patterns               factors (weather, events)
```

---

## 11. Practical Notebook Mapping

```
┌────────────────────────────────────────────────────────────────┐
│            NOTEBOOK COMPANION TO TRAINING PIPELINE            │
└────────────────────────────────────────────────────────────────┘

TRAINING STAGE / FLOW             NOTEBOOK SECTION / OUTPUT
════════════════════════════════════════════════════════════════

Stage 0: Preparation              Quality checks table
                                  └─ readiness summary before fit

Stage 2: Data collection          Dataset loading + raw preview
                                  └─ normalized frame with ds/y

Stage 3: Preprocessing            EDA + profiling + split setup
                                  └─ clean dataset and diagnostics

Stage 4: Model training           Candidate blocks
                                  ├─ baseline
                                  ├─ Prophet
                                  ├─ XGBoost
                                  └─ new algorithm template

Stage 5: MLflow logging           Report bundle and artifact checklist
                                  └─ metrics table + recommendation

Stage 6: Return results           Manual decision summary
                                  └─ recommended algorithm and next steps
```

---

## Summary

These diagrams show:

1. **Architecture** - How components interact
2. **Request/Response flow** - What happens at each step
3. **Data transformation** - From raw data → clean → trained model
4. **State transitions** - Possible error paths
5. **MLflow storage** - Where everything is saved
6. **Timeline example** - Real timing of a training run
7. **Model comparison** - Prophet vs XGBoost differences
8. **Notebook mapping** - How the manual workflow aligns with Stage 0-6

**Key Takeaway:** The training pipeline is a structured process that takes external data, cleans it, trains a model, logs everything to MLflow, and stores the **data_source_config** so the system knows where to get data during inference automatically!

