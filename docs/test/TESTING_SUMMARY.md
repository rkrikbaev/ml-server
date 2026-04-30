# 📋 Production Testing Plan — Summary & Overview

Полный план поэтапного тестирования и 50+ готовых тестов для production deployment.

---

## 📚 Созданные документы и скрипты

### 🎯 Главные документы

| Файл | Размер | Назначение | Когда читать |
|------|--------|-----------|---------------|
| **START_TESTING.md** | 5 KB | 3-команда quick start | ПЕРВЫЙ |
| **PRODUCTION_TEST_PLAN.md** | 35 KB | Полный план (6 фаз) | Детальное чтение |
| **TESTING_EXECUTION_GUIDE.md** | 25 KB | Пошаговая инструкция | Во время тестирования |

### 🔧 Исполняемые скрипты

| Скрипт | Язык | Назначение |
|--------|------|-----------|
| **scripts/run_all_tests.sh** | Bash | Все тесты инфра (45 тестов) |
| **scripts/api_test_suite.py** | Python | API тесты (10 тестов) |

---

## 🧪 Тестовое покрытие

### PHASE 1: Infrastructure (8 тестов)
- ✅ Pre-deployment checks
- ✅ Docker build verification
- ✅ Volume mount verification
- ✅ Directory checks
- ✅ .env validation
- ✅ Disk space check
- ✅ Docker daemon status
- ✅ Required files verification

### PHASE 2: Services (12 тестов)
- ✅ Docker Compose startup
- ✅ Service status verification
- ✅ Redis connectivity (PING, SET/GET)
- ✅ Redis database health
- ✅ MLflow HTTP endpoints
- ✅ MLflow SQLite backend
- ✅ ML Model port accessibility
- ✅ ML Model health endpoint
- ✅ Python environment in container
- ✅ Inter-service communication
- ✅ Service logs inspection
- ✅ Error log analysis

### PHASE 3: Data Pipeline (8 тестов)
- ✅ base_interface imports
- ✅ adapters imports
- ✅ fpforecast imports
- ✅ PYTHONPATH validation
- ✅ Model directory accessibility
- ✅ MLflow artifacts access
- ✅ JSON serialization
- ✅ Dictionary serialization

### PHASE 4: API (10 тестов)
- ✅ /health endpoint
- ✅ /forecast endpoint (basic)
- ✅ /forecast with metadata
- ✅ /load_model endpoint
- ✅ Invalid JSON rejection
- ✅ Missing field validation
- ✅ Empty features handling
- ✅ Response schema validation
- ✅ Error message format
- ✅ Status code correctness

### PHASE 5: Performance (8 тестов)
- ✅ Latency measurement (10 requests)
- ✅ Latency percentiles (p50, p95, p99)
- ✅ Concurrent requests (5-10x)
- ✅ Large payload (1000+ records)
- ✅ Resource usage (CPU, memory)
- ✅ Memory stability over time
- ✅ No memory leaks detection
- ✅ Throughput measurement

### PHASE 6: End-to-End (6 тестов)
- ✅ Full lifecycle (down → rebuild → up)
- ✅ Data flow complete
- ✅ Redis caching verification
- ✅ MLflow logging verification
- ✅ Service health check
- ✅ Failure recovery test

**Total: 52 тестов** ✅

---

## 🚀 Быстрый старт

### 1️⃣ Запустить все инфра-тесты
```bash
bash scripts/run_all_tests.sh
```
**Время**: 5-10 минут  
**Результат**: Файл test_results_YYYYMMDD_HHMMSS.log

### 2️⃣ Запустить API тесты
```bash
python3 scripts/api_test_suite.py
```
**Время**: 2-3 минуты  
**Результат**: 10 детальных API тестов

### 3️⃣ Проверить результаты
```bash
# Если все прошли:
echo "✅ Ready for Production"

# Если ошибки:
cat test_results_*.log | grep "❌"
```

---

## 📊 Структура тестирования

```
START_TESTING.md (это прочитайте первым!)
  ├─ 3 команды для запуска
  ├─ Таблица Quick Fix'ов
  ├─ Пошаговый процесс
  └─ Ссылки на другие docs

PRODUCTION_TEST_PLAN.md (подробный план)
  ├─ PHASE 1: Infrastructure (8 тестов)
  ├─ PHASE 2: Services (12 тестов)
  ├─ PHASE 3: Data Pipeline (8 тестов)
  ├─ PHASE 4: API (10 тестов)
  ├─ PHASE 5: Performance (8 тестов)
  ├─ PHASE 6: End-to-End (6 тестов)
  └─ Monitoring & Metrics

TESTING_EXECUTION_GUIDE.md (как запускать)
  ├─ Детальное описание каждого теста
  ├─ Expected результаты
  ├─ Как интерпретировать ошибки
  ├─ Pre-Production Checklist
  └─ Emergency Rollback

run_all_tests.sh (Bash скрипт)
  ├─ Автоматически запускает все тесты
  ├─ Цветной вывод с ✅/❌
  ├─ Собирает результаты в лог
  └─ Возвращает exit code

api_test_suite.py (Python скрипт)
  ├─ 10 детальных API тестов
  ├─ Latency analysis
  ├─ Concurrent request testing
  └─ Response validation
```

---

## ✅ Контрольный список перед Production

```
Перед тестированием:
  ☐ Docker daemon запущен
  ☐ .env файл создан (MODEL, PORT, REDIS_PORT и т.д.)
  ☐ Достаточно памяти (4GB min, 8GB рекомендуется)
  ☐ Достаточно дискового пространства (10GB)

Во время тестирования:
  ☐ Запустить run_all_tests.sh
  ☐ Если Failed > 0, применить Fix из таблицы
  ☐ Переалзапустить failed тесты
  ☐ Запустить api_test_suite.py
  ☐ Проверить test_results_*.log

После успешного тестирования:
  ☐ Сохранить результаты: cp test_results_*.log archives/
  ☐ Проверить логи на ошибки: docker-compose logs | grep -i error
  ☐ Убедиться нет memory leaks: docker stats --no-stream
  ☐ Обновить Release Notes
  ☐ Готово к deployment! 🚀
```

---

## 🎯 Метрики приемки (SLA)

```
Service Health:
  ✅ All services healthy and responsive
  ✅ No critical errors in logs
  ✅ No import errors (ModuleNotFoundError)

API Endpoints:
  ✅ /health returns 200 OK
  ✅ /forecast returns predictions in < 500ms
  ✅ /load_model endpoint functional
  ✅ Invalid requests return 4xx errors

Performance:
  ✅ Average latency < 300ms
  ✅ P95 latency < 500ms
  ✅ P99 latency < 1000ms
  ✅ Concurrent requests (10x) all successful
  ✅ Large payload (1000 records) processed

Resource Usage:
  ✅ ml_model CPU < 70%
  ✅ ml_model Memory < 80% allocated
  ✅ redis Memory stable
  ✅ No memory leaks detected

Data Integrity:
  ✅ Input features preserved
  ✅ Output predictions valid
  ✅ Serialization/deserialization working
  ✅ Cache hit ratio verified

Reliability:
  ✅ Service recovery after failure
  ✅ Redis reconnection working
  ✅ No data loss during restart
  ✅ All services restart cleanly
```

---

## �� Таблица быстрых Fix'ов

| Ошибка | Причина | Fix |
|--------|---------|-----|
| Redis port 6379 not accessible | Сервис не запустился | `docker-compose restart redis && sleep 3` |
| ML Model port 18888 not accessible | Порт занят или сервис не поднялся | `lsof -i :18888` или `docker-compose restart ml_model` |
| `ModuleNotFoundError: api` | PYTHONPATH неправильный | Проверить docker-compose.yml environment |
| `ModuleNotFoundError: fpforecast` | Volume mount неправильный | Проверить абсолютные пути в volumes |
| HTTP 422 Validation Error | JSON schema неправильный | Проверить required fields в request |
| Average latency > 500ms | Low resources | Увеличить CPU/Memory или оптимизировать код |
| Concurrent requests failing | Resource exhaustion | Уменьшить concurrency level или масштабировать |

---

## 📈 Что происходит в каждой фазе?

### 🔧 PHASE 1: Setup (2 минуты)
- Проверяет наличие файлов
- Валидирует .env
- Проверяет Docker
- Проверяет дисковое пространство

### 🌐 PHASE 2: Connectivity (3 минуты)
- Запускает все сервисы
- Проверяет каждый сервис
- Проверяет inter-service communication
- Анализирует логи

### 📦 PHASE 3: Data (2 минуты)
- Проверяет Python imports
- Проверяет PYTHONPATH
- Проверяет файловый доступ
- Проверяет сериализацию

### 🔌 PHASE 4: API (2 минуты)
- Тестирует /health
- Тестирует /forecast
- Тестирует error handling
- Валидирует response schemas

### ⚡ PHASE 5: Performance (2 минуты)
- Измеряет latency
- Тестирует concurrent requests
- Тестирует large payloads
- Мониторит ресурсы

### 🔄 PHASE 6: E2E (2 минуты)
- Полный lifecycle test
- Complete data flow verification
- Caching verification
- Recovery verification

**Total Time: 13-15 минут для всех фаз**

---

## 🚨 Emergency Scenarios

### Если Redis не работает:
```bash
docker-compose logs redis
docker-compose restart redis
sleep 3
bash scripts/run_all_tests.sh  # Retry
```

### Если ML Model не запускается:
```bash
docker-compose logs ml_model | tail -100
docker-compose down
docker-compose up -d
sleep 5
bash scripts/run_all_tests.sh  # Retry
```

### Если есть import ошибки:
```bash
docker-compose exec -T ml_model python -c "import sys; print(sys.path)"
# Должны быть /workspace/server и /workspace/lib
```

### Если нужен rollback:
```bash
docker-compose down
tar -xzf ml-server-backup-YYYYMMDD.tar.gz
docker-compose up -d
```

---

## 📞 Getting Help

1. **Прочитать START_TESTING.md** (этот файл) — быстрый старт
2. **Посмотреть таблицу Fix'ов** выше — решение типовых ошибок
3. **Прочитать PRODUCTION_TEST_PLAN.md** — полный план
4. **Запустить диагностику:**
   ```bash
   docker-compose logs > diagnostic.log
   docker ps -a > containers.txt
   cat .env > config.txt
   python3 scripts/api_test_suite.py > api_tests.log
   ```
5. **Обратиться за помощью** с логами

---

## 🎉 Success Criteria

Тестирование успешно завершено если:

```
✅ run_all_tests.sh вернул: 0 Failed, 45+ Passed
✅ api_test_suite.py вернул: 10/10 tests passed
✅ Нет критических ошибок в docker-compose logs
✅ Все сервисы здоровы (docker-compose ps)
✅ Average latency < 300ms (acceptable)
✅ Concurrent requests 10/10 successful
✅ Health check returning 200 OK
```

**При соблюдении всех критериев** → ✅ **READY FOR PRODUCTION** 🚀

---

## 📊 Reporting

После успешного тестирования создать отчет:

```markdown
## Production Deployment Report - [DATE]

### Test Execution
- Start time: [TIME]
- End time: [TIME]
- Duration: [X minutes]
- Status: ✅ PASSED

### Test Results
- Infrastructure: PASSED (8/8 tests)
- Services: PASSED (12/12 tests)
- Data Pipeline: PASSED (8/8 tests)
- API: PASSED (10/10 tests)
- Performance: PASSED (8/8 tests)
- End-to-End: PASSED (6/6 tests)

### Performance Metrics
- Average latency: XXms
- P95 latency: XXms
- Concurrent requests (10x): 100% success
- Large payload (1000 records): XXms

### Resource Usage
- ml_model CPU: XX%
- ml_model Memory: XXmb
- redis Memory: XXmb

### Notes
- [Any observations or notes]

### Approval
- Tested by: [Name]
- Approved by: [Name]
- Date: [DATE]
```

---

**Создано**: 2024-04-19  
**Версия**: 1.0  
**Статус**: ✅ Ready for Use  

**Следующий шаг**: Прочитай START_TESTING.md и запусти `bash scripts/run_all_tests.sh`
