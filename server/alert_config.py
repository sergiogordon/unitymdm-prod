import os
from typing import Optional
from config import config

class AlertConfig:
    def __init__(self):
        # Heartbeat interval in seconds (default: 600 seconds = 10 minutes)
        self.HEARTBEAT_INTERVAL_SECONDS = int(os.getenv("HEARTBEAT_INTERVAL_SECONDS", "600"))
        
        # Alert threshold: require 3 consecutive missed heartbeats
        # Calculated as: heartbeat_interval * 3 / 60 (convert to minutes)
        # Default: 600 * 3 / 60 = 30 minutes
        alert_offline_minutes_env = os.getenv("ALERT_OFFLINE_MINUTES")
        if alert_offline_minutes_env:
            self.ALERT_OFFLINE_MINUTES = int(alert_offline_minutes_env)
        else:
            self.ALERT_OFFLINE_MINUTES = int(self.HEARTBEAT_INTERVAL_SECONDS * 3 / 60)
        
        self.ALERT_LOW_BATTERY_PCT = int(os.getenv("ALERT_LOW_BATTERY_PCT", "15"))
        self.ALERT_DEVICE_COOLDOWN_MIN = int(os.getenv("ALERT_DEVICE_COOLDOWN_MIN", "30"))
        self.ALERT_GLOBAL_CAP_PER_MIN = int(os.getenv("ALERT_GLOBAL_CAP_PER_MIN", "60"))
        self.ALERT_ROLLUP_THRESHOLD = int(os.getenv("ALERT_ROLLUP_THRESHOLD", "10"))
        self.ALERTS_ENABLE_AUTOREMEDIATION = os.getenv("ALERTS_ENABLE_AUTOREMEDIATION", "false").lower() == "true"
        self.UNITY_DOWN_REQUIRE_CONSECUTIVE = os.getenv("UNITY_DOWN_REQUIRE_CONSECUTIVE", "false").lower() == "true"
        self.DISCORD_WEBHOOK_URL: Optional[str] = os.getenv("DISCORD_WEBHOOK_URL")
        self.DASHBOARD_BASE_URL = config.server_url

alert_config = AlertConfig()
