from datetime import datetime, timezone
from sqlalchemy import String, DateTime, Text, create_engine, Integer, Index, Boolean, ForeignKey, UniqueConstraint, BigInteger, func, Computed
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from typing import Optional
import os
import uuid

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
    token_revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)
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
    monitored_threshold_min: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    monitor_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    monitoring_use_defaults: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    auto_relaunch_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    
    __table_args__ = (
        Index('idx_device_status_query', 'last_seen'),
        Index('idx_device_token_lookup', 'token_id'),
        Index('idx_device_monitoring', 'monitor_enabled', 'monitored_package'),
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
    
    build_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    ci_run_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    git_sha: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    signer_fingerprint: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    storage_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    is_current: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    staged_rollout_percent: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    promoted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    promoted_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    rollback_from_build_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    wifi_only: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    must_install: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    __table_args__ = (
        Index('idx_apk_version_lookup', 'package_name', 'version_code'),
        Index('idx_apk_build_type', 'version_code', 'build_type'),
        Index('idx_apk_current', 'is_current', 'package_name'),
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

class EnrollmentToken(Base):
    __tablename__ = "enrollment_tokens"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    token_id: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    alias: Mapped[str] = mapped_column(String, nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    scope: Mapped[str] = mapped_column(String, default='register', nullable=False)
    
    issued_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    issued_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    
    uses_allowed: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    uses_consumed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String, default='active', nullable=False, index=True)
    
    device_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    __table_args__ = (
        Index('idx_enrollment_token_status', 'status', 'expires_at'),
        Index('idx_enrollment_token_lookup', 'token_id'),
        Index('idx_enrollment_issued_by', 'issued_by', 'issued_at'),
    )

class EnrollmentEvent(Base):
    __tablename__ = "enrollment_events"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String, nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    
    token_id: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)
    alias: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    device_serial: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    device_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    
    request_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    build_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    
    details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    __table_args__ = (
        Index('idx_enrollment_event_type', 'event_type', 'timestamp'),
        Index('idx_enrollment_event_token', 'token_id', 'timestamp'),
    )

class Command(Base):
    __tablename__ = "commands"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    device_id: Mapped[str] = mapped_column(String, ForeignKey("devices.id"), nullable=False, index=True)
    command_type: Mapped[str] = mapped_column(String, nullable=False)
    parameters: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    status: Mapped[str] = mapped_column(String, default='pending', nullable=False)
    result: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    __table_args__ = (
        Index('idx_command_status', 'device_id', 'status'),
        Index('idx_command_created', 'created_at'),
    )

class FcmDispatch(Base):
    __tablename__ = "fcm_dispatches"
    
    request_id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    device_id: Mapped[str] = mapped_column(String, ForeignKey("devices.id"), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String, nullable=False)
    payload_hash: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    
    sent_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    fcm_message_id: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)
    http_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    fcm_status: Mapped[str] = mapped_column(String, default='pending', nullable=False)
    error_msg: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    response_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    result: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    result_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    retries: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    __table_args__ = (
        Index('idx_fcm_device_sent', 'device_id', 'sent_at'),
        Index('idx_fcm_action_sent', 'action', 'sent_at'),
    )

class ApkDownloadEvent(Base):
    __tablename__ = "apk_download_events"
    
    event_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    build_id: Mapped[int] = mapped_column(Integer, ForeignKey("apk_versions.id"), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String, nullable=False)
    
    token_id: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)
    admin_user: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    ip: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    
    __table_args__ = (
        Index('idx_apk_download_build_ts', 'build_id', 'ts'),
        Index('idx_apk_download_token_ts', 'token_id', 'ts'),
    )

class ApkDeploymentStats(Base):
    __tablename__ = "apk_deployment_stats"
    
    build_id: Mapped[int] = mapped_column(Integer, ForeignKey("apk_versions.id"), primary_key=True)
    total_checks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_eligible: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_downloads: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    installs_success: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    installs_failed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    verify_failed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_updated: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    
    __table_args__ = (
        Index('idx_deployment_stats_updated', 'last_updated'),
    )

class DeviceHeartbeat(Base):
    __tablename__ = "device_heartbeats"
    
    hb_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(String, ForeignKey("devices.id"), nullable=False, index=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    
    ip: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, default='ok', nullable=False)
    
    battery_pct: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    plugged: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    temp_c: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    network_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    signal_dbm: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    uptime_s: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    ram_used_mb: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    unity_pkg_version: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    unity_running: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    agent_version: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    
    __table_args__ = (
        Index('idx_heartbeat_device_ts', 'device_id', 'ts'),
    )

class DeviceLastStatus(Base):
    __tablename__ = "device_last_status"
    
    device_id: Mapped[str] = mapped_column(String, ForeignKey("devices.id"), primary_key=True, nullable=False)
    last_ts: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    
    battery_pct: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    network_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    unity_running: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    signal_dbm: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    agent_version: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    ip: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, default='ok', nullable=False)
    
    service_up: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    monitored_foreground_recent_s: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    monitored_package: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    monitored_threshold_min: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    __table_args__ = (
        Index('idx_last_status_ts', 'last_ts'),
        Index('idx_last_status_offline_query', 'last_ts', 'status'),
        Index('idx_last_status_unity_down', 'unity_running', 'last_ts'),
        Index('idx_last_status_service_down', 'service_up', 'last_ts'),
    )

class HeartbeatPartition(Base):
    __tablename__ = "hb_partitions"
    
    partition_name: Mapped[str] = mapped_column(String, primary_key=True, nullable=False)
    range_start: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    range_end: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    state: Mapped[str] = mapped_column(String, nullable=False, default='active')
    
    row_count: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    bytes_size: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    checksum_sha256: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    archive_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    archived_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    dropped_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    __table_args__ = (
        Index('idx_hb_partition_range', 'range_start', 'range_end'),
        Index('idx_hb_partition_state', 'state'),
    )

class AlertState(Base):
    __tablename__ = "alert_states"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(String, ForeignKey("devices.id"), nullable=False, index=True)
    condition: Mapped[str] = mapped_column(String, nullable=False)
    state: Mapped[str] = mapped_column(String, nullable=False, default='ok')
    
    last_raised_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_recovered_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    cooldown_until: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)
    
    consecutive_violations: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_value: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    
    __table_args__ = (
        Index('idx_alert_device_condition', 'device_id', 'condition'),
        Index('idx_alert_cooldown', 'cooldown_until'),
        UniqueConstraint('device_id', 'condition', name='uq_device_condition'),
    )

class DeviceSelection(Base):
    __tablename__ = "device_selections"
    
    selection_id: Mapped[str] = mapped_column(String, primary_key=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    
    filter_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    total_count: Mapped[int] = mapped_column(Integer, nullable=False)
    device_ids_json: Mapped[str] = mapped_column(Text, nullable=False)
    
    created_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    
    __table_args__ = (
        Index('idx_selection_expires', 'expires_at'),
        Index('idx_selection_created', 'created_at'),
    )

class MonitoringDefaults(Base):
    __tablename__ = "monitoring_defaults"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    package: Mapped[str] = mapped_column(String, nullable=False, default="org.zwanoo.android.speedtest")
    alias: Mapped[str] = mapped_column(String, nullable=False, default="Speedtest")
    threshold_min: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    
    __table_args__ = (
        Index('idx_monitoring_defaults_updated', 'updated_at'),
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
