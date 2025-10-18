"""
Async SQLAlchemy Models for MDM System
Optimized for high-concurrency device management
"""

from datetime import datetime, timezone
from sqlalchemy import (
    String, DateTime, Text, Integer, Index, Boolean, 
    ForeignKey, UniqueConstraint, Float, JSON, func
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Optional, List, Dict, Any
from database import Base

class User(Base):
    __tablename__ = "users"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), unique=True, nullable=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Relationships
    password_resets: Mapped[List["PasswordResetToken"]] = relationship(
        back_populates="user", 
        cascade="all, delete-orphan"
    )
    
    __table_args__ = (
        Index('idx_user_username_active', 'username', 'is_active'),
    )

class Device(Base):
    __tablename__ = "devices"
    
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    alias: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    app_version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    token_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    token_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True, unique=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    last_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True
    )
    
    # Device status and metadata
    last_status: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    last_alert_state: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    fcm_token: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    
    # Ping tracking
    last_ping_sent: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_ping_response: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    ping_request_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # Device information
    model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    manufacturer: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    android_version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    sdk_int: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    build_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    is_device_owner: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True, default=False)
    
    # Remote control
    clipboard_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    clipboard_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # App monitoring
    monitored_package: Mapped[str] = mapped_column(
        String(255), 
        nullable=False, 
        default="org.zwanoo.android.speedtest"
    )
    monitored_app_name: Mapped[str] = mapped_column(
        String(100), 
        nullable=False, 
        default="Speedtest"
    )
    auto_relaunch_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    
    # Performance metrics
    battery_level: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    battery_charging: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    memory_available_mb: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    memory_total_mb: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    network_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    
    # Relationships
    events: Mapped[List["DeviceEvent"]] = relationship(
        back_populates="device",
        cascade="all, delete-orphan",
        lazy="select"
    )
    installations: Mapped[List["ApkInstallation"]] = relationship(
        back_populates="device",
        cascade="all, delete-orphan"
    )
    
    __table_args__ = (
        Index('idx_device_status_query', 'last_seen', 'battery_level'),
        Index('idx_device_token_lookup', 'token_id'),
        Index('idx_device_monitoring', 'monitored_package', 'auto_relaunch_enabled'),
    )

class DeviceEvent(Base):
    __tablename__ = "device_events"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(
        String(100), 
        ForeignKey("devices.id", ondelete="CASCADE"),
        nullable=False, 
        index=True
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True
    )
    details: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    severity: Mapped[str] = mapped_column(
        String(20), 
        nullable=False, 
        default="info"
    )  # info, warning, error, critical
    
    # Relationships
    device: Mapped["Device"] = relationship(back_populates="events")
    
    __table_args__ = (
        Index('idx_device_event_query', 'device_id', 'timestamp'),
        Index('idx_device_event_type_time', 'event_type', 'timestamp'),
        Index('idx_device_event_cleanup', 'timestamp'),  # For efficient cleanup
    )

class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, 
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, 
        index=True
    )
    token: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True
    )
    used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    
    # Relationships
    user: Mapped["User"] = relationship(back_populates="password_resets")
    
    __table_args__ = (
        Index('idx_password_reset_token_lookup', 'token', 'expires_at', 'used'),
        Index('idx_password_reset_user', 'user_id', 'created_at'),
        Index('idx_password_reset_cleanup', 'expires_at'),  # For cleanup tasks
    )

class ApkVersion(Base):
    __tablename__ = "apk_versions"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    version_name: Mapped[str] = mapped_column(String(50), nullable=False)
    version_code: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False)  # SHA256
    
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    uploaded_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    min_sdk: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    target_sdk: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    release_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Relationships
    installations: Mapped[List["ApkInstallation"]] = relationship(
        back_populates="apk_version",
        cascade="all, delete-orphan"
    )
    
    __table_args__ = (
        Index('idx_apk_version_active', 'is_active', 'version_code'),
        UniqueConstraint('version_code', name='uq_apk_version_code'),
    )

class ApkInstallation(Base):
    __tablename__ = "apk_installations"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("devices.id", ondelete="CASCADE"),
        nullable=False
    )
    apk_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("apk_versions.id", ondelete="CASCADE"),
        nullable=False
    )
    
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="pending"
    )  # pending, downloading, installing, completed, failed
    
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    # Relationships
    device: Mapped["Device"] = relationship(back_populates="installations")
    apk_version: Mapped["ApkVersion"] = relationship(back_populates="installations")
    
    __table_args__ = (
        Index('idx_apk_installation_device', 'device_id', 'status'),
        Index('idx_apk_installation_status', 'status', 'requested_at'),
        UniqueConstraint('device_id', 'apk_id', name='uq_device_apk'),
    )

class BatteryWhitelist(Base):
    __tablename__ = "battery_whitelist"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    package_name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    added_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    __table_args__ = (
        Index('idx_battery_whitelist_package', 'package_name'),
    )

class Command(Base):
    __tablename__ = "commands"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    device_id: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("devices.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    command_type: Mapped[str] = mapped_column(String(50), nullable=False)
    parameters: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True
    )
    
    fcm_sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    fcm_response_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    fcm_response_body: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="pending"
    )
    result: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    initiated_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    __table_args__ = (
        Index('idx_command_request_lookup', 'request_id'),
        Index('idx_command_device_status', 'device_id', 'status', 'created_at'),
        Index('idx_command_pending', 'status', 'created_at'),
    )

class SessionToken(Base):
    __tablename__ = "session_tokens"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    token_jti: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    __table_args__ = (
        Index('idx_session_token_lookup', 'token_jti', 'revoked'),
        Index('idx_session_token_cleanup', 'expires_at'),
    )

class EnrollmentToken(Base):
    __tablename__ = "enrollment_tokens"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    token: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    
    alias: Mapped[str] = mapped_column(String(255), nullable=False)
    unity_package: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True
    )
    
    used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    device_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    created_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    
    __table_args__ = (
        Index('idx_enrollment_token_lookup', 'token', 'expires_at', 'used'),
        Index('idx_enrollment_token_cleanup', 'expires_at'),
    )