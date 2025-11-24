from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import datetime

class AppVersion(BaseModel):
    installed: bool
    version_name: Optional[str] = None
    version_code: Optional[int] = None

class SpeedtestRunningSignals(BaseModel):
    has_service_notification: bool
    foreground_recent_seconds: Optional[int] = None

class Battery(BaseModel):
    pct: int
    charging: bool
    temperature_c: float

class SystemInfo(BaseModel):
    uptime_seconds: int
    android_version: str
    sdk_int: int
    patch_level: str
    build_id: str
    model: str
    manufacturer: str

class Memory(BaseModel):
    total_ram_mb: int
    avail_ram_mb: int
    pressure_pct: int

class Network(BaseModel):
    transport: str
    ssid: Optional[str] = None
    carrier: Optional[str] = None
    ip: Optional[str] = None

class SelfHealHints(BaseModel):
    last_crash_speedtest: Optional[str] = None

class HeartbeatPayload(BaseModel):
    device_id: Optional[str] = Field(None, max_length=100)  # Optional - use authenticated device.id instead
    alias: str = Field(..., min_length=1, max_length=200)
    app_version: Optional[str] = Field(None, max_length=50)
    timestamp_utc: str = Field(..., max_length=50)
    app_versions: dict[str, AppVersion]
    speedtest_running_signals: SpeedtestRunningSignals
    battery: Battery
    system: SystemInfo
    memory: Memory
    network: Network
    fcm_token: Optional[str] = Field(None, max_length=500)
    is_ping_response: Optional[bool] = None
    ping_request_id: Optional[str] = Field(None, max_length=100)
    self_heal_hints: Optional[SelfHealHints] = None
    is_device_owner: Optional[bool] = None
    monitored_foreground_recent_s: Optional[int] = Field(None, ge=-1, le=86400)  # -1 sentinel for unavailable, 0-86400 seconds (0 to 24 hours)

class HeartbeatResponse(BaseModel):
    ok: bool

class DeviceSummary(BaseModel):
    id: str
    alias: str
    app_version: Optional[str] = None
    last_seen: datetime
    created_at: datetime
    status: str
    last_status: Optional[dict] = None
    model: Optional[str] = None
    manufacturer: Optional[str] = None
    android_version: Optional[str] = None
    sdk_int: Optional[int] = None
    build_id: Optional[str] = None
    is_device_owner: Optional[bool] = None
    monitored_package: str = "com.unitynetwork.unityapp"
    monitored_app_name: str = "Speedtest"
    monitored_threshold_min: int = 10
    monitor_enabled: bool = True
    auto_relaunch_enabled: bool = False

class RegisterResponse(BaseModel):
    device_token: str
    device_id: str

class UserRegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50, pattern="^[a-zA-Z0-9_-]+$")
    password: str = Field(..., min_length=8, max_length=200)
    email: Optional[str] = Field(None, max_length=255)

    @field_validator('email')
    @classmethod
    def validate_email(cls, v):
        if v and '@' not in v:
            raise ValueError('Invalid email format')
        return v

class UserLoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=1, max_length=200)

class UpdateDeviceAliasRequest(BaseModel):
    alias: str = Field(..., min_length=1, max_length=200)

class DeployApkRequest(BaseModel):
    apk_id: int
    device_ids: Optional[list[str]] = None

class UpdateDeviceSettingsRequest(BaseModel):
    monitored_package: Optional[str] = Field(None, max_length=200)
    monitored_app_name: Optional[str] = Field(None, max_length=200)
    monitored_threshold_min: Optional[int] = Field(None, ge=1, le=1440)  # 1 to 1440 minutes (24 hours) - values > 120 minutes are deprecated but allowed for backward compatibility
    monitor_enabled: Optional[bool] = None
    auto_relaunch_enabled: Optional[bool] = None

class ActionResultRequest(BaseModel):
    request_id: str = Field(..., min_length=1, max_length=100)
    device_id: str = Field(..., min_length=1, max_length=100)
    action: str = Field(..., max_length=50)
    outcome: str = Field(..., max_length=50)
    message: Optional[str] = Field(None, max_length=1000)
    finished_at: datetime

class UpdateAutoRelaunchDefaultsRequest(BaseModel):
    enabled: Optional[bool] = None
    package: Optional[str] = Field(None, max_length=200)

class UpdateDiscordSettingsRequest(BaseModel):
    enabled: Optional[bool] = None
