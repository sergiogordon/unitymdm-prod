from fastapi import UploadFile, HTTPException
from sqlalchemy.orm import Session
from models import ApkVersion
from datetime import datetime, timezone
from typing import Optional
from object_storage import get_storage_service, ObjectNotFoundError
import hashlib

async def save_apk_file(
    file: UploadFile, 
    package_name: str,
    version_name: str,
    version_code: int,
    db: Session, 
    uploaded_by: Optional[str] = None,
    notes: Optional[str] = None
) -> ApkVersion:
    """
    Save uploaded APK file to App Storage and create database record
    """
    if not file.filename or not file.filename.endswith('.apk'):
        raise HTTPException(status_code=400, detail="File must be an APK")
    
    existing = db.query(ApkVersion).filter(
        ApkVersion.package_name == package_name,
        ApkVersion.version_code == version_code
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=409, 
            detail=f"APK version {version_name} (code {version_code}) already exists for {package_name}"
        )
    
    try:
        # Read file content
        content = await file.read()
        file_size = len(content)
        
        # Calculate SHA-256 hash for caching and verification
        sha256_hash = hashlib.sha256(content).hexdigest()
        
        # Upload to App Storage
        storage = get_storage_service()
        final_filename = f"{package_name}_{version_code}.apk"
        object_path = storage.upload_file(
            file_data=content,
            filename=final_filename,
            content_type="application/vnd.android.package-archive"
        )
        
        # Create database record with App Storage path
        apk_version = ApkVersion(
            version_name=version_name,
            version_code=version_code,
            file_path=object_path,  # Store App Storage path (e.g., /bucket/uuid_file.apk)
            file_size=file_size,
            package_name=package_name,
            uploaded_at=datetime.now(timezone.utc),
            uploaded_by=uploaded_by,
            is_active=True,
            notes=notes,
            sha256=sha256_hash
        )
        
        db.add(apk_version)
        db.commit()
        db.refresh(apk_version)
        
        return apk_version
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save APK to App Storage: {str(e)}")

def get_apk_download_url(apk_version: ApkVersion, base_url: str) -> str:
    """Generate download URL for APK"""
    return f"{base_url}/v1/apk/download/{apk_version.id}"
