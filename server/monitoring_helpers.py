"""
Helper functions for monitoring configuration.
Handles fallback to global defaults for devices without per-device overrides.
"""
from typing import Dict, Any
from sqlalchemy.orm import Session
from models import Device
from monitoring_defaults_cache import monitoring_defaults_cache
from observability import structured_logger

def get_effective_monitoring_settings(db: Session, device: Device) -> Dict[str, Any]:
    """
    Get effective monitoring settings for a device.
    If device is using defaults (monitoring_use_defaults=True), return global defaults.
    Otherwise, return device-specific settings.
    
    Returns:
        dict with keys: enabled, package, alias, threshold_min, source
    """
    if device.monitoring_use_defaults:
        defaults = monitoring_defaults_cache.get_defaults(db)
        
        structured_logger.log_event(
            "monitoring.get_settings",
            device_id=device.id,
            source="global_defaults"
        )
        
        return {
            "enabled": defaults["enabled"],
            "package": defaults["package"],
            "alias": defaults["alias"],
            "threshold_min": defaults["threshold_min"],
            "source": "global"
        }
    else:
        structured_logger.log_event(
            "monitoring.get_settings",
            device_id=device.id,
            source="device_override"
        )
        
        return {
            "enabled": device.monitor_enabled,
            "package": device.monitored_package,
            "alias": device.monitored_app_name,
            "threshold_min": device.monitored_threshold_min,
            "source": "device"
        }
