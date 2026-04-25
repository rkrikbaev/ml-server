.PHONY: help setup-test clean-test test run-api mlflow-ui smoke-positive smoke-negative wait-api

help:
	@echo "🚀 ML-Server Test Environment Management"
	@echo ""
	@echo "Available commands:"
	@echo "  make setup-test      - Set up test environment and model"
	@echo "  make clean-test      - Clean test artifacts and data"
	@echo "  make test            - Run test suite"
	@echo "  make smoke-positive  - Recreate ml_model with SCADA stub and run positive smoke test"
	@echo "  make smoke-negative  - Recreate ml_model without SCADA stub and run negative smoke test"
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
	@pytest tests/ -v

smoke-positive:
	@echo "🧪 Running positive predict smoke test with SCADA stub enabled..."
	@SCADA_STUB_ENABLED=true docker compose up -d --force-recreate ml_model
	@$(MAKE) wait-api
	@/Users/rustamkrikbayev/Documents/projects/forecast/.venv/bin/python -m pytest tests/test_predict_smoke.py -v

smoke-negative:
	@echo "🧪 Running negative predict smoke test with SCADA stub disabled..."
	@SCADA_STUB_ENABLED=false docker compose up -d --force-recreate ml_model
	@$(MAKE) wait-api
	@/Users/rustamkrikbayev/Documents/projects/forecast/.venv/bin/python -m pytest tests/test_predict_negative_smoke.py -v

wait-api:
	@echo "⏳ Waiting for API to accept connections on http://localhost:18888..."
	@attempt=0; \
	until curl -sS -o /dev/null http://localhost:18888/predict; do \
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

install-deps:
	@echo "📦 Installing dependencies..."
	@pip install -r requirements.txt

.env.test:
	@cp .env.test .env.test.bak 2>/dev/null || true
	@echo "✓ Environment configured"
