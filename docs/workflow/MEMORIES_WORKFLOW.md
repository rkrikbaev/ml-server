# WORKFLOW: План документа на уровне кода

Цель: подготовить структуру для подробного пошагового описания полного workflow сервиса на уровне функций, модулей и переходов данных.

## 1. Область документа

- Что покрываем: путь запроса от входа в API до финального ответа и мониторинга.
- Что не покрываем: бизнес-обоснование моделей и обучение (вынесено в training-документацию).
- Артефакты: API, broker/worker, inference pipeline, обработка ошибок, тестовые сценарии.

## 2. Формат будущего пошагового описания

Для каждого шага в финальной версии использовать единый шаблон:

- Цель шага.
- Точка входа (endpoint/функция).
- Входные данные и валидация.
- Вызовы внутри шага (кто кого вызывает).
- Выход/состояние/HTTP-код.
- Ошибки и fallback-поведение.
- Как проверить шаг (команда/запрос).

## 3. Основные этапы workflow (каркас документа)

### Этап 0. Инициализация приложения и инфраструктуры

- Поднять FastAPI и lifecycle startup/shutdown.
- Подключить broker и result backend.
- Проверить режимы Redis/InMemory.
- Ключевые точки кода:
	- src/api/server.py -> lifespan
	- src/api/broker/broker.py -> broker, result_backend

### Этап 1. Прием запроса `/predict` (create-ветка)

- Разобрать входной payload через дискриминатор схем.
- Провалидировать `model_id` и `object_reference`.
- Определить online/offline режим.
- Ключевые точки кода:
	- src/api/server.py -> process_data
	- src/api/data/predict.py -> PredictCreateSchema, predict_discriminator

### Этап 2. Постановка задачи в очередь

- Вызвать `api_predict.kiq(...)`.
- Зафиксировать задачу в task monitor.
- Вернуть `202 START` + `task_id`.
- Ключевые точки кода:
	- src/api/server.py -> process_data (1st run)
	- src/api/broker/broker.py -> api_predict
	- src/api/message.py -> accepted_start, to_json_response

### Этап 3. Выполнение worker-задачи

- Войти в `predict_logic` и подготовить общий контекст выполнения.
- Загрузить конфиг модели по `model_id`.
- Подготовить рабочие параметры `step` (мс), `input_range`, `output_range` из runtime-конфига.
- Ключевые точки кода:
	- src/api/broker/tasks/predict.py -> logic
	- src/api/forecast/* -> load_model_config

### Этап 4. Сбор входных данных для инференса

- Загрузить historical data.
- Опционально загрузить weather payload.
- Опционально загрузить CMMS planned adjustments.
- Обработать ошибки внешних источников и деградацию.
- Ключевые точки кода:
	- src/api/broker/tasks/predict.py -> _get_historical_data_payload
	- src/api/broker/tasks/predict.py -> _get_weather_payload
	- src/api/broker/tasks/predict.py -> _get_planned_adjustments
	- src/api/collector/*

### Этап 5. Инициализация модели и расчет прогноза

- Инициализировать адаптер модели.
- Подготовить prediction input.
- Выполнить `predict(...)` и получить `preds/pred_ts`.
- Ключевые точки кода:
	- src/api/broker/tasks/predict.py -> init_model, predict
	- src/api/forecast/inference.py -> predict
	- src/api/forecast/adapters.py

### Этап 6. Постобработка, качество и формирование результата

- Применить CMMS-корректировки к прогнозу.
- Оценить QDS входа.
- Сформировать результирующий payload и статистику.
- Вернуть `200/422/500` как результат задачи.
- Ключевые точки кода:
	- src/api/broker/tasks/predict.py -> _apply_planned_adjustments
	- src/api/broker/tasks/predict.py -> _build_result
	- src/api/message.py -> ok_done / unprocessable_entity_* / internal_server_error

### Этап 7. Polling-ветка `/predict` (update-ветка)

- Принять `task_id`.
- Проверить готовность результата.
- Если не готово: вернуть `202 PROCESSING`.
- Если готово: получить result backend payload и вернуть `DONE`.
- Ключевые точки кода:
	- src/api/server.py -> process_data (2nd run)
	- src/api/message.py -> accepted_processing, to_json_response

### Этап 8. Мониторинг и UI-эндпоинты

- История задач, фильтрация и детализация.
- Список моделей и runtime статус.
- Связь с task monitor и analytics.
- Ключевые точки кода:
	- src/api/server.py -> /ui/tasks, /ui/models, /ui/runtime-status
	- src/api/task_monitor.py

### Этап 9. Обработка ошибок и контракт статусов

- Глобальные обработчики 404/422.
- Единые структуры ответов (`status`, `state`, `task_id`).
- Матрица соответствия ошибок и HTTP-кодов.
- Ключевые точки кода:
	- src/api/server.py -> exception handlers
	- src/api/message.py -> HTTPStatuses, HTTPState, HTTPMessages

### Этап 10. Окружение, конфигурация и зависимости

- Docker Compose сервисы и их роли.
- Переменные окружения и пути моделей.
- Режимы тестирования (`TEST_MODE`, `USE_IN_MEMORY_BROKER`).
- Ключевые точки кода/конфига:
	- docker-compose.yml
	- src/api/config.py
	- src/api/broker/broker.py

### Этап 11. Проверка workflow через тесты

- Базовый test suite.
- Smoke тесты для позитивного/негативного сценария.
- Проверка двухшагового `/predict` через make target.
- Основные команды:
	- make test
	- make smoke-positive
	- make smoke-negative
	- make test-predict PREDICT_MODEL_ID=<model_id>

## 4. Чеклист готовности финальной версии документа

- Для каждого этапа есть sequence: вход -> вызовы -> выход.
- Для каждого этапа есть минимум один воспроизводимый способ проверки.
- Все статусы и переходы `START -> PROCESSING -> DONE` описаны без пробелов.
- Указаны точки расширения (где добавлять новые источники данных/модели).
- Содержание синхронизировано с docs/API и текущей реализацией в src/api.

## 5. Следующий шаг

На базе этого плана заполнить каждый этап детальным пошаговым описанием на уровне кода, с примерами payload и ожидаемыми ответами для каждой ветки.
