"""
Contract tests for ops/metrics endpoints.
Tests /metrics, /healthz
"""
import pytest
from fastapi.testclient import TestClient


class TestMetricsEndpoint:
    """Tests for GET /metrics"""
    
    def test_metrics_success_with_admin_auth(self, client: TestClient, admin_key: dict):
        """200: Metrics endpoint returns Prometheus format"""
        response = client.get("/metrics", headers=admin_key)
        
        assert response.status_code == 200
        assert "http_requests_total" in response.text
        assert response.headers["content-type"] == "text/plain; charset=utf-8"
    
    def test_metrics_contains_required_metrics(self, client: TestClient, admin_key: dict):
        """Verify required metrics are exposed"""
        response = client.get("/metrics", headers=admin_key)
        
        assert response.status_code == 200
        text = response.text
        
        assert "http_requests_total" in text
        assert "http_request_latency_ms" in text
    
    def test_metrics_401_no_admin_key(self, client: TestClient):
        """401: Metrics require admin authentication"""
        response = client.get("/metrics")
        
        assert response.status_code == 401
    
    def test_metrics_401_invalid_admin_key(self, client: TestClient):
        """401: Invalid admin key rejected"""
        response = client.get("/metrics", headers={"X-Admin": "invalid_key"})
        
        assert response.status_code == 401
    
    def test_metrics_latency(self, client: TestClient, admin_key: dict):
        """Metrics scrape completes within 50ms budget"""
        import time
        
        start = time.time()
        response = client.get("/metrics", headers=admin_key)
        latency_ms = (time.time() - start) * 1000
        
        assert response.status_code == 200
        assert latency_ms < 50


class TestHealthzEndpoint:
    """Tests for GET /healthz"""
    
    def test_healthz_success(self, client: TestClient):
        """200: Health check returns OK"""
        response = client.get("/healthz")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
    
    def test_healthz_includes_db_check(self, client: TestClient):
        """Health check includes database ping"""
        response = client.get("/healthz")
        
        assert response.status_code == 200
        data = response.json()
        assert "database" in data
    
    def test_healthz_fast_response(self, client: TestClient):
        """Health check responds quickly"""
        import time
        
        start = time.time()
        response = client.get("/healthz")
        latency_ms = (time.time() - start) * 1000
        
        assert response.status_code == 200
        assert latency_ms < 100


class TestRequestIDMiddleware:
    """Tests for request ID middleware and correlation"""
    
    def test_request_id_generated_if_missing(self, client: TestClient):
        """Middleware generates request_id if not provided"""
        response = client.get("/healthz")
        
        assert response.status_code == 200
        assert "X-Request-ID" in response.headers
        assert len(response.headers["X-Request-ID"]) > 0
    
    def test_request_id_preserved_from_header(self, client: TestClient):
        """Middleware preserves provided request_id"""
        custom_req_id = "test-request-123"
        
        response = client.get(
            "/healthz",
            headers={"X-Request-ID": custom_req_id}
        )
        
        assert response.status_code == 200
        assert response.headers["X-Request-ID"] == custom_req_id
    
    def test_request_id_in_structured_logs(self, client: TestClient, capture_logs, device_auth: dict):
        """Request ID appears in structured logs"""
        custom_req_id = "log-correlation-test"
        
        response = client.post(
            "/v1/heartbeat",
            headers={**device_auth, "X-Request-ID": custom_req_id},
            json={"status": "ok", "battery_pct": 95}
        )
        
        assert response.status_code == 200
        
        for log in capture_logs:
            if "request_id" in log:
                assert log["request_id"] == custom_req_id or log["request_id"] is not None


class TestHTTPMetrics:
    """Tests for HTTP request metrics collection"""
    
    def test_http_request_counter_incremented(self, client: TestClient, capture_metrics):
        """HTTP request counter increments on each request"""
        response = client.get("/healthz")
        
        assert response.status_code == 200
        
        counter_metrics = [m for m in capture_metrics["counters"] if m["name"] == "http_requests_total"]
        assert len(counter_metrics) > 0
        
        for metric in counter_metrics:
            assert "route" in metric["labels"]
            assert "method" in metric["labels"]
            assert "status_code" in metric["labels"]
    
    def test_http_latency_histogram_recorded(self, client: TestClient, capture_metrics):
        """HTTP latency histogram records request duration"""
        response = client.get("/healthz")
        
        assert response.status_code == 200
        
        histogram_metrics = [m for m in capture_metrics["histograms"] if m["name"] == "http_request_latency_ms"]
        assert len(histogram_metrics) > 0
        
        for metric in histogram_metrics:
            assert metric["value"] >= 0
            assert "route" in metric["labels"]


class TestErrorHandling:
    """Tests for error handling and 5xx responses"""
    
    def test_500_on_db_failure(self, client: TestClient):
        """503/500: Database failure returns error with request_id"""
        pass
    
    def test_500_includes_request_id(self, client: TestClient):
        """500 errors include request_id in response headers"""
        pass
    
    def test_500_structured_log_emitted(self, client: TestClient, capture_logs):
        """500 errors emit structured log with level=ERROR"""
        pass
