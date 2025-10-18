import asyncio
import httpx
import os
import json
import uuid
from typing import Optional
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
from models import Device, DeviceEvent, SessionLocal
from fcm_v1 import get_access_token, get_firebase_project_id, build_fcm_v1_url

# Helper function to ensure datetime is timezone-aware (assume UTC for naive datetimes)
def ensure_utc(dt: Optional[datetime]) -> datetime:
    """Convert naive datetime to timezone-aware UTC datetime. Returns current time if None."""
    if dt is None:
        return datetime.now(timezone.utc)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

async def send_fcm_ping(device: Device, db: Session) -> bool:
    """
    Send FCM ping/wake notification to a device.
    Returns True if sent successfully, False otherwise.
    """
    if not device.fcm_token:
        print(f"[FCM-PING] Device {device.alias} has no FCM token, cannot ping")
        return False
    
    try:
        access_token = get_access_token()
        project_id = get_firebase_project_id()
        fcm_url = build_fcm_v1_url(project_id)
        
        request_id = str(uuid.uuid4())
        
        message = {
            "message": {
                "token": device.fcm_token,
                "data": {
                    "action": "ping",
                    "request_id": request_id
                },
                "android": {
                    "priority": "high"
                }
            }
        }
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(fcm_url, json=message, headers=headers)
            
            if response.status_code == 200:
                device.last_ping_sent = datetime.now(timezone.utc)
                device.ping_request_id = request_id
                # Clear previous ping response to track this new ping's outcome
                device.last_ping_response = None
                db.commit()
                print(f"[FCM-PING] ✓ Sent to {device.alias} (request_id: {request_id})")
                return True
            else:
                print(f"[FCM-PING] ✗ Failed for {device.alias}: FCM status {response.status_code}")
                return False
                
    except Exception as e:
        print(f"[FCM-PING] ✗ Exception sending to {device.alias}: {e}")
        return False

class AlertManager:
    def __init__(self):
        self.webhook_url = os.getenv("DISCORD_WEBHOOK_URL", "")
        self.offline_threshold = int(os.getenv("OFFLINE_THRESHOLD_SECONDS", "900"))
        self.heartbeat_interval = int(os.getenv("HEARTBEAT_INTERVAL_SECONDS", "300"))
        
    async def send_discord_alert(self, title: str, description: str, color: int, device_data: Optional[dict] = None):
        if not self.webhook_url:
            print(f"⚠️  No Discord webhook configured. Alert: {title} - {description}")
            return
            
        embed = {
            "title": title,
            "description": description,
            "color": color,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "fields": []
        }
        
        if device_data:
            embed["fields"].append({
                "name": "Device ID",
                "value": device_data.get("id", "Unknown"),
                "inline": True
            })
            embed["fields"].append({
                "name": "Last Seen",
                "value": device_data.get("last_seen", "Unknown"),
                "inline": True
            })
            if device_data.get("battery"):
                embed["fields"].append({
                    "name": "Battery",
                    "value": f"{device_data['battery']}%",
                    "inline": True
                })
            if device_data.get("network"):
                embed["fields"].append({
                    "name": "Network",
                    "value": device_data["network"],
                    "inline": True
                })
        
        payload = {"embeds": [embed]}
        
        async with httpx.AsyncClient() as client:
            try:
                await client.post(self.webhook_url, json=payload)
            except Exception as e:
                print(f"Failed to send Discord alert: {e}")
    
    def get_alert_state(self, device: Device) -> dict:
        if not device.last_status:
            return {}
            
        try:
            status = json.loads(device.last_status)
        except:
            return {}
        
        state = {}
        now = datetime.now(timezone.utc)
        
        if device.last_seen:
            offline_minutes = (now - ensure_utc(device.last_seen)).total_seconds() / 60
            state["offline"] = offline_minutes > (self.offline_threshold / 60)
        
        battery = status.get("battery", {})
        state["low_battery"] = battery.get("pct", 100) < 15
        
        # Unity app validation - COMMENTED OUT (Unity app not yet installed)
        # unity_app = status.get("app_versions", {}).get("unity", {})
        # state["unity_not_installed"] = not unity_app.get("installed", False)
        # 
        # unity_signals = status.get("unity_running_signals", {})
        # has_notif = unity_signals.get("has_service_notification", False)
        # recent_fg = unity_signals.get("foreground_recent_seconds")
        # state["unity_not_running"] = not has_notif and (recent_fg is None or recent_fg > 300)
        # 
        # expected_packages = os.getenv("EXPECTED_UNITY_PACKAGES", "com.unity.app").split(",")
        # if unity_app.get("installed"):
        #     state["wrong_version"] = False
        # else:
        #     state["wrong_version"] = False
        
        return state
    
    async def check_and_alert(self):
        db = SessionLocal()
        try:
            devices = db.query(Device).all()
            
            for device in devices:
                current_state = self.get_alert_state(device)
                
                try:
                    last_alert_state = json.loads(device.last_alert_state) if device.last_alert_state else {}
                except:
                    last_alert_state = {}
                
                if not device.last_status:
                    continue
                
                try:
                    status = json.loads(device.last_status)
                except:
                    continue
                
                device_info = {
                    "id": device.id,
                    "last_seen": ensure_utc(device.last_seen).isoformat() if device.last_seen else "Unknown",
                    "battery": status.get("battery", {}).get("pct"),
                    "network": status.get("network", {}).get("transport")
                }
                
                now = datetime.now(timezone.utc)
                minutes_since_heartbeat = (now - ensure_utc(device.last_seen)).total_seconds() / 60
                
                # Two-tier offline detection:
                # Tier 1: First missed heartbeat (6+ minutes) -> Send FCM ping
                if minutes_since_heartbeat > 6 and minutes_since_heartbeat < 10:
                    # Only ping if we haven't already sent one recently (within last 5 minutes)
                    if not device.last_ping_sent or (now - ensure_utc(device.last_ping_sent)).total_seconds() > 300:
                        print(f"[OFFLINE-DETECT] Tier 1: {device.alias} late ({minutes_since_heartbeat:.1f}m), sending FCM ping")
                        await send_fcm_ping(device, db)
                
                # Tier 2: Second missed heartbeat (10+ minutes) AND ping failed -> Alert
                # Check directly against 10 minutes instead of relying on global offline threshold
                if minutes_since_heartbeat >= 10:
                    # If still offline, preserve the offline state from last alert
                    current_state["offline"] = True
                    
                    # Only send new alert if we haven't already alerted
                    if not last_alert_state.get("offline"):
                        # Check if we tried to ping and it failed (no response within timeout)
                        ping_failed = False
                        if device.last_ping_sent:
                            minutes_since_ping = (now - ensure_utc(device.last_ping_sent)).total_seconds() / 60
                            # If we sent a ping more than 4 minutes ago and still no heartbeat, consider it failed
                            if minutes_since_ping > 4 and not device.last_ping_response:
                                ping_failed = True
                                print(f"[OFFLINE-DETECT] Tier 2: {device.alias} - FCM ping timed out, triggering alert")
                        
                        # Only alert if we either didn't try to ping, or the ping failed
                        if not device.last_ping_sent or ping_failed:
                            await self.send_discord_alert(
                                "🔴 Device OFFLINE",
                                f"Device **{device.alias}** has not checked in for over 10 minutes (FCM wake attempt {'failed' if ping_failed else 'not attempted'})",
                                0xFF0000,
                                device_info
                            )
                
                # Unity app alerts - COMMENTED OUT (Unity app not yet installed)
                # if current_state.get("unity_not_running") and not last_alert_state.get("unity_not_running"):
                #     await self.send_discord_alert(
                #         "⚠️  Unity NOT Running",
                #         f"Unity app is not running on **{device.alias}**",
                #         0xFFA500,
                #         device_info
                #     )
                # 
                # if current_state.get("unity_not_installed") and not last_alert_state.get("unity_not_installed"):
                #     await self.send_discord_alert(
                #         "❌ Unity NOT Installed",
                #         f"Unity app is not installed on **{device.alias}**",
                #         0xFF0000,
                #         device_info
                #     )
                
                if current_state.get("low_battery") and not last_alert_state.get("low_battery"):
                    await self.send_discord_alert(
                        "🔋 Low Battery",
                        f"Device **{device.alias}** battery is below 15%",
                        0xFFA500,
                        device_info
                    )
                
                device.last_alert_state = json.dumps(current_state)
            
            db.commit()
        finally:
            db.close()

alert_manager = AlertManager()

async def cleanup_old_events():
    """Delete device events older than 24 hours and events for devices offline for 2+ days"""
    db = SessionLocal()
    try:
        # Delete events older than retention period (optimized for 100+ devices)
        retention_days = int(os.getenv("EVENT_RETENTION_DAYS", "1"))
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=retention_days)
        
        deleted_old = db.query(DeviceEvent).filter(
            DeviceEvent.timestamp < cutoff_date
        ).delete()
        
        if deleted_old > 0:
            print(f"[CLEANUP] Deleted {deleted_old} device events older than {retention_days} days")
        
        # Delete events for devices that have been offline for 2+ days
        offline_cutoff = datetime.now(timezone.utc) - timedelta(days=2)
        
        # Get all devices that have been offline for 2+ days
        offline_devices = db.query(Device.id).filter(
            Device.last_seen < offline_cutoff
        ).all()
        
        offline_device_ids = [d[0] for d in offline_devices]
        
        if offline_device_ids:
            deleted_offline = db.query(DeviceEvent).filter(
                DeviceEvent.device_id.in_(offline_device_ids)
            ).delete(synchronize_session=False)
            
            if deleted_offline > 0:
                print(f"[CLEANUP] Deleted {deleted_offline} events from {len(offline_device_ids)} devices offline for 2+ days")
        
        db.commit()
    except Exception as e:
        print(f"[CLEANUP] Error cleaning up old events: {e}")
        db.rollback()
    finally:
        db.close()

async def alert_scheduler():
    cleanup_counter = 0
    while True:
        await asyncio.sleep(60)
        try:
            await alert_manager.check_and_alert()
            
            cleanup_counter += 1
            if cleanup_counter >= 60:
                await cleanup_old_events()
                cleanup_counter = 0
        except Exception as e:
            print(f"Alert scheduler error: {e}")
