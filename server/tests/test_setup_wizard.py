"""
Tests for setup wizard endpoints.
Tests /api/setup/status and /api/setup/validate-firebase
"""
import pytest
import os
import json
from fastapi.testclient import TestClient
from unittest.mock import patch
from main import app


# Create a test client without database dependencies for setup endpoints
# These endpoints don't use the database, so we can use a simple client
@pytest.fixture
def setup_client():
    """Create a test client for setup endpoints (no database needed)"""
    # Reset rate limiter before each test to avoid cross-test interference
    from main import setup_rate_limiter
    setup_rate_limiter.requests.clear()
    
    return TestClient(app)


class TestSetupStatusEndpoint:
    """Tests for GET /api/setup/status"""
    
    def test_setup_status_returns_correct_structure(self, setup_client: TestClient):
        """Verify setup status endpoint returns correct JSON structure"""
        response = setup_client.get("/api/setup/status")
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify top-level structure
        assert "required" in data
        assert "optional" in data
        assert "ready" in data
        assert isinstance(data["ready"], bool)
        
        # Verify required secrets structure
        required = data["required"]
        assert "admin_key" in required
        assert "jwt_secret" in required
        assert "firebase" in required
        
        # Verify each required secret has correct structure
        for secret_name, secret_data in required.items():
            assert "configured" in secret_data
            assert "valid" in secret_data
            assert "message" in secret_data
            assert isinstance(secret_data["configured"], bool)
            assert isinstance(secret_data["valid"], bool)
            assert isinstance(secret_data["message"], str)
        
        # Verify optional secrets structure
        optional = data["optional"]
        assert "discord_webhook" in optional
        assert "github_ci" in optional
        
        # Verify optional secrets have correct structure
        for secret_name, secret_data in optional.items():
            assert "configured" in secret_data
            assert "message" in secret_data
            assert isinstance(secret_data["configured"], bool)
            assert isinstance(secret_data["message"], str)
    
    def test_setup_status_no_secrets_configured(self, setup_client: TestClient):
        """Test setup status when no secrets are configured"""
        # Clear all secrets
        with patch.dict(os.environ, {}, clear=True):
            response = setup_client.get("/api/setup/status")
            
            assert response.status_code == 200
            data = response.json()
            
            # All required secrets should be not configured
            assert data["required"]["admin_key"]["configured"] is False
            assert data["required"]["jwt_secret"]["configured"] is False
            assert data["required"]["firebase"]["configured"] is False
            
            # Setup should not be ready
            assert data["ready"] is False
            
            # Messages should indicate not configured
            assert "Not configured" in data["required"]["admin_key"]["message"]
            assert "Not configured" in data["required"]["jwt_secret"]["message"]
            assert "Not configured" in data["required"]["firebase"]["message"]
    
    def test_setup_status_admin_key_validation(self, setup_client: TestClient):
        """Test admin key validation logic"""
        # Test too short admin key
        with patch('main.os.getenv', side_effect=lambda key, default=None: {
            "ADMIN_KEY": "short"
        }.get(key, os.environ.get(key, default))):
            response = setup_client.get("/api/setup/status")
            data = response.json()
            
            assert data["required"]["admin_key"]["configured"] is True
            assert data["required"]["admin_key"]["valid"] is False
            assert "at least 16 characters" in data["required"]["admin_key"]["message"]
        
        # Test insecure default value (exact match - "changeme" is too short, so it fails length check)
        # Note: Backend checks exact matches, so "changeme" (7 chars) fails length check first
        with patch('main.os.getenv', side_effect=lambda key, default=None: {
            "ADMIN_KEY": "changeme"
        }.get(key, os.environ.get(key, default))):
            response = setup_client.get("/api/setup/status")
            data = response.json()
            
            assert data["required"]["admin_key"]["valid"] is False
            # "changeme" is only 7 chars, so it fails length check (not insecure check)
            assert "at least 16 characters" in data["required"]["admin_key"]["message"]
        
        # Test another insecure default value that's long enough to pass length check
        # Use "default" which is 7 chars, but we'll test with "default" + padding to pass length
        # Actually, let's test with "admin" + padding - but wait, backend checks exact match
        # So "admin123456789012345" would pass. Let's test with exactly "admin" (too short)
        with patch('main.os.getenv', side_effect=lambda key, default=None: {
            "ADMIN_KEY": "admin"
        }.get(key, os.environ.get(key, default))):
            response = setup_client.get("/api/setup/status")
            data = response.json()
            
            assert data["required"]["admin_key"]["valid"] is False
            # "admin" is only 5 chars, so it fails length check
            assert "at least 16 characters" in data["required"]["admin_key"]["message"]
        
        # Test valid admin key
        with patch('main.os.getenv', side_effect=lambda key, default=None: {
            "ADMIN_KEY": "a" * 32
        }.get(key, os.environ.get(key, default))):
            response = setup_client.get("/api/setup/status")
            data = response.json()
            
            assert data["required"]["admin_key"]["configured"] is True
            assert data["required"]["admin_key"]["valid"] is True
            assert "✓ Valid" in data["required"]["admin_key"]["message"]
    
    def test_setup_status_jwt_secret_validation(self, setup_client: TestClient):
        """Test JWT secret validation logic"""
        # Test default secret
        with patch('main.os.getenv', side_effect=lambda key, default=None: {
            "SESSION_SECRET": "dev-secret-change-in-production"
        }.get(key, os.environ.get(key, default))):
            response = setup_client.get("/api/setup/status")
            data = response.json()
            
            assert data["required"]["jwt_secret"]["configured"] is True
            assert data["required"]["jwt_secret"]["valid"] is False
            assert "default secret" in data["required"]["jwt_secret"]["message"]
        
        # Test too short secret
        with patch('main.os.getenv', side_effect=lambda key, default=None: {
            "SESSION_SECRET": "short"
        }.get(key, os.environ.get(key, default))):
            response = setup_client.get("/api/setup/status")
            data = response.json()
            
            assert data["required"]["jwt_secret"]["valid"] is False
            assert "at least 32 characters" in data["required"]["jwt_secret"]["message"]
        
        # Test valid secret
        with patch('main.os.getenv', side_effect=lambda key, default=None: {
            "SESSION_SECRET": "a" * 64
        }.get(key, os.environ.get(key, default))):
            response = setup_client.get("/api/setup/status")
            data = response.json()
            
            assert data["required"]["jwt_secret"]["configured"] is True
            assert data["required"]["jwt_secret"]["valid"] is True
            assert "✓ Valid" in data["required"]["jwt_secret"]["message"]
    
    def test_setup_status_firebase_validation(self, setup_client: TestClient):
        """Test Firebase JSON validation"""
        # Test invalid JSON
        invalid_json = '{"invalid": "json"}'
        with patch('main.os.getenv', side_effect=lambda key, default=None: {
            "FIREBASE_SERVICE_ACCOUNT_JSON": invalid_json
        }.get(key, os.environ.get(key, default))):
            response = setup_client.get("/api/setup/status")
            data = response.json()
            
            assert data["required"]["firebase"]["configured"] is True
            assert data["required"]["firebase"]["valid"] is False
            assert "Invalid service account" in data["required"]["firebase"]["message"]
        
        # Test malformed JSON
        malformed_json = "{invalid json}"
        with patch('main.os.getenv', side_effect=lambda key, default=None: {
            "FIREBASE_SERVICE_ACCOUNT_JSON": malformed_json
        }.get(key, os.environ.get(key, default))):
            response = setup_client.get("/api/setup/status")
            data = response.json()
            
            assert data["required"]["firebase"]["valid"] is False
            assert "Invalid JSON format" in data["required"]["firebase"]["message"]
        
        # Test valid Firebase JSON
        valid_firebase = json.dumps({
            "type": "service_account",
            "project_id": "test-project",
            "private_key_id": "test-key-id",
            "private_key": "-----BEGIN PRIVATE KEY-----\n" + "a" * 100 + "\n-----END PRIVATE KEY-----\n",
            "client_email": "test@test-project.iam.gserviceaccount.com"
        })
        with patch('main.os.getenv', side_effect=lambda key, default=None: {
            "FIREBASE_SERVICE_ACCOUNT_JSON": valid_firebase
        }.get(key, os.environ.get(key, default))):
            response = setup_client.get("/api/setup/status")
            data = response.json()
            
            assert data["required"]["firebase"]["configured"] is True
            assert data["required"]["firebase"]["valid"] is True
            assert "✓ Valid" in data["required"]["firebase"]["message"]
    
    def test_setup_status_all_configured(self, setup_client: TestClient):
        """Test setup status when all required secrets are configured and valid"""
        valid_firebase = json.dumps({
            "type": "service_account",
            "project_id": "test-project",
            "private_key_id": "test-key-id",
            "private_key": "-----BEGIN PRIVATE KEY-----\n" + "a" * 100 + "\n-----END PRIVATE KEY-----\n",
            "client_email": "test@test-project.iam.gserviceaccount.com"
        })
        
        with patch('main.os.getenv', side_effect=lambda key, default=None: {
            "ADMIN_KEY": "a" * 32,
            "SESSION_SECRET": "b" * 64,
            "FIREBASE_SERVICE_ACCOUNT_JSON": valid_firebase
        }.get(key, os.environ.get(key, default))):
            response = setup_client.get("/api/setup/status")
            data = response.json()
            
            # All should be configured and valid
            assert data["required"]["admin_key"]["configured"] is True
            assert data["required"]["admin_key"]["valid"] is True
            assert data["required"]["jwt_secret"]["configured"] is True
            assert data["required"]["jwt_secret"]["valid"] is True
            assert data["required"]["firebase"]["configured"] is True
            assert data["required"]["firebase"]["valid"] is True
            
            # Setup should be ready
            assert data["ready"] is True
    
    def test_setup_status_optional_secrets(self, setup_client: TestClient):
        """Test optional secrets detection"""
        # Test Discord webhook
        with patch('main.os.getenv', side_effect=lambda key, default=None: {
            "DISCORD_WEBHOOK_URL": "https://discord.com/api/webhooks/123"
        }.get(key, os.environ.get(key, default))):
            response = setup_client.get("/api/setup/status")
            data = response.json()
            
            assert data["optional"]["discord_webhook"]["configured"] is True
        
        # Test GitHub CI secrets
        with patch('main.os.getenv', side_effect=lambda key, default=None: {
            "ANDROID_KEYSTORE_BASE64": "base64data",
            "KEYSTORE_PASSWORD": "password",
            "ANDROID_KEY_ALIAS": "nexmdm",
            "ANDROID_KEY_ALIAS_PASSWORD": "keypass",
            "BACKEND_URL": "https://example.com",
            "ADMIN_KEY": "admin12345678901234567890"
        }.get(key, os.environ.get(key, default))):
            response = setup_client.get("/api/setup/status")
            data = response.json()
            
            assert data["optional"]["github_ci"]["configured"] is True
            assert "✓ Configured" in data["optional"]["github_ci"]["message"]
    
    def test_setup_status_rate_limiting(self, setup_client: TestClient):
        """Test that rate limiting works (should allow 10 requests)"""
        # Reset rate limiter at start of test
        from main import setup_rate_limiter
        setup_rate_limiter.requests.clear()
        
        # Make 10 requests (should all succeed)
        for i in range(10):
            response = setup_client.get("/api/setup/status")
            assert response.status_code == 200, f"Request {i+1} should succeed"
        
        # 11th request should be rate limited
        response = setup_client.get("/api/setup/status")
        assert response.status_code == 429
        assert "Too many requests" in response.json()["detail"]


class TestFirebaseValidationEndpoint:
    """Tests for POST /api/setup/validate-firebase"""
    
    def test_validate_firebase_returns_correct_structure(self, setup_client: TestClient):
        """Verify Firebase validation endpoint returns correct structure"""
        valid_json = json.dumps({
            "type": "service_account",
            "project_id": "test-project",
            "private_key_id": "test-key-id",
            "private_key": "-----BEGIN PRIVATE KEY-----\n" + "a" * 100 + "\n-----END PRIVATE KEY-----\n",
            "client_email": "test@test-project.iam.gserviceaccount.com"
        })
        
        response = setup_client.post(
            "/api/setup/validate-firebase",
            json={"firebase_json": valid_json}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "valid" in data
        assert "message" in data
        assert isinstance(data["valid"], bool)
        assert isinstance(data["message"], str)
    
    def test_validate_firebase_valid_json(self, setup_client: TestClient):
        """Test validation with valid Firebase service account JSON"""
        valid_json = json.dumps({
            "type": "service_account",
            "project_id": "test-project",
            "private_key_id": "test-key-id",
            "private_key": "-----BEGIN PRIVATE KEY-----\n" + "a" * 100 + "\n-----END PRIVATE KEY-----\n",
            "client_email": "test@test-project.iam.gserviceaccount.com"
        })
        
        response = setup_client.post(
            "/api/setup/validate-firebase",
            json={"firebase_json": valid_json}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True
        assert "✓ Valid" in data["message"]
    
    def test_validate_firebase_invalid_json_format(self, setup_client: TestClient):
        """Test validation with invalid JSON format"""
        response = setup_client.post(
            "/api/setup/validate-firebase",
            json={"firebase_json": "{invalid json}"}
        )
        
        assert response.status_code == 400
        data = response.json()
        assert data["valid"] is False
        assert "Invalid JSON format" in data["message"]
    
    def test_validate_firebase_missing_required_fields(self, setup_client: TestClient):
        """Test validation with missing required fields"""
        incomplete_json = json.dumps({
            "type": "service_account",
            "project_id": "test-project"
            # Missing private_key_id, private_key, client_email
        })
        
        response = setup_client.post(
            "/api/setup/validate-firebase",
            json={"firebase_json": incomplete_json}
        )
        
        assert response.status_code == 400
        data = response.json()
        assert data["valid"] is False
        assert "Missing required fields" in data["message"]
    
    def test_validate_firebase_wrong_type(self, setup_client: TestClient):
        """Test validation with wrong type"""
        wrong_type_json = json.dumps({
            "type": "user_account",  # Should be "service_account"
            "project_id": "test-project",
            "private_key_id": "test-key-id",
            "private_key": "key",
            "client_email": "test@test.com"
        })
        
        response = setup_client.post(
            "/api/setup/validate-firebase",
            json={"firebase_json": wrong_type_json}
        )
        
        assert response.status_code == 400
        data = response.json()
        assert data["valid"] is False
        assert "not a service account type" in data["message"]
    
    def test_validate_firebase_empty_fields(self, setup_client: TestClient):
        """Test validation with empty critical fields"""
        empty_fields_json = json.dumps({
            "type": "service_account",
            "project_id": "",  # Empty
            "private_key_id": "test-key-id",
            "private_key": "key",
            "client_email": ""  # Empty
        })
        
        response = setup_client.post(
            "/api/setup/validate-firebase",
            json={"firebase_json": empty_fields_json}
        )
        
        assert response.status_code == 400
        data = response.json()
        assert data["valid"] is False
        assert "cannot be empty" in data["message"]
    
    def test_validate_firebase_short_private_key(self, setup_client: TestClient):
        """Test validation with too short private key"""
        short_key_json = json.dumps({
            "type": "service_account",
            "project_id": "test-project",
            "private_key_id": "test-key-id",
            "private_key": "short",  # Too short
            "client_email": "test@test.com"
        })
        
        response = setup_client.post(
            "/api/setup/validate-firebase",
            json={"firebase_json": short_key_json}
        )
        
        assert response.status_code == 400
        data = response.json()
        assert data["valid"] is False
        assert "too short" in data["message"]
    
    def test_validate_firebase_whitespace_handling(self, setup_client: TestClient):
        """Test that whitespace is handled correctly"""
        valid_json = json.dumps({
            "type": "service_account",
            "project_id": "test-project",
            "private_key_id": "test-key-id",
            "private_key": "-----BEGIN PRIVATE KEY-----\n" + "a" * 100 + "\n-----END PRIVATE KEY-----\n",
            "client_email": "test@test-project.iam.gserviceaccount.com"
        })
        
        # Add whitespace around JSON
        json_with_whitespace = f"  {valid_json}  "
        
        response = setup_client.post(
            "/api/setup/validate-firebase",
            json={"firebase_json": json_with_whitespace}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True
    
    def test_validate_firebase_missing_field(self, setup_client: TestClient):
        """Test validation when firebase_json field is missing"""
        response = setup_client.post(
            "/api/setup/validate-firebase",
            json={}
        )
        
        assert response.status_code == 400
        data = response.json()
        assert data["valid"] is False
        assert "Firebase JSON is required" in data["message"]
    
    def test_validate_firebase_rate_limiting(self, setup_client: TestClient):
        """Test that rate limiting works for Firebase validation"""
        # Reset rate limiter at start of test
        from main import setup_rate_limiter
        setup_rate_limiter.requests.clear()
        
        valid_json = json.dumps({
            "type": "service_account",
            "project_id": "test-project",
            "private_key_id": "test-key-id",
            "private_key": "-----BEGIN PRIVATE KEY-----\n" + "a" * 100 + "\n-----END PRIVATE KEY-----\n",
            "client_email": "test@test-project.iam.gserviceaccount.com"
        })
        
        # Make 10 requests (should all succeed)
        for i in range(10):
            response = setup_client.post(
                "/api/setup/validate-firebase",
                json={"firebase_json": valid_json}
            )
            assert response.status_code == 200, f"Request {i+1} should succeed"
        
        # 11th request should be rate limited
        response = setup_client.post(
            "/api/setup/validate-firebase",
            json={"firebase_json": valid_json}
        )
        assert response.status_code == 429
        assert "Too many requests" in response.json()["detail"]

