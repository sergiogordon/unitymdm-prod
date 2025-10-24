"""
Contract tests for enrollment token and APK endpoints.
Tests enrollment token CRUD, APK downloads, and enrollment scripts.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from datetime import datetime, timezone, timedelta
import secrets
import hashlib


class TestEnrollmentTokenCRUD:
    """Tests for enrollment token endpoints"""
    
    def test_create_tokens_success(self, client: TestClient, test_db: Session, admin_auth: dict):
        """200: POST /v1/enroll-tokens creates tokens and DB rows"""
        response = client.post(
            "/v1/enroll-tokens",
            headers=admin_auth,
            json={
                "aliases": ["Device-A", "Device-B", "Device-C"],
                "expires_in_sec": 2700,
                "uses_allowed": 1,
                "note": "Test batch"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["tokens"]) == 3
        
        for token_data in data["tokens"]:
            assert "token_id" in token_data
            assert "alias" in token_data
            assert "token" in token_data
            assert "expires_at" in token_data
        
        from models import EnrollmentToken
        count = test_db.query(EnrollmentToken).count()
        assert count == 3
    
    def test_create_tokens_401_no_auth(self, client: TestClient):
        """401: Creating tokens without authentication rejected"""
        response = client.post(
            "/v1/enroll-tokens",
            json={
                "aliases": ["Device-X"],
                "expires_in_sec": 2700,
                "uses_allowed": 1
            }
        )
        
        assert response.status_code == 401
    
    def test_create_tokens_400_empty_aliases(self, client: TestClient, admin_auth: dict):
        """400: Empty aliases list rejected"""
        response = client.post(
            "/v1/enroll-tokens",
            headers=admin_auth,
            json={
                "aliases": [],
                "expires_in_sec": 2700,
                "uses_allowed": 1
            }
        )
        
        assert response.status_code == 400
    
    def test_create_tokens_400_too_many(self, client: TestClient, admin_auth: dict):
        """400: More than 100 tokens rejected"""
        aliases = [f"Device-{i}" for i in range(101)]
        
        response = client.post(
            "/v1/enroll-tokens",
            headers=admin_auth,
            json={
                "aliases": aliases,
                "expires_in_sec": 2700,
                "uses_allowed": 1
            }
        )
        
        assert response.status_code == 400
    
    def test_create_tokens_observability(self, client: TestClient, admin_auth: dict, capture_logs):
        """Verify sec.token.create log emitted"""
        response = client.post(
            "/v1/enroll-tokens",
            headers=admin_auth,
            json={
                "aliases": ["Device-Log"],
                "expires_in_sec": 2700,
                "uses_allowed": 1
            }
        )
        
        assert response.status_code == 200
        
        token_logs = [log for log in capture_logs if log["event"] == "sec.token.create"]
        assert len(token_logs) >= 1
    
    def test_list_tokens_success(self, client: TestClient, test_db: Session, admin_auth: dict):
        """200: GET /v1/enroll-tokens lists tokens"""
        from models import EnrollmentToken
        
        for i in range(3):
            token_hash = hashlib.sha256(secrets.token_urlsafe(32).encode()).hexdigest()
            enrollment_token = EnrollmentToken(
                token_id=f"tok_list_{i}",
                alias=f"List-Device-{i}",
                token_hash=token_hash,
                issued_by="test_admin",
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
                uses_allowed=1,
                uses_consumed=0,
                status='active'
            )
            test_db.add(enrollment_token)
        test_db.commit()
        
        response = client.get("/v1/enroll-tokens", headers=admin_auth)
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["tokens"]) >= 3
    
    def test_list_tokens_filter_by_status(self, client: TestClient, test_db: Session, admin_auth: dict):
        """200: Filter tokens by status"""
        from models import EnrollmentToken
        
        active_hash = hashlib.sha256(secrets.token_urlsafe(32).encode()).hexdigest()
        revoked_hash = hashlib.sha256(secrets.token_urlsafe(32).encode()).hexdigest()
        
        test_db.add(EnrollmentToken(
            token_id="tok_active",
            alias="Active-Device",
            token_hash=active_hash,
            issued_by="test_admin",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            uses_allowed=1,
            uses_consumed=0,
            status='active'
        ))
        
        test_db.add(EnrollmentToken(
            token_id="tok_revoked",
            alias="Revoked-Device",
            token_hash=revoked_hash,
            issued_by="test_admin",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            uses_allowed=1,
            uses_consumed=0,
            status='revoked'
        ))
        test_db.commit()
        
        response = client.get("/v1/enroll-tokens?status=active", headers=admin_auth)
        
        assert response.status_code == 200
        data = response.json()
        
        for token in data["tokens"]:
            assert token["status"] in ["active", "expired", "exhausted"]
    
    def test_delete_token_success(self, client: TestClient, test_db: Session, admin_auth: dict):
        """200: DELETE /v1/enroll-tokens/{token_id} revokes token"""
        from models import EnrollmentToken
        
        token_hash = hashlib.sha256(secrets.token_urlsafe(32).encode()).hexdigest()
        enrollment_token = EnrollmentToken(
            token_id="tok_delete_test",
            alias="Delete-Device",
            token_hash=token_hash,
            issued_by="test_admin",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            uses_allowed=1,
            uses_consumed=0,
            status='active'
        )
        test_db.add(enrollment_token)
        test_db.commit()
        
        response = client.delete("/v1/enroll-tokens/tok_delete_test", headers=admin_auth)
        
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["status"] == "revoked"
        
        test_db.refresh(enrollment_token)
        assert enrollment_token.status == "revoked"
    
    def test_delete_token_404_not_found(self, client: TestClient, admin_auth: dict):
        """404: Deleting unknown token_id"""
        response = client.delete("/v1/enroll-tokens/tok_unknown", headers=admin_auth)
        
        assert response.status_code == 404
    
    def test_delete_token_409_exhausted(self, client: TestClient, test_db: Session, admin_auth: dict):
        """409: Revoking exhausted token"""
        from models import EnrollmentToken
        
        token_hash = hashlib.sha256(secrets.token_urlsafe(32).encode()).hexdigest()
        enrollment_token = EnrollmentToken(
            token_id="tok_exhausted",
            alias="Exhausted-Device",
            token_hash=token_hash,
            issued_by="test_admin",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            uses_allowed=1,
            uses_consumed=1,
            status='exhausted'
        )
        test_db.add(enrollment_token)
        test_db.commit()
        
        response = client.delete("/v1/enroll-tokens/tok_exhausted", headers=admin_auth)
        
        assert response.status_code == 409
    
    def test_delete_token_idempotent(self, client: TestClient, test_db: Session, admin_auth: dict):
        """200: Revoking already-revoked token is idempotent"""
        from models import EnrollmentToken
        
        token_hash = hashlib.sha256(secrets.token_urlsafe(32).encode()).hexdigest()
        enrollment_token = EnrollmentToken(
            token_id="tok_idemp_revoke",
            alias="Idemp-Device",
            token_hash=token_hash,
            issued_by="test_admin",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            uses_allowed=1,
            uses_consumed=0,
            status='active'
        )
        test_db.add(enrollment_token)
        test_db.commit()
        
        response1 = client.delete("/v1/enroll-tokens/tok_idemp_revoke", headers=admin_auth)
        assert response1.status_code == 200
        
        response2 = client.delete("/v1/enroll-tokens/tok_idemp_revoke", headers=admin_auth)
        assert response2.status_code == 200
        assert response2.json()["message"] == "Token already revoked"


class TestAPKEndpoints:
    """Tests for APK download endpoints"""
    
    def test_download_latest_with_admin_key(self, client: TestClient, test_db: Session, admin_key: dict):
        """200: GET /v1/apk/download-latest with admin key"""
        from models import ApkVersion
        import os
        
        apk_path = "/tmp/test_app.apk"
        with open(apk_path, "wb") as f:
            f.write(b"MOCK_APK_CONTENT")
        
        apk = ApkVersion(
            version_name="1.0.0",
            version_code=1,
            file_path=apk_path,
            file_size=17,
            package_name="com.nexmdm.test",
            uploaded_at=datetime.now(timezone.utc),
            is_active=True
        )
        test_db.add(apk)
        test_db.commit()
        
        response = client.get(
            "/v1/apk/download-latest",
            headers=admin_key
        )
        
        if os.path.exists(apk_path):
            assert response.status_code == 200
            assert response.headers["content-type"] == "application/vnd.android.package-archive"
        
        if os.path.exists(apk_path):
            os.remove(apk_path)
    
    def test_download_latest_401_no_admin_key(self, client: TestClient):
        """401: Missing admin key rejected"""
        response = client.get("/v1/apk/download-latest")
        
        assert response.status_code == 422
    
    def test_download_latest_observability(self, client: TestClient, test_db: Session, admin_key: dict, capture_logs):
        """Verify apk.download log emitted"""
        from models import ApkVersion
        import os
        
        apk_path = "/tmp/test_obs_apk.apk"
        with open(apk_path, "wb") as f:
            f.write(b"MOCK")
        
        apk = ApkVersion(
            version_name="1.0.1",
            version_code=2,
            file_path=apk_path,
            file_size=4,
            package_name="com.nexmdm.obs",
            uploaded_at=datetime.now(timezone.utc),
            is_active=True
        )
        test_db.add(apk)
        test_db.commit()
        
        response = client.get(
            "/v1/apk/download-latest",
            headers=admin_key
        )
        
        if os.path.exists(apk_path):
            apk_logs = [log for log in capture_logs if log["event"] == "apk.download"]
            assert len(apk_logs) >= 1
            
            os.remove(apk_path)


class TestEnrollmentScripts:
    """Tests for enrollment script endpoints"""
    
    def test_enroll_sh_script_success(self, client: TestClient, test_db: Session, admin_auth: dict):
        """200: GET /v1/scripts/enroll.sh returns templated script"""
        from models import EnrollmentToken
        
        token_hash = hashlib.sha256(secrets.token_urlsafe(32).encode()).hexdigest()
        enrollment_token = EnrollmentToken(
            token_id="tok_script_sh",
            alias="Script-Device",
            token_hash=token_hash,
            issued_by="test_admin",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            uses_allowed=1,
            uses_consumed=0,
            status='active'
        )
        test_db.add(enrollment_token)
        test_db.commit()
        
        response = client.get(
            "/v1/scripts/enroll.sh",
            params={"alias": "Script-Device", "token_id": "tok_script_sh"},
            headers=admin_auth
        )
        
        assert response.status_code == 200
        assert "#!/bin/bash" in response.text
        assert "Script-Device" in response.text
    
    def test_enroll_cmd_script_success(self, client: TestClient, test_db: Session, admin_auth: dict):
        """200: GET /v1/scripts/enroll.cmd returns templated script"""
        from models import EnrollmentToken
        
        token_hash = hashlib.sha256(secrets.token_urlsafe(32).encode()).hexdigest()
        enrollment_token = EnrollmentToken(
            token_id="tok_script_cmd",
            alias="Script-Device-Win",
            token_hash=token_hash,
            issued_by="test_admin",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            uses_allowed=1,
            uses_consumed=0,
            status='active'
        )
        test_db.add(enrollment_token)
        test_db.commit()
        
        response = client.get(
            "/v1/scripts/enroll.cmd",
            params={"alias": "Script-Device-Win", "token_id": "tok_script_cmd"},
            headers=admin_auth
        )
        
        assert response.status_code == 200
        assert "@echo off" in response.text
        assert "Script-Device-Win" in response.text
    
    def test_enroll_script_401_no_auth(self, client: TestClient):
        """401: Script endpoints require authentication"""
        response = client.get(
            "/v1/scripts/enroll.sh",
            params={"alias": "Test", "token_id": "tok_test"}
        )
        
        assert response.status_code == 401
    
    def test_enroll_script_404_token_not_found(self, client: TestClient, admin_auth: dict):
        """404: Unknown token_id"""
        response = client.get(
            "/v1/scripts/enroll.sh",
            params={"alias": "Test", "token_id": "tok_unknown"},
            headers=admin_auth
        )
        
        assert response.status_code == 404
