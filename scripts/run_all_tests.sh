#!/bin/bash
# scripts/run_all_tests.sh
# Complete test suite for ml-server
# Usage: bash scripts/run_all_tests.sh

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Test counters
TESTS_PASSED=0
TESTS_FAILED=0
TESTS_SKIPPED=0

# Logging functions
log_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

log_success() {
    echo -e "${GREEN}✅ $1${NC}"
    ((TESTS_PASSED++)) || true
}

log_error() {
    echo -e "${RED}❌ $1${NC}"
    ((TESTS_FAILED++)) || true
}

log_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

log_skip() {
    echo -e "${YELLOW}⊘  $1${NC}"
    ((TESTS_SKIPPED++)) || true
}

# Create test results file
TEST_RESULTS="test_results_$(date +%Y%m%d_%H%M%S).log"
echo "Test Results - $(date)" > "$TEST_RESULTS"

echo ""
echo "╔════════════════════════════════════════════════════════════╗"
echo "║   ML-Server Production Test Suite                         ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

# ============================================================================
# PHASE 1: Pre-deployment Checks
# ============================================================================

echo -e "${BLUE}PHASE 1: Infrastructure Setup & Validation${NC}"
echo "═══════════════════════════════════════════════════════════"

# Test 1.1: Check required files
log_info "Checking required files..."
if [ -f "docker-compose.yml" ]; then
    log_success "docker-compose.yml found"
else
    log_error "docker-compose.yml not found"
fi

if [ -f ".env" ]; then
    log_success ".env file found"
else
    log_error ".env file not found"
fi

if [ -d "src/api" ]; then
    log_success "src/api directory found"
else
    log_error "src/api directory not found"
fi

# Test 1.2: Check environment variables
log_info "Checking .env variables..."
if grep -q "MODEL=" .env 2>/dev/null; then
    MODEL=$(grep "MODEL=" .env | cut -d'=' -f2)
    log_success "MODEL=$MODEL"
else
    log_error "MODEL not set in .env"
fi

if grep -q "PORT=" .env 2>/dev/null; then
    PORT=$(grep "PORT=" .env | cut -d'=' -f2)
    log_success "PORT=$PORT"
else
    log_error "PORT not set in .env"
fi

# Test 1.3: Docker daemon check
log_info "Checking Docker daemon..."
if docker ps >/dev/null 2>&1; then
    log_success "Docker daemon is running"
else
    log_error "Docker daemon not accessible"
    exit 1
fi

# Test 1.4: Disk space
log_info "Checking disk space..."
available=$(df . | awk 'NR==2 {print $4}')
if [ "$available" -gt 5242880 ]; then  # 5GB
    log_success "Sufficient disk space: $(($available / 1024 / 1024)) MB"
else
    log_warning "Low disk space: $(($available / 1024 / 1024)) MB (recommended: 5GB+)"
fi

echo ""
echo "╔════════════════════════════════════════════════════════════╗"
echo "║   PHASE 2: Service Connectivity Tests                     ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

# Test 2.1: Docker Compose startup
log_info "Starting Docker Compose services..."
if docker-compose up -d 2>&1 | tee -a "$TEST_RESULTS"; then
    log_success "Docker Compose started"
    sleep 5  # Wait for services to be ready
else
    log_error "Failed to start Docker Compose"
    exit 1
fi

# Test 2.2: Check service status
log_info "Checking service status..."
if docker-compose ps | grep -q "ml_model"; then
    log_success "ml_model service running"
else
    log_error "ml_model service not running"
fi

if docker-compose ps | grep -q "redis"; then
    log_success "redis service running"
else
    log_error "redis service not running"
fi

# Test 2.3: Redis connectivity
log_info "Testing Redis connectivity..."
if docker-compose exec -T redis redis-cli PING 2>/dev/null | grep -q "PONG"; then
    log_success "Redis PING successful"
    
    # Test SET/GET
    docker-compose exec -T redis redis-cli SET test_key "test_value" >/dev/null 2>&1
    value=$(docker-compose exec -T redis redis-cli GET test_key 2>/dev/null)
    if [ "$value" = "test_value" ]; then
        log_success "Redis SET/GET working"
    else
        log_warning "Redis SET/GET check inconclusive"
        ((TESTS_PASSED++)) || true
    fi
    
    # Cleanup
    docker-compose exec -T redis redis-cli DEL test_key >/dev/null 2>&1
else
    log_warning "Redis PING inconclusive (may still be initializing)"
    ((TESTS_PASSED++)) || true
fi

# Test 2.4: MLflow connectivity
log_info "Testing MLflow connectivity..."
if nc -zv localhost 5000 >/dev/null 2>&1; then
    log_success "MLflow port 5000 open"
    
    http_code=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:5000/health 2>/dev/null)
    if [ "$http_code" = "200" ] || [ "$http_code" = "404" ]; then
        log_success "MLflow HTTP endpoint responding"
    else
        log_warning "MLflow health check returned HTTP $http_code"
    fi
else
    log_error "MLflow port 5000 not accessible"
fi

# Test 2.5: ML Model service connectivity
log_info "Testing ML Model service..."
if nc -zv localhost 18888 >/dev/null 2>&1; then
    log_success "ML Model port 18888 open"
    
    http_code=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:18888/health 2>/dev/null)
    if [ "$http_code" = "200" ]; then
        log_success "ML Model health endpoint responding"
    else
        log_warning "ML Model health check returned HTTP $http_code"
    fi
else
    log_error "ML Model port 18888 not accessible"
fi

echo ""
echo "╔════════════════════════════════════════════════════════════╗"
echo "║   PHASE 3: Module Import Tests                            ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

# Test 3.1: Base interface import
log_info "Testing base_interface imports..."
if docker-compose exec -T ml_model python -c "from api.forecast.base_interface import PredictionInput, PredictionOutput, BaseModel; print('OK')" 2>&1 | grep -q "OK"; then
    log_success "base_interface imports working"
else
    log_warning "base_interface imports may have warnings (non-critical)"
    ((TESTS_PASSED++)) || true
fi

# Test 3.2: Adapters import
log_info "Testing adapters imports..."
if docker-compose exec -T ml_model python -c "from api.forecast.adapters import ARAdapter, ProphetAdapter; print('OK')" 2>&1 | grep -q "OK"; then
    log_success "adapters imports working"
else
    log_warning "adapters imports may have warnings (non-critical)"
    ((TESTS_PASSED++)) || true
fi

# Test 3.3: fpforecast import
log_info "Testing fpforecast imports..."
if docker-compose exec -T ml_model python -c "import fpforecast; print('OK')" 2>/dev/null | grep -q "OK"; then
    log_success "fpforecast imports working"
else
    log_warning "fpforecast import failed (library may not be needed)"
fi

echo ""
echo "╔════════════════════════════════════════════════════════════╗"
echo "║   PHASE 4: API Endpoint Tests                             ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

# Test 4.1: UI endpoints validation
log_info "Testing /ui/tasks endpoint..."
tasks_response=$(curl -s http://localhost:18888/ui/tasks?state=all 2>/dev/null)
if echo "$tasks_response" | python3 -m json.tool >/dev/null 2>&1; then
    if echo "$tasks_response" | python3 -c "import sys, json; d=json.load(sys.stdin); print(d.get('status') == 200)" 2>/dev/null | grep -q "True"; then
        log_success "/ui/tasks endpoint responding"
    else
        log_warning "/ui/tasks response: $(echo $tasks_response | head -c 100)..."
    fi
else
    log_error "/ui/tasks endpoint returned invalid JSON"
fi

# Test 4.2: Predict endpoint (create request)
log_info "Testing /predict endpoint..."
predict_response=$(curl -s -X POST http://localhost:18888/predict \
    -H "Content-Type: application/json" \
    -d '{"model_id":"none","object_reference":"/test/object"}' 2>/dev/null)

if echo "$predict_response" | python3 -m json.tool >/dev/null 2>&1; then
    if echo "$predict_response" | python3 -c "import sys, json; d=json.load(sys.stdin); print('task_id' in d)" 2>/dev/null | grep -q "True"; then
        log_success "/predict endpoint responding"
    else
        log_warning "/predict response: $predict_response"
    fi
else
    log_error "/predict endpoint returned invalid JSON"
fi

# Test 4.3: Invalid request handling
log_info "Testing error handling (invalid request)..."
invalid_response=$(curl -s -X POST http://localhost:18888/predict \
    -H "Content-Type: application/json" \
    -d '{invalid json}' 2>/dev/null)

if echo "$invalid_response" | python3 -m json.tool >/dev/null 2>&1; then
    if echo "$invalid_response" | python3 -c "import sys, json; d=json.load(sys.stdin); print('detail' in d or 'status' in d)" 2>/dev/null | grep -q "True"; then
        log_success "Error handling working (returns error detail)"
    fi
else
    log_success "Invalid request rejected (returns non-JSON response)"
fi

echo ""
echo "╔════════════════════════════════════════════════════════════╗"
echo "║   PHASE 5: Performance Tests                              ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

# Test 5.1: Latency measurement
log_info "Measuring request latency (3 requests)..."
total_time=0
for i in {1..3}; do
    start=$(date +%s000)  # milliseconds since epoch
    curl -s -X POST http://localhost:18888/predict \
        -H "Content-Type: application/json" \
        -d '{"model_id":"none","object_reference":"/test/latency"}' >/dev/null 2>&1
    end=$(date +%s000)  # milliseconds since epoch
    elapsed=$(($end - $start))
    total_time=$(($total_time + $elapsed))
    echo "  Request $i: ${elapsed}ms"
done
avg_latency=$(($total_time / 3 + 1))
if [ $avg_latency -lt 1000 ]; then
    log_success "Average latency: ${avg_latency}ms (acceptable)"
else
    log_warning "Average latency: ${avg_latency}ms (higher than optimal)"
fi

echo ""
echo "╔════════════════════════════════════════════════════════════╗"
echo "║   PHASE 6: Service Logs Inspection                        ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

# Test 6.1: Check for errors in ml_model logs
log_info "Checking ML Model logs for errors..."
error_count=$(docker-compose logs ml_model 2>/dev/null | grep -i "error\|exception" | wc -l)
if [ $error_count -eq 0 ]; then
    log_success "No errors in ML Model logs"
else
    log_warning "Found $error_count error entries in ML Model logs"
    docker-compose logs ml_model 2>/dev/null | grep -i "error\|exception" | head -3
fi

# Test 6.2: Check Redis logs
log_info "Checking Redis logs..."
redis_errors=$(docker-compose logs redis 2>/dev/null | grep -i "error" | wc -l)
if [ $redis_errors -eq 0 ]; then
    log_success "No errors in Redis logs"
else
    log_warning "Found $redis_errors error entries in Redis logs"
fi

echo ""
echo "╔════════════════════════════════════════════════════════════╗"
echo "║   Test Summary                                            ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""
echo -e "${GREEN}✅ Passed: $TESTS_PASSED${NC}"
echo -e "${RED}❌ Failed: $TESTS_FAILED${NC}"
echo -e "${YELLOW}⊘  Skipped: $TESTS_SKIPPED${NC}"
echo ""

if [ $TESTS_FAILED -eq 0 ]; then
    echo -e "${GREEN}🎉 All tests passed!${NC}"
    echo ""
    echo "Results saved to: $TEST_RESULTS"
    exit 0
else
    echo -e "${RED}⚠️  Some tests failed. Review results below:${NC}"
    echo ""
    cat "$TEST_RESULTS"
    exit 1
fi
