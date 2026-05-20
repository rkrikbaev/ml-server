#!/bin/bash
# scripts/diagnose.sh
# Comprehensive diagnostic script for ml-server troubleshooting
# Usage: bash scripts/diagnose.sh

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# Diagnostic output file
DIAG_FILE="diagnostic_$(date +%Y%m%d_%H%M%S).log"

# Helper functions
print_header() {
    echo ""
    echo -e "${CYAN}╔════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║ $1${NC}"
    echo -e "${CYAN}╚════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo "╔════════════════════════════════════════════════════════════╗" >> "$DIAG_FILE"
    echo "║ $1" >> "$DIAG_FILE"
    echo "╚════════════════════════════════════════════════════════════╝" >> "$DIAG_FILE"
    echo "" >> "$DIAG_FILE"
}

print_section() {
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo "" >> "$DIAG_FILE"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" >> "$DIAG_FILE"
    echo "$1" >> "$DIAG_FILE"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" >> "$DIAG_FILE"
    echo "" >> "$DIAG_FILE"
}

pass() {
    echo -e "${GREEN}✅ $1${NC}"
    echo "✅ $1" >> "$DIAG_FILE"
}

fail() {
    echo -e "${RED}❌ $1${NC}"
    echo "❌ $1" >> "$DIAG_FILE"
}

warn() {
    echo -e "${YELLOW}⚠️  $1${NC}"
    echo "⚠️  $1" >> "$DIAG_FILE"
}

info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
    echo "ℹ️  $1" >> "$DIAG_FILE"
}

run_cmd() {
    echo -e "${CYAN}$ $1${NC}"
    echo "$ $1" >> "$DIAG_FILE"
    eval "$1" 2>&1 | tee -a "$DIAG_FILE" || true
    echo "" >> "$DIAG_FILE"
}

# ============================================================================
# MAIN DIAGNOSTICS
# ============================================================================

print_header "ML-Server Diagnostic Report"

echo "Diagnostic file: $DIAG_FILE"
echo "Diagnostic file: $DIAG_FILE" >> "$DIAG_FILE"
echo "Started: $(date)" >> "$DIAG_FILE"
echo ""

# ============================================================================
# 1. SYSTEM CHECKS
# ============================================================================

print_section "1. SYSTEM ENVIRONMENT"

info "Checking system information..."
run_cmd "uname -a"
run_cmd "docker --version"
run_cmd "docker-compose --version"
run_cmd "python3 --version"
run_cmd "bash --version | head -3"

# ============================================================================
# 2. CONFIGURATION CHECKS
# ============================================================================

print_section "2. CONFIGURATION FILES"

info "Checking .env file..."
if [ -f ".env" ]; then
    pass ".env file exists"
    run_cmd "cat .env"
else
    fail ".env file missing"
fi

info "Checking docker-compose.yml..."
if [ -f "docker-compose.yml" ]; then
    pass "docker-compose.yml exists"
    run_cmd "grep -E 'services|image|ports|environment' docker-compose.yml | head -30"
else
    fail "docker-compose.yml missing"
fi

# ============================================================================
# 3. DOCKER STATUS
# ============================================================================

print_section "3. DOCKER STATUS"

info "Checking Docker daemon..."
if docker ps >/dev/null 2>&1; then
    pass "Docker daemon is running"
else
    fail "Docker daemon not accessible"
    exit 1
fi

info "Checking running containers..."
run_cmd "docker ps --all"

info "Checking Docker networks..."
run_cmd "docker network ls"

# ============================================================================
# 4. SERVICE CONNECTIVITY
# ============================================================================

print_section "4. SERVICE CONNECTIVITY"

info "Checking Docker Compose services..."
run_cmd "docker-compose ps"

# Test Redis
info "Testing Redis connectivity..."
if docker-compose exec -T redis redis-cli PING 2>/dev/null | grep -q "PONG"; then
    pass "Redis PING successful"
    run_cmd "docker-compose exec -T redis redis-cli INFO server | head -10"
else
    fail "Redis PING failed"
    info "Checking Redis container logs..."
    run_cmd "docker-compose logs redis | tail -50"
fi

# Test MLflow
info "Testing MLflow connectivity..."
if curl -s http://localhost:5000/ >/dev/null 2>&1; then
    pass "MLflow HTTP endpoint accessible"
    run_cmd "curl -s http://localhost:5000/ | head -20"
else
    warn "MLflow HTTP endpoint not responding"
fi

# Test ML Model
info "Testing ML Model connectivity..."
if nc -z localhost 18888 2>/dev/null; then
    pass "ML Model port 18888 is open"
    if curl -s http://localhost:18888/health 2>/dev/null | grep -q "404\|status\|healthy"; then
        pass "ML Model responds to requests"
        run_cmd "curl -s http://localhost:18888/health | jq . 2>/dev/null || curl -s http://localhost:18888/health"
    else
        warn "ML Model responds but with unexpected format"
    fi
else
    fail "ML Model port 18888 is not accessible"
fi

# ============================================================================
# 5. PYTHON ENVIRONMENT
# ============================================================================

print_section "5. PYTHON ENVIRONMENT (In Container)"

info "Checking Python environment in ml_model container..."
run_cmd "docker-compose exec -T models_models python3 --version"

info "Checking Python path..."
run_cmd "docker-compose exec -T models_models python3 -c \"import sys; print('\\n'.join(sys.path))\""

info "Checking required packages..."
run_cmd "docker-compose exec -T models_models python3 -m pip list | grep -E 'fastapi|redis|mlflow|prophet|xgboost|numpy|pandas'"

# ============================================================================
# 6. MODULE IMPORTS
# ============================================================================

print_section "6. MODULE IMPORTS (In Container)"

info "Testing base_interface import..."
if docker-compose exec -T models_models python3 -c "from api.forecast.base_interface import PredictionInput, PredictionOutput" 2>/dev/null; then
    pass "base_interface import successful"
else
    fail "base_interface import failed"
    info "Checking if files exist in container..."
    run_cmd "docker-compose exec -T models_models find /workspace -name 'base_interface.py' 2>/dev/null || echo 'File not found'"
    run_cmd "docker-compose exec -T models_models ls -la /workspace/server/api/forecast/ 2>/dev/null || echo 'Directory not found'"
fi

info "Testing adapters import..."
if docker-compose exec -T models_models python3 -c "from api.forecast.adapters import ProphetAdapter, XGBoostAdapter" 2>/dev/null; then
    pass "adapters import successful"
else
    fail "adapters import failed"
    info "Checking if files exist in container..."
    run_cmd "docker-compose exec -T models_models find /workspace -name 'adapters.py' 2>/dev/null || echo 'File not found'"
fi

info "Testing fpforecast import..."
if docker-compose exec -T models_models python3 -c "from fpforecast import utils" 2>/dev/null; then
    pass "fpforecast import successful"
else
    warn "fpforecast import failed (may be optional)"
fi

# ============================================================================
# 7. VOLUME MOUNTS
# ============================================================================

print_section "7. VOLUME MOUNTS"

info "Checking volume mounts in container..."
run_cmd "docker-compose exec -T models_models mount | grep -E '/workspace|/models|/app'"

info "Checking accessible directories in container..."
run_cmd "docker-compose exec -T models_models ls -la /workspace/server/ 2>/dev/null || echo 'Directory not accessible'"
run_cmd "docker-compose exec -T models_models ls -la /workspace/lib/ 2>/dev/null || echo 'Directory not accessible'"
run_cmd "docker-compose exec -T models_models ls -la /models/ 2>/dev/null || echo 'Directory not accessible'"

# ============================================================================
# 8. API ENDPOINT TESTS
# ============================================================================

print_section "8. API ENDPOINT TESTS"

info "Testing /health endpoint..."
HEALTH_RESPONSE=$(curl -s -w "\n%{http_code}" http://localhost:18888/health 2>/dev/null || echo "Connection failed\n000")
HTTP_CODE=$(echo "$HEALTH_RESPONSE" | tail -1)
BODY=$(echo "$HEALTH_RESPONSE" | head -n -1)

echo "HTTP Status: $HTTP_CODE" | tee -a "$DIAG_FILE"
echo "Response body:" | tee -a "$DIAG_FILE"
echo "$BODY" | tee -a "$DIAG_FILE"

if [ "$HTTP_CODE" = "200" ]; then
    pass "Health endpoint returned 200"
elif [ "$HTTP_CODE" = "404" ]; then
    fail "Health endpoint returned 404 - endpoint not found"
else
    warn "Health endpoint returned $HTTP_CODE"
fi

info "Testing /forecast endpoint with sample data..."
FORECAST_REQUEST='{
  "features": [1.0, 2.0, 3.0],
  "timestamps": ["2024-01-01", "2024-01-02", "2024-01-03"]
}'

FORECAST_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST \
  -H "Content-Type: application/json" \
  -d "$FORECAST_REQUEST" \
  http://localhost:18888/forecast 2>/dev/null || echo "Connection failed\n000")

HTTP_CODE=$(echo "$FORECAST_RESPONSE" | tail -1)
BODY=$(echo "$FORECAST_RESPONSE" | head -n -1)

echo "HTTP Status: $HTTP_CODE" | tee -a "$DIAG_FILE"
echo "Response body:" | tee -a "$DIAG_FILE"
echo "$BODY" | tee -a "$DIAG_FILE"

if [ "$HTTP_CODE" = "200" ]; then
    pass "Forecast endpoint responded"
elif [ "$HTTP_CODE" = "404" ]; then
    fail "Forecast endpoint returned 404"
else
    warn "Forecast endpoint returned $HTTP_CODE"
fi

# ============================================================================
# 9. SERVICE LOGS
# ============================================================================

print_section "9. SERVICE LOGS (Last 100 lines each)"

info "ML Model service logs..."
run_cmd "docker-compose logs models_models | tail -100"

info "Redis service logs..."
run_cmd "docker-compose logs redis | tail -50"

info "MLflow service logs..."
run_cmd "docker-compose logs mlflow | tail -50"

# ============================================================================
# 10. ERRORS AND WARNINGS
# ============================================================================

print_section "10. ERROR ANALYSIS"

info "Searching for ERROR entries in all logs..."
run_cmd "docker-compose logs | grep -i error | head -20"

info "Searching for CRITICAL entries..."
run_cmd "docker-compose logs | grep -i critical || echo 'No critical entries found'"

# ============================================================================
# 11. FILE SYSTEM CHECKS
# ============================================================================

print_section "11. LOCAL FILE SYSTEM"

info "Checking required directories..."
for dir in "src/api" "src/api/forecast" "models" "scripts"; do
    if [ -d "$dir" ]; then
        pass "$dir directory exists"
        run_cmd "ls -la $dir/ | head -10"
    else
        fail "$dir directory missing"
    fi
done

info "Checking required files..."
for file in "docker-compose.yml" ".env" "requirements.txt"; do
    if [ -f "$file" ]; then
        pass "$file exists"
    else
        fail "$file missing"
    fi
done

# ============================================================================
# 12. DISK AND MEMORY
# ============================================================================

print_section "12. DISK AND MEMORY"

info "Disk space usage..."
run_cmd "df -h | grep -E 'Filesystem|/'"

info "Docker disk usage..."
run_cmd "docker system df"

info "Container resource usage..."
run_cmd "docker stats --no-stream"

# ============================================================================
# 13. NETWORK DIAGNOSTICS
# ============================================================================

print_section "13. NETWORK DIAGNOSTICS"

info "Testing inter-container communication..."
run_cmd "docker-compose exec -T models_models curl -s -o /dev/null -w '%{http_code}' http://redis:6379 2>&1 || echo 'Redis connectivity test'"
run_cmd "docker-compose exec -T models_models python3 -c \"import socket; socket.create_connection(('redis', 6379), timeout=2)\" 2>&1 && echo 'Redis socket connection successful' || echo 'Redis socket connection failed'"

info "Checking DNS resolution in container..."
run_cmd "docker-compose exec -T models_models nslookup redis 2>/dev/null || echo 'nslookup not available'"
run_cmd "docker-compose exec -T models_models getent hosts redis 2>/dev/null || echo 'getent not available'"

# ============================================================================
# 14. SUMMARY AND RECOMMENDATIONS
# ============================================================================

print_section "14. DIAGNOSTIC SUMMARY"

echo "" | tee -a "$DIAG_FILE"
echo "════════════════════════════════════════════════════════════" | tee -a "$DIAG_FILE"
echo "ISSUES FOUND:" | tee -a "$DIAG_FILE"
echo "════════════════════════════════════════════════════════════" | tee -a "$DIAG_FILE"
echo "" | tee -a "$DIAG_FILE"

# Check for common issues
ISSUES=0

if ! docker-compose exec -T redis redis-cli PING 2>/dev/null | grep -q "PONG"; then
    echo "1. Redis connectivity issue:" | tee -a "$DIAG_FILE"
    echo "   - Redis container may not be running or responding" | tee -a "$DIAG_FILE"
    echo "   - Fix: docker-compose restart redis && sleep 3" | tee -a "$DIAG_FILE"
    echo "" | tee -a "$DIAG_FILE"
    ((ISSUES++))
fi

if docker-compose exec -T models_models python3 -c "from api.forecast.base_interface import PredictionInput" 2>/dev/null; then
    echo "2. Missing base_interface module:" | tee -a "$DIAG_FILE"
    echo "   - File src/api/forecast/base_interface.py not found or PYTHONPATH not set" | tee -a "$DIAG_FILE"
    echo "   - Fix: Create the module or check PYTHONPATH in docker-compose.yml" | tee -a "$DIAG_FILE"
    echo "" | tee -a "$DIAG_FILE"
    ((ISSUES++))
fi

if ! curl -s http://localhost:18888/health >/dev/null 2>&1; then
    echo "3. ML Model API not responding:" | tee -a "$DIAG_FILE"
    echo "   - /health endpoint returns 404 or is not accessible" | tee -a "$DIAG_FILE"
    echo "   - Fix: Check application startup and endpoint configuration" | tee -a "$DIAG_FILE"
    echo "" | tee -a "$DIAG_FILE"
    ((ISSUES++))
fi

if [ $ISSUES -eq 0 ]; then
    echo -e "${GREEN}✅ No major issues detected!${NC}" | tee -a "$DIAG_FILE"
else
    echo -e "${YELLOW}⚠️  Found $ISSUES issue(s) to fix${NC}" | tee -a "$DIAG_FILE"
fi

echo "" | tee -a "$DIAG_FILE"
echo "════════════════════════════════════════════════════════════" | tee -a "$DIAG_FILE"
echo "RECOMMENDATIONS:" | tee -a "$DIAG_FILE"
echo "════════════════════════════════════════════════════════════" | tee -a "$DIAG_FILE"
echo "" | tee -a "$DIAG_FILE"
echo "1. Review the full diagnostic log: $DIAG_FILE" | tee -a "$DIAG_FILE"
echo "2. Check container logs: docker-compose logs -f" | tee -a "$DIAG_FILE"
echo "3. Verify all environment variables: cat .env" | tee -a "$DIAG_FILE"
echo "4. Ensure all volumes are correctly mounted" | tee -a "$DIAG_FILE"
echo "5. Test connectivity from inside container:" | tee -a "$DIAG_FILE"
echo "   docker-compose exec -T models_models bash" | tee -a "$DIAG_FILE"
echo "6. Check Python path in container:" | tee -a "$DIAG_FILE"
echo "   docker-compose exec -T models_models python3 -c \"import sys; print(sys.path)\"" | tee -a "$DIAG_FILE"
echo "" | tee -a "$DIAG_FILE"

echo ""
echo -e "${GREEN}Diagnostic complete!${NC}"
echo "Full report saved to: ${CYAN}$DIAG_FILE${NC}"
echo ""
echo "════════════════════════════════════════════════════════════"
echo "Quick commands to view results:"
echo "════════════════════════════════════════════════════════════"
echo "View full report:     cat $DIAG_FILE"
echo "View only errors:     grep '❌' $DIAG_FILE"
echo "View recommendations: tail -30 $DIAG_FILE"
echo ""
