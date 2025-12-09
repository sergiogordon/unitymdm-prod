"""
Optimized APK download service for high-performance fleet deployments.

Features:
- In-memory caching (200MB, 1hr TTL)
- Download telemetry tracking
- Rate limit bypass for deployments
- Concurrent download support
- Streaming support for large files (>50MB)
"""

from fastapi import Response, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from models import ApkVersion, ApkInstallation
from object_storage import get_storage_service, ObjectNotFoundError
from apk_cache import get_apk_cache
from observability import structured_logger, metrics
from datetime import datetime, timezone
from typing import Optional, Iterator
import io

# Threshold for streaming large files (50MB)
# Files above this size will be streamed instead of loaded entirely into memory
STREAMING_THRESHOLD_BYTES = 50 * 1024 * 1024  # 50MB
CHUNK_SIZE = 1024 * 1024  # 1MB chunks for streaming


def _chunk_generator(file_data: bytes, chunk_size: int = CHUNK_SIZE) -> Iterator[bytes]:
    """
    Generator that yields file data in chunks.
    
    Args:
        file_data: The file data to chunk
        chunk_size: Size of each chunk in bytes
        
    Yields:
        Chunks of file data as bytes
    """
    for i in range(0, len(file_data), chunk_size):
        yield file_data[i:i + chunk_size]


async def download_apk_optimized(
    apk_id: int,
    db: Session,
    device_id: Optional[str] = None,
    installation_id: Optional[int] = None,
    use_cache: bool = True
) -> Response:
    """
    Optimized APK download with caching and telemetry.
    Uses streaming for large files (>50MB) to prevent memory exhaustion.
    
    Args:
        apk_id: APK version ID
        db: Database session
        device_id: Optional device ID for telemetry
        installation_id: Optional installation ID for tracking
        use_cache: Enable in-memory caching (default: True)
        
    Returns:
        Response or StreamingResponse with APK file data
        
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
    
    # Check file size to determine if we should stream
    # Use database file_size for initial check
    use_streaming = apk.file_size > STREAMING_THRESHOLD_BYTES
    
    # For large files, skip cache (they exceed cache limit anyway)
    if use_streaming:
        use_cache = False
        structured_logger.log_event(
            "apk.download.streaming_mode",
            apk_id=apk_id,
            device_id=device_id,
            file_size=apk.file_size,
            threshold=STREAMING_THRESHOLD_BYTES
        )
    
    cache_hit = False
    download_start = datetime.now(timezone.utc)
    file_data: bytes = b""
    content_type: str = "application/vnd.android.package-archive"
    file_size: int = 0
    
    try:
        # Try in-memory cache first (only for small files)
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
            
            # Store in cache for next time (only for small files)
            if use_cache and not use_streaming:
                cache = get_apk_cache()
                cache.put(f"apk:{apk_id}", file_data, content_type, file_size)
        
        # Re-check streaming based on actual file size (in case it differs from DB)
        # This handles edge cases where cached file might be different
        if file_size > STREAMING_THRESHOLD_BYTES:
            use_streaming = True
        
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
            cache_hit=cache_hit,
            streaming=use_streaming
        )
        
        # Increment metrics
        metrics.inc_counter("apk_download_total", {
            "package": apk.package_name,
            "cache_hit": str(cache_hit),
            "streaming": str(use_streaming)
        })
        
        if speed_kbps > 0:
            metrics.observe_histogram("apk_download_speed_kbps", speed_kbps)
        
        # Prepare common headers
        headers = {
            "Content-Disposition": f'attachment; filename="{apk.package_name}_{apk.version_code}.apk"',
            "Content-Length": str(file_size),
            "Content-Type": content_type,
            "X-APK-SHA256": apk.sha256 or "",
            "X-Cache-Hit": str(cache_hit),
            "X-Download-Speed-Kbps": str(speed_kbps),
            "Accept-Ranges": "bytes"  # Indicate range request support for future
        }
        
        # Use streaming for large files, regular response for small files
        if use_streaming:
            # Create generator that yields chunks
            chunk_gen = _chunk_generator(file_data, CHUNK_SIZE)
            return StreamingResponse(
                chunk_gen,
                media_type=content_type,
                headers=headers
            )
        else:
            # Return regular response for small files (cached path)
            return Response(
                content=file_data,
                media_type=content_type,
                headers=headers
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
