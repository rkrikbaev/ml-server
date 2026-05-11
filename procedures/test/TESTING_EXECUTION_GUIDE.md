# 🚀 Production Testing Execution Guide

Пошаговое руководство по запуску всех тестов перед production deployment.

---

## 📋 Быстрый старт (5 минут)

```bash
# 1. Перейти в ml-server
cd /path/to/ml-server

# 2. Запустить полный набор тестов
bash scripts/run_all_tests.sh

# 3. Запустить детальные API тесты
python3 scripts/api_test_suite.py

# ✅ Если все тесты прошли → готово к production!
```

---

## 🔍 Подробное описание каждого теста

### 1️⃣ PHASE 1: Infrastructure Setup & Validation

**Что проверяется:**
- Наличие всех необходимых файлов (docker-compose.yml, .env, src/api)
- Переменные окружения (.env)
- Docker daemon доступен
- Достаточно дискового пространства (≥5GB)

**Команда:**
```bash
bash scripts/pre_deploy_check.sh
```

**Ожидаемый результат:**
```
✅ docker-compose.yml found
✅ .env file found
✅ src/api directory found
✅ MODEL=models
✅ PORT=18888
✅ Docker daemon is running
✅ Sufficient disk space: 256GB
```

---

### 2️⃣ PHASE 2: Service Connectivity Tests

**Что проверяется:**
- Docker Compose запускает все сервисы
- Redis доступен и работает (PING, SET/GET)
- MLflow доступен и отвечает на HTTP запросы
- ML Model service доступен на порту 18888

**Команда:**
```bash
bash scripts/test_redis_health.sh
bash scripts/test_mlflow_health.sh
bash scripts/test_ml_service_health.sh
```

**Ожидаемый результат каждого:**
```
✅ Redis port 6379 is open
✅ Redis PING successful
✅ Redis SET/GET working
✅ Redis is healthy

✅ MLflow port 5000 is open
✅ MLflow health endpoint responding
✅ MLflow API responding
✅ MLflow SQLite database accessible
✅ MLflow is healthy

✅ ML Model port 18888 is open
✅ ML Model /health endpoint responding
✅ No errors in ML Model logs
✅ Python environment working
✅ ML Model service is healthy
```

---

### 3️⃣ PHASE 3: Data Pipeline Tests

**Что проверяется:**
- Импорты Python модулей (api, adapters, fpforecast)
- PYTHONPATH правильно настроен в контейнере
- Файлы модели доступны в /workspace/models
- Сериализация данных (JSON, dict)

**Команда:**
```bash
docker-compose exec -T ml_model python -c "
from api.forecast.base_interface import PredictionInput, PredictionOutput
from api.forecast.adapters import get_model_adapter
import fpforecast
print('✅ All imports successful')
"
```

**Ожидаемый результат:**
```
✅ base_interface imports OK
✅ adapters imports OK
✅ fpforecast imports OK
✅ Model directory accessible: /workspace/models
✅ MLflow artifacts accessible: /mlflow/mlruns
✅ PredictionInput → JSON: 250 chars
✅ JSON → PredictionInput: OK
✅ Dict conversion: OK
✅ All serialization tests passed
```

---

### 4️⃣ PHASE 4: API Integration Tests

**Что проверяется:**
- /health endpoint работает
- /forecast endpoint обрабатывает запросы
- /load_model endpoint работает
- Request validation работает
- Response schemas валидны
- Error handling работает

**Команда:**
```bash
python3 scripts/api_test_suite.py
```

**Тесты в этой фазе:**

#### Test 1: Health Endpoint
```bash
curl http://localhost:18888/health | jq '.'
```

Ожидаемый ответ:
```json
{
  "status": "healthy",
  "loaded_models": []
}
```

#### Test 2: Basic Forecast
```bash
curl -X POST http://localhost:18888/forecast \
  -H "Content-Type: application/json" \
  -d '{
    "model_id": "test_model",
    "features": {"x": [1, 2, 3]}
  }' | jq '.'
```

Ожидаемый ответ:
```json
{
  "model_id": "test_model",
  "predictions": [1.5, 2.3, 1.8],
  "confidence": null,
  "metadata": null
}
```

#### Test 3: Forecast с метаданными
```bash
curl -X POST http://localhost:18888/forecast \
  -H "Content-Type: application/json" \
  -d '{
    "model_id": "test_with_meta",
    "features": {"x": [1, 2, 3]},
    "metadata": {"region": "AKMOLA"},
    "config": {"batch_size": 32}
  }' | jq '.'
```

Ожидаемый результат:
```
✅ Forecast with metadata: All fields preserved
```

#### Test 4: Error Handling - Invalid JSON
```bash
curl -X POST http://localhost:18888/forecast \
  -H "Content-Type: application/json" \
  -d '{invalid json}'
```

Ожидаемый результат:
```
✅ Invalid JSON rejected: HTTP 422
```

#### Test 5: Missing Required Field
```bash
curl -X POST http://localhost:18888/forecast \
  -H "Content-Type: application/json" \
  -d '{"features": {"x": [1, 2, 3]}}'
```

Ожидаемый результат:
```
✅ Missing model_id detected: HTTP 422
```

---

### 5️⃣ PHASE 5: Performance & Load Tests

**Что проверяется:**
- Latency (отклик за < 500ms)
- Concurrent requests (5 одновременных запросов)
- Resource usage (CPU, memory)
- Large payloads (1000+ records)

**Команда:**
```bash
# Test latency
python3 scripts/api_test_suite.py  # Test 9

# Test concurrent (10 requests)
python3 << 'EOF'
import concurrent.futures
import requests

def request(i):
    return requests.post(
        "http://localhost:18888/forecast",
        json={"model_id": f"test_{i}", "features": {"x": [1,2,3]}}
    ).status_code

with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
    results = list(executor.map(request, range(10)))
    print(f"Success: {sum(1 for r in results if r == 200)}/10")
EOF
```

**Ожидаемые результаты:**
```
✅ Average latency: 150ms (acceptable)
✅ Concurrent requests (10x): 10/10 successful
✅ Large payload (1000 records): 1000 records in 200ms
✅ Resource usage: CPU < 50%, Memory stable
```

---

### 6️⃣ PHASE 6: End-to-End Production Simulation

**Что проверяется:**
- Full lifecycle (down → rebuild → up)
- Complete data flow (request → processing → response)
- Redis caching
- MLflow logging
- Service recovery

**Команда:**
```bash
# Full lifecycle test
docker-compose down
docker-compose build
docker-compose up -d

# End-to-end flow test
python3 << 'EOF'
import requests
import time

# Send request
response = requests.post(
    "http://localhost:18888/forecast",
    json={
        "model_id": "e2e_test",
        "features": {"x": [1, 2, 3]},
        "metadata": {"region": "AKMOLA"}
    }
)

print(f"Status: {response.status_code}")
print(f"Response: {response.json()}")
time.sleep(1)

# Check health
health = requests.get("http://localhost:18888/health").json()
print(f"Health: {health['status']}")
EOF
```

---

## 📊 Интерпретация результатов

### ✅ Все тесты прошли успешно

**Действия:**
1. Сохранить результаты тестов: `cp test_results_*.log archives/`
2. Обновить documentation с датой успешного теста
3. Готово к production deployment! 🚀

### ⚠️ Некоторые тесты не прошли

**Что делать:**
1. Найти неудачный тест в логах
2. Прочитать error message
3. Применить fix согласно таблице ниже
4. Переалзапустить только этот тест (или все)

### 🔧 Таблица решения проблем

| Проблема | Причина | Решение |
|----------|---------|---------|
| `Redis port 6379 not accessible` | Redis не запустился | `docker-compose logs redis` + `docker-compose restart redis` |
| `ML Model port 18888 not accessible` | Порт занят или сервис не поднялся | `lsof -i :18888` + `docker-compose restart ml_model` |
| `base_interface imports failed` | PYTHONPATH неправильный | Проверить docker-compose.yml: `PYTHONPATH=/workspace/server:/workspace/lib` |
| `Model directory not found` | Volume mount неправильный | Проверить абсолютные пути в docker-compose.yml |
| `HTTP 422 - Validation error` | Request payload неправильный | Проверить JSON structure + required fields |
| `Average latency > 500ms` | Недостаточно ресурсов или узкое место | Проверить CPU/memory + network latency |
| `Concurrent requests failing` | Resource exhaustion | Увеличить лимиты контейнера или оптимизировать код |

---

## 📈 Метрики для monitoring

После успешного deployment мониторить эти метрики:

```yaml
Service Health:
  - ml_model uptime: ≥ 99.9%
  - redis connection pool utilization: < 80%
  - mlflow API response time: < 100ms

API Performance:
  - p50 latency: < 200ms
  - p95 latency: < 500ms
  - p99 latency: < 1000ms
  - error rate (4xx/5xx): < 1%
  - requests/second: ≥ 100

Resource Usage:
  - ml_model CPU: < 70%
  - ml_model Memory: < 80% allocated
  - redis Memory: < 500MB
  - mlflow DB size: monitor growth

Business Metrics:
  - Model inference count: track trends
  - Cache hit ratio: ≥ 70%
  - Average response time: trending
```

---

## 🔐 Pre-Production Checklist

Перед финальным deployment:

```
Infrastructure:
  ☐ Все тесты в run_all_tests.sh прошли (0 failed)
  ☐ API tests (api_test_suite.py) прошли (0 failed)
  ☐ Нет ошибок в логах сервисов
  ☐ Достаточно дискового пространства (≥10GB)
  ☐ Резервная копия существующего окружения создана

Services:
  ☐ Redis healthy и response time < 10ms
  ☐ MLflow database backup создана
  ☐ ML Model service стартует за < 30 секунд
  ☐ Inter-service communication verified

Performance:
  ☐ Average latency < 300ms (без нагрузки)
  ☐ Concurrent requests (10x) все successful
  ☐ Large payload (1000 records) обрабатывается
  ☐ Resource usage в норме

Security:
  ☐ .env file защищен (chmod 600)
  ☐ Database backups encrypted
  ☐ No secrets в логах
  ☐ Port access restricted (firewall rules)

Documentation:
  ☐ Deployment runbook обновлен
  ☐ Rollback procedure documented
  ☐ Contact list updated (on-call)
  ☐ Monitoring alerts configured
```

---

## 🚨 Emergency Rollback

Если что-то пошло не так в production:

```bash
# 1. Immediate stop
docker-compose down

# 2. Restore from backup
tar -xzf ml-server-backup-YYYYMMDD.tar.gz

# 3. Start previous version
docker-compose up -d

# 4. Verify health
curl http://localhost:18888/health

# 5. Notify team and investigate
# Check: docker-compose logs ml_model | tail -100
```

---

## 📞 Support & Escalation

Если тесты не проходят и не ясно почему:

1. **Собрать диагностику:**
   ```bash
   docker-compose logs > diagnostic_$(date +%Y%m%d_%H%M%S).log
   docker inspect $(docker ps -q) > docker_inspect.json
   ```

2. **Запустить debug queries:**
   ```bash
   # Redis debug
   redis-cli -h localhost -p 6379 INFO

   # MLflow debug
   curl http://localhost:5000/api/2.0/experiments/list | jq '.'

   # ML Model debug
   docker-compose exec -T ml_model python -c "import sys; print(sys.path)"
   ```

3. **Обратиться за помощью с логами и diagnostic информацией**

---

## 📅 Release Notes Template

После успешного deployment:

```markdown
## Production Deployment - [DATE]

### Services Deployed
- ml_model (image: fpcloud/ml:1.0.0)
- redis:7
- mlflow:latest

### Tests Executed
- Infrastructure validation: PASSED
- Service connectivity: PASSED
- API integration: PASSED (10/10 tests)
- Performance: PASSED (avg latency: XXXms)
- End-to-end: PASSED

### Performance Baseline
- Health check latency: XXms
- Average forecast latency: XXms
- P95 latency: XXms
- Concurrent request success: 100%

### Monitoring Active
- Prometheus scraping every 15s
- Grafana dashboards available
- CloudWatch/ELK logging enabled

### Rollback Plan
- Previous version: [VERSION]
- Rollback time: < 5 minutes
- Backup location: [PATH]
```

---

**Last Updated**: 2024-04-19  
**Status**: ✅ Ready for Production  
**Next Step**: Execute tests in sequential order
