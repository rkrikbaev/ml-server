.PHONY: help setup-test clean-test test run-api mlflow-ui smoke-positive smoke-negative wait-api ml-model-status smoke-api

MODEL_SERVICE ?= model-server

help:
	@echo "🚀 ML-Server Test Environment Management"
	@echo ""
	@echo "Available commands:"
	@echo "  make setup-test      - Set up test environment and model"
	@echo "  make clean-test      - Clean test artifacts and data"
	@echo "  make test            - Run test suite"
	@echo "  make smoke-positive  - Recreate model service with SCADA stub and run positive smoke test"
	@echo "  make smoke-negative  - Recreate model service without SCADA stub and run negative smoke test"
	@echo "  make ml-model-status - Show model service container status and recent logs"
	@echo "  make smoke-api       - Check /ui/runtime-status on mapped model service port"
	@echo "  make run-api         - Start API server"
	@echo "  make mlflow-ui       - Start MLflow UI"
	@echo "  make test-predict    - Test prediction endpoint"
	@echo "  make logs            - Show recent logs"
	@echo "  make help            - Show this help message"

setup-test:
	@echo "⚙️  Setting up test environment..."
	@bash scripts/setup_test_env.sh

clean-test:
	@echo "🧹 Cleaning test artifacts..."
	@rm -rf mlflow_artifacts mlflow.db logs/*.log tests/fixtures/test_data/*
	@echo "✓ Test artifacts cleaned"

test:
	@echo "🧪 Running test suite..."
	@pytest tests/ -v --ignore=tests/test_predict_smoke.py --ignore=tests/test_predict_negative_smoke.py

smoke-positive:
	@echo "🧪 Running positive predict smoke test with SCADA stub enabled..."
	@SCADA_STUB_ENABLED=true docker compose up -d --force-recreate $(MODEL_SERVICE)
	@$(MAKE) wait-api
	@/Users/rustamkrikbayev/Documents/projects/forecast/.venv/bin/python -m pytest tests/test_predict_smoke.py -v

smoke-negative:
	@echo "🧪 Running negative predict smoke test with SCADA stub disabled..."
	@SCADA_STUB_ENABLED=false docker compose up -d --force-recreate $(MODEL_SERVICE)
	@$(MAKE) wait-api
	@/Users/rustamkrikbayev/Documents/projects/forecast/.venv/bin/python -m pytest tests/test_predict_negative_smoke.py -v

wait-api:
	@port=$$(docker compose port $(MODEL_SERVICE) 8000 2>/dev/null | awk -F: '{print $$NF}'); \
	if [ -z "$$port" ]; then \
		echo "Could not determine mapped port for $(MODEL_SERVICE). Is it running?"; \
		exit 1; \
	fi; \
	echo "⏳ Waiting for API to accept connections on http://localhost:$$port..."; \
	@attempt=0; \
	until curl -sS -o /dev/null "http://localhost:$$port/predict"; do \
		attempt=$$((attempt + 1)); \
		if [ $$attempt -ge 30 ]; then \
			echo "API did not become ready in time"; \
			exit 1; \
		fi; \
		sleep 1; \
	done; \
	echo "✓ API is ready"

test-predict:
	@echo "🔍 Testing prediction endpoint..."
	@curl -X POST http://localhost:8000/predict \
		-H "Content-Type: application/json" \
		-d '{"object_reference": "/KAZ/AKMOLA/@models/P_WATT", "model_id": "prophet_watt_h_AKMOLA_test"}'

run-api:
	@echo "🚀 Starting API server..."
	@python3 -m uvicorn src.api.main:app --reload --port 8000

mlflow-ui:
	@echo "📊 Starting MLflow UI..."
	@mlflow ui --backend-store-uri sqlite:///mlflow.db

logs:
	@tail -f logs/test.log 2>/dev/null || echo "No logs found. Run setup-test first."

ml-model-status:
	@echo "📦 $(MODEL_SERVICE) container status"
	@docker compose ps $(MODEL_SERVICE)
	@echo ""
	@echo "📝 $(MODEL_SERVICE) recent logs"
	@docker compose logs --no-color --tail=80 $(MODEL_SERVICE)

smoke-api:
	@echo "🔎 Running API smoke check for $(MODEL_SERVICE) (/ui/runtime-status)..."
	@port=$$(docker compose port $(MODEL_SERVICE) 8000 2>/dev/null | awk -F: '{print $$NF}'); \
	if [ -z "$$port" ]; then \
		echo "Could not determine mapped port for $(MODEL_SERVICE). Is it running?"; \
		exit 1; \
	fi; \
	attempt=0; \
	code="000"; \
	until [ "$$code" = "200" ] || [ $$attempt -ge 30 ]; do \
		code=$$(curl -sS -o /tmp/ml_model_runtime_status.json -w "%{http_code}" "http://localhost:$$port/ui/runtime-status" || true); \
		if [ "$$code" = "200" ]; then \
			break; \
		fi; \
		attempt=$$((attempt + 1)); \
		sleep 1; \
	done; \
	if [ "$$code" != "200" ]; then \
		echo "Smoke check failed: expected HTTP 200, got $$code"; \
		cat /tmp/ml_model_runtime_status.json 2>/dev/null || true; \
		exit 1; \
	fi; \
	echo "✓ Smoke check passed on http://localhost:$$port/ui/runtime-status"

install-deps:
	@echo "📦 Installing dependencies..."
	@pip install -r requirements.txt

.env.test:
	@cp .env.test .env.test.bak 2>/dev/null || true
	@echo "✓ Environment configured"
