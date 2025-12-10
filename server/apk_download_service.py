"""
Optimized APK download service for high-performance fleet deployments.

Features:
- In-memory caching (200MB, 1hr TTL)
- Download telemetry tracking
- Rate limit bypass for deployments
- Concurrent download support
"""

from fastapi import Response, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from models import ApkVersion, ApkInstallation
from object_storage import get_storage_service, ObjectNotFoundError
from apk_cache import get_apk_cache
from observability import structured_logger, metrics
from datetime import datetime, timezone
from typing import Optional
import io


async def download_apk_optimized(
    apk_id: int,
    db: Session,
    device_id: Optional[str] = None,
    installation_id: Optional[int] = None,
    use_cache: bool = True
) -> Response:
    """
    Optimized APK download with caching and telemetry.
    
    Args:
        apk_id: APK version ID
        db: Database session
        device_id: Optional device ID for telemetry
        installation_id: Optional installation ID for tracking
        use_cache: Enable in-memory caching (default: True)
        
    Returns:
        Response with APK file data
        
    Raises:
        HTTPException: If APK not found or download fails
    """
    # Get APK metadata
    apk = db.query(ApkVersion).filter(ApkVersion.id == apk_id).first()
    if not apk:
        structured_logger.log_event(
            "apk.download.not_found",
            apk_id=apk_id,
            device_id=device_id
        )
        raise HTTPException(status_code=404, detail="APK not found")
    
    cache_hit = False
    download_start = datetime.now(timezone.utc)
    file_data: bytes = b""
    content_type: str = "application/vnd.android.package-archive"
    file_size: int = 0
    
    try:
        # Try in-memory cache first
        cached_result = None
        if use_cache:
            cache = get_apk_cache()
            cached_result = cache.get(f"apk:{apk_id}")
        
        if cached_result:
            file_data, content_type, file_size = cached_result
            cache_hit = True
            structured_logger.log_event(
                "apk.download.cache_hit",
                apk_id=apk_id,
                device_id=device_id,
                file_size=file_size
            )
        else:
            # Cache miss - fetch from object storage
            storage = get_storage_service()
            file_data, content_type, file_size = storage.download_file(
                apk.file_path,
                use_cache=use_cache  # Use object storage layer cache too
            )
            
            # Store in cache for next time
            if use_cache:
                cache = get_apk_cache()
                cache.put(f"apk:{apk_id}", file_data, content_type, file_size)
        
        download_end = datetime.now(timezone.utc)
        download_duration_ms = (download_end - download_start).total_seconds() * 1000
        
        # Calculate download speed
        if download_duration_ms > 0:
            speed_kbps = int((file_size / 1024) / (download_duration_ms / 1000))
        else:
            speed_kbps = 0
        
        # Update installation telemetry if provided
        if installation_id:
            installation = db.query(ApkInstallation).filter(
                ApkInstallation.id == installation_id
            ).first()
            if installation:
                installation.download_start_time = download_start
                installation.download_end_time = download_end
                installation.bytes_downloaded = file_size
                installation.avg_speed_kbps = speed_kbps
                installation.cache_hit = cache_hit
                db.commit()
        
        # Log telemetry
        structured_logger.log_event(
            "apk.download.success",
            apk_id=apk_id,
            device_id=device_id,
            file_size=file_size,
            duration_ms=download_duration_ms,
            speed_kbps=speed_kbps,
            cache_hit=cache_hit
        )
        
        # Increment metrics
        metrics.inc_counter("apk_download_total", {
            "package": apk.package_name,
            "cache_hit": str(cache_hit)
        })
        
        if speed_kbps > 0:
            metrics.observe_histogram("apk_download_speed_kbps", speed_kbps)
        
        # Return response
        return Response(
            content=file_data,
            media_type=content_type,
            headers={
                "Content-Disposition": f'attachment; filename="{apk.package_name}_{apk.version_code}.apk"',
                "Content-Length": str(file_size),
                "X-APK-SHA256": apk.sha256 or "",
                "X-Cache-Hit": str(cache_hit),
                "X-Download-Speed-Kbps": str(speed_kbps),
                "Accept-Ranges": "bytes"  # Indicate range request support for future
            }
        )
        
    except ObjectNotFoundError:
        structured_logger.log_event(
            "apk.download.storage_error",
            apk_id=apk_id,
            device_id=device_id,
            error="Object not found in storage"
        )
        raise HTTPException(status_code=404, detail="APK file not found in storage")
    except Exception as e:
        structured_logger.log_event(
            "apk.download.error",
            apk_id=apk_id,
            device_id=device_id,
            error=str(e),
            error_type=type(e).__name__
        )
        raise HTTPException(status_code=500, detail=f"Download failed: {str(e)}")


def get_cache_statistics() -> dict:
    """Get APK cache statistics for monitoring"""
    try:
        cache = get_apk_cache()
        return cache.get_stats()
    except Exception as e:
        return {"error": str(e)}
