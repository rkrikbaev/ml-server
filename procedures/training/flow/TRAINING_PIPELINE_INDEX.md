# Training Pipeline (Section 4.2) - Documentation Index

**Purpose:** Complete documentation for understanding the training pipeline  
**Covers:** Section 4.2 from ТЗ_ML_Infrastructure.md  
**Date:** April 19, 2026

> Implementation note: `POST /train` is documented here as a target workflow, but is currently **not implemented** in the active codebase.

---

## 📚 Documentation Files

### 1. TRAINING_PIPELINE_DETAILED_EXPLANATION.md
**Type:** Detailed Technical Guide  
**Length:** ~1200 lines  
**Read Time:** 20-30 minutes  
**Best For:** Complete understanding of how pipeline works

**Contents:**
- Overview of 6 core steps and pre
- **Step 0**: Preparation (environment, readiness checks)
- **Step 1**: Request reception (JSON parsing, validation)
- **Step 2**: Data collection (DataLoader, external APIs, data passport)
- **Step 3**: Preprocessing (cleaning, validation, feature engineering)
- **Step 4**: Model training (Prophet & XGBoost implementations)
- **Step 5**: MLflow logging (metadata, parameters, metrics, artifacts)
- **Step 6**: Return results (API response format)
- Error handling scenarios
- Performance characteristics
- Practical example (AKMOLA load forecast)
- Connection to inference pipeline

**Key Sections:**
```
✓ Step-by-step breakdown with code examples
✓ "Data Passport" explanation
✓ Data transformation examples
✓ Error handling flowcharts
✓ Complete request/response cycle
✓ Real timing example (8+ minutes)
```

**Start Here For:** Deep technical understanding

---

### 2. TRAINING_PIPELINE_VISUAL_GUIDES.md
**Type:** Visual Reference & Diagrams  
**Length:** ~800 lines  
**Read Time:** 15-20 minutes  
**Best For:** Visual learners, quick reference

**Contents:**
- Overall architecture diagram (SCADA ↔ ML-Server)
- Request/response flow diagram
- Data passport structure visualization
- Data transformation flow (Step 2-6)
- Complete data flow diagram
- State transitions during training
- MLflow storage organization
- Error handling flow
- Real timeline example (14:25:00 → 14:34:14)
- Prophet vs XGBoost comparison table

**Key Diagrams:**
```
✓ 10 ASCII diagrams
✓ Flow charts
✓ State machines
✓ Storage structure visualization
✓ Timeline visualization
✓ Error handling paths
```

**Start Here For:** Visual overview, quick reference

---

### 3. TRAINING STAGE Documents (1 file per step)
**Type:** Stage-by-stage detailed guides  
**Read Time:** 3-7 minutes per stage  
**Best For:** Точечная проработка одного шага без чтения всего большого документа

**Files:**
- TRAINING_STAGE0_PREPARATION.md
- TRAINING_STAGE1_REQUEST_RECEPTION.md
- TRAINING_STAGE2_DATA_COLLECTION.md
- TRAINING_STAGE3_PREPROCESSING.md
- TRAINING_STAGE4_MODEL_TRAINING.md
- TRAINING_STAGE5_MLFLOW_LOGGING.md
- TRAINING_STAGE6_RETURN_RESULTS.md

**Contents (by stage):**
- **Stage 0**: Подготовка окружения, readiness-checks, pre-flight валидация
- **Stage 1**: Контракт входного запроса `/train`, валидация, data passport
- **Stage 2**: Сбор данных из источников, ошибки интеграций, выходной raw dataset
- **Stage 3**: Очистка/валидация/подготовка данных к обучению
- **Stage 4**: Обучение Prophet/XGBoost, выход model object
- **Stage 5**: Логирование run в MLflow (tags, params, metrics, artifacts)
- **Stage 6**: Формирование и возврат итогового API-ответа

**Start Here For:** Разбор или ревью конкретного шага pipeline

---

### 4. TRAINING_MANUAL_WORKFLOW.ipynb
**Type:** Executable Jupyter Notebook  
**Read Time:** 15-30 minutes + execution time  
**Best For:** Ручной анализ данных, manual retraining, сравнение алгоритмов, подготовка отчетов

**Contents:**
- загрузка и профилирование исходного датасета;
- pre-flight quality checks в стиле Stage 0 / Stage 3;
- baseline и candidate models в едином формате сравнения;
- manual training блоки для Prophet и XGBoost;
- шаблон добавления нового алгоритма;
- export human-readable report bundle (`csv` + `json`).

**Start Here For:** Практическая работа с данными и ручной retraining без backend `POST /train`

---

## 🎯 Quick Navigation

### "I want to understand..."

**"...how data flows from external API to trained model"**
→ See: TRAINING_PIPELINE_VISUAL_GUIDES.md → Section 4 (Data Transformation Flow)

**"...what happens in each stage of training"**
→ See: TRAINING_STAGE0_PREPARATION.md + TRAINING_STAGE1...6_*.md

**"...what the Data Passport is"**
→ See: TRAINING_PIPELINE_DETAILED_EXPLANATION.md → Step 1 (Understanding Data Passport)
→ Or: TRAINING_PIPELINE_VISUAL_GUIDES.md → Section 3 (Data Passport Structure)

**"...how to debug training failures"**
→ See: TRAINING_PIPELINE_DETAILED_EXPLANATION.md → Error Handling Scenarios

**"...how Prophet differs from XGBoost"**
→ See: TRAINING_PIPELINE_DETAILED_EXPLANATION.md → Step 4 (Model Training)
→ Or: TRAINING_PIPELINE_VISUAL_GUIDES.md → Section 10 (Prophet vs XGBoost)

**"...how to manually analyze data, compare candidates, and prepare a training report"**
→ See: TRAINING_MANUAL_WORKFLOW.ipynb

**"...what MLflow stores and why"**
→ See: TRAINING_PIPELINE_DETAILED_EXPLANATION.md → Step 5 (MLflow Logging)
→ Or: TRAINING_PIPELINE_VISUAL_GUIDES.md → Section 7 (MLflow Storage)

**"...the timing of a training run"**
→ See: TRAINING_PIPELINE_VISUAL_GUIDES.md → Section 9 (Timeline Example)

**"...error handling"**
→ See: TRAINING_PIPELINE_DETAILED_EXPLANATION.md → Error Handling Scenarios
→ Or: TRAINING_PIPELINE_VISUAL_GUIDES.md → Section 8 (Error Handling Flow)

---

## 📖 Reading Recommendations

### For Quick Overview (10 minutes)
1. Read: TRAINING_PIPELINE_VISUAL_GUIDES.md → Section 1 (Architecture)
2. Look at: Section 2 (Request/Response Flow)
3. Check: Section 9 (Timeline)

### For Technical Deep Dive (30 minutes)
1. Read: TRAINING_PIPELINE_DETAILED_EXPLANATION.md → Overview
2. Study: Stage 0 + Steps 1-6
3. Review: Error handling scenarios
4. Look at: Practical example (AKMOLA)

### For Implementation/Development (45 minutes)
1. Read: TRAINING_PIPELINE_DETAILED_EXPLANATION.md → Complete
2. Reference: Code examples in each step
3. Study: Step 4 (Model Training) - understand Prophet & XGBoost
4. Study: Step 5 (MLflow Logging) - understand data storage
5. Reference: TRAINING_PIPELINE_VISUAL_GUIDES.md → Section 7 (Storage structure)

### For Manual Analysis & Retraining (20-40 minutes)
1. Run: TRAINING_MANUAL_WORKFLOW.ipynb
2. Review: Stage 0 checks before fitting candidates
3. Compare: Prophet / XGBoost / baseline metrics in one table
4. Export: report bundle for review and publication decision

### For Visual Learners (20 minutes)
1. Look at: TRAINING_PIPELINE_VISUAL_GUIDES.md → All sections
2. Understand: Architecture and data flows
3. Reference: Timeline and state transitions

---

## 🔑 Key Concepts

### 1. Data Passport (data_source_config)

**What:** JSON object describing where data comes from

```json
{
"sources": {
        "step": 3600,
        "input_range": 168,
        "output_range": 24,
        "historical": {
            "pattern": "historic",
            "archives": ["/root/FP/.../archives/out_value"],
            "url": "http://host.docker.internal:7080/api/v1/read/archives",
            "request_overrides": {
                "archive": ["/root/FP/.../archives/out_value"]
            }
        },
        "weather": {
            "pattern": "forecast",
            "lat": 43.25,
            "lon": 76.92,
            "url": "http://127.0.0.1:8050/api/v1/forecast",
            "units": "metric",
            "hours": 24
        },
        "cmms": {
            "pattern": "planned",
            "url": null,
            "request_overrides": {}
        }
    }
}
```

**Why Important:**
- Tells DataLoader where to fetch training data
- **Stored in MLflow during training**
- During inference, retrieved automatically (no reconfiguration!)
- Enables dynamic configuration without code changes

**See:** 
- TRAINING_PIPELINE_DETAILED_EXPLANATION.md → Step 1 (Understanding Data Passport)
- TRAINING_PIPELINE_VISUAL_GUIDES.md → Section 3 (Data Passport Structure)

### 2. MLflow Logging

**What:** Storing all model metadata, parameters, metrics, and artifacts

**Why Important:**
- Complete model reproducibility
- Automatic version control
- Easy model retrieval for inference
- Experiment tracking
- Artifact (model file) storage

**Structure:**
```
Experiment: /KAZ/AKMOLA/P_WATT
└── Run: abc123def456
    ├── Tags: {object_reference, model_type, data_source_config}
    ├── Params: {hyperparameters}
    ├── Metrics: {mae, mape, rmse}
    └── Artifacts:
        └── bundle/
            ├── model/
            ├── configuration/cache_config.json
            └── assets/ (optional)
```

**See:**
- TRAINING_PIPELINE_DETAILED_EXPLANATION.md → Step 5 (MLflow Logging)
- TRAINING_PIPELINE_VISUAL_GUIDES.md → Section 7 (MLflow Storage)

### 3. Training Pipeline Steps

```
Request → DataCollection → Preprocessing → Training → MLflowLogging → Response
```

**Each step:**
1. Has specific function
2. Can fail (with error handling)
3. Produces specific output
4. Feeds into next step

**See:**
- TRAINING_PIPELINE_DETAILED_EXPLANATION.md → Steps 1-6 (Complete breakdown)
- TRAINING_PIPELINE_VISUAL_GUIDES.md → Section 2 (Flow) or Section 4 (Data flow)

---

## 📊 Performance Metrics

| Step | Duration | Bottleneck | Notes |
|------|----------|-----------|-------|
| 1. Request | < 1ms | Network | Fast |
| 2. Data Collection | 5-30s | External API | **Main bottleneck** |
| 3. Preprocessing | < 5s | CPU | Fast |
| 4. Training | 1-10 min | CPU/RAM | Depends on data size |
| 5. MLflow Logging | 5-30s | Disk I/O | Artifact upload |
| 6. Response | < 1ms | Network | Fast |
| **Total** | **10-15 min** | Step 4 | Typical |

**See:** TRAINING_PIPELINE_DETAILED_EXPLANATION.md → Performance Characteristics

---

## 🐛 Troubleshooting Guide

### Problem: Training Fails at Step 2 (Data Collection)

**Error:** "Connection timeout"
**Cause:** External API unreachable or slow
**Solution:**
1. Check external API availability
2. Increase timeout threshold
3. Check network connectivity

**See:** TRAINING_PIPELINE_DETAILED_EXPLANATION.md → Step 2 (Error Handling)

### Problem: Training Fails at Step 3 (Preprocessing)

**Error:** "Insufficient data"
**Cause:** Only 50 rows (need 100+)
**Solution:**
1. Increase historical data period
2. Use different time interval (e.g., hourly vs daily)
3. Add more data sources to data_source_config

**See:** TRAINING_PIPELINE_DETAILED_EXPLANATION.md → Step 3 (Preprocessing Checks)

### Problem: Training Takes Too Long (Step 4)

**Cause:** Large dataset (3+ years of data)
**Solution:**
1. Use subset of recent data
2. Increase preprocessing efficiency
3. Use XGBoost instead of Prophet (faster)
4. Increase RAM allocation

**See:** TRAINING_PIPELINE_DETAILED_EXPLANATION.md → Step 4 (Model Training)

### Problem: MLflow Connection Failed (Step 5)

**Error:** "Cannot connect to mlflow:5000"
**Cause:** MLflow service unavailable
**Solution:**
1. Check if MLflow container running
2. Check network connectivity
3. Verify MLFLOW_TRACKING_URI environment variable

**See:** TRAINING_PIPELINE_DETAILED_EXPLANATION.md → Step 5 (Error Handling)

---

## 🔗 Connection to Other Sections

These documents explain **Section 4.2** of ТЗ_ML_Infrastructure.md:

```
ТЗ_ML_Infrastructure.md (Main specification)
└── Section 4.2: Шаги пайплайна (Pipeline steps)
    │
    └── Explained in detail by:
        ├── TRAINING_PIPELINE_DETAILED_EXPLANATION.md
        └── TRAINING_PIPELINE_VISUAL_GUIDES.md
```

**Related sections:**
- **Section 4.1** (Pipeline initiation): Read about POST /train endpoint
- **Section 5** (Inference pipeline): Uses data_source_config from training
- **Section 6** (MLflow management): Explains MLflow structure
- **Section 7.2** (POST /train endpoint): API specification

---

## 💾 Code References

### External API Call Example
```python
# From TRAINING_PIPELINE_DETAILED_EXPLANATION.md → Step 2
response = httpx.get(url, params=params, timeout=30)
data = response.json()
df = pd.DataFrame(data)
```

### Prophet Model Training
```python
# From TRAINING_PIPELINE_DETAILED_EXPLANATION.md → Step 4
model = Prophet(
    changepoint_prior_scale=train_params.get('changepoint_prior_scale', 0.05),
    seasonality_mode=train_params.get('seasonality_mode', 'multiplicative')
)
model.fit(df)
```

### XGBoost Model Training
```python
# From TRAINING_PIPELINE_DETAILED_EXPLANATION.md → Step 4
model = xgb.XGBRegressor(
    n_estimators=train_params.get('n_estimators', 200),
    max_depth=train_params.get('max_depth', 6)
)
model.fit(X_train, y_train)
```

### MLflow Logging
```python
# From TRAINING_PIPELINE_DETAILED_EXPLANATION.md → Step 5
with mlflow.start_run(run_name="prophet_run"):
    mlflow.set_tag("data_source_config", json.dumps(config))
    mlflow.log_param("changepoint_prior_scale", 0.05)
    mlflow.log_metric("mae", 45.2)
    mlflow.prophet.log_model(model, "model")
```

---

## 🎓 Learning Path

**Level 1: Overview (10 min)**
- Read: TRAINING_PIPELINE_VISUAL_GUIDES.md → Section 1 & 2
- Understand: Basic request/response cycle

**Level 2: Detailed (30 min)**
- Read: TRAINING_PIPELINE_DETAILED_EXPLANATION.md → All 6 steps
- Understand: Each step's purpose and implementation

**Level 3: Deep Dive (45 min)**
- Study: Code examples in TRAINING_PIPELINE_DETAILED_EXPLANATION.md
- Reference: TRAINING_PIPELINE_VISUAL_GUIDES.md → Storage & timings
- Understand: Error handling and edge cases

**Level 4: Expert (2+ hours)**
- Implement: Based on documentation
- Debug: Using error handling guide
- Optimize: Using performance metrics

---

## ✅ Checklist: Understanding the Pipeline

After reading these documents, you should understand:

- [ ] What the 6 steps of the pipeline are
- [ ] What "data passport" means
- [ ] How DataLoader works
- [ ] What preprocessing does
- [ ] Difference between Prophet and XGBoost training
- [ ] How MLflow stores model metadata
- [ ] Why data_source_config is stored in MLflow
- [ ] What metrics are calculated
- [ ] How errors are handled
- [ ] Typical timing of a training run
- [ ] Connection to inference pipeline
- [ ] How to troubleshoot common issues

---

## 📞 Quick Links

| Topic | File | Section |
|-------|------|---------|
| Data Passport | DETAILED_EXPLANATION.md | Step 1 |
| Data Collection | DETAILED_EXPLANATION.md | Step 2 |
| Preprocessing | DETAILED_EXPLANATION.md | Step 3 |
| Model Training | DETAILED_EXPLANATION.md | Step 4 |
| MLflow Logging | DETAILED_EXPLANATION.md | Step 5 |
| Return Results | DETAILED_EXPLANATION.md | Step 6 |
| Architecture | VISUAL_GUIDES.md | Section 1 |
| Request/Response | VISUAL_GUIDES.md | Section 2 |
| Data Transformation | VISUAL_GUIDES.md | Section 4 |
| State Transitions | VISUAL_GUIDES.md | Section 6 |
| MLflow Storage | VISUAL_GUIDES.md | Section 7 |
| Timeline | VISUAL_GUIDES.md | Section 9 |
| Prophet vs XGBoost | VISUAL_GUIDES.md | Section 10 |

---

## 🏁 Summary

These documents provide complete coverage of Section 4.2 (Pipeline Steps):

1. **TRAINING_STAGE0_PREPARATION.md**
    - Pre-flight preparation and readiness checks
    - Environment and source availability checks
    - Input consistency checks before launch

2. **TRAINING_PIPELINE_DETAILED_EXPLANATION.md**
   - Complete technical breakdown
   - Code examples
   - Error scenarios
   - Real-world example

3. **TRAINING_PIPELINE_VISUAL_GUIDES.md**
   - Visual diagrams
   - Flowcharts
   - State machines
   - Timeline visualization

**Together they explain:** Everything you need to know about how the training pipeline works, from request reception through MLflow logging to response generation.

**Use them to:**
- Understand the system
- Implement the pipeline
- Debug issues
- Optimize performance
- Train new team members

---

**Ready to dive in?**

Start with: TRAINING_STAGE0_PREPARATION.md for readiness checks, then TRAINING_PIPELINE_VISUAL_GUIDES.md for overview, then TRAINING_PIPELINE_DETAILED_EXPLANATION.md for full depth.
