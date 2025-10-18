from fastapi import UploadFile, HTTPException
from sqlalchemy.orm import Session
from models import ApkVersion
from datetime import datetime, timezone
import os
from pathlib import Path
from typing import Optional

APK_STORAGE_DIR = os.getenv("APK_STORAGE_DIR", "./apk_storage")

def ensure_apk_storage_dir() -> str:
    """Ensure APK storage directory exists and return its path"""
    Path(APK_STORAGE_DIR).mkdir(parents=True, exist_ok=True)
    return APK_STORAGE_DIR

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
    Save uploaded APK file and create database record
    """
    ensure_apk_storage_dir()
    
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
    
    final_filename = f"{package_name}_{version_code}.apk"
    final_path = os.path.join(APK_STORAGE_DIR, final_filename)
    temp_path = f"{final_path}.tmp"
    
    try:
        with open(temp_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
        
        os.rename(temp_path, final_path)
        
        file_size = os.path.getsize(final_path)
        
        apk_version = ApkVersion(
            version_name=version_name,
            version_code=version_code,
            file_path=final_path,
            file_size=file_size,
            package_name=package_name,
            uploaded_at=datetime.now(timezone.utc),
            uploaded_by=uploaded_by,
            is_active=True,
            notes=notes
        )
        
        db.add(apk_version)
        db.commit()
        db.refresh(apk_version)
        
        return apk_version
        
    except HTTPException:
        raise
    except Exception as e:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        if os.path.exists(final_path):
            os.remove(final_path)
        raise HTTPException(status_code=500, detail=f"Failed to save APK: {str(e)}")

def get_apk_download_url(apk_version: ApkVersion, base_url: str) -> str:
    """Generate download URL for APK"""
    return f"{base_url}/v1/apk/download/{apk_version.id}"
