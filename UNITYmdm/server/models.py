from datetime import datetime, timezone
from sqlalchemy import String, DateTime, Text, create_engine, Integer, Index, Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from typing import Optional
import os

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String, unique=True, nullable=True)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

class Session(Base):
    __tablename__ = "sessions"
    
    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

class Device(Base):
    __tablename__ = "devices"
    
    id: Mapped[str] = mapped_column(String, primary_key=True)
    alias: Mapped[str] = mapped_column(String, nullable=False)
    app_version: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    token_hash: Mapped[str] = mapped_column(String, nullable=False)
    token_id: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    last_seen: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    last_status: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_alert_state: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    fcm_token: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    last_ping_sent: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_ping_response: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    ping_request_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    model: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    manufacturer: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    android_version: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    sdk_int: Mapped[Optional[int]] = mapped_column(nullable=True)
    build_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    is_device_owner: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True, default=False)
    clipboard_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    clipboard_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    monitored_package: Mapped[str] = mapped_column(String, nullable=False, default="org.zwanoo.android.speedtest")
    monitored_app_name: Mapped[str] = mapped_column(String, nullable=False, default="Speedtest")
    auto_relaunch_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    
    __table_args__ = (
        Index('idx_device_status_query', 'last_seen'),
        Index('idx_device_token_lookup', 'token_id'),
    )

class DeviceEvent(Base):
    __tablename__ = "device_events"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    __table_args__ = (
        Index('idx_device_event_query', 'device_id', 'timestamp'),
    )

class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    token: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    used: Mapped[bool] = mapped_column(Boolean, default=False)
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    
    __table_args__ = (
        Index('idx_password_reset_token_lookup', 'token', 'expires_at'),
        Index('idx_password_reset_user', 'user_id', 'created_at'),
    )

class ApkVersion(Base):
    __tablename__ = "apk_versions"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    version_name: Mapped[str] = mapped_column(String, nullable=False)
    version_code: Mapped[int] = mapped_column(Integer, nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    package_name: Mapped[str] = mapped_column(String, nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    uploaded_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    __table_args__ = (
        Index('idx_apk_version_lookup', 'package_name', 'version_code'),
        UniqueConstraint('package_name', 'version_code', name='uq_package_version'),
    )

class ApkInstallation(Base):
    __tablename__ = "apk_installations"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(String, ForeignKey("devices.id"), nullable=False, index=True)
    apk_version_id: Mapped[int] = mapped_column(Integer, ForeignKey("apk_versions.id"), nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    initiated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    download_progress: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    initiated_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    
    __table_args__ = (
        Index('idx_installation_status', 'device_id', 'status'),
        Index('idx_installation_time', 'initiated_at'),
        Index('idx_installation_version_status', 'apk_version_id', 'status'),
    )

class BatteryWhitelist(Base):
    __tablename__ = "battery_whitelist"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    package_name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    app_name: Mapped[str] = mapped_column(String, nullable=False)
    added_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    added_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    
    __table_args__ = (
        Index('idx_whitelist_enabled', 'enabled'),
    )

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data.db")

# Configure connection pool for better concurrency (handles 100+ devices)
if "sqlite" in DATABASE_URL:
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    # PostgreSQL: optimized for 100+ devices with WebSocket connections
    engine = create_engine(
        DATABASE_URL,
        pool_size=50,          # Base pool size - 50 persistent connections
        max_overflow=50,       # Additional connections when needed - 100 total max
        pool_pre_ping=True,    # Verify connections before use
        pool_recycle=3600,     # Recycle connections after 1 hour
        pool_timeout=30        # Wait up to 30s for available connection
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
