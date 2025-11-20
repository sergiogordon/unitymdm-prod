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
        # Device-specific settings, but fallback to defaults if fields are None/empty
        defaults = monitoring_defaults_cache.get_defaults(db)
        
        # Track which fields needed fallback to defaults
        used_fallback = False
        
        # Use device-specific values if available, otherwise fallback to defaults
        if device.monitor_enabled is not None:
            enabled = device.monitor_enabled
        else:
            enabled = defaults["enabled"]
            used_fallback = True
        
        if device.monitored_package:
            package = device.monitored_package
        else:
            package = defaults["package"]
            used_fallback = True
        
        if device.monitored_app_name:
            alias = device.monitored_app_name
        else:
            alias = defaults["alias"]
            used_fallback = True
        
        if device.monitored_threshold_min is not None:
            threshold_min = device.monitored_threshold_min
        else:
            threshold_min = defaults["threshold_min"]
            used_fallback = True
        
        # Determine source based on whether any fallback occurred
        if used_fallback:
            # Log warning if critical field (package) was missing
            if not device.monitored_package:
                structured_logger.log_event(
                    "monitoring.get_settings.fallback",
                    level="WARN",
                    device_id=device.id,
                    reason="missing_package",
                    source="device_override_with_fallback"
                )
            source = "device_with_fallback"
        else:
            source = "device"
        
        structured_logger.log_event(
            "monitoring.get_settings",
            device_id=device.id,
            source=source
        )
        
        return {
            "enabled": enabled,
            "package": package,
            "alias": alias,
            "threshold_min": threshold_min,
            "source": source
        }
