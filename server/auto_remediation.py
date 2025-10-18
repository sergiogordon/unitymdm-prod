import httpx
import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session

from alert_config import alert_config
from observability import structured_logger, metrics
from fcm_v1 import get_access_token, get_firebase_project_id, build_fcm_v1_url
from hmac_utils import compute_hmac_signature
from models import Device, FcmDispatch
from db_utils import record_fcm_dispatch

class AutoRemediationEngine:
    def __init__(self):
        self.enabled = alert_config.ALERTS_ENABLE_AUTOREMEDIATION
    
    async def remediate_unity_down(
        self,
        db: Session,
        device: Device,
        package_name: str = "org.zwanoo.android.speedtest"
    ) -> bool:
        if not self.enabled:
            structured_logger.log_event(
                "remediation.skip.disabled",
                level="INFO",
                device_id=device.id,
                action="launch_app"
            )
            return False
        
        if not device.fcm_token:
            structured_logger.log_event(
                "remediation.skip.no_fcm_token",
                level="WARN",
                device_id=device.id,
                action="launch_app"
            )
            metrics.inc_counter("remediations_skipped_total", {"reason": "no_fcm_token"})
            return False
        
        request_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()
        action = "launch_app"
        
        signature = compute_hmac_signature(
            request_id=request_id,
            device_id=device.id,
            action=action,
            timestamp=timestamp
        )
        
        start_time = datetime.now(timezone.utc)
        
        try:
            access_token = get_access_token()
            project_id = get_firebase_project_id()
            fcm_url = build_fcm_v1_url(project_id)
            
            message = {
                "message": {
                    "token": device.fcm_token,
                    "data": {
                        "action": action,
                        "request_id": request_id,
                        "device_id": device.id,
                        "ts": timestamp,
                        "hmac": signature,
                        "package_name": package_name
                    }
                }
            }
            
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(fcm_url, json=message, headers=headers)
                latency_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
                
                fcm_status = "success" if response.status_code == 200 else "failed"
                fcm_message_id = response.json().get("name") if response.status_code == 200 else None
                
                record_fcm_dispatch(
                    db=db,
                    request_id=request_id,
                    device_id=device.id,
                    action=action,
                    fcm_status=fcm_status,
                    latency_ms=int(latency_ms),
                    fcm_message_id=fcm_message_id,
                    http_code=response.status_code,
                    response_json=response.text[:500]
                )
                
                if response.status_code == 200:
                    structured_logger.log_event(
                        "remediation.attempt.success",
                        level="INFO",
                        device_id=device.id,
                        action=action,
                        request_id=request_id,
                        latency_ms=latency_ms
                    )
                    metrics.inc_counter("remediations_attempted_total", {"action": action})
                    metrics.observe_histogram("remediation_latency_ms", latency_ms, {"action": action})
                    return True
                else:
                    structured_logger.log_event(
                        "remediation.attempt.failed",
                        level="ERROR",
                        device_id=device.id,
                        action=action,
                        http_code=response.status_code,
                        error=response.text[:200]
                    )
                    metrics.inc_counter("remediations_failed_total", {"action": action, "reason": "fcm_error"})
                    return False
        
        except Exception as e:
            latency_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            structured_logger.log_event(
                "remediation.attempt.exception",
                level="ERROR",
                device_id=device.id,
                action=action,
                error=str(e),
                latency_ms=latency_ms
            )
            metrics.inc_counter("remediations_failed_total", {"action": action, "reason": "exception"})
            return False
    
    async def remediate_offline(
        self,
        db: Session,
        device: Device
    ) -> bool:
        if not self.enabled:
            structured_logger.log_event(
                "remediation.skip.disabled",
                level="INFO",
                device_id=device.id,
                action="ping"
            )
            return False
        
        if not device.fcm_token:
            structured_logger.log_event(
                "remediation.skip.no_fcm_token",
                level="WARN",
                device_id=device.id,
                action="ping"
            )
            metrics.inc_counter("remediations_skipped_total", {"reason": "no_fcm_token"})
            return False
        
        request_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()
        action = "ping"
        
        signature = compute_hmac_signature(
            request_id=request_id,
            device_id=device.id,
            action=action,
            timestamp=timestamp
        )
        
        start_time = datetime.now(timezone.utc)
        
        try:
            access_token = get_access_token()
            project_id = get_firebase_project_id()
            fcm_url = build_fcm_v1_url(project_id)
            
            message = {
                "message": {
                    "token": device.fcm_token,
                    "data": {
                        "action": action,
                        "request_id": request_id,
                        "device_id": device.id,
                        "ts": timestamp,
                        "hmac": signature
                    }
                }
            }
            
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(fcm_url, json=message, headers=headers)
                latency_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
                
                fcm_status = "success" if response.status_code == 200 else "failed"
                fcm_message_id = response.json().get("name") if response.status_code == 200 else None
                
                record_fcm_dispatch(
                    db=db,
                    request_id=request_id,
                    device_id=device.id,
                    action=action,
                    fcm_status=fcm_status,
                    latency_ms=int(latency_ms),
                    fcm_message_id=fcm_message_id,
                    http_code=response.status_code,
                    response_json=response.text[:500]
                )
                
                device.last_ping_sent = datetime.now(timezone.utc)
                device.ping_request_id = request_id
                db.commit()
                
                if response.status_code == 200:
                    structured_logger.log_event(
                        "remediation.attempt.success",
                        level="INFO",
                        device_id=device.id,
                        action=action,
                        request_id=request_id,
                        latency_ms=latency_ms
                    )
                    metrics.inc_counter("remediations_attempted_total", {"action": action})
                    metrics.observe_histogram("remediation_latency_ms", latency_ms, {"action": action})
                    return True
                else:
                    structured_logger.log_event(
                        "remediation.attempt.failed",
                        level="ERROR",
                        device_id=device.id,
                        action=action,
                        http_code=response.status_code
                    )
                    metrics.inc_counter("remediations_failed_total", {"action": action, "reason": "fcm_error"})
                    return False
        
        except Exception as e:
            latency_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            structured_logger.log_event(
                "remediation.attempt.exception",
                level="ERROR",
                device_id=device.id,
                action=action,
                error=str(e),
                latency_ms=latency_ms
            )
            metrics.inc_counter("remediations_failed_total", {"action": action, "reason": "exception"})
            return False

remediation_engine = AutoRemediationEngine()
