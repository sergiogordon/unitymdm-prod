from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import func, and_

from models import Device, DeviceHeartbeat, AlertState, SessionLocal
from alert_config import alert_config
from observability import structured_logger, metrics

class AlertCondition:
    OFFLINE = "offline"
    LOW_BATTERY = "low_battery"
    UNITY_DOWN = "unity_down"
    SERVICE_DOWN = "service_down"

class AlertEvaluator:
    def __init__(self):
        self.config = alert_config
    
    def _check_min_duration_met(
        self,
        alert_state: Optional[AlertState],
        started_at_field: str,
        min_duration_minutes: int
    ) -> Tuple[bool, Optional[datetime]]:
        """
        Check if minimum duration has passed since condition started.
        Returns (met, started_at_datetime)
        """
        now = datetime.now(timezone.utc)
        
        if not alert_state:
            return False, None
        
        started_at = getattr(alert_state, started_at_field, None)
        if not started_at:
            return False, None
        
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=timezone.utc)
        
        duration_minutes = (now - started_at).total_seconds() / 60
        return duration_minutes >= min_duration_minutes, started_at
    
    def _update_condition_started_at(
        self,
        db: Session,
        alert_state: Optional[AlertState],
        device_id: str,
        condition: str
    ) -> AlertState:
        """Update or set condition_started_at timestamp."""
        if not alert_state:
            alert_state = self._get_alert_state(db, device_id, condition)
        
        if not alert_state:
            alert_state = AlertState(
                device_id=device_id,
                condition=condition,
                state='ok',
                condition_started_at=datetime.now(timezone.utc)
            )
            db.add(alert_state)
        elif not alert_state.condition_started_at:
            alert_state.condition_started_at = datetime.now(timezone.utc)
        
        # Clear cleared_at when condition starts again
        alert_state.condition_cleared_at = None
        db.commit()
        db.refresh(alert_state)
        return alert_state
    
    def _update_condition_cleared_at(
        self,
        db: Session,
        alert_state: Optional[AlertState],
        device_id: str,
        condition: str
    ) -> AlertState:
        """Update or set condition_cleared_at timestamp."""
        if not alert_state:
            alert_state = self._get_alert_state(db, device_id, condition)
        
        if not alert_state:
            alert_state = AlertState(
                device_id=device_id,
                condition=condition,
                state='ok',
                condition_cleared_at=datetime.now(timezone.utc)
            )
            db.add(alert_state)
        elif not alert_state.condition_cleared_at:
            alert_state.condition_cleared_at = datetime.now(timezone.utc)
        
        # Clear started_at when condition clears
        alert_state.condition_started_at = None
        db.commit()
        db.refresh(alert_state)
        return alert_state
    
    def _get_latest_heartbeat(self, db: Session, device_id: str) -> Optional[DeviceHeartbeat]:
        return db.query(DeviceHeartbeat).filter(
            DeviceHeartbeat.device_id == device_id
        ).order_by(DeviceHeartbeat.ts.desc()).first()
    
    def _get_alert_state(self, db: Session, device_id: str, condition: str) -> Optional[AlertState]:
        return db.query(AlertState).filter(
            and_(
                AlertState.device_id == device_id,
                AlertState.condition == condition
            )
        ).first()
    
    def _create_or_update_alert_state(
        self,
        db: Session,
        device_id: str,
        condition: str,
        state: str,
        value: Optional[str] = None
    ) -> AlertState:
        alert_state = self._get_alert_state(db, device_id, condition)
        
        if not alert_state:
            alert_state = AlertState(
                device_id=device_id,
                condition=condition,
                state=state,
                last_value=value
            )
            db.add(alert_state)
        else:
            alert_state.state = state
            alert_state.last_value = value
            alert_state.updated_at = datetime.now(timezone.utc)
        
        db.commit()
        db.refresh(alert_state)
        return alert_state
    
    def evaluate_offline(
        self,
        db: Session,
        device: Device
    ) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        """
        Evaluate if device is offline, requiring 2 consecutive missed heartbeats.
        
        Alert threshold: heartbeat_interval * 2 (default: 4 minutes with 2-min interval)
        This ensures we've missed 2 consecutive expected heartbeats before alerting.
        """
        now = datetime.now(timezone.utc)
        heartbeat_interval_seconds = self.config.HEARTBEAT_INTERVAL_SECONDS
        
        # Get last 2 heartbeats to verify consecutive missed heartbeats
        heartbeats = db.query(DeviceHeartbeat).filter(
            DeviceHeartbeat.device_id == device.id
        ).order_by(DeviceHeartbeat.ts.desc()).limit(2).all()
        
        if not heartbeats:
            # No heartbeats at all - can't determine offline status
            return False, None, None
        
        latest_heartbeat = heartbeats[0]
        last_seen = latest_heartbeat.ts
        
        if last_seen.tzinfo is None:
            last_seen = last_seen.replace(tzinfo=timezone.utc)
        
        # Calculate time since last heartbeat
        time_since_last_seen = now - last_seen
        
        # Alert threshold: require 2 consecutive missed heartbeats
        # If time since last heartbeat > heartbeat_interval * 2, we've missed 2 consecutive expected heartbeats
        alert_threshold_seconds = heartbeat_interval_seconds * 2
        alert_threshold = timedelta(seconds=alert_threshold_seconds)
        
        # Check if we've missed 2 consecutive heartbeats
        is_offline = time_since_last_seen > alert_threshold
        
        alert_state = self._get_alert_state(db, device.id, AlertCondition.OFFLINE)
        
        if is_offline:
            # Track when condition started
            alert_state = self._update_condition_started_at(
                db, alert_state, device.id, AlertCondition.OFFLINE
            )
            
            # Check if minimum duration has passed
            min_duration_met, _ = self._check_min_duration_met(
                alert_state,
                'condition_started_at',
                self.config.ALERT_MIN_DURATION_BEFORE_ALERT_MIN
            )
            
            minutes_offline = int(time_since_last_seen.total_seconds() / 60)
            value = f"{minutes_offline}m"
            
            # Only alert if condition has persisted for minimum duration
            if min_duration_met and (not alert_state or alert_state.state != "raised"):
                context = {
                    "device_id": device.id,
                    "alias": device.alias,
                    "last_seen": last_seen,
                    "minutes_offline": minutes_offline,
                    "missed_heartbeats": int(time_since_last_seen.total_seconds() / heartbeat_interval_seconds),
                    "severity": "CRIT"
                }
                return True, value, context
        
        else:
            # Device is online - track when condition cleared
            if alert_state and alert_state.state == "raised":
                alert_state = self._update_condition_cleared_at(
                    db, alert_state, device.id, AlertCondition.OFFLINE
                )
                
                # Check if minimum duration has passed since clearing
                min_duration_met, _ = self._check_min_duration_met(
                    alert_state,
                    'condition_cleared_at',
                    self.config.ALERT_MIN_DURATION_BEFORE_RECOVERY_MIN
                )
                
                # Only recover if condition has been clear for minimum duration
                if min_duration_met:
                    context = {
                        "device_id": device.id,
                        "alias": device.alias,
                        "recovered": True
                    }
                    return False, None, context
        
        return False, None, None
    
    def evaluate_low_battery(
        self,
        db: Session,
        device: Device
    ) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        heartbeat = self._get_latest_heartbeat(db, device.id)
        
        if not heartbeat or heartbeat.battery_pct is None:
            return False, None, None
        
        is_low = heartbeat.battery_pct < self.config.ALERT_LOW_BATTERY_PCT
        
        alert_state = self._get_alert_state(db, device.id, AlertCondition.LOW_BATTERY)
        
        if is_low:
            # Track when condition started
            alert_state = self._update_condition_started_at(
                db, alert_state, device.id, AlertCondition.LOW_BATTERY
            )
            
            # Check if minimum duration has passed
            min_duration_met, _ = self._check_min_duration_met(
                alert_state,
                'condition_started_at',
                self.config.ALERT_MIN_DURATION_BEFORE_ALERT_MIN
            )
            
            value = f"{heartbeat.battery_pct}%"
            
            # Only alert if condition has persisted for minimum duration
            if min_duration_met and (not alert_state or alert_state.state != "raised"):
                context = {
                    "device_id": device.id,
                    "alias": device.alias,
                    "battery_pct": heartbeat.battery_pct,
                    "plugged": heartbeat.plugged,
                    "network_type": heartbeat.network_type,
                    "last_seen": device.last_seen,
                    "severity": "WARN"
                }
                return True, value, context
        
        else:
            # Battery is above threshold - track when condition cleared
            if alert_state and alert_state.state == "raised":
                alert_state = self._update_condition_cleared_at(
                    db, alert_state, device.id, AlertCondition.LOW_BATTERY
                )
                
                # Check if minimum duration has passed since clearing
                min_duration_met, _ = self._check_min_duration_met(
                    alert_state,
                    'condition_cleared_at',
                    self.config.ALERT_MIN_DURATION_BEFORE_RECOVERY_MIN
                )
                
                # Only recover if condition has been clear for minimum duration
                if min_duration_met:
                    context = {
                        "device_id": device.id,
                        "alias": device.alias,
                        "battery_pct": heartbeat.battery_pct,
                        "recovered": True
                    }
                    return False, None, context
        
        return False, None, None
    
    def evaluate_unity_down(
        self,
        db: Session,
        device: Device
    ) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        if self.config.UNITY_DOWN_REQUIRE_CONSECUTIVE:
            heartbeats = db.query(DeviceHeartbeat).filter(
                DeviceHeartbeat.device_id == device.id
            ).order_by(DeviceHeartbeat.ts.desc()).limit(2).all()
            
            if len(heartbeats) < 2:
                return False, None, None
            
            is_down = all(hb.unity_running is False for hb in heartbeats)
        else:
            heartbeat = self._get_latest_heartbeat(db, device.id)
            
            if not heartbeat or heartbeat.unity_running is None:
                return False, None, None
            
            is_down = heartbeat.unity_running is False
        
        alert_state = self._get_alert_state(db, device.id, AlertCondition.UNITY_DOWN)
        
        if is_down:
            # Track when condition started
            alert_state = self._update_condition_started_at(
                db, alert_state, device.id, AlertCondition.UNITY_DOWN
            )
            
            # Check if minimum duration has passed
            min_duration_met, _ = self._check_min_duration_met(
                alert_state,
                'condition_started_at',
                self.config.ALERT_MIN_DURATION_BEFORE_ALERT_MIN
            )
            
            latest_hb = self._get_latest_heartbeat(db, device.id)
            value = "down"
            
            # Only alert if condition has persisted for minimum duration
            if min_duration_met and (not alert_state or alert_state.state != "raised"):
                alert_state_obj = self._create_or_update_alert_state(
                    db, device.id, AlertCondition.UNITY_DOWN, "raised", value
                )
                
                if alert_state_obj.consecutive_violations == 0:
                    alert_state_obj.consecutive_violations = 1
                else:
                    alert_state_obj.consecutive_violations += 1
                
                db.commit()
                
                severity = "CRIT"
                
                context = {
                    "device_id": device.id,
                    "alias": device.alias,
                    "unity_running": False,
                    "unity_version": latest_hb.unity_pkg_version if latest_hb else None,
                    "last_seen": device.last_seen,
                    "network_type": latest_hb.network_type if latest_hb else None,
                    "severity": severity,
                    "requires_remediation": True
                }
                return True, value, context
        
        else:
            # Unity is running - track when condition cleared
            if alert_state and alert_state.state == "raised":
                alert_state = self._update_condition_cleared_at(
                    db, alert_state, device.id, AlertCondition.UNITY_DOWN
                )
                
                # Check if minimum duration has passed since clearing
                min_duration_met, _ = self._check_min_duration_met(
                    alert_state,
                    'condition_cleared_at',
                    self.config.ALERT_MIN_DURATION_BEFORE_RECOVERY_MIN
                )
                
                # Only recover if condition has been clear for minimum duration
                if min_duration_met:
                    latest_hb = self._get_latest_heartbeat(db, device.id)
                    
                    self_healed = alert_state.consecutive_violations > 0
                    
                    context = {
                        "device_id": device.id,
                        "alias": device.alias,
                        "unity_running": True,
                        "unity_version": latest_hb.unity_pkg_version if latest_hb else None,
                        "recovered": True,
                        "self_healed": self_healed
                    }
                    return False, None, context
        
        return False, None, None
    
    def evaluate_service_down(
        self,
        db: Session,
        device: Device
    ) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        """
        Evaluate if the monitored service is down based on foreground recency.
        Uses DeviceLastStatus for efficient querying.
        Respects global defaults for devices without per-device overrides.
        """
        from monitoring_helpers import get_effective_monitoring_settings
        monitoring_settings = get_effective_monitoring_settings(db, device)
        
        if not monitoring_settings["enabled"] or not monitoring_settings["package"]:
            return False, None, None
        
        from models import DeviceLastStatus
        last_status = db.query(DeviceLastStatus).filter(
            DeviceLastStatus.device_id == device.id
        ).first()
        
        if not last_status:
            return False, None, None
        
        service_up = last_status.service_up
        foreground_recent_s = last_status.monitored_foreground_recent_s
        
        # Service status unknown (no foreground data)
        if service_up is None:
            return False, None, None
        
        alert_state = self._get_alert_state(db, device.id, AlertCondition.SERVICE_DOWN)
        threshold_minutes = monitoring_settings["threshold_min"]
        threshold_seconds = threshold_minutes * 60
        
        # Hysteresis: recovery threshold is lower than alert threshold
        recovery_threshold_seconds = int(threshold_seconds * self.config.ALERT_RECOVERY_THRESHOLD_MULTIPLIER)
        recovery_threshold_minutes = recovery_threshold_seconds / 60
        
        if not service_up:
            # Service is DOWN - check against alert threshold
            is_below_alert_threshold = foreground_recent_s and foreground_recent_s > threshold_seconds
            
            if is_below_alert_threshold:
                # Track when condition started
                alert_state = self._update_condition_started_at(
                    db, alert_state, device.id, AlertCondition.SERVICE_DOWN
                )
                
                # Check if minimum duration has passed
                min_duration_met, _ = self._check_min_duration_met(
                    alert_state,
                    'condition_started_at',
                    self.config.ALERT_MIN_DURATION_BEFORE_ALERT_MIN
                )
                
                value = f"{int(foreground_recent_s)}s" if foreground_recent_s else "unknown"
                
                # Only alert if condition has persisted for minimum duration
                if min_duration_met and (not alert_state or alert_state.state != "raised"):
                    self._create_or_update_alert_state(
                        db, device.id, AlertCondition.SERVICE_DOWN, "raised", value
                    )
                    
                    context = {
                        "device_id": device.id,
                        "alias": device.alias,
                        "monitored_package": monitoring_settings["package"],
                        "monitored_app_name": monitoring_settings["alias"],
                        "foreground_recent_s": foreground_recent_s,
                        "threshold_min": threshold_minutes,
                        "last_seen": device.last_seen,
                        "severity": "CRIT",
                        "requires_remediation": False
                    }
                    return True, value, context
            else:
                # Service is down but below alert threshold - clear started_at if set
                if alert_state and alert_state.condition_started_at:
                    alert_state.condition_started_at = None
                    db.commit()
        else:
            # Service is UP - check against recovery threshold (hysteresis)
            is_above_recovery_threshold = foreground_recent_s and foreground_recent_s <= recovery_threshold_seconds
            
            if alert_state and alert_state.state == "raised":
                if is_above_recovery_threshold:
                    # Service is above recovery threshold - track when condition cleared
                    alert_state = self._update_condition_cleared_at(
                        db, alert_state, device.id, AlertCondition.SERVICE_DOWN
                    )
                    
                    # Check if minimum duration has passed since clearing
                    min_duration_met, _ = self._check_min_duration_met(
                        alert_state,
                        'condition_cleared_at',
                        self.config.ALERT_MIN_DURATION_BEFORE_RECOVERY_MIN
                    )
                    
                    # Only recover if condition has been clear for minimum duration
                    if min_duration_met:
                        context = {
                            "device_id": device.id,
                            "alias": device.alias,
                            "monitored_package": monitoring_settings["package"],
                            "monitored_app_name": monitoring_settings["alias"],
                            "foreground_recent_s": foreground_recent_s,
                            "recovered": True,
                            "self_healed": False
                        }
                        return False, None, context
                else:
                    # Service is up but still below recovery threshold - clear cleared_at if set
                    if alert_state.condition_cleared_at:
                        alert_state.condition_cleared_at = None
                        db.commit()
        
        return False, None, None
    
    def evaluate_all_devices(self, db: Session) -> List[Dict[str, Any]]:
        start_time = datetime.now(timezone.utc)
        
        structured_logger.log_event("alert.evaluate.start", level="INFO")
        
        devices = db.query(Device).all()
        alerts_to_raise = []
        
        for device in devices:
            for condition in [AlertCondition.OFFLINE, AlertCondition.LOW_BATTERY, AlertCondition.UNITY_DOWN, AlertCondition.SERVICE_DOWN]:
                try:
                    should_alert = False
                    value = None
                    context = None
                    
                    if condition == AlertCondition.OFFLINE:
                        should_alert, value, context = self.evaluate_offline(db, device)
                    elif condition == AlertCondition.LOW_BATTERY:
                        should_alert, value, context = self.evaluate_low_battery(db, device)
                    elif condition == AlertCondition.UNITY_DOWN:
                        should_alert, value, context = self.evaluate_unity_down(db, device)
                    elif condition == AlertCondition.SERVICE_DOWN:
                        should_alert, value, context = self.evaluate_service_down(db, device)
                    
                    if should_alert and context:
                        alerts_to_raise.append({
                            "condition": condition,
                            "value": value,
                            **context
                        })
                    elif context and context.get("recovered"):
                        alerts_to_raise.append({
                            "condition": condition,
                            "recovery": True,
                            **context
                        })
                
                except Exception as e:
                    structured_logger.log_event(
                        "alert.evaluate.error",
                        level="ERROR",
                        device_id=device.id,
                        condition=condition,
                        error=str(e)
                    )
        
        latency_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
        
        structured_logger.log_event(
            "alert.evaluate.end",
            level="INFO",
            devices_checked=len(devices),
            alerts_found=len(alerts_to_raise),
            latency_ms=latency_ms
        )
        
        metrics.observe_histogram("alert_evaluation_latency_ms", latency_ms)
        metrics.inc_counter("alert_evaluations_total", {"alerts_found": str(len(alerts_to_raise))})
        
        return alerts_to_raise

alert_evaluator = AlertEvaluator()
