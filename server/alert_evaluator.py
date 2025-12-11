from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from collections import defaultdict

from models import Device, DeviceHeartbeat, AlertState, SessionLocal, DeviceLastStatus
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
    
    def _batch_load_alert_states(self, db: Session, device_ids: List[str]) -> Dict[Tuple[str, str], AlertState]:
        """
        Batch load all alert states for given devices.
        Returns dict indexed by (device_id, condition) -> AlertState
        """
        alert_states = db.query(AlertState).filter(
            AlertState.device_id.in_(device_ids)
        ).all()
        
        result = {}
        for alert_state in alert_states:
            result[(alert_state.device_id, alert_state.condition)] = alert_state
        
        return result
    
    def _batch_load_latest_heartbeats(self, db: Session, device_ids: List[str]) -> Dict[str, DeviceHeartbeat]:
        """
        Batch load latest heartbeat for each device.
        Returns dict indexed by device_id -> DeviceHeartbeat
        
        Optimized: Uses time window and DISTINCT ON for faster queries.
        """
        from sqlalchemy import text
        
        if not device_ids:
            return {}
        
        # Use time window to limit data scanned - only look at last 30 minutes
        time_window = datetime.now(timezone.utc) - timedelta(minutes=30)
        
        try:
            # Use PostgreSQL DISTINCT ON for efficient "latest per group" query
            device_id_list = ",".join(f"'{did}'" for did in device_ids)
            
            query = text(f"""
                SELECT DISTINCT ON (device_id)
                    hb_id, device_id, ts, battery_pct, plugged, network_type,
                    unity_running, unity_pkg_version
                FROM device_heartbeats
                WHERE device_id IN ({device_id_list})
                AND ts > :time_window
                ORDER BY device_id, ts DESC
            """)
            
            rows = db.execute(query, {"time_window": time_window}).fetchall()
            
            result = {}
            for row in rows:
                hb = DeviceHeartbeat()
                hb.hb_id = row[0]
                hb.device_id = row[1]
                hb.ts = row[2]
                hb.battery_pct = row[3]
                hb.plugged = row[4]
                hb.network_type = row[5]
                hb.unity_running = row[6]
                hb.unity_pkg_version = row[7]
                result[row[1]] = hb
            
            return result
            
        except Exception as e:
            # Rollback the failed transaction before attempting fallback
            try:
                db.rollback()
            except Exception:
                pass
            
            # Fallback to original query if DISTINCT ON fails
            structured_logger.log_event(
                "alert.batch_load_latest.fallback",
                level="WARN",
                error=str(e)
            )
            
            # Fallback with time filter
            max_ts_subquery = (
                db.query(
                    DeviceHeartbeat.device_id,
                    func.max(DeviceHeartbeat.ts).label('max_ts')
                )
                .filter(
                    DeviceHeartbeat.device_id.in_(device_ids),
                    DeviceHeartbeat.ts > time_window
                )
                .group_by(DeviceHeartbeat.device_id)
                .subquery()
            )
            
            latest_heartbeats = (
                db.query(DeviceHeartbeat)
                .join(
                    max_ts_subquery,
                    and_(
                        DeviceHeartbeat.device_id == max_ts_subquery.c.device_id,
                        DeviceHeartbeat.ts == max_ts_subquery.c.max_ts
                    )
                )
                .all()
            )
            
            result = {}
            for hb in latest_heartbeats:
                result[hb.device_id] = hb
            
            return result
    
    def _batch_load_device_last_status(self, db: Session, device_ids: List[str]) -> Dict[str, DeviceLastStatus]:
        """
        Batch load all DeviceLastStatus records for given devices.
        Returns dict indexed by device_id -> DeviceLastStatus
        """
        last_statuses = db.query(DeviceLastStatus).filter(
            DeviceLastStatus.device_id.in_(device_ids)
        ).all()
        
        result = {}
        for status in last_statuses:
            result[status.device_id] = status
        
        return result
    
    def _batch_load_recent_heartbeats(self, db: Session, device_ids: List[str], limit: int = 2) -> Dict[str, List[DeviceHeartbeat]]:
        """
        Batch load last N heartbeats per device for consecutive checks.
        Returns dict indexed by device_id -> List[DeviceHeartbeat] (ordered by ts desc)
        
        Optimized: Uses time window filter to avoid loading ancient heartbeats.
        """
        from sqlalchemy import text
        
        if not device_ids:
            return {}
        
        # Use a time window to limit data - only look at heartbeats from last 30 minutes
        # This focuses on most recent data and gets updated info on new heartbeats
        time_window = datetime.now(timezone.utc) - timedelta(minutes=30)
        
        # Use window function to efficiently get top N per device
        # This is much faster than loading all heartbeats and filtering in Python
        try:
            # Build the query using raw SQL with window function for efficiency
            device_id_list = ",".join(f"'{did}'" for did in device_ids)
            
            query = text(f"""
                WITH ranked AS (
                    SELECT 
                        hb_id, device_id, ts, battery_pct, plugged, network_type,
                        unity_running, unity_pkg_version,
                        ROW_NUMBER() OVER (PARTITION BY device_id ORDER BY ts DESC) as rn
                    FROM device_heartbeats
                    WHERE device_id IN ({device_id_list})
                    AND ts > :time_window
                )
                SELECT hb_id, device_id, ts, battery_pct, plugged, network_type,
                       unity_running, unity_pkg_version, rn
                FROM ranked WHERE rn <= :limit
                ORDER BY device_id, ts DESC
            """)
            
            rows = db.execute(query, {"time_window": time_window, "limit": limit}).fetchall()
            
            # Convert to DeviceHeartbeat objects grouped by device_id
            result = defaultdict(list)
            for row in rows:
                hb = DeviceHeartbeat()
                hb.hb_id = row[0]
                hb.device_id = row[1]
                hb.ts = row[2]
                hb.battery_pct = row[3]
                hb.plugged = row[4]
                hb.network_type = row[5]
                hb.unity_running = row[6]
                hb.unity_pkg_version = row[7]
                result[row[1]].append(hb)
            
            return dict(result)
            
        except Exception as e:
            # Rollback the failed transaction before attempting fallback
            try:
                db.rollback()
            except Exception:
                pass
            
            # Fallback to simpler query if window function fails
            structured_logger.log_event(
                "alert.batch_load.fallback",
                level="WARN",
                error=str(e)
            )
            
            # Fallback: Use time-filtered simple query
            all_heartbeats = (
                db.query(DeviceHeartbeat)
                .filter(
                    DeviceHeartbeat.device_id.in_(device_ids),
                    DeviceHeartbeat.ts > time_window
                )
                .order_by(DeviceHeartbeat.device_id, DeviceHeartbeat.ts.desc())
                .all()
            )
            
            # Group by device_id and take first N per device
            result = defaultdict(list)
            current_device = None
            count = 0
            
            for hb in all_heartbeats:
                if hb.device_id != current_device:
                    current_device = hb.device_id
                    count = 0
                
                if count < limit:
                    result[hb.device_id].append(hb)
                    count += 1
            
            return dict(result)
    
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
        device: Device,
        alert_states: Dict[Tuple[str, str], AlertState],
        recent_heartbeats: Dict[str, List[DeviceHeartbeat]]
    ) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        """
        Evaluate if device is offline, requiring 3 consecutive missed heartbeats.
        
        Alert threshold: heartbeat_interval * 3 (default: 30 minutes with 10-min interval)
        This ensures we've missed 3 consecutive expected heartbeats before alerting.
        """
        now = datetime.now(timezone.utc)
        heartbeat_interval_seconds = self.config.HEARTBEAT_INTERVAL_SECONDS
        
        # Get last 2 heartbeats from pre-loaded data
        heartbeats = recent_heartbeats.get(device.id, [])
        
        if not heartbeats:
            # No heartbeats at all - can't determine offline status
            return False, None, None
        
        latest_heartbeat = heartbeats[0]
        last_seen = latest_heartbeat.ts
        
        if last_seen.tzinfo is None:
            last_seen = last_seen.replace(tzinfo=timezone.utc)
        
        # Calculate time since last heartbeat
        time_since_last_seen = now - last_seen
        
        # Alert threshold: require 3 consecutive missed heartbeats
        # If time since last heartbeat > heartbeat_interval * 3, we've missed 3 consecutive expected heartbeats
        alert_threshold_seconds = heartbeat_interval_seconds * 3
        alert_threshold = timedelta(seconds=alert_threshold_seconds)
        
        # Check if we've missed 3 consecutive heartbeats
        is_offline = time_since_last_seen > alert_threshold
        
        alert_state = alert_states.get((device.id, AlertCondition.OFFLINE))
        
        if is_offline:
            minutes_offline = int(time_since_last_seen.total_seconds() / 60)
            value = f"{minutes_offline}m"
            
            if not alert_state or alert_state.state != "raised":
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
        device: Device,
        alert_states: Dict[Tuple[str, str], AlertState],
        latest_heartbeats: Dict[str, DeviceHeartbeat]
    ) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        heartbeat = latest_heartbeats.get(device.id)
        
        if not heartbeat or heartbeat.battery_pct is None:
            return False, None, None
        
        is_low = heartbeat.battery_pct < self.config.ALERT_LOW_BATTERY_PCT
        
        alert_state = alert_states.get((device.id, AlertCondition.LOW_BATTERY))
        
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
        device: Device,
        alert_states: Dict[Tuple[str, str], AlertState],
        latest_heartbeats: Dict[str, DeviceHeartbeat],
        recent_heartbeats: Dict[str, List[DeviceHeartbeat]]
    ) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        if self.config.UNITY_DOWN_REQUIRE_CONSECUTIVE:
            heartbeats = recent_heartbeats.get(device.id, [])
            
            if len(heartbeats) < 2:
                return False, None, None
            
            is_down = all(hb.unity_running is False for hb in heartbeats[:2])
        else:
            heartbeat = latest_heartbeats.get(device.id)
            
            if not heartbeat or heartbeat.unity_running is None:
                return False, None, None
            
            is_down = heartbeat.unity_running is False
        
        alert_state = alert_states.get((device.id, AlertCondition.UNITY_DOWN))
        
        if is_down:
            latest_hb = latest_heartbeats.get(device.id)
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
                latest_hb = latest_heartbeats.get(device.id)
                
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
        device: Device,
        alert_states: Dict[Tuple[str, str], AlertState],
        device_last_status: Dict[str, DeviceLastStatus],
        monitoring_settings: Dict[str, Dict[str, Any]]
    ) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        """
        Evaluate if the monitored service is down based on foreground recency.
        Uses DeviceLastStatus for efficient querying.
        Respects global defaults for devices without per-device overrides.
        """
        settings = monitoring_settings.get(device.id)
        if not settings:
            return False, None, None
        
        if not settings["enabled"] or not settings["package"]:
            return False, None, None
        
        last_status = device_last_status.get(device.id)
        
        if not last_status:
            return False, None, None
        
        service_up = last_status.service_up
        foreground_recent_s = last_status.monitored_foreground_recent_s
        
        # Service status unknown (no foreground data)
        if service_up is None:
            return False, None, None
        
        alert_state = alert_states.get((device.id, AlertCondition.SERVICE_DOWN))
        
        if not service_up:
            # Service is DOWN
            # Handle -1 sentinel value (unavailable) same as None
            if foreground_recent_s is not None and foreground_recent_s >= 0:
                value = f"{int(foreground_recent_s)}s"
            else:
                value = "unknown"
            
            if not alert_state or alert_state.state != "raised":
                self._create_or_update_alert_state(
                    db, device.id, AlertCondition.SERVICE_DOWN, "raised", value
                )
                
                context = {
                    "device_id": device.id,
                    "alias": device.alias,
                    "monitored_package": settings["package"],
                    "monitored_app_name": settings["alias"],
                    "foreground_recent_s": foreground_recent_s,
                    "threshold_min": settings["threshold_min"],
                    "last_seen": device.last_seen,
                    "severity": "CRIT",
                    "requires_remediation": False
                }
                return True, value, context
        else:
            # Service is UP
            if alert_state and alert_state.state == "raised":
                context = {
                    "device_id": device.id,
                    "alias": device.alias,
                    "monitored_package": settings["package"],
                    "monitored_app_name": settings["alias"],
                    "foreground_recent_s": foreground_recent_s,
                    "recovered": True,
                    "self_healed": False
                }
                return False, None, context
        
        return False, None, None
    
    def evaluate_all_devices(self, db: Session) -> List[Dict[str, Any]]:
        start_time = datetime.now(timezone.utc)
        
        structured_logger.log_event("alert.evaluate.start", level="INFO")
        
        # Load all devices
        devices = db.query(Device).all()
        device_ids = [device.id for device in devices]
        
        if not device_ids:
            return []
        
        # Batch load all data needed for evaluation
        alert_states = self._batch_load_alert_states(db, device_ids)
        latest_heartbeats = self._batch_load_latest_heartbeats(db, device_ids)
        recent_heartbeats = self._batch_load_recent_heartbeats(db, device_ids, limit=2)
        device_last_status = self._batch_load_device_last_status(db, device_ids)
        
        # Cache monitoring settings for all devices
        # Wrap in try-catch to handle per-device errors gracefully
        from monitoring_helpers import get_effective_monitoring_settings
        monitoring_settings = {}
        for device in devices:
            try:
                monitoring_settings[device.id] = get_effective_monitoring_settings(db, device)
            except Exception as e:
                structured_logger.log_event(
                    "alert.evaluate.monitoring_settings_error",
                    level="ERROR",
                    device_id=device.id,
                    error=str(e)
                )
                # Set None so evaluate_service_down can handle it gracefully
                monitoring_settings[device.id] = None
        
        alerts_to_raise = []
        
        for device in devices:
            for condition in [AlertCondition.OFFLINE, AlertCondition.LOW_BATTERY, AlertCondition.UNITY_DOWN, AlertCondition.SERVICE_DOWN]:
                try:
                    should_alert = False
                    value = None
                    context = None
                    
                    if condition == AlertCondition.OFFLINE:
                        should_alert, value, context = self.evaluate_offline(
                            db, device, alert_states, recent_heartbeats
                        )
                    elif condition == AlertCondition.LOW_BATTERY:
                        should_alert, value, context = self.evaluate_low_battery(
                            db, device, alert_states, latest_heartbeats
                        )
                    elif condition == AlertCondition.UNITY_DOWN:
                        should_alert, value, context = self.evaluate_unity_down(
                            db, device, alert_states, latest_heartbeats, recent_heartbeats
                        )
                    elif condition == AlertCondition.SERVICE_DOWN:
                        should_alert, value, context = self.evaluate_service_down(
                            db, device, alert_states, device_last_status, monitoring_settings
                        )
                    
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
