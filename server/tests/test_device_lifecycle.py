"""
Contract tests for device lifecycle endpoints.
Tests /v1/register, /v1/heartbeat, /v1/action-result
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
import json


class TestRegisterEndpoint:
    """Tests for POST /v1/register"""
    
    def test_register_success_with_enrollment_token(self, client: TestClient, test_db: Session, admin_auth: dict):
        """200: Valid enrollment token creates device and returns credentials"""
        from models import EnrollmentToken
        from datetime import datetime, timezone, timedelta
        import hashlib
        import secrets
        
        raw_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        
        enrollment_token = EnrollmentToken(
            token_id="tok_test_001",
            alias="Device-001",
            token_hash=token_hash,
            issued_by="test_admin",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            uses_allowed=1,
            uses_consumed=0,
            status='active'
        )
        test_db.add(enrollment_token)
        test_db.commit()
        
        response = client.post(
            "/v1/register",
            params={"alias": "Device-001"},
            headers={"Authorization": f"Bearer {raw_token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "device_id" in data
        assert "device_token" in data
        assert data["device_id"].startswith("Device-001")
        
        from models import Device
        device = test_db.query(Device).filter(Device.id == data["device_id"]).first()
        assert device is not None
        assert device.alias == "Device-001"
    
    def test_register_401_invalid_enrollment_token(self, client: TestClient):
        """401: Invalid enrollment token rejected"""
        response = client.post(
            "/v1/register",
            params={"alias": "Test"},
            headers={"Authorization": "Bearer invalid_token"}
        )
        
        assert response.status_code == 401
    
    def test_register_401_expired_enrollment_token(self, client: TestClient, test_db: Session):
        """401: Expired enrollment token rejected"""
        from models import EnrollmentToken
        from datetime import datetime, timezone, timedelta
        import hashlib
        import secrets
        
        raw_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        
        enrollment_token = EnrollmentToken(
            token_id="tok_expired",
            alias="Device-Expired",
            token_hash=token_hash,
            issued_by="test_admin",
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
            uses_allowed=1,
            uses_consumed=0,
            status='active'
        )
        test_db.add(enrollment_token)
        test_db.commit()
        
        response = client.post(
            "/v1/register",
            params={"alias": "Device-Expired"},
            headers={"Authorization": f"Bearer {raw_token}"}
        )
        
        assert response.status_code == 401
    
    def test_register_401_revoked_enrollment_token(self, client: TestClient, test_db: Session):
        """401: Revoked enrollment token rejected"""
        from models import EnrollmentToken
        from datetime import datetime, timezone, timedelta
        import hashlib
        import secrets
        
        raw_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        
        enrollment_token = EnrollmentToken(
            token_id="tok_revoked",
            alias="Device-Revoked",
            token_hash=token_hash,
            issued_by="test_admin",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            uses_allowed=1,
            uses_consumed=0,
            status='revoked'
        )
        test_db.add(enrollment_token)
        test_db.commit()
        
        response = client.post(
            "/v1/register",
            params={"alias": "Device-Revoked"},
            headers={"Authorization": f"Bearer {raw_token}"}
        )
        
        assert response.status_code == 401
    
    def test_register_observability(self, client: TestClient, test_db: Session, capture_logs):
        """Verify structured log emitted on success"""
        from models import EnrollmentToken
        from datetime import datetime, timezone, timedelta
        import hashlib
        import secrets
        
        raw_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        
        enrollment_token = EnrollmentToken(
            token_id="tok_log_test",
            alias="Device-Log",
            token_hash=token_hash,
            issued_by="test_admin",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            uses_allowed=1,
            uses_consumed=0,
            status='active'
        )
        test_db.add(enrollment_token)
        test_db.commit()
        
        response = client.post(
            "/v1/register",
            params={"alias": "Device-Log"},
            headers={"Authorization": f"Bearer {raw_token}"}
        )
        
        assert response.status_code == 200
        
        register_logs = [log for log in capture_logs if log["event"] == "register.success"]
        assert len(register_logs) > 0


class TestHeartbeatEndpoint:
    """Tests for POST /v1/heartbeat"""
    
    def test_heartbeat_success(self, client: TestClient, test_device: tuple, device_auth: dict):
        """200: Valid heartbeat updates device status"""
        device, _ = test_device
        
        response = client.post(
            "/v1/heartbeat",
            headers=device_auth,
            json={
                "status": "ok",
                "battery_pct": 85,
                "network_type": "wifi",
                "uptime_sec": 3600
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
    
    def test_heartbeat_401_no_auth(self, client: TestClient):
        """401: Missing Bearer token rejected"""
        response = client.post(
            "/v1/heartbeat",
            json={"status": "ok"}
        )
        
        assert response.status_code == 403
    
    def test_heartbeat_401_invalid_token(self, client: TestClient):
        """401: Invalid device token rejected"""
        response = client.post(
            "/v1/heartbeat",
            headers={"Authorization": "Bearer invalid_device_token"},
            json={"status": "ok"}
        )
        
        assert response.status_code == 401
    
    def test_heartbeat_422_bad_payload(self, client: TestClient, device_auth: dict):
        """422: Schema violation rejected"""
        response = client.post(
            "/v1/heartbeat",
            headers=device_auth,
            json={"invalid_field": "value"}
        )
        
        assert response.status_code == 422
    
    def test_heartbeat_idempotency_within_bucket(self, client: TestClient, test_device: tuple, device_auth: dict, test_db: Session):
        """Idempotency: Multiple heartbeats within 10s bucket deduped"""
        device, _ = test_device
        
        for i in range(3):
            response = client.post(
                "/v1/heartbeat",
                headers=device_auth,
                json={
                    "status": "ok",
                    "battery_pct": 80 + i
                }
            )
            assert response.status_code == 200
        
        from models import DeviceHeartbeat
        count = test_db.query(DeviceHeartbeat).filter(
            DeviceHeartbeat.device_id == device.id
        ).count()
        
        assert count <= 1
    
    def test_heartbeat_observability(self, client: TestClient, device_auth: dict, capture_logs):
        """Verify structured log with event heartbeat.ingest"""
        response = client.post(
            "/v1/heartbeat",
            headers=device_auth,
            json={"status": "ok", "battery_pct": 90}
        )
        
        assert response.status_code == 200
        
        heartbeat_logs = [log for log in capture_logs if "heartbeat" in log["event"]]
        assert len(heartbeat_logs) > 0


class TestActionResultEndpoint:
    """Tests for POST /v1/action-result"""
    
    def test_action_result_success(self, client: TestClient, test_device: tuple, device_auth: dict, test_db: Session):
        """200: Valid action result marks dispatch complete"""
        from models import FcmDispatch
        from datetime import datetime, timezone
        
        device, _ = test_device
        
        dispatch = FcmDispatch(
            request_id="req_test_001",
            device_id=device.id,
            action="ping",
            sent_at=datetime.now(timezone.utc),
            fcm_status="sent"
        )
        test_db.add(dispatch)
        test_db.commit()
        
        response = client.post(
            "/v1/action-result",
            headers=device_auth,
            json={
                "request_id": "req_test_001",
                "result": "ok",
                "data": {"ping_time_ms": 42}
            }
        )
        
        assert response.status_code == 200
        
        test_db.refresh(dispatch)
        assert dispatch.completed_at is not None
    
    def test_action_result_404_unknown_request_id(self, client: TestClient, device_auth: dict):
        """404: Unknown request_id rejected"""
        response = client.post(
            "/v1/action-result",
            headers=device_auth,
            json={
                "request_id": "unknown_request",
                "result": "ok"
            }
        )
        
        assert response.status_code == 404
    
    def test_action_result_401_no_auth(self, client: TestClient):
        """401: Missing Bearer token rejected"""
        response = client.post(
            "/v1/action-result",
            json={"request_id": "req_001", "result": "ok"}
        )
        
        assert response.status_code == 403
    
    def test_action_result_idempotency(self, client: TestClient, test_device: tuple, device_auth: dict, test_db: Session):
        """Idempotency: Posting same result twice is idempotent"""
        from models import FcmDispatch
        from datetime import datetime, timezone
        
        device, _ = test_device
        
        dispatch = FcmDispatch(
            request_id="req_idemp_001",
            device_id=device.id,
            action="ping",
            sent_at=datetime.now(timezone.utc),
            fcm_status="sent"
        )
        test_db.add(dispatch)
        test_db.commit()
        
        for _ in range(2):
            response = client.post(
                "/v1/action-result",
                headers=device_auth,
                json={
                    "request_id": "req_idemp_001",
                    "result": "ok"
                }
            )
            assert response.status_code == 200
        
        test_db.refresh(dispatch)
        assert dispatch.completed_at is not None
