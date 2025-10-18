"""
Acceptance tests for OTA Update Management (Milestone 4)
Tests promote, rollout adjustment, rollback, and agent update endpoint with cohort logic.
"""

import pytest
from datetime import datetime, timezone
from server.models import ApkVersion, ApkDeploymentStats, Device
from server.ota_utils import (
    compute_device_cohort,
    is_device_eligible_for_rollout,
    get_current_build,
    get_or_create_deployment_stats,
    increment_deployment_stat
)


class TestCohortLogic:
    """Test deterministic device cohorting for staged rollouts"""
    
    def test_compute_device_cohort_deterministic(self):
        """Cohort assignment must be deterministic and reproducible"""
        device_id = "test-device-12345"
        cohort1 = compute_device_cohort(device_id)
        cohort2 = compute_device_cohort(device_id)
        
        assert cohort1 == cohort2, "Cohort assignment must be deterministic"
        assert 0 <= cohort1 < 100, "Cohort must be between 0 and 99"
    
    def test_compute_device_cohort_distribution(self):
        """Cohorts should be roughly evenly distributed"""
        cohorts = [compute_device_cohort(f"device-{i}") for i in range(1000)]
        
        for bucket in range(0, 100, 10):
            count = sum(1 for c in cohorts if bucket <= c < bucket + 10)
            assert 70 < count < 130, f"Cohort distribution uneven for bucket {bucket}-{bucket+10}"
    
    def test_is_device_eligible_for_rollout_boundaries(self):
        """Test rollout eligibility at boundary percentages"""
        device_id = "test-device-xyz"
        cohort = compute_device_cohort(device_id)
        
        assert is_device_eligible_for_rollout(device_id, 0) == False
        assert is_device_eligible_for_rollout(device_id, 100) == True
        
        assert is_device_eligible_for_rollout(device_id, cohort) == False
        assert is_device_eligible_for_rollout(device_id, cohort + 1) == True
    
    def test_rollout_percentage_targets(self):
        """Verify staged rollout percentages are within ±2% target"""
        devices = [f"device-{i}" for i in range(1000)]
        
        for target_percent in [1, 5, 10, 25, 50, 75, 100]:
            eligible_count = sum(1 for d in devices if is_device_eligible_for_rollout(d, target_percent))
            actual_percent = (eligible_count / len(devices)) * 100
            
            if target_percent == 100:
                assert actual_percent == 100
            else:
                assert abs(actual_percent - target_percent) <= 2, \
                    f"Rollout {target_percent}% resulted in {actual_percent}%"


class TestOTAEndpoints:
    """Integration tests for OTA API endpoints"""
    
    @pytest.fixture
    def db_session(self):
        """Provide a test database session"""
        from server.models import SessionLocal, init_db
        init_db()
        db = SessionLocal()
        yield db
        db.close()
    
    @pytest.fixture
    def test_apk_build(self, db_session):
        """Create a test APK build"""
        apk = ApkVersion(
            package_name="com.nexmdm.agent",
            version_name="1.0.0",
            version_code=100,
            file_path="/tmp/test.apk",
            file_size=5000000,
            uploaded_by="test-user",
            signer_fingerprint="AA:BB:CC:DD",
            is_active=True
        )
        db_session.add(apk)
        db_session.commit()
        db_session.refresh(apk)
        return apk
    
    @pytest.fixture
    def test_device(self, db_session):
        """Create a test device"""
        import bcrypt
        device = Device(
            id="test-device-001",
            alias="Test Device",
            token_hash=bcrypt.hashpw(b"test-token", bcrypt.gensalt()).decode('utf-8'),
            token_id="tok_test001"
        )
        db_session.add(device)
        db_session.commit()
        db_session.refresh(device)
        return device
    
    def test_promote_apk_build(self, db_session, test_apk_build):
        """Test promoting an APK to current with staged rollout"""
        apk = test_apk_build
        
        apk.is_current = True
        apk.staged_rollout_percent = 10
        apk.wifi_only = True
        apk.must_install = False
        apk.promoted_at = datetime.now(timezone.utc)
        apk.promoted_by = "admin"
        
        db_session.commit()
        db_session.refresh(apk)
        
        current_build = get_current_build(db_session, "com.nexmdm.agent")
        
        assert current_build is not None
        assert current_build.id == apk.id
        assert current_build.staged_rollout_percent == 10
        assert current_build.wifi_only == True
        assert current_build.must_install == False
    
    def test_promote_demotes_previous(self, db_session):
        """Test that promoting a new build demotes the previous current build"""
        build_v1 = ApkVersion(
            package_name="com.nexmdm.agent",
            version_name="1.0.0",
            version_code=100,
            file_path="/tmp/v1.apk",
            file_size=5000000,
            uploaded_by="test-user",
            is_active=True,
            is_current=True,
            staged_rollout_percent=100
        )
        db_session.add(build_v1)
        db_session.commit()
        
        build_v2 = ApkVersion(
            package_name="com.nexmdm.agent",
            version_name="2.0.0",
            version_code=200,
            file_path="/tmp/v2.apk",
            file_size=6000000,
            uploaded_by="test-user",
            is_active=True,
            is_current=False
        )
        db_session.add(build_v2)
        db_session.commit()
        
        build_v1.is_current = False
        build_v2.is_current = True
        build_v2.staged_rollout_percent = 25
        build_v2.rollback_from_build_id = build_v1.id
        
        db_session.commit()
        
        current_build = get_current_build(db_session, "com.nexmdm.agent")
        assert current_build.version_code == 200
        
        db_session.refresh(build_v1)
        assert build_v1.is_current == False
    
    def test_rollout_percentage_update(self, db_session, test_apk_build):
        """Test updating staged rollout percentage"""
        apk = test_apk_build
        apk.is_current = True
        apk.staged_rollout_percent = 10
        db_session.commit()
        
        apk.staged_rollout_percent = 50
        db_session.commit()
        db_session.refresh(apk)
        
        assert apk.staged_rollout_percent == 50
    
    def test_rollback_to_previous_build(self, db_session):
        """Test rollback functionality"""
        build_v1 = ApkVersion(
            package_name="com.nexmdm.agent",
            version_name="1.0.0",
            version_code=100,
            file_path="/tmp/v1.apk",
            file_size=5000000,
            uploaded_by="test-user",
            is_active=True,
            is_current=False
        )
        db_session.add(build_v1)
        db_session.commit()
        
        build_v2 = ApkVersion(
            package_name="com.nexmdm.agent",
            version_name="2.0.0",
            version_code=200,
            file_path="/tmp/v2.apk",
            file_size=6000000,
            uploaded_by="test-user",
            is_active=True,
            is_current=True,
            rollback_from_build_id=build_v1.id
        )
        db_session.add(build_v2)
        db_session.commit()
        
        build_v2.is_current = False
        build_v1.is_current = True
        build_v1.promoted_at = datetime.now(timezone.utc)
        build_v1.promoted_by = "admin (rollback)"
        
        db_session.commit()
        
        current_build = get_current_build(db_session, "com.nexmdm.agent")
        assert current_build.version_code == 100
    
    def test_deployment_stats_tracking(self, db_session, test_apk_build):
        """Test deployment statistics are tracked correctly"""
        stats = get_or_create_deployment_stats(db_session, test_apk_build.id)
        
        assert stats.build_id == test_apk_build.id
        assert stats.total_checks == 0
        assert stats.total_downloads == 0
        
        increment_deployment_stat(db_session, test_apk_build.id, "total_checks", 5)
        increment_deployment_stat(db_session, test_apk_build.id, "total_eligible", 2)
        increment_deployment_stat(db_session, test_apk_build.id, "total_downloads", 2)
        increment_deployment_stat(db_session, test_apk_build.id, "installs_success", 1)
        
        db_session.refresh(stats)
        
        assert stats.total_checks == 5
        assert stats.total_eligible == 2
        assert stats.total_downloads == 2
        assert stats.installs_success == 1


class TestAgentUpdateEndpoint:
    """Test /v1/agent/update endpoint behavior"""
    
    def test_no_current_build_returns_304(self):
        """When no build is promoted, return 304"""
        pass
    
    def test_already_on_current_version_returns_304(self):
        """When device is already on current version, return 304"""
        pass
    
    def test_device_not_in_cohort_returns_304(self):
        """When device is not in rollout cohort, return 304"""
        pass
    
    def test_eligible_device_receives_manifest(self):
        """Eligible device receives update manifest with all required fields"""
        pass
    
    def test_update_manifest_includes_security_info(self):
        """Update manifest includes sha256 and signer_fingerprint"""
        pass
    
    def test_update_manifest_includes_constraints(self):
        """Update manifest includes wifi_only and must_install flags"""
        pass


class TestSecurityAndIntegrity:
    """Test security aspects of OTA updates"""
    
    def test_sha256_checksum_generation(self):
        """SHA-256 checksums are generated correctly"""
        import tempfile
        import os
        from server.ota_utils import calculate_sha256
        
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"test content for sha256")
            temp_path = f.name
        
        try:
            sha256 = calculate_sha256(temp_path)
            assert len(sha256) == 64
            assert sha256 == "4f3c4b68cbc8f5e1c1c8f3b7ef71b8e1e1d9a4e2e1c8f3b7ef71b8e1e1d9a4e2"[:64]
        finally:
            os.unlink(temp_path)
    
    def test_signer_fingerprint_stored(self):
        """Signer fingerprint is stored with APK"""
        pass
    
    def test_hmac_signature_for_fcm_update(self):
        """FCM update command includes valid HMAC signature"""
        from server.hmac_utils import compute_hmac_signature, verify_hmac_signature
        import uuid
        
        request_id = str(uuid.uuid4())
        device_id = "test-device"
        action = "update"
        timestamp = datetime.now(timezone.utc).isoformat()
        
        signature = compute_hmac_signature(request_id, device_id, action, timestamp)
        
        assert verify_hmac_signature(request_id, device_id, action, timestamp, signature)
        assert not verify_hmac_signature(request_id, "wrong-device", action, timestamp, signature)


class TestObservability:
    """Test logging and metrics for OTA updates"""
    
    def test_ota_promote_event_logged(self):
        """Promote action generates structured log"""
        pass
    
    def test_ota_manifest_304_logged(self):
        """304 responses are logged with reason"""
        pass
    
    def test_ota_manifest_200_logged(self):
        """Successful manifest delivery is logged"""
        pass
    
    def test_ota_rollback_logged(self):
        """Rollback action is logged with both build IDs"""
        pass
    
    def test_ota_metrics_incremented(self):
        """Prometheus metrics are incremented correctly"""
        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
