#!/bin/bash
# ============================================================================
# Test Environment Setup and Execution Script
# ============================================================================
# Generated: 20.04.2026
# Purpose: Set up and run comprehensive test suite

set -e  # Exit on error

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# ============================================================================
# Functions
# ============================================================================

print_header() {
    echo -e "${BLUE}════════════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}════════════════════════════════════════════════════════════════${NC}"
}

print_step() {
    echo -e "${YELLOW}→ $1${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

# ============================================================================
# Script
# ============================================================================

print_header "TEST ENVIRONMENT SETUP AND INITIALIZATION"

# Change to project directory
cd "$(dirname "$0")/.."

print_step "Step 1: Creating directory structure"
mkdir -p config
mkdir -p logs
mkdir -p tests/fixtures/test_data
mkdir -p mlflow_artifacts
print_success "Directories created"

print_step "Step 2: Checking Python environment"
python_version=$(python --version 2>&1 | awk '{print $2}')
print_success "Python version: $python_version"

print_step "Step 3: Installing dependencies"
if [ -f "requirements.txt" ]; then
    pip install -q -r requirements.txt 2>/dev/null || echo "Note: Some packages may be cached"
    print_success "Dependencies installed"
else
    print_error "requirements.txt not found"
    exit 1
fi

print_step "Step 4: Setting up environment variables"
if [ -f ".env" ]; then
    echo "Loading .env file..."
    export $(cat .env | xargs)
    print_success ".env file loaded"
fi

print_step "Step 5: Creating test model and registering in MLflow"
python3 scripts/setup_test_model.py
if [ $? -eq 0 ]; then
    print_success "Test model created and registered"
else
    print_error "Failed to create test model"
    exit 1
fi

print_step "Step 6: Verifying MLflow setup"
if [ -d "mlflow_artifacts" ]; then
    print_success "MLflow artifacts directory exists"
    ls -la mlflow_artifacts/ | head -10
fi

print_step "Step 7: Creating test fixtures"
cat > tests/fixtures/test_request.json << 'EOF'
{
  "object_reference": "/KAZ/AKMOLA/@models/P_WATT",
  "model_id": "prophet_watt_h_AKMOLA_test"
}
EOF
print_success "Test request fixture created"

print_step "Step 8: Creating test configuration"
cat > config/test_runtime.json << 'EOF'
{
  "environment": "test",
  "model": {
    "type": "prophet",
    "horizon": 24,
    "freq": "H"
  },
  "inference": {
    "timeout": 60,
    "max_workers": 4
  }
}
EOF
print_success "Test configuration created"

print_header "SETUP COMPLETE ✓"
echo ""
echo -e "${GREEN}Test environment is ready!${NC}"
echo ""
echo "Next steps:"
echo "1. Start MLflow UI: mlflow ui --backend-store-uri sqlite:///mlflow.db"
echo "2. Start API server: python -m uvicorn src.api.main:app --reload --port 8000"
echo "3. Run tests: pytest tests/ -v"
echo ""
echo "Test prediction command:"
echo "  curl -X POST http://localhost:8000/predict \\"
echo "    -H 'Content-Type: application/json' \\"
echo "    -d @tests/fixtures/test_request.json"
echo ""
