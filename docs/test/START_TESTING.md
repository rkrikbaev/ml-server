# 🧪 START HERE — Production Testing Quick Start

**Время выполнения**: 15-30 минут  
**Требования**: Docker, Python 3.7+, curl

---

## ⚡ Быстрый старт (3 команды)

```bash
# 1. Перейти в ml-server
cd /Users/rustamkrikbayev/Documents/projects/forecast/ml-server

# 2. Запустить все тесты
bash scripts/run_all_tests.sh

# 3. Запустить API тесты (если первые прошли)
python3 scripts/api_test_suite.py
```

**Ожидаемое время**: 5-10 минут  
**Успех**: Все тесты зелёные ✅

---

## 📊 Интерпретация результатов

### ✅ Если видите это:
```
═══════════════════════════════════════════════════════════
Test Summary
═══════════════════════════════════════════════════════════
✅ Passed: 45/45
❌ Failed: 0/45

🎉 All tests passed!
```

**Действие**: Готово к production! 🚀

---

### ⚠️ Если видите это:
```
✅ Passed: 42/45
❌ Failed: 3/45
```

**Действие**: Прочитать failed тесты и применить fix из таблицы ниже

---

## 🔧 Быстрые Fix'ы

| Ошибка | Команда для Fix |
|--------|-----------------|
| `Redis port 6379 not accessible` | `docker-compose restart redis && sleep 3` |
| `ML Model port 18888 not accessible` | `docker-compose restart ml_model && sleep 5` |
| `PYTHONPATH import error` | Проверить docker-compose.yml: `PYTHONPATH=/workspace/server:/workspace/lib` |
| `Model directory not found` | Проверить абсолютные пути в docker-compose.yml volumes |
| `HTTP 422 validation error` | Проверить JSON в тестовом запросе (обязательные поля) |

---

## 📈 Пошаговый процесс

### Шаг 1: Стартовые проверки (1 минута)
```bash
# Проверить Docker
docker ps
docker-compose --version

# Проверить .env файл
cat .env | grep MODEL
cat .env | grep PORT

# Ожидаемый результат:
# MODEL=models
# PORT=18888
```

### Шаг 2: Запустить Docker Compose (2-3 минуты)
```bash
docker-compose up -d

# Проверить статус
docker-compose ps

# Ожидаемый результат:
# NAME        STATE    PORTS
# ml_model    running  18888:8000
# redis       running  6379:6379
# mlflow      running  5000:5000
```

### Шаг 3: Быстрая проверка (30 секунд)
```bash
# Health check
curl http://localhost:18888/health | jq '.'

# Ожидаемый результат:
# {
#   "status": "healthy",
#   "loaded_models": []
# }
```

### Шаг 4: Запустить полный тест (5-10 минут)
```bash
bash scripts/run_all_tests.sh

# Ожидаемый результат: 0 Failed, XXX Passed
```

### Шаг 5: API тесты (2-3 минуты)
```bash
python3 scripts/api_test_suite.py

# Ожидаемый результат: все зелёные ✅
```

---

## 🎯 Что тестируется?

| Тест | Описание | Важность |
|------|---------|----------|
| Health Endpoint | Проверка /health | 🔴 CRITICAL |
| Forecast Basic | Базовый forecast запрос | 🔴 CRITICAL |
| Redis Connectivity | Redis доступен | 🔴 CRITICAL |
| MLflow Connectivity | MLflow доступен | 🟡 HIGH |
| Module Imports | Python modules загружаются | 🔴 CRITICAL |
| Large Payload | Обработка 1000+ records | 🟡 HIGH |
| Concurrent Requests | 5+ одновременных запросов | 🟡 HIGH |
| Error Handling | Invalid JSON rejected | 🟡 HIGH |
| Latency | Response < 500ms | 🟢 MEDIUM |

---

## 📋 Быстрый контрольный список

```
Перед запуском тестов:
  ☐ Docker daemon запущен (docker ps работает)
  ☐ .env файл существует и заполнен
  ☐ Достаточно памяти (min 4GB, рекомендуется 8GB)
  ☐ Достаточно дискового пространства (min 5GB)

Во время тестов:
  ☐ Не запускать другие сервисы на портах 18888, 6379, 5000
  ☐ Не перезагружать систему

После тестов:
  ☐ Проверить test_results_*.log
  ☐ Если Failed > 0, применить fixes
  ☐ Если Failed = 0, ГОТОВО К PRODUCTION
```

---

## 🆘 Если что-то сломалось

### Вариант 1: Сервис не запускается
```bash
# Посмотреть логи
docker-compose logs ml_model | tail -50

# Перезагрузить контейнер
docker-compose down
docker-compose up -d
sleep 5

# Повторить тесты
bash scripts/run_all_tests.sh
```

### Вариант 2: Import ошибка (api.forecast)
```bash
# Проверить что находится в контейнере
docker-compose exec -T ml_model ls -la /workspace/server/api/

# Проверить PYTHONPATH
docker-compose exec -T ml_model python -c "import sys; print(sys.path)"

# Ожидаемый результат: должны быть /workspace/server и /workspace/lib
```

### Вариант 3: Redis не отвечает
```bash
# Проверить Redis в контейнере
docker-compose exec redis redis-cli PING

# Если не работает, перезагрузить
docker-compose restart redis
sleep 3

# Повторить тесты
bash scripts/run_all_tests.sh
```

### Вариант 4: Порт уже занят
```bash
# Узнать что занимает порт
lsof -i :18888
lsof -i :6379
lsof -i :5000

# Завершить процесс или изменить PORT в .env
# Потом переделать: docker-compose up -d
```

---

## 📚 Дальнейшие документы

Для более подробной информации:

- **`PRODUCTION_TEST_PLAN.md`** — полный план с 6 фазами тестирования
- **`TESTING_EXECUTION_GUIDE.md`** — подробный гайд по каждому тесту
- **`docs/INDEX.md`** — навигация по всей документации

---

## ✅ Успех!

Если все тесты прошли:

```bash
# 1. Сохранить результаты
cp test_results_*.log archives/prod_test_$(date +%Y%m%d).log

# 2. Проверить логи на ошибки
docker-compose logs | grep -i error

# 3. Готово!
echo "✅ Ready for Production Deployment!"
```

---

## 📞 Support

**Если нужна помощь:**

1. Проверить таблицу Quick Fix выше ☝️
2. Прочитать TESTING_EXECUTION_GUIDE.md
3. Собрать диагностику:
   ```bash
   docker-compose logs > diagnostic.log
   docker ps -a > containers.txt
   cat .env > config.txt
   ```

---

**Last Updated**: 2024-04-19  
**Версия**: 1.0  
**Статус**: Ready to Use ✅

**Следующий шаг**: `bash scripts/run_all_tests.sh`
