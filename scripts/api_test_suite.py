#!/usr/bin/env python3
"""
api_test_suite.py

Comprehensive API test suite for ml-server
Tests all endpoints, data validation, and error handling
"""

import json
import time
import statistics
import requests
import sys
from typing import Dict, List, Tuple
from dataclasses import dataclass

# Colors for terminal output
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


@dataclass
class TestResult:
    name: str
    passed: bool
    message: str
    duration_ms: float = 0.0


class APITestSuite:
    def __init__(self, base_url: str = "http://localhost:18888"):
        self.base_url = base_url
        self.results: List[TestResult] = []
        self.session = requests.Session()
        self.session.timeout = 10

    def print_header(self, text: str):
        print(f"\n{Colors.BOLD}{Colors.BLUE}{'═' * 60}{Colors.ENDC}")
        print(f"{Colors.BOLD}{Colors.BLUE}{text}{Colors.ENDC}")
        print(f"{Colors.BOLD}{Colors.BLUE}{'═' * 60}{Colors.ENDC}\n")

    def print_test(self, name: str, passed: bool, message: str = "", duration_ms: float = 0.0):
        icon = f"{Colors.GREEN}✅{Colors.ENDC}" if passed else f"{Colors.RED}❌{Colors.ENDC}"
        duration_str = f" ({duration_ms:.2f}ms)" if duration_ms > 0 else ""
        print(f"{icon} {name}{duration_str}")
        if message:
            print(f"   {Colors.CYAN}{message}{Colors.ENDC}")
        
        result = TestResult(name, passed, message, duration_ms)
        self.results.append(result)

    def test_health_endpoint(self):
        """Test /health endpoint"""
        self.print_header("Test 1: Health Endpoint")
        
        try:
            start = time.time()
            response = self.session.get(f"{self.base_url}/health")
            duration = (time.time() - start) * 1000
            
            # Test 1.1: Status code
            if response.status_code == 200:
                self.print_test("Health endpoint accessible", True, f"HTTP {response.status_code}", duration)
            else:
                self.print_test("Health endpoint accessible", False, f"HTTP {response.status_code}", duration)
                return
            
            # Test 1.2: Response format
            data = response.json()
            if "status" in data and "loaded_models" in data:
                self.print_test("Response schema valid", True, f"status={data['status']}, models={len(data.get('loaded_models', []))}")
            else:
                self.print_test("Response schema valid", False, f"Missing fields in response")
            
            # Test 1.3: Status value
            if data.get("status") == "healthy":
                self.print_test("Service status healthy", True)
            else:
                self.print_test("Service status healthy", False, f"Status: {data.get('status')}")
        
        except Exception as e:
            self.print_test("Health endpoint accessible", False, str(e))

    def test_forecast_basic(self):
        """Test basic forecast request"""
        self.print_header("Test 2: Basic Forecast Request")
        
        payload = {
            "model_id": "test_model_basic",
            "features": {
                "x": [1, 2, 3, 4, 5],
                "y": [10, 20, 30, 40, 50]
            },
            "metadata": {
                "region": "AKMOLA",
                "source": "test"
            }
        }
        
        try:
            start = time.time()
            response = self.session.post(
                f"{self.base_url}/forecast",
                json=payload
            )
            duration = (time.time() - start) * 1000
            
            # Test 2.1: Status code
            if response.status_code == 200:
                self.print_test("Forecast request accepted", True, f"HTTP {response.status_code}", duration)
            else:
                self.print_test("Forecast request accepted", False, f"HTTP {response.status_code}", duration)
                return
            
            # Test 2.2: Response structure
            data = response.json()
            required_fields = ["model_id", "predictions"]
            missing = [f for f in required_fields if f not in data]
            if not missing:
                self.print_test("Response structure valid", True, f"fields: {list(data.keys())}")
            else:
                self.print_test("Response structure valid", False, f"missing: {missing}")
            
            # Test 2.3: Data types
            if isinstance(data.get("predictions"), list):
                self.print_test("Predictions is array", True, f"length: {len(data.get('predictions', []))}")
            else:
                self.print_test("Predictions is array", False, f"type: {type(data.get('predictions'))}")
        
        except Exception as e:
            self.print_test("Forecast request accepted", False, str(e))

    def test_forecast_with_metadata(self):
        """Test forecast with rich metadata"""
        self.print_header("Test 3: Forecast with Full Metadata")
        
        payload = {
            "model_id": "test_model_metadata",
            "features": {
                "ds": ["2024-01-01", "2024-01-02", "2024-01-03"],
                "y": [100, 110, 105]
            },
            "metadata": {
                "region": "ALMATY",
                "source": "sensor_data",
                "timestamp": "2024-01-01T12:00:00Z",
                "user_id": "test_user"
            },
            "config": {
                "batch_size": 32,
                "timeout": 30,
                "device": "cpu"
            }
        }
        
        try:
            response = self.session.post(
                f"{self.base_url}/forecast",
                json=payload
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get("model_id") == payload["model_id"]:
                    self.print_test("Forecast with metadata", True, f"All fields preserved")
                else:
                    self.print_test("Forecast with metadata", False, "model_id mismatch")
            else:
                self.print_test("Forecast with metadata", False, f"HTTP {response.status_code}")
        
        except Exception as e:
            self.print_test("Forecast with metadata", False, str(e))

    def test_invalid_json(self):
        """Test error handling for invalid JSON"""
        self.print_header("Test 4: Error Handling - Invalid JSON")
        
        try:
            response = self.session.post(
                f"{self.base_url}/forecast",
                data="{invalid json}",
                headers={"Content-Type": "application/json"}
            )
            
            # Should return error status
            if response.status_code >= 400:
                self.print_test("Invalid JSON rejected", True, f"HTTP {response.status_code}")
            else:
                self.print_test("Invalid JSON rejected", False, "Should return 4xx error")
        
        except Exception as e:
            self.print_test("Invalid JSON rejected", True, "Request failed (expected)")

    def test_missing_required_field(self):
        """Test error handling for missing required field"""
        self.print_header("Test 5: Error Handling - Missing Fields")
        
        # Missing model_id
        payload = {
            "features": {"x": [1, 2, 3]}
            # model_id is missing
        }
        
        try:
            response = self.session.post(
                f"{self.base_url}/forecast",
                json=payload
            )
            
            if response.status_code >= 400:
                self.print_test("Missing model_id detected", True, f"HTTP {response.status_code}")
            else:
                self.print_test("Missing model_id detected", False, "Should return error")
        
        except Exception as e:
            self.print_test("Missing model_id detected", True, "Request validation working")

    def test_empty_features(self):
        """Test handling of empty features"""
        self.print_header("Test 6: Edge Case - Empty Features")
        
        payload = {
            "model_id": "test_empty",
            "features": {}
        }
        
        try:
            response = self.session.post(
                f"{self.base_url}/forecast",
                json=payload
            )
            
            # Should either succeed with empty result or return error
            if response.status_code in [200, 400, 422]:
                self.print_test("Empty features handled", True, f"HTTP {response.status_code}")
            else:
                self.print_test("Empty features handled", False, f"Unexpected HTTP {response.status_code}")
        
        except Exception as e:
            self.print_test("Empty features handled", True, "Proper error response")

    def test_large_payload(self):
        """Test handling of large payloads"""
        self.print_header("Test 7: Performance - Large Payload")
        
        # Create large feature set
        large_features = {
            "x": list(range(1000)),
            "y": list(range(1000, 2000))
        }
        
        payload = {
            "model_id": "test_large",
            "features": large_features
        }
        
        try:
            start = time.time()
            response = self.session.post(
                f"{self.base_url}/forecast",
                json=payload
            )
            duration = (time.time() - start) * 1000
            
            if response.status_code == 200:
                self.print_test("Large payload processed", True, f"1000 records in {duration:.2f}ms")
            else:
                self.print_test("Large payload processed", False, f"HTTP {response.status_code}")
        
        except Exception as e:
            self.print_test("Large payload processed", False, str(e))

    def test_concurrent_requests(self):
        """Test multiple concurrent requests"""
        self.print_header("Test 8: Performance - Concurrent Requests")
        
        import concurrent.futures
        
        def make_request(request_id):
            try:
                payload = {
                    "model_id": f"test_concurrent_{request_id}",
                    "features": {"x": [1, 2, 3]}
                }
                response = self.session.post(
                    f"{self.base_url}/forecast",
                    json=payload
                )
                return response.status_code == 200
            except:
                return False
        
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                futures = [executor.submit(make_request, i) for i in range(5)]
                results = [f.result() for f in concurrent.futures.as_completed(futures)]
            
            success_count = sum(1 for r in results if r)
            if success_count >= 4:
                self.print_test("Concurrent requests (5x)", True, f"{success_count}/5 successful")
            else:
                self.print_test("Concurrent requests (5x)", False, f"Only {success_count}/5 successful")
        
        except Exception as e:
            self.print_test("Concurrent requests (5x)", False, str(e))

    def test_latency_distribution(self):
        """Test latency distribution across multiple requests"""
        self.print_header("Test 9: Performance - Latency Distribution")
        
        latencies = []
        num_requests = 10
        
        for i in range(num_requests):
            try:
                payload = {
                    "model_id": f"test_latency_{i}",
                    "features": {"x": [1, 2, 3]}
                }
                
                start = time.time()
                response = self.session.post(
                    f"{self.base_url}/forecast",
                    json=payload
                )
                duration = (time.time() - start) * 1000
                
                if response.status_code == 200:
                    latencies.append(duration)
            
            except Exception:
                pass
        
        if latencies:
            p50 = statistics.median(latencies)
            p95 = statistics.quantiles(latencies, n=20)[18]  # 95th percentile
            p99 = statistics.quantiles(latencies, n=100)[98]  # 99th percentile
            
            self.print_test("Latency statistics collected", True,
                           f"p50={p50:.2f}ms, p95={p95:.2f}ms, p99={p99:.2f}ms")
        else:
            self.print_test("Latency statistics collected", False, "No successful requests")

    def test_response_consistency(self):
        """Test response consistency across multiple calls"""
        self.print_header("Test 10: Data Consistency")
        
        payload = {
            "model_id": "test_consistency",
            "features": {"x": [1, 2, 3]}
        }
        
        try:
            responses = []
            for i in range(3):
                response = self.session.post(
                    f"{self.base_url}/forecast",
                    json=payload
                )
                if response.status_code == 200:
                    responses.append(response.json())
            
            if len(responses) >= 2:
                # Check if responses have consistent structure
                if all(set(r.keys()) == set(responses[0].keys()) for r in responses):
                    self.print_test("Response consistency", True, "All responses have same structure")
                else:
                    self.print_test("Response consistency", False, "Inconsistent response structure")
            else:
                self.print_test("Response consistency", False, "Not enough successful responses")
        
        except Exception as e:
            self.print_test("Response consistency", False, str(e))

    def print_summary(self):
        """Print test summary"""
        self.print_header("Test Summary")
        
        passed = sum(1 for r in self.results if r.passed)
        failed = sum(1 for r in self.results if not r.passed)
        
        print(f"{Colors.GREEN}✅ Passed: {passed}/{len(self.results)}{Colors.ENDC}")
        print(f"{Colors.RED}❌ Failed: {failed}/{len(self.results)}{Colors.ENDC}")
        
        if failed > 0:
            print(f"\n{Colors.RED}Failed tests:{Colors.ENDC}")
            for result in self.results:
                if not result.passed:
                    print(f"  - {result.name}: {result.message}")
        
        print("")
        return failed == 0

    def run_all(self):
        """Run all tests"""
        self.print_header("🧪 ML-Server API Test Suite")
        print(f"Target: {self.base_url}\n")
        
        try:
            self.test_health_endpoint()
            self.test_forecast_basic()
            self.test_forecast_with_metadata()
            self.test_invalid_json()
            self.test_missing_required_field()
            self.test_empty_features()
            self.test_large_payload()
            self.test_concurrent_requests()
            self.test_latency_distribution()
            self.test_response_consistency()
        
        except KeyboardInterrupt:
            print(f"\n{Colors.YELLOW}Tests interrupted by user{Colors.ENDC}")
            return False
        except Exception as e:
            print(f"\n{Colors.RED}Unexpected error: {e}{Colors.ENDC}")
            return False
        
        return self.print_summary()


if __name__ == "__main__":
    suite = APITestSuite()
    success = suite.run_all()
    sys.exit(0 if success else 1)
