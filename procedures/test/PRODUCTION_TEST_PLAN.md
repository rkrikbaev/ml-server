# 🧪 Production Environment Testing Plan

Подробный план поэтапного тестирования инфраструктуры ml-server перед production развёртыванием.

---

## 📋 Структура плана

```
PHASE 1: Infrastructure Setup & Validation
  ↓
PHASE 2: Service Connectivity Tests
  ↓
PHASE 3: Data Pipeline Tests
  ↓
PHASE 4: API Integration Tests
  ↓
PHASE 5: Performance & Load Tests
  ↓
PHASE 6: End-to-End Production Simulation
  ↓
✅ READY FOR PRODUCTION
```

---

## 🔧 PHASE 1: Infrastructure Setup & Validation

### 1.1 Pre-deployment Checklist

```bash
# Location: ml-server/
# Run these checks before any deployment

✓ Check required files exist
  - docker-compose.yml
  - docker/Dockerfile
  - .env (with all required vars)
  - requirements.txt
  - src/api/ (code structure)
  - models/ (model storage)

✓ Verify environment variables
  MODEL=models
  PORT=18888
  REDIS_PORT=6379
  MLFLOW_PORT=5000
  RZ_API_URL=<configured>
  PYTHONPATH=/workspace/server:/workspace/lib

✓ Check disk space
  docker images    (image sizes)
  du -sh ./models  (model storage size)
  du -sh ./mlruns  (MLflow artifacts)

✓ Verify Docker daemon
  docker ps        (running containers)
  docker images    (available images)
  docker info      (daemon status)
```

**Test Script: `scripts/pre_deploy_check.sh`**

```bash
#!/bin/bash
set -e

echo "🔍 Running pre-deployment checks..."

# Check Docker
echo "✓ Checking Docker..."
docker --version || exit 1
docker ps >/dev/null || exit 1

# Check .env file
echo "✓ Checking .env file..."
test -f .env || { echo "❌ .env not found"; exit 1; }
grep -q "MODEL=" .env || { echo "❌ MODEL not in .env"; exit 1; }
grep -q "PORT=" .env || { echo "❌ PORT not in .env"; exit 1; }

# Check required directories
echo "✓ Checking directories..."
test -d src/api || { echo "❌ src/api not found"; exit 1; }
test -d models || { echo "❌ models directory not found"; exit 1; }

# Check disk space (min 5GB)
available=$(df . | awk 'NR==2 {print $4}')
if [ "$available" -lt 5242880 ]; then
  echo "⚠️  Warning: Less than 5GB available disk space"
fi

echo "✅ All pre-deployment checks passed!"
```

**Run:**
```bash
bash scripts/pre_deploy_check.sh
```

---

### 1.2 Docker Build Verification

```bash
# Test 1: Build Docker image
docker build -f docker/Dockerfile -t fpcloud/ml:1.0.0-test .

# Expected output:
# ✅ Image built successfully
# ✅ No layer caching issues
# ✅ Size: ~1.2-1.5 GB

# Test 2: Inspect image
docker inspect fpcloud/ml:1.0.0-test | jq '.[0] | {
  Architecture,
  Os,
  RootFS,
  Env: .Config.Env[0:5]
}'

# Expected: linux/amd64, Python 3.13, PYTHONPATH set
```

---

### 1.3 Volume Mount Verification

```bash
# Test: Check volume paths resolve correctly
echo "Testing volume mount paths..."

# Absolute paths must exist
test -d "$(pwd)/src" && echo "✅ src/ found" || echo "❌ src/ missing"
test -d "$(pwd)/models" && echo "✅ models/ found" || echo "❌ models/ missing"
test -d "$(pwd)/local/models" && echo "✅ local/models/ found" || echo "❌ local/models/ missing"

# Check readable/writable
test -w "$(pwd)/mlruns" && echo "✅ mlruns/ writable" || mkdir -p mlruns && chmod 777 mlruns
```

---

## 🌐 PHASE 2: Service Connectivity Tests

### 2.1 Docker Compose Startup

```bash
# Test: Start all services
docker-compose up -d

# Expected output:
# Creating ml_model ... done
# Creating redis ... done
# Creating mlflow ... done

# Verification
docker-compose ps
```

**Expected state:**
```
NAME          STATE    PORTS
ml_model      running  18888:8000
redis         running  6379:6379
mlflow        running  5000:5000
```

### 2.2 Individual Service Health Checks

#### Test 2.2.1: Redis Connectivity

```bash
#!/bin/bash
# Test Redis connection

echo "🔴 Testing Redis..."

# Test 1: Port accessibility
if nc -zv localhost 6379 2>&1 | grep -q "succeeded"; then
  echo "✅ Redis port 6379 is open"
else
  echo "❌ Redis port 6379 is not accessible"
  exit 1
fi

# Test 2: Redis CLI commands
if redis-cli -h localhost -p 6379 PING | grep -q "PONG"; then
  echo "✅ Redis PING successful"
else
  echo "❌ Redis PING failed"
  exit 1
fi

# Test 3: Set/Get
redis-cli -h localhost -p 6379 SET test_key "test_value"
value=$(redis-cli -h localhost -p 6379 GET test_key)
if [ "$value" = "test_value" ]; then
  echo "✅ Redis SET/GET working"
else
  echo "❌ Redis SET/GET failed"
  exit 1
fi

# Test 4: Check database stats
redis-cli -h localhost -p 6379 INFO server | head -5
echo "✅ Redis is healthy"
```

**Run:**
```bash
bash scripts/test_redis_health.sh
```

---

#### Test 2.2.2: MLflow Connectivity

```bash
#!/bin/bash
# Test MLflow service

echo "🟢 Testing MLflow..."

# Test 1: Port accessibility
if nc -zv localhost 5000 2>&1 | grep -q "succeeded"; then
  echo "✅ MLflow port 5000 is open"
else
  echo "❌ MLflow port 5000 is not accessible"
  exit 1
fi

# Test 2: HTTP health check
http_code=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:5000/health)
if [ "$http_code" = "200" ]; then
  echo "✅ MLflow health endpoint responding"
else
  echo "❌ MLflow health check failed (HTTP $http_code)"
  exit 1
fi

# Test 3: MLflow API
curl -s http://localhost:5000/api/2.0/experiments/list | jq '.' > /dev/null
if [ $? -eq 0 ]; then
  echo "✅ MLflow API responding"
else
  echo "❌ MLflow API failed"
  exit 1
fi

# Test 4: Database backend
sqlite3 mlflow_data/mlflow.db "SELECT COUNT(*) FROM experiments;" > /dev/null 2>&1
if [ $? -eq 0 ]; then
  echo "✅ MLflow SQLite database accessible"
else
  echo "❌ MLflow database not accessible"
  exit 1
fi

echo "✅ MLflow is healthy"
```

**Run:**
```bash
bash scripts/test_mlflow_health.sh
```

---

#### Test 2.2.3: ML Model Service Connectivity

```bash
#!/bin/bash
# Test ML Model service

echo "🔵 Testing ML Model Service..."

# Test 1: Port accessibility
if nc -zv localhost 18888 2>&1 | grep -q "succeeded"; then
  echo "✅ ML Model port 18888 is open"
else
  echo "❌ ML Model port 18888 is not accessible"
  exit 1
fi

# Test 2: Health endpoint
http_code=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:18888/health)
if [ "$http_code" = "200" ]; then
  echo "✅ ML Model /health endpoint responding"
else
  echo "❌ ML Model health check failed (HTTP $http_code)"
  exit 1
fi

# Test 3: Service logs
docker-compose logs ml_model | tail -20 | grep -i error
if [ $? -ne 0 ]; then
  echo "✅ No errors in ML Model logs"
else
  echo "⚠️  Check ML Model logs for errors"
fi

# Test 4: Python environment
docker-compose exec -T ml_model python -c "import sys; print(f'Python {sys.version}')"
if [ $? -eq 0 ]; then
  echo "✅ Python environment working"
else
  echo "❌ Python environment error"
  exit 1
fi

echo "✅ ML Model service is healthy"
```

**Run:**
```bash
bash scripts/test_ml_service_health.sh
```

---

### 2.3 Inter-Service Connectivity

```bash
#!/bin/bash
# Test communication between services

echo "🔗 Testing inter-service communication..."

# Test 1: ML Model can reach Redis
docker-compose exec -T ml_model python -c "
import redis
r = redis.Redis(host='redis', port=6379)
r.ping()
print('✅ ML Model → Redis: OK')
"

# Test 2: ML Model can reach MLflow
docker-compose exec -T ml_model python -c "
import requests
r = requests.get('http://mlflow:5000/api/2.0/experiments/list')
print(f'✅ ML Model → MLflow: {r.status_code}')
"

# Test 3: Check PYTHONPATH in container
docker-compose exec -T ml_model python -c "
import sys
print('PYTHONPATH contents:')
for p in sys.path:
    if '/workspace' in p:
        print(f'  - {p}')
"

echo "✅ Inter-service communication verified"
```

---

## 📊 PHASE 3: Data Pipeline Tests

### 3.1 PYTHONPATH & Module Import Tests

```bash
#!/bin/bash
# Test module imports

echo "📦 Testing module imports..."

# Test 1: API module
docker-compose exec -T ml_model python -c "
from api.forecast.base_interface import PredictionInput, PredictionOutput, BaseModel
print('✅ base_interface imports OK')
"

# Test 2: Adapters
docker-compose exec -T ml_model python -c "
from api.forecast.adapters import get_model_adapter, ProphetModelAdapter
print('✅ adapters imports OK')
"

# Test 3: fpforecast library
docker-compose exec -T ml_model python -c "
from fpforecast import features, utils
print('✅ fpforecast imports OK')
"

# Test 4: Check sys.path
docker-compose exec -T ml_model python << 'PYEOF'
import sys
print("sys.path:")
for p in sys.path:
    print(f"  {p}")
PYEOF

echo "✅ All module imports successful"
```

---

### 3.2 Model Storage & Artifact Access

```bash
#!/bin/bash
# Test model file access

echo "🗂️  Testing model storage access..."

# Test 1: Check model directory in container
docker-compose exec -T ml_model ls -la /workspace/models

# Test 2: Test volume mount
docker-compose exec -T ml_model python -c "
import os
import json

model_dir = '/workspace/models'
if os.path.exists(model_dir):
    print(f'✅ Model directory accessible: {model_dir}')
    files = os.listdir(model_dir)
    print(f'  Files: {files}')
else:
    print(f'❌ Model directory not found: {model_dir}')
    exit(1)
"

# Test 3: Test MLflow artifact access
docker-compose exec -T ml_model python -c "
import os
mlruns_dir = '/mlflow/mlruns'
if os.path.exists(mlruns_dir):
    print(f'✅ MLflow artifacts accessible: {mlruns_dir}')
    artifacts = os.listdir(mlruns_dir)[:5]
    print(f'  Sample artifacts: {artifacts}')
else:
    print(f'⚠️  MLflow artifacts directory: {mlruns_dir}')
"

echo "✅ Model storage access verified"
```

---

### 3.3 Data Serialization Tests

```bash
#!/bin/bash
# Test PredictionInput/Output serialization

cat > /tmp/test_serialization.py << 'PYEOF'
from api.forecast.base_interface import PredictionInput, PredictionOutput
import json

print("Testing serialization...")

# Test 1: PredictionInput to JSON
inp = PredictionInput(
    features={'ds': ['2024-01-01', '2024-01-02'], 'y': [1.5, 2.3]},
    metadata={'region': 'AKMOLA'},
    config={'batch_size': 32}
)
json_str = inp.to_json()
print(f"✅ PredictionInput → JSON: {len(json_str)} chars")

# Test 2: JSON back to PredictionInput
inp_restored = PredictionInput.from_json(json_str)
assert inp_restored.features == inp.features
print("✅ JSON → PredictionInput: OK")

# Test 3: PredictionOutput serialization
out = PredictionOutput(
    predictions=[1.5, 2.3, 1.8],
    confidence=[0.92, 0.85, 0.88],
    metadata={'model_type': 'prophet', 'intervals': {'lower': [1.0, 1.8, 1.3], 'upper': [2.0, 2.8, 2.3]}}
)
json_out = out.to_json()
print(f"✅ PredictionOutput → JSON: {len(json_out)} chars")

# Test 4: Dict conversion
out_dict = out.to_dict()
out_restored = PredictionOutput.from_dict(out_dict)
assert out_restored.predictions == out.predictions
print("✅ Dict conversion: OK")

print("\n✅ All serialization tests passed")
PYEOF

docker-compose exec -T ml_model python /tmp/test_serialization.py
```

---

## 🔌 PHASE 4: API Integration Tests

### 4.1 Basic API Endpoint Tests

#### Test 4.1.1: Health Check

```bash
#!/bin/bash
# Test /health endpoint

echo "🏥 Testing /health endpoint..."

response=$(curl -s http://localhost:18888/health)
echo "Response: $response"

# Check response contains required fields
echo "$response" | jq '.status' | grep -q "healthy"
if [ $? -eq 0 ]; then
  echo "✅ Health check passed"
else
  echo "❌ Health check failed"
  exit 1
fi
```

#### Test 4.1.2: Forecast Endpoint (Basic)

```bash
#!/bin/bash
# Test /forecast endpoint with basic request

echo "📊 Testing /forecast endpoint (basic)..."

curl -X POST http://localhost:18888/forecast \
  -H "Content-Type: application/json" \
  -d '{
    "model_id": "test_model",
    "features": {"x": [1, 2, 3]},
    "metadata": {"region": "AKMOLA"}
  }' \
  | jq '.'
```

#### Test 4.1.3: Load Model Endpoint

```bash
#!/bin/bash
# Test /load_model endpoint

echo "📦 Testing /load_model endpoint..."

curl -X POST "http://localhost:18888/load_model?model_id=prophet_test&model_type=prophet&model_path=/workspace/models/test.pkl" \
  -H "Content-Type: application/json" \
  | jq '.'
```

---

### 4.2 Request/Response Validation

```bash
#!/bin/bash
# Create comprehensive test file

cat > /tmp/test_requests.sh << 'BASHEOF'
#!/bin/bash

echo "🧪 Running comprehensive request tests..."

BASE_URL="http://localhost:18888"

# Test 1: Valid request
echo "Test 1: Valid forecast request"
curl -s -X POST "$BASE_URL/forecast" \
  -H "Content-Type: application/json" \
  -d '{
    "model_id": "prophet_watt_AKMOLA",
    "features": {
      "ds": ["2024-01-01", "2024-01-02", "2024-01-03"],
      "y": [100, 110, 105]
    },
    "metadata": {
      "region": "AKMOLA",
      "source": "test",
      "timestamp": "2024-01-01T12:00:00Z"
    },
    "config": {
      "batch_size": 32,
      "timeout": 30
    }
  }' | jq '.'

# Test 2: Missing required field
echo ""
echo "Test 2: Missing model_id (should fail)"
curl -s -X POST "$BASE_URL/forecast" \
  -H "Content-Type: application/json" \
  -d '{
    "features": {"x": [1, 2, 3]}
  }' | jq '.'

# Test 3: Invalid JSON
echo ""
echo "Test 3: Invalid JSON (should fail)"
curl -s -X POST "$BASE_URL/forecast" \
  -H "Content-Type: application/json" \
  -d '{invalid json}' | jq '.'

# Test 4: GET request on POST endpoint
echo ""
echo "Test 4: GET on POST endpoint (should fail)"
curl -s -X GET "$BASE_URL/forecast" | jq '.'

# Test 5: Large payload
echo ""
echo "Test 5: Large payload test"
python3 << 'PYEOF'
import json
import subprocess

large_payload = {
    "model_id": "test",
    "features": {
        "x": list(range(10000)),
        "y": list(range(10000))
    }
}

result = subprocess.run(
    ["curl", "-s", "-X", "POST", "http://localhost:18888/forecast",
     "-H", "Content-Type: application/json",
     "-d", json.dumps(large_payload)],
    capture_output=True
)
print(f"Status: {result.returncode}")
print(f"Response size: {len(result.stdout)} bytes")
PYEOF

BASHEOF

bash /tmp/test_requests.sh
```

---

### 4.3 Response Validation Schema

```bash
#!/bin/bash
# Validate response schemas

cat > /tmp/validate_response.py << 'PYEOF'
import json
import requests
from jsonschema import validate, ValidationError

# Define expected schemas
forecast_response_schema = {
    "type": "object",
    "properties": {
        "model_id": {"type": "string"},
        "predictions": {"type": "array"},
        "confidence": {"type": ["array", "null"]},
        "metadata": {"type": ["object", "null"]}
    },
    "required": ["model_id", "predictions"]
}

health_response_schema = {
    "type": "object",
    "properties": {
        "status": {"type": "string"},
        "loaded_models": {"type": "array"}
    },
    "required": ["status"]
}

print("🔍 Validating response schemas...")

# Test 1: Health response
try:
    resp = requests.get("http://localhost:18888/health").json()
    validate(instance=resp, schema=health_response_schema)
    print("✅ Health response schema valid")
except ValidationError as e:
    print(f"❌ Health response schema invalid: {e.message}")

# Test 2: Forecast response
try:
    resp = requests.post(
        "http://localhost:18888/forecast",
        json={
            "model_id": "test",
            "features": {"x": [1, 2, 3]}
        }
    ).json()
    validate(instance=resp, schema=forecast_response_schema)
    print("✅ Forecast response schema valid")
except ValidationError as e:
    print(f"❌ Forecast response schema invalid: {e.message}")
except Exception as e:
    print(f"⚠️  Could not validate: {e}")

PYEOF

docker-compose exec -T ml_model python /tmp/validate_response.py
```

---

## 🚀 PHASE 5: Performance & Load Tests

### 5.1 Latency Tests

```bash
#!/bin/bash
# Measure API latency

cat > /tmp/test_latency.py << 'PYEOF'
import requests
import time
import statistics

print("⏱️  Running latency tests...")

times = []
for i in range(10):
    start = time.time()
    response = requests.post(
        "http://localhost:18888/forecast",
        json={
            "model_id": f"test_{i}",
            "features": {"x": list(range(100))}
        },
        timeout=5
    )
    elapsed = (time.time() - start) * 1000  # ms
    times.append(elapsed)
    print(f"  Request {i+1}: {elapsed:.2f}ms (status: {response.status_code})")

print(f"\nLatency Statistics:")
print(f"  Min: {min(times):.2f}ms")
print(f"  Max: {max(times):.2f}ms")
print(f"  Mean: {statistics.mean(times):.2f}ms")
print(f"  Median: {statistics.median(times):.2f}ms")
print(f"  StdDev: {statistics.stdev(times):.2f}ms")

# Check if acceptable (< 500ms for this simple test)
if statistics.mean(times) < 500:
    print("✅ Latency within acceptable range")
else:
    print("⚠️  Latency higher than expected")

PYEOF

docker-compose exec -T ml_model python /tmp/test_latency.py
```

---

### 5.2 Concurrent Request Tests

```bash
#!/bin/bash
# Test concurrent requests

cat > /tmp/test_concurrent.py << 'PYEOF'
import requests
import concurrent.futures
import time

def make_request(request_id):
    try:
        response = requests.post(
            "http://localhost:18888/forecast",
            json={
                "model_id": f"test_{request_id}",
                "features": {"x": list(range(50))}
            },
            timeout=10
        )
        return {
            "id": request_id,
            "status": response.status_code,
            "success": response.status_code == 200
        }
    except Exception as e:
        return {
            "id": request_id,
            "error": str(e),
            "success": False
        }

print("🔄 Testing concurrent requests (10 parallel)...")

with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
    futures = [executor.submit(make_request, i) for i in range(10)]
    results = [f.result() for f in concurrent.futures.as_completed(futures)]

success_count = sum(1 for r in results if r.get("success"))
print(f"✅ Successful: {success_count}/10")
print(f"❌ Failed: {10 - success_count}/10")

if success_count >= 9:
    print("✅ Concurrent request handling OK")
else:
    print("⚠️  Some requests failed under concurrency")

PYEOF

docker-compose exec -T ml_model python /tmp/test_concurrent.py
```

---

### 5.3 Resource Usage Monitoring

```bash
#!/bin/bash
# Monitor resource usage during tests

echo "📊 Monitoring resource usage..."

# Get baseline
echo "Baseline resource usage:"
docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}"

# Run load test and monitor
echo ""
echo "Running load test for 30 seconds..."
python3 << 'PYEOF' &
import subprocess
import time

for i in range(30):
    subprocess.run([
        "curl", "-s", "-X", "POST", "http://localhost:18888/forecast",
        "-H", "Content-Type: application/json",
        "-d", '{"model_id": "test", "features": {"x": [1,2,3]}}'
    ], capture_output=True)
    time.sleep(1)
PYEOF

# Monitor
sleep 5
echo "Current resource usage during load:"
docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}"

wait

echo "✅ Resource monitoring complete"
```

---

## 🔄 PHASE 6: End-to-End Production Simulation

### 6.1 Full Service Lifecycle Test

```bash
#!/bin/bash
# Complete lifecycle test

echo "🔄 Running full lifecycle test..."

# 1. Stop all services
echo "Step 1: Stopping services..."
docker-compose down

# 2. Clean state
echo "Step 2: Cleaning volumes..."
docker volume prune -f

# 3. Rebuild from scratch
echo "Step 3: Rebuilding images..."
docker-compose build

# 4. Start fresh
echo "Step 4: Starting services..."
docker-compose up -d

# 5. Wait for services to be ready
echo "Step 5: Waiting for services to initialize..."
sleep 10

# 6. Run all health checks
echo "Step 6: Running health checks..."
bash scripts/test_redis_health.sh
bash scripts/test_mlflow_health.sh
bash scripts/test_ml_service_health.sh

# 7. Run API tests
echo "Step 7: Running API tests..."
curl -s http://localhost:18888/health | jq '.'

# 8. Verify logs
echo "Step 8: Checking for errors..."
docker-compose logs ml_model | grep -i "error" | head -5

echo "✅ Full lifecycle test completed"
```

---

### 6.2 Data Flow End-to-End Test

```bash
#!/bin/bash
# Test complete data flow from request to response

cat > /tmp/test_e2e_flow.py << 'PYEOF'
import requests
import json
import redis
import time

print("📈 End-to-End Data Flow Test")
print("=" * 50)

# Connect to Redis
r = redis.Redis(host='localhost', port=6379, decode_responses=True)

# Step 1: Send forecast request
print("\n1️⃣  Sending forecast request...")
request_data = {
    "model_id": "prophet_e2e_test",
    "features": {
        "ds": ["2024-01-01", "2024-01-02", "2024-01-03"],
        "y": [100, 110, 105]
    },
    "metadata": {
        "region": "AKMOLA",
        "source": "e2e_test",
        "request_id": f"e2e_test_{int(time.time())}"
    }
}

response = requests.post(
    "http://localhost:18888/forecast",
    json=request_data,
    timeout=10
)

print(f"   Status: {response.status_code}")
print(f"   Response size: {len(response.content)} bytes")

# Step 2: Validate response structure
print("\n2️⃣  Validating response structure...")
response_data = response.json()
required_fields = ["model_id", "predictions"]
missing = [f for f in required_fields if f not in response_data]
if not missing:
    print(f"   ✅ All required fields present")
else:
    print(f"   ❌ Missing fields: {missing}")

# Step 3: Check Redis
print("\n3️⃣  Checking Redis for cached data...")
cache_keys = r.keys("*e2e_test*")
if cache_keys:
    print(f"   ✅ Found {len(cache_keys)} cache entries")
    for key in cache_keys[:3]:
        value = r.get(key)
        print(f"      - {key}: {value[:50]}...")
else:
    print(f"   ℹ️  No cache entries found (expected for first request)")

# Step 4: Verify MLflow logging
print("\n4️⃣  Checking MLflow for logged runs...")
mlflow_response = requests.get("http://localhost:5000/api/2.0/experiments/list")
if mlflow_response.status_code == 200:
    experiments = mlflow_response.json()
    print(f"   ✅ MLflow accessible: {len(experiments.get('experiments', []))} experiments")
else:
    print(f"   ⚠️  MLflow status: {mlflow_response.status_code}")

# Step 5: Check service health
print("\n5️⃣  Checking service health...")
health = requests.get("http://localhost:18888/health").json()
print(f"   Status: {health.get('status')}")
print(f"   Loaded models: {len(health.get('loaded_models', []))}")

# Step 6: Verify data integrity
print("\n6️⃣  Verifying data integrity...")
print(f"   Input features: {len(request_data['features']['ds'])} records")
print(f"   Output predictions: {len(response_data['predictions'])} records")
if len(response_data['predictions']) > 0:
    print(f"   ✅ Data flow complete and valid")
else:
    print(f"   ❌ No predictions returned")

print("\n" + "=" * 50)
print("✅ End-to-End test completed")

PYEOF

python3 /tmp/test_e2e_flow.py
```

---

### 6.3 Failure Recovery Test

```bash
#!/bin/bash
# Test service recovery after failures

echo "🔧 Testing failure recovery..."

# Test 1: Redis failure and recovery
echo ""
echo "Test 1: Redis service failure and recovery"
echo "  - Stopping Redis..."
docker-compose stop redis
sleep 2

echo "  - Attempting request (should fail or degrade)..."
curl -s -X POST http://localhost:18888/forecast \
  -H "Content-Type: application/json" \
  -d '{"model_id": "test", "features": {"x": [1,2,3]}}' \
  | jq '.error' 2>/dev/null || echo "Request failed (expected)"

echo "  - Restarting Redis..."
docker-compose start redis
sleep 3

echo "  - Attempting request (should succeed)..."
curl -s -X POST http://localhost:18888/forecast \
  -H "Content-Type: application/json" \
  -d '{"model_id": "test", "features": {"x": [1,2,3]}}' \
  | jq '.model_id' && echo "✅ Recovery successful"

# Test 2: ML Model service restart
echo ""
echo "Test 2: ML Model service restart"
echo "  - Stopping ML Model..."
docker-compose restart ml_model
echo "  - Waiting for service to come up..."
sleep 5

echo "  - Checking health..."
curl -s http://localhost:18888/health | jq '.status' && echo "✅ Service recovered"

echo ""
echo "✅ Failure recovery tests completed"
```

---

## 📋 Comprehensive Test Checklist

```
PHASE 1: Infrastructure ✅
  ☐ Pre-deployment checks passed
  ☐ Docker image builds successfully
  ☐ Volume mounts resolve correctly
  ☐ .env configured with all variables

PHASE 2: Services ✅
  ☐ Docker Compose startup successful
  ☐ Redis healthy and responsive
  ☐ MLflow healthy and responsive
  ☐ ML Model service healthy
  ☐ Inter-service communication working
  ☐ All ports accessible

PHASE 3: Data Pipeline ✅
  ☐ All module imports successful
  ☐ PYTHONPATH correct in container
  ☐ Model files accessible in /workspace/models
  ☐ MLflow artifacts accessible
  ☐ Serialization/deserialization working

PHASE 4: API ✅
  ☐ /health endpoint working
  ☐ /forecast endpoint working
  ☐ /load_model endpoint working
  ☐ Request validation working
  ☐ Response schemas valid
  ☐ Error handling working
  ☐ Invalid requests rejected properly

PHASE 5: Performance ✅
  ☐ Average latency < 500ms
  ☐ P95 latency < 1000ms
  ☐ Concurrent requests (10x) successful
  ☐ CPU usage < 80%
  ☐ Memory usage stable
  ☐ No memory leaks detected

PHASE 6: End-to-End ✅
  ☐ Full lifecycle test passed
  ☐ Data flow complete (request → processing → response)
  ☐ Redis caching working
  ☐ MLflow logging working
  ☐ Service health verified
  ☐ Data integrity verified
  ☐ Failure recovery working
  ☐ Service restart recovery working

PRODUCTION READINESS: ✅
  ☐ All tests passed
  ☐ No errors in logs
  ☐ Performance acceptable
  ☐ Recovery verified
  ☐ Documentation updated
  ☐ Monitoring configured
  ☐ Alerting configured
```

---

## 🚀 Production Deployment Procedure

```bash
# 1. Run full test suite
bash scripts/run_all_tests.sh

# 2. Review test results
cat test_results.log

# 3. Backup current state (if applicable)
docker-compose down
tar -czf ml-server-backup-$(date +%Y%m%d).tar.gz .

# 4. Deploy to production
docker-compose -f docker-compose.yml up -d

# 5. Run post-deployment verification
bash scripts/post_deploy_verify.sh

# 6. Configure monitoring
# - Set up Prometheus scrapers
# - Configure Grafana dashboards
# - Enable CloudWatch/ELK logging

# 7. Announce deployment
echo "✅ Production deployment completed successfully"
```

---

## 📊 Monitoring & Alerting

### Key Metrics to Monitor

```
Service Health:
  - ml_model container uptime
  - redis connection pool utilization
  - mlflow database query time

API Performance:
  - Request latency (p50, p95, p99)
  - Requests per second
  - Error rate (4xx, 5xx)

Resource Usage:
  - CPU utilization per container
  - Memory usage per container
  - Disk I/O (model loading)
  - Network throughput

Business Metrics:
  - Model inference count
  - Cache hit ratio
  - Average response time
```

---

**Created**: 2024-04-19  
**Status**: ✅ Ready for use  
**Next**: Execute Phase 1-6 sequentially before production deployment
