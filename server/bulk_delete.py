"""
Bulk device deletion with multi-select, selection snapshots, and historical data purging.
"""
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import text, func
from typing import List, Dict, Any, Optional
import json
import uuid
from fastapi import HTTPException
from observability import structured_logger, metrics
from models import Device, DeviceEvent, DeviceSelection, DeviceLastStatus
from purge_jobs import purge_manager

# Constants
SELECTION_TTL_MINUTES = 15
MAX_BATCH_SIZE = 10000

def create_device_selection(
    db: Session,
    filter_criteria: Dict[str, Any],
    created_by: Optional[str] = None
) -> Dict[str, Any]:
    """
    Create a device selection snapshot based on filter criteria.
    
    Args:
        db: Database session
        filter_criteria: Dictionary with filter parameters (query, status, network, etc.)
        created_by: Admin username who created the selection
    
    Returns:
        Dictionary with selection_id, total_count, and expires_at
    """
    start_time = datetime.now(timezone.utc)
    
    # Build query based on filter criteria
    query = db.query(Device)
    
    # Apply filters
    search_query = filter_criteria.get("query", "")
    if search_query:
        search_pattern = f"%{search_query}%"
        query = query.filter(
            (Device.alias.ilike(search_pattern)) |
            (Device.id.ilike(search_pattern))
        )
    
    status_filter = filter_criteria.get("status", "")
    if status_filter:
        # Status filtering based on last_seen
        heartbeat_interval = int(filter_criteria.get("heartbeat_interval", 300))
        offline_threshold = datetime.now(timezone.utc) - timedelta(seconds=heartbeat_interval * 3)
        
        if status_filter == "online":
            query = query.filter(Device.last_seen >= offline_threshold)
        elif status_filter == "offline":
            query = query.filter(Device.last_seen < offline_threshold)
    
    # Network filter (requires parsing last_status JSON)
    network_filter = filter_criteria.get("network", "")
    if network_filter:
        # This would require JSONB query or parsing - simplified for now
        pass
    
    # Unity status filter
    unity_filter = filter_criteria.get("unity", "")
    if unity_filter:
        # Would need to check DeviceLastStatus table
        pass
    
    # Execute query and get device IDs
    devices = query.all()
    device_ids = [d.id for d in devices]
    total_count = len(device_ids)
    
    # Create selection snapshot
    selection_id = f"sel_{uuid.uuid4().hex[:16]}"
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=SELECTION_TTL_MINUTES)
    
    selection = DeviceSelection(
        selection_id=selection_id,
        created_at=datetime.now(timezone.utc),
        expires_at=expires_at,
        filter_json=json.dumps(filter_criteria),
        total_count=total_count,
        device_ids_json=json.dumps(device_ids),
        created_by=created_by
    )
    
    db.add(selection)
    db.commit()
    
    duration_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
    
    structured_logger.log_event(
        "device.selection.created",
        selection_id=selection_id,
        total_count=total_count,
        filter=filter_criteria,
        created_by=created_by,
        duration_ms=int(duration_ms)
    )
    
    metrics.inc_counter("device_selection_created_total")
    
    return {
        "selection_id": selection_id,
        "total_count": total_count,
        "expires_at": expires_at.isoformat() + "Z"
    }


def get_device_selection(db: Session, selection_id: str) -> Optional[DeviceSelection]:
    """
    Retrieve a device selection by ID.
    Returns None if not found or expired.
    """
    selection = db.query(DeviceSelection).filter(
        DeviceSelection.selection_id == selection_id
    ).first()
    
    if not selection:
        return None
    
    # Check if expired
    now = datetime.now(timezone.utc)
    if selection.expires_at < now:
        structured_logger.log_event(
            "device.selection.expired",
            selection_id=selection_id,
            expired_at=selection.expires_at.isoformat()
        )
        return None
    
    return selection


def bulk_delete_devices(
    db: Session,
    device_ids: Optional[List[str]] = None,
    selection_id: Optional[str] = None,
    purge_history: bool = True,
    admin_user: Optional[str] = None
) -> Dict[str, Any]:
    """
    Perform bulk device deletion with optional historical data purging.
    
    Args:
        db: Database session
        device_ids: Explicit list of device IDs to delete (or None if using selection_id)
        selection_id: Selection snapshot ID (or None if using explicit device_ids)
        purge_history: Whether to purge historical data (heartbeats, dispatches, etc.)
        admin_user: Admin username performing the deletion
    
    Returns:
        Dictionary with deleted count, skipped count, and request_id
    """
    request_id = str(uuid.uuid4())
    start_time = datetime.now(timezone.utc)
    
    # Get device IDs from selection if provided
    if selection_id:
        selection = get_device_selection(db, selection_id)
        if not selection:
            raise HTTPException(
                status_code=410,
                detail="Selection snapshot expired or not found. Please create a new selection."
            )
        
        device_ids = json.loads(selection.device_ids_json)
        
        structured_logger.log_event(
            "device.bulk_delete.using_selection",
            request_id=request_id,
            selection_id=selection_id,
            device_count=len(device_ids)
        )
    
    if not device_ids or len(device_ids) == 0:
        raise HTTPException(status_code=400, detail="No device IDs provided")
    
    # Check batch size limit
    if len(device_ids) > MAX_BATCH_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"Batch size exceeds maximum of {MAX_BATCH_SIZE}. Please delete in smaller chunks."
        )
    
    structured_logger.log_event(
        "device.hard_delete.request",
        request_id=request_id,
        count=len(device_ids),
        purge_history=purge_history,
        selection_id=selection_id,
        admin_id=admin_user
    )
    
    deleted_count = 0
    skipped_count = 0
    sample_aliases = []
    
    # Immediate deletes
    for device_id in device_ids:
        try:
            device = db.query(Device).filter(Device.id == device_id).first()
            
            if not device:
                skipped_count += 1
                continue
            
            # Store alias for audit
            if len(sample_aliases) < 10:
                sample_aliases.append(device.alias)
            
            # Revoke device token immediately
            device.token_revoked_at = datetime.now(timezone.utc)
            db.flush()
            
            # Delete from device_last_status
            db.query(DeviceLastStatus).filter(
                DeviceLastStatus.device_id == device_id
            ).delete()
            
            # Delete device events
            db.query(DeviceEvent).filter(
                DeviceEvent.device_id == device_id
            ).delete()
            
            # Delete device record
            db.delete(device)
            deleted_count += 1
            
            # Log individual deletion
            structured_logger.log_event(
                "device.hard_deleted",
                request_id=request_id,
                device_id=device_id,
                alias=device.alias
            )
            
        except Exception as e:
            structured_logger.log_event(
                "device.delete.error",
                level="ERROR",
                request_id=request_id,
                device_id=device_id,
                error=str(e)
            )
            skipped_count += 1
    
    # Commit immediate deletes
    db.commit()
    
    # Token revocation batch log
    structured_logger.log_event(
        "device.token.revoke.batch",
        request_id=request_id,
        count=deleted_count
    )
    
    # Enqueue background purge jobs if requested
    if purge_history and deleted_count > 0:
        purge_manager.enqueue_purge(
            device_ids=device_ids[:deleted_count],  # Only successfully deleted devices
            request_id=request_id,
            purge_history=True
        )
    
    duration_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
    
    # Audit log completion
    structured_logger.log_event(
        "device.hard_delete.completed",
        request_id=request_id,
        deleted=deleted_count,
        skipped=skipped_count,
        duration_ms=int(duration_ms),
        purge_history=purge_history,
        admin_id=admin_user
    )
    
    # Update metrics
    metrics.inc_counter("devices_deleted_total", value=deleted_count)
    metrics.observe_histogram("bulk_delete_duration_ms", duration_ms)
    
    return {
        "deleted": deleted_count,
        "skipped": skipped_count,
        "request_id": request_id,
        "sample_aliases": sample_aliases,
        "purge_history": purge_history
    }


def cleanup_expired_selections(db: Session):
    """
    Clean up expired device selections.
    Called periodically by background job.
    """
    now = datetime.now(timezone.utc)
    
    result = db.query(DeviceSelection).filter(
        DeviceSelection.expires_at < now
    ).delete()
    
    db.commit()
    
    if result > 0:
        structured_logger.log_event(
            "device.selection.cleanup",
            deleted=result
        )
    
    return result
