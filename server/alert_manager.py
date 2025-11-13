import asyncio
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
from collections import defaultdict
from sqlalchemy.orm import Session

from models import AlertState, SessionLocal
from alert_config import alert_config
from alert_evaluator import alert_evaluator, AlertCondition
from discord_webhook import discord_client
from auto_remediation import remediation_engine
from observability import structured_logger, metrics

class AlertManager:
    def __init__(self):
        self.config = alert_config
        self.global_alert_window = []
        self.rollup_tracker = defaultdict(list)
    
    def _is_in_cooldown(self, alert_state: Optional[AlertState]) -> bool:
        if not alert_state or not alert_state.cooldown_until:
            return False
        
        now = datetime.now(timezone.utc)
        cooldown_until = alert_state.cooldown_until
        
        if cooldown_until.tzinfo is None:
            cooldown_until = cooldown_until.replace(tzinfo=timezone.utc)
        
        return now < cooldown_until
    
    def _set_cooldown(self, db: Session, alert_state: AlertState):
        cooldown_duration = timedelta(minutes=self.config.ALERT_DEVICE_COOLDOWN_MIN)
        alert_state.cooldown_until = datetime.now(timezone.utc) + cooldown_duration
        db.commit()
    
    def _check_global_rate_limit(self) -> bool:
        now = datetime.now(timezone.utc)
        one_minute_ago = now - timedelta(minutes=1)
        
        self.global_alert_window = [ts for ts in self.global_alert_window if ts > one_minute_ago]
        
        if len(self.global_alert_window) >= self.config.ALERT_GLOBAL_CAP_PER_MIN:
            return True
        
        self.global_alert_window.append(now)
        return False
    
    def _check_rollup_needed(self, condition: str) -> tuple[bool, int, List[Dict[str, str]]]:
        now = datetime.now(timezone.utc)
        one_minute_ago = now - timedelta(minutes=1)
        
        self.rollup_tracker[condition] = [
            entry for entry in self.rollup_tracker[condition]
            if entry['timestamp'] > one_minute_ago
        ]
        
        recent_count = len(self.rollup_tracker[condition])
        
        if recent_count >= self.config.ALERT_ROLLUP_THRESHOLD:
            device_list = [
                {"device_id": e['device_id'], "alias": e['alias']}
                for e in self.rollup_tracker[condition]
            ]
            return True, recent_count, device_list
        
        return False, recent_count, []
    
    def _track_for_rollup(self, condition: str, device_id: str, alias: str):
        self.rollup_tracker[condition].append({
            'device_id': device_id,
            'alias': alias,
            'timestamp': datetime.now(timezone.utc)
        })
    
    async def _raise_alert(
        self,
        db: Session,
        alert_data: Dict[str, Any]
    ):
        condition = alert_data['condition']
        device_id = alert_data['device_id']
        alias = alert_data['alias']
        
        alert_state = db.query(AlertState).filter(
            AlertState.device_id == device_id,
            AlertState.condition == condition
        ).first()
        
        if self._is_in_cooldown(alert_state):
            structured_logger.log_event(
                "alert.dedupe.hit",
                level="INFO",
                device_id=device_id,
                condition=condition
            )
            metrics.inc_counter("alerts_suppressed_total", {"reason": "cooldown", "condition": condition})
            return
        
        if self._check_global_rate_limit():
            structured_logger.log_event(
                "alert.rate_limited",
                level="WARN",
                device_id=device_id,
                condition=condition
            )
            metrics.inc_counter("alerts_suppressed_total", {"reason": "rate_limit", "condition": condition})
            return
        
        self._track_for_rollup(condition, device_id, alias)
        
        needs_rollup, total_count, device_list = self._check_rollup_needed(condition)
        
        if needs_rollup:
            severity = alert_data.get('severity', 'WARN')
            success = await discord_client.send_rollup_alert(
                condition=condition,
                severity=severity,
                total_devices=total_count,
                device_list=device_list
            )
            
            if success:
                structured_logger.log_event(
                    "alert.rollup.sent",
                    level="INFO",
                    condition=condition,
                    total_devices=total_count
                )
            
            self.rollup_tracker[condition] = []
            
            return
        
        severity = alert_data.get('severity', 'WARN')
        
        success = await discord_client.send_alert(
            condition=condition,
            device_id=device_id,
            alias=alias,
            severity=severity,
            last_seen=alert_data.get('last_seen'),
            battery_pct=alert_data.get('battery_pct'),
            network_type=alert_data.get('network_type'),
            unity_running=alert_data.get('unity_running'),
            unity_version=alert_data.get('unity_version'),
            details=alert_data.get('details'),
            monitored_app_name=alert_data.get('monitored_app_name'),
            monitored_package=alert_data.get('monitored_package'),
            foreground_recent_s=alert_data.get('foreground_recent_s'),
            threshold_min=alert_data.get('threshold_min')
        )
        
        if success:
            if not alert_state:
                alert_state = AlertState(
                    device_id=device_id,
                    condition=condition,
                    state='raised',
                    last_raised_at=datetime.now(timezone.utc),
                    last_value=alert_data.get('value')
                )
                db.add(alert_state)
            else:
                alert_state.state = 'raised'
                alert_state.last_raised_at = datetime.now(timezone.utc)
                alert_state.last_value = alert_data.get('value')
            
            self._set_cooldown(db, alert_state)
            db.commit()
            
            structured_logger.log_event(
                f"alert.raise.{condition}",
                level="INFO",
                device_id=device_id,
                alias=alias,
                severity=severity
            )
            metrics.inc_counter("alerts_sent_total", {"condition": condition, "severity": severity})
            
            if alert_data.get('requires_remediation'):
                from models import Device
                device = db.query(Device).filter(Device.id == device_id).first()
                if device:
                    if condition == AlertCondition.UNITY_DOWN:
                        await remediation_engine.remediate_unity_down(db, device, device.monitored_package)
                    elif condition == AlertCondition.OFFLINE:
                        await remediation_engine.remediate_offline(db, device)
    
    async def _handle_recovery(
        self,
        db: Session,
        alert_data: Dict[str, Any]
    ):
        condition = alert_data['condition']
        device_id = alert_data['device_id']
        alias = alert_data['alias']
        
        alert_state = db.query(AlertState).filter(
            AlertState.device_id == device_id,
            AlertState.condition == condition
        ).first()
        
        if not alert_state or alert_state.state != 'raised':
            return
        
        alert_state.state = 'ok'
        alert_state.last_recovered_at = datetime.now(timezone.utc)
        db.commit()
        
        if alert_data.get('self_healed'):
            structured_logger.log_event(
                "remediation.success.self_healed",
                level="INFO",
                device_id=device_id,
                condition=condition
            )
            metrics.inc_counter("remediations_success_total", {"action": "launch_app"})
        
        success = await discord_client.send_recovery(
            condition=condition,
            device_id=device_id,
            alias=alias
        )
        
        if success:
            structured_logger.log_event(
                "alert.recover",
                level="INFO",
                device_id=device_id,
                alias=alias,
                condition=condition
            )
            metrics.inc_counter("alerts_recovered_total", {"condition": condition})
    
    async def process_alerts(self):
        db = SessionLocal()
        
        try:
            alerts = alert_evaluator.evaluate_all_devices(db)
            
            for alert_data in alerts:
                # Use a savepoint for each alert to allow rollback without affecting others
                try:
                    # Create a savepoint for this alert
                    db.begin_nested()
                    
                    if alert_data.get('recovery'):
                        await self._handle_recovery(db, alert_data)
                    else:
                        await self._raise_alert(db, alert_data)
                    
                    # Commit this alert's changes
                    db.commit()
                
                except Exception as e:
                    # Rollback this alert's transaction (savepoint)
                    try:
                        db.rollback()
                    except Exception as rollback_error:
                        structured_logger.log_event(
                            "alert.process.rollback_error",
                            level="ERROR",
                            device_id=alert_data.get('device_id', 'unknown'),
                            condition=alert_data.get('condition', 'unknown'),
                            rollback_error=str(rollback_error)
                        )
                    
                    structured_logger.log_event(
                        "alert.process.error",
                        level="ERROR",
                        device_id=alert_data.get('device_id', 'unknown'),
                        condition=alert_data.get('condition', 'unknown'),
                        error=str(e),
                        error_type=type(e).__name__
                    )
                    # Continue processing other alerts
        
        except Exception as e:
            # Critical error - rollback entire batch
            try:
                db.rollback()
            except:
                pass
            structured_logger.log_event(
                "alert.process.critical_error",
                level="ERROR",
                error=str(e),
                error_type=type(e).__name__
            )
            raise
        
        finally:
            db.close()

alert_manager = AlertManager()
