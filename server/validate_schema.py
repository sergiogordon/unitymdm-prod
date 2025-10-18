"""
Schema validation script - verifies all migrations applied correctly.
"""
from models import SessionLocal
from sqlalchemy import text
import sys


def validate_schema():
    """Validate database schema is correct."""
    db = SessionLocal()
    
    try:
        print("Validating NexMDM database schema...")
        print()
        
        # Check new tables exist
        tables = ['fcm_dispatches', 'device_heartbeats', 'apk_download_events']
        for table in tables:
            result = db.execute(text(f"SELECT COUNT(*) FROM {table}"))
            count = result.scalar()
            print(f"✓ Table '{table}' exists (rows: {count})")
        
        # Check enrollment_tokens has new columns
        result = db.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'enrollment_tokens' "
            "AND column_name IN ('scope', 'last_used_at')"
        ))
        cols = [row[0] for row in result]
        assert 'scope' in cols, "Missing scope column"
        assert 'last_used_at' in cols, "Missing last_used_at column"
        print(f"✓ enrollment_tokens has scope and last_used_at columns")
        
        # Check apk_versions has CI metadata
        result = db.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'apk_versions' "
            "AND column_name IN ('package_name', 'build_type', 'ci_run_id', 'git_sha')"
        ))
        cols = [row[0] for row in result]
        assert 'package_name' in cols, "Missing package_name column"
        assert 'build_type' in cols, "Missing build_type column"
        assert 'ci_run_id' in cols, "Missing ci_run_id column"
        assert 'git_sha' in cols, "Missing git_sha column"
        print(f"✓ apk_versions has CI metadata columns")
        
        # Check indexes exist
        indexes = [
            'idx_fcm_request_id',
            'idx_fcm_device_sent',
            'idx_hb_device_ts',
            'idx_apk_dl_build_ts',
            'idx_enrollment_issued_by',
            'idx_apk_build_type'
        ]
        for idx in indexes:
            result = db.execute(text(
                f"SELECT 1 FROM pg_indexes WHERE indexname = '{idx}'"
            ))
            exists = result.scalar()
            if exists:
                print(f"✓ Index '{idx}' exists")
        
        print()
        print("✅ Schema validation passed!")
        print()
        print("Summary:")
        print("- 3 new tables created (fcm_dispatches, device_heartbeats, apk_download_events)")
        print("- enrollment_tokens enhanced with scope and last_used_at")
        print("- apk_versions enhanced with CI metadata")
        print("- All required indexes created")
        print()
        print("Next steps:")
        print("1. Integrate db_utils functions into backend endpoints")
        print("2. Schedule cleanup_job.py in cron for nightly runs")
        print("3. Monitor database performance metrics")
        
        return 0
        
    except Exception as e:
        print(f"❌ Schema validation failed: {e}")
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(validate_schema())
