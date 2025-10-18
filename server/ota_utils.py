import hashlib
from typing import Optional
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from server.models import ApkVersion, ApkDeploymentStats
import logging
import json

logger = logging.getLogger(__name__)

def compute_device_cohort(device_id: str) -> int:
    """
    Compute deterministic cohort for a device (0-99) using SHA-256 hash.
    This ensures stable, reproducible cohorting for staged rollouts.
    
    Args:
        device_id: Unique device identifier
        
    Returns:
        Integer between 0 and 99 representing the device's cohort
    """
    hash_bytes = hashlib.sha256(device_id.encode('utf-8')).digest()
    cohort = int.from_bytes(hash_bytes[:4], byteorder='big') % 100
    return cohort


def is_device_eligible_for_rollout(device_id: str, rollout_percent: int) -> bool:
    """
    Check if a device is eligible for a staged rollout based on cohort hashing.
    
    Args:
        device_id: Unique device identifier
        rollout_percent: Rollout percentage (0-100)
        
    Returns:
        True if device is in the eligible cohort, False otherwise
    """
    if rollout_percent >= 100:
        return True
    if rollout_percent <= 0:
        return False
    
    cohort = compute_device_cohort(device_id)
    return cohort < rollout_percent


def get_current_build(db: Session, package_name: str = "com.nexmdm.agent") -> Optional[ApkVersion]:
    """
    Get the current promoted build for a package.
    
    Args:
        db: Database session
        package_name: APK package name
        
    Returns:
        Current ApkVersion or None if no build is promoted
    """
    return db.query(ApkVersion).filter(
        ApkVersion.package_name == package_name,
        ApkVersion.is_current == True,
        ApkVersion.is_active == True
    ).first()


def get_or_create_deployment_stats(db: Session, build_id: int) -> ApkDeploymentStats:
    """
    Get or create deployment stats for a build.
    
    Args:
        db: Database session
        build_id: APK version ID
        
    Returns:
        ApkDeploymentStats instance
    """
    stats = db.query(ApkDeploymentStats).filter(
        ApkDeploymentStats.build_id == build_id
    ).first()
    
    if not stats:
        stats = ApkDeploymentStats(build_id=build_id)
        db.add(stats)
        db.commit()
        db.refresh(stats)
    
    return stats


def increment_deployment_stat(db: Session, build_id: int, stat_name: str, increment: int = 1):
    """
    Atomically increment a deployment stat counter.
    
    Args:
        db: Database session
        build_id: APK version ID
        stat_name: Name of the stat field to increment
        increment: Amount to increment by (default 1)
    """
    stats = get_or_create_deployment_stats(db, build_id)
    
    current_value = getattr(stats, stat_name, 0)
    setattr(stats, stat_name, current_value + increment)
    stats.last_updated = datetime.now(timezone.utc)
    
    db.commit()
    
    logger.info(json.dumps({
        "event": "ota.stat.increment",
        "build_id": build_id,
        "stat": stat_name,
        "value": current_value + increment
    }))


def log_ota_event(event_type: str, build_id: Optional[int] = None, device_id: Optional[str] = None, 
                  rollout_percent: Optional[int] = None, **extra_fields):
    """
    Log structured OTA event for observability.
    
    Args:
        event_type: Type of OTA event
        build_id: APK version ID
        device_id: Device identifier
        rollout_percent: Rollout percentage
        **extra_fields: Additional fields to include in log
    """
    log_data = {
        "event": event_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    
    if build_id is not None:
        log_data["build_id"] = build_id
    if device_id is not None:
        log_data["device_id"] = device_id
    if rollout_percent is not None:
        log_data["rollout_percent"] = rollout_percent
    
    log_data.update(extra_fields)
    
    logger.info(json.dumps(log_data))


def calculate_sha256(file_path: str) -> str:
    """
    Calculate SHA-256 checksum of a file.
    
    Args:
        file_path: Path to the file
        
    Returns:
        Hex-encoded SHA-256 checksum
    """
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()
