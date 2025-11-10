from pydantic import BaseModel
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
    device_id: str
    alias: str
    app_version: Optional[str] = None
    timestamp_utc: str
    app_versions: dict[str, AppVersion]
    speedtest_running_signals: SpeedtestRunningSignals
    battery: Battery
    system: SystemInfo
    memory: Memory
    network: Network
    fcm_token: Optional[str] = None
    is_ping_response: Optional[bool] = None
    ping_request_id: Optional[str] = None
    self_heal_hints: Optional[SelfHealHints] = None
    is_device_owner: Optional[bool] = None
    monitored_foreground_recent_s: Optional[int] = None

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
    username: str
    password: str
    email: Optional[str] = None

class UserLoginRequest(BaseModel):
    username: str
    password: str

class UpdateDeviceAliasRequest(BaseModel):
    alias: str

class DeployApkRequest(BaseModel):
    apk_id: int
    device_ids: Optional[list[str]] = None

class UpdateDeviceSettingsRequest(BaseModel):
    monitored_package: Optional[str] = None
    monitored_app_name: Optional[str] = None
    monitored_threshold_min: Optional[int] = None
    monitor_enabled: Optional[bool] = None
    auto_relaunch_enabled: Optional[bool] = None

class ActionResultRequest(BaseModel):
    request_id: str
    device_id: str
    action: str
    outcome: str
    message: Optional[str] = None
    finished_at: datetime
