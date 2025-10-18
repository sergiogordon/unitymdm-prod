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

class AlertEvaluator:
    def __init__(self):
        self.config = alert_config
    
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
        now = datetime.now(timezone.utc)
        last_seen = device.last_seen
        
        if not last_seen:
            return False, None, None
        
        if last_seen.tzinfo is None:
            last_seen = last_seen.replace(tzinfo=timezone.utc)
        
        offline_threshold = timedelta(minutes=self.config.ALERT_OFFLINE_MINUTES)
        time_since_last_seen = now - last_seen
        
        is_offline = time_since_last_seen > offline_threshold
        
        alert_state = self._get_alert_state(db, device.id, AlertCondition.OFFLINE)
        
        if is_offline:
            minutes_offline = int(time_since_last_seen.total_seconds() / 60)
            value = f"{minutes_offline}m"
            
            if not alert_state or alert_state.state != "raised":
                context = {
                    "device_id": device.id,
                    "alias": device.alias,
                    "last_seen": last_seen,
                    "minutes_offline": minutes_offline,
                    "severity": "CRIT"
                }
                return True, value, context
        
        else:
            if alert_state and alert_state.state == "raised":
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
            value = f"{heartbeat.battery_pct}%"
            
            if not alert_state or alert_state.state != "raised":
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
            if alert_state and alert_state.state == "raised":
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
            latest_hb = self._get_latest_heartbeat(db, device.id)
            value = "down"
            
            if not alert_state or alert_state.state != "raised":
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
            if alert_state and alert_state.state == "raised":
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
    
    def evaluate_all_devices(self, db: Session) -> List[Dict[str, Any]]:
        start_time = datetime.now(timezone.utc)
        
        structured_logger.log_event("alert.evaluate.start", level="INFO")
        
        devices = db.query(Device).all()
        alerts_to_raise = []
        
        for device in devices:
            for condition in [AlertCondition.OFFLINE, AlertCondition.LOW_BATTERY, AlertCondition.UNITY_DOWN]:
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
