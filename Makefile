.PHONY: help setup-test clean-test test mlflow-ui smoke-positive smoke-negative wait-api ml-model-status smoke-api train-xgb notebook-up notebook-logs notebook-down

MODEL_SERVICE ?= model-server
PREDICT_URL ?= http://localhost:8030/predict
PREDICT_MODELS_DIR ?= ../local/mlruns
TRAIN_MODELS_DIR ?= ../local/models
TRAIN_MODEL_ID ?= /xgb
TRAIN_LOOKBACK_DAYS ?= 30
PREDICT_MODEL_ID ?= root_FP_PROJECT_AKMOLA_VostVet_VES_models_P_watt
PREDICT_MODEL_RUN_ID ?= 3ec5decd466b40aea7623e46ed690e43
PREDICT_OBJECT_REFERENCE ?= /root/FP/PROJECT/AKMOLA/@regions/KOKSHETAU/Load/P_load/archives/out_value
PREDICT_CONFIG_FILE ?= $(PREDICT_MODELS_DIR)/$(PREDICT_MODEL_ID)/$(PREDICT_MODEL_RUN_ID)/bundle/configuration/cache_config.json
PREDICT_MAX_ATTEMPTS ?= 30
PREDICT_POLL_INTERVAL ?= 1

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
	@echo "  make mlflow-ui       - Start MLflow UI"
	@echo "  make test-predict    - Test 2-step async /predict flow"
	@echo "                         vars: PREDICT_URL, PREDICT_MODELS_DIR, PREDICT_MODEL_ID, PREDICT_OBJECT_REFERENCE"
	@echo "                               PREDICT_CONFIG_FILE (optional; defaults to cache_config.json)"
	@echo "                         example: make test-predict PREDICT_MODEL_ID=/xgb"
	@echo "  make logs            - Show recent logs"
	@echo "  make help            - Show this help message"
	@echo "  make train-xgb       - Fetch SCADA data and train XGBoost model"
	@echo "                         vars: TRAIN_MODELS_DIR (default: ../local/models), TRAIN_MODEL_ID (default: /xgb), TRAIN_LOOKBACK_DAYS (default: 30)"
	@echo "                         example: make train-xgb TRAIN_MODEL_ID=/xgb TRAIN_LOOKBACK_DAYS=60"
	@echo "  make notebook-up     - Start Jupyter Notebook Server service"
	@echo "  make notebook-logs   - Show Jupyter Notebook Server logs"
	@echo "  make notebook-down   - Stop Jupyter Notebook Server service"

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
	attempt=0; \
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
	@echo "🔍 Testing 2-step /predict flow..."
	@api_url="$(PREDICT_URL)"; \
	model_id="$(PREDICT_MODEL_ID)"; \
	model_dir="$(PREDICT_MODELS_DIR)/$$model_id"; \
	cache_config_file="$(PREDICT_CONFIG_FILE)"; \
	if [ ! -f "$$cache_config_file" ]; then \
		cache_config_file=$$(find "$(PREDICT_MODELS_DIR)" -type f -path "*/artifacts/bundle/configuration/cache_config.json" -print 2>/dev/null | head -n 1); \
	fi; \
	if [ ! -f "$$cache_config_file" ]; then \
		echo "cache_config.json not found. Checked explicit path: $(PREDICT_CONFIG_FILE) and MLflow tree under $(PREDICT_MODELS_DIR)"; \
		exit 1; \
	fi; \
	object_reference="$(PREDICT_OBJECT_REFERENCE)"; \
	if [ "$${SCADA_STUB_ENABLED:-true}" = "false" ]; then \
		object_reference=$$(/Users/rustamkrikbayev/Documents/projects/forecast/.venv/bin/python -c 'import json,sys; p=sys.argv[1]; d=json.load(open(p)); a=d.get("archives") or []; print(a[0] if a else "")' "$$cache_config_file" 2>/dev/null || true); \
		if [ -z "$$object_reference" ]; then \
			echo "Could not read archives[0] from $$cache_config_file"; \
			exit 1; \
		fi; \
		echo "Using object_reference from cache_config ($$cache_config_file): $$object_reference"; \
	fi; \
	payload="{\"object_reference\": \"$$object_reference\", \"model_id\": \"$$model_id\"}"; \
	echo "[1/2] Starting predict task..."; \
	start_resp=$$(curl -sS -X POST "$$api_url" -H "Content-Type: application/json" -d "$$payload"); \
	task_id=$$(echo "$$start_resp" | /Users/rustamkrikbayev/Documents/projects/forecast/.venv/bin/python -c 'import json,sys; print(json.load(sys.stdin).get("task_id", ""))' 2>/dev/null || true); \
	if [ -z "$$task_id" ]; then \
		echo "Failed to get task_id from start response:"; \
		echo "$$start_resp"; \
		exit 1; \
	fi; \
	echo "Task created: $$task_id"; \
	echo "[2/2] Polling task result..."; \
	attempt=0; \
	while [ $$attempt -lt $(PREDICT_MAX_ATTEMPTS) ]; do \
		poll_resp=$$(curl -sS -X POST "$$api_url" -H "Content-Type: application/json" -d "{\"task_id\": \"$$task_id\"}"); \
		status=$$(echo "$$poll_resp" | /Users/rustamkrikbayev/Documents/projects/forecast/.venv/bin/python -c 'import json,sys; print(json.load(sys.stdin).get("status", ""))' 2>/dev/null || true); \
		state=$$(echo "$$poll_resp" | /Users/rustamkrikbayev/Documents/projects/forecast/.venv/bin/python -c 'import json,sys; print(json.load(sys.stdin).get("state", ""))' 2>/dev/null || true); \
		if [ "$$status" = "200" ]; then \
			echo "✓ Predict completed (state=$$state)"; \
			echo "$$poll_resp" | /Users/rustamkrikbayev/Documents/projects/forecast/.venv/bin/python -m json.tool; \
			exit 0; \
		fi; \
		if [ "$$status" != "202" ]; then \
			echo "Predict failed with status=$$status:"; \
			echo "$$poll_resp"; \
			exit 1; \
		fi; \
		attempt=$$((attempt + 1)); \
		sleep $(PREDICT_POLL_INTERVAL); \
	done; \
	echo "Timeout waiting for predict task completion"; \
	exit 1

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

train-xgb:
	@echo "🏋️ Training XGBoost model for $(TRAIN_MODEL_ID) (lookback=$(TRAIN_LOOKBACK_DAYS)d)..."
	@/Users/rustamkrikbayev/Documents/projects/forecast/.venv/bin/python scripts/train_xgb.py \
		--model-dir $(abspath $(TRAIN_MODELS_DIR)/$(TRAIN_MODEL_ID)) \
		--lookback-days $(TRAIN_LOOKBACK_DAYS)

notebook-up:
	@echo "📓 Starting Jupyter Notebook Server..."
	@docker compose up -d jupyter-notebook-server
	@echo "✓ Jupyter Notebook is available on http://localhost:$${JUPYTER_PORT:-8888}"

notebook-logs:
	@echo "📝 Jupyter Notebook Server logs"
	@docker compose logs --no-color --tail=120 jupyter-notebook-server

notebook-down:
	@echo "🛑 Stopping Jupyter Notebook Server..."
	@docker compose stop jupyter-notebook-server

.env.test:
	@cp .env.test .env.test.bak 2>/dev/null || true
	@echo "✓ Environment configured"
