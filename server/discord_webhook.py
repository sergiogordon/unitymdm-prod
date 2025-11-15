import httpx
import logging
from datetime import datetime
from typing import Optional, Dict, Any
from alert_config import alert_config
from observability import structured_logger, metrics
from models import SessionLocal
from discord_settings_cache import discord_settings_cache

logger = logging.getLogger(__name__)

class DiscordWebhookClient:
    def __init__(self):
        self.webhook_url = alert_config.DISCORD_WEBHOOK_URL
        self.timeout = 5.0
    
    def _is_enabled(self) -> bool:
        """Check if Discord alerts are enabled."""
        db = SessionLocal()
        try:
            return discord_settings_cache.is_enabled(db)
        finally:
            db.close()
    
    def _get_severity_color(self, severity: str) -> int:
        colors = {
            "CRIT": 0xFF0000,
            "WARN": 0xFFA500,
            "INFO": 0x00FF00,
        }
        return colors.get(severity, 0x808080)
    
    def _build_embed(
        self,
        condition: str,
        device_id: str,
        alias: str,
        severity: str,
        last_seen: Optional[datetime],
        battery_pct: Optional[int],
        network_type: Optional[str],
        unity_running: Optional[bool],
        unity_version: Optional[str],
        details: Optional[str] = None,
        monitored_app_name: Optional[str] = None,
        monitored_package: Optional[str] = None,
        foreground_recent_s: Optional[int] = None,
        threshold_min: Optional[int] = None
    ) -> Dict[str, Any]:
        embed = {
            "title": f"🚨 Alert: {condition.replace('_', ' ').title()}",
            "color": self._get_severity_color(severity),
            "timestamp": datetime.utcnow().isoformat(),
            "fields": [
                {"name": "Device", "value": alias, "inline": True},
                {"name": "Device ID", "value": device_id, "inline": True},
                {"name": "Severity", "value": severity, "inline": True},
            ]
        }
        
        # Service Down specific fields
        if condition == "service_down" and monitored_app_name:
            embed["fields"].append({
                "name": "Service",
                "value": f"{monitored_app_name} ({monitored_package})" if monitored_package else monitored_app_name,
                "inline": False
            })
            
            if foreground_recent_s is not None:
                minutes_ago = int(foreground_recent_s / 60)
                embed["fields"].append({
                    "name": "Last Foreground",
                    "value": f"{minutes_ago} minutes ago",
                    "inline": True
                })
            
            if threshold_min is not None:
                embed["fields"].append({
                    "name": "Threshold",
                    "value": f"{threshold_min} minutes",
                    "inline": True
                })
        
        if last_seen:
            embed["fields"].append({
                "name": "Last Seen",
                "value": f"<t:{int(last_seen.timestamp())}:R>",
                "inline": True
            })
        
        if battery_pct is not None:
            embed["fields"].append({
                "name": "Battery",
                "value": f"{battery_pct}%",
                "inline": True
            })
        
        if network_type:
            embed["fields"].append({
                "name": "Network",
                "value": network_type,
                "inline": True
            })
        
        if unity_running is not None:
            status = "✅ Running" if unity_running else "❌ Stopped"
            embed["fields"].append({
                "name": "Unity Status",
                "value": status,
                "inline": True
            })
        
        if unity_version:
            embed["fields"].append({
                "name": "Unity Version",
                "value": unity_version,
                "inline": True
            })
        
        device_url = f"{alert_config.DASHBOARD_BASE_URL}/?device={device_id}"
        embed["fields"].append({
            "name": "Dashboard Link",
            "value": f"[View Device]({device_url})",
            "inline": False
        })
        
        if details:
            embed["description"] = details
        
        return embed
    
    def _build_rollup_embed(
        self,
        condition: str,
        severity: str,
        total_devices: int,
        device_list: list[Dict[str, str]]
    ) -> Dict[str, Any]:
        embed = {
            "title": f"🚨 Mass Alert: {condition.replace('_', ' ').title()}",
            "color": self._get_severity_color(severity),
            "timestamp": datetime.utcnow().isoformat(),
            "description": f"**{total_devices} devices** triggered {condition.replace('_', ' ')} condition",
            "fields": []
        }
        
        display_count = min(len(device_list), 20)
        device_names = [f"• {d['alias']} ({d['device_id'][:8]}...)" for d in device_list[:display_count]]
        
        embed["fields"].append({
            "name": f"Affected Devices (showing {display_count} of {total_devices})",
            "value": "\n".join(device_names) if device_names else "See dashboard",
            "inline": False
        })
        
        if total_devices > display_count:
            embed["fields"].append({
                "name": "Additional Devices",
                "value": f"and {total_devices - display_count} more...",
                "inline": False
            })
        
        dashboard_url = f"{alert_config.DASHBOARD_BASE_URL}/"
        embed["fields"].append({
            "name": "Dashboard",
            "value": f"[View All Devices]({dashboard_url})",
            "inline": False
        })
        
        return embed
    
    async def send_alert(
        self,
        condition: str,
        device_id: str,
        alias: str,
        severity: str,
        last_seen: Optional[datetime] = None,
        battery_pct: Optional[int] = None,
        network_type: Optional[str] = None,
        unity_running: Optional[bool] = None,
        unity_version: Optional[str] = None,
        details: Optional[str] = None,
        monitored_app_name: Optional[str] = None,
        monitored_package: Optional[str] = None,
        foreground_recent_s: Optional[int] = None,
        threshold_min: Optional[int] = None
    ) -> bool:
        if not self.webhook_url:
            structured_logger.log_event(
                "discord.webhook.not_configured",
                level="WARN",
                device_id=device_id,
                condition=condition
            )
            return False
        
        if not self._is_enabled():
            structured_logger.log_event(
                "discord.webhook.disabled",
                level="INFO",
                device_id=device_id,
                condition=condition
            )
            return False
        
        embed = self._build_embed(
            condition=condition,
            device_id=device_id,
            alias=alias,
            severity=severity,
            last_seen=last_seen,
            battery_pct=battery_pct,
            network_type=network_type,
            unity_running=unity_running,
            unity_version=unity_version,
            details=details,
            monitored_app_name=monitored_app_name,
            monitored_package=monitored_package,
            foreground_recent_s=foreground_recent_s,
            threshold_min=threshold_min
        )
        
        payload = {
            "embeds": [embed]
        }
        
        start_time = datetime.utcnow()
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(self.webhook_url, json=payload)
                latency_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
                
                if response.status_code in (200, 204):
                    structured_logger.log_event(
                        "discord.webhook.sent",
                        level="INFO",
                        device_id=device_id,
                        condition=condition,
                        severity=severity,
                        latency_ms=latency_ms
                    )
                    metrics.observe_histogram("discord_webhook_latency_ms", latency_ms)
                    metrics.inc_counter("discord_webhooks_sent_total", {"condition": condition, "severity": severity})
                    return True
                else:
                    structured_logger.log_event(
                        "discord.webhook.failed",
                        level="ERROR",
                        device_id=device_id,
                        condition=condition,
                        http_code=response.status_code,
                        response=response.text[:200]
                    )
                    metrics.inc_counter("discord_webhooks_failed_total", {"reason": "http_error"})
                    return False
        
        except Exception as e:
            latency_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
            structured_logger.log_event(
                "discord.webhook.error",
                level="ERROR",
                device_id=device_id,
                condition=condition,
                error=str(e),
                latency_ms=latency_ms
            )
            metrics.inc_counter("discord_webhooks_failed_total", {"reason": "exception"})
            return False
    
    async def send_rollup_alert(
        self,
        condition: str,
        severity: str,
        total_devices: int,
        device_list: list[Dict[str, str]]
    ) -> bool:
        if not self.webhook_url:
            return False
        
        if not self._is_enabled():
            structured_logger.log_event(
                "discord.webhook.disabled",
                level="INFO",
                condition=condition,
                type="rollup"
            )
            return False
        
        embed = self._build_rollup_embed(
            condition=condition,
            severity=severity,
            total_devices=total_devices,
            device_list=device_list
        )
        
        payload = {
            "embeds": [embed]
        }
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(self.webhook_url, json=payload)
                
                if response.status_code in (200, 204):
                    structured_logger.log_event(
                        "discord.webhook.rollup_sent",
                        level="INFO",
                        condition=condition,
                        total_devices=total_devices
                    )
                    metrics.inc_counter("discord_webhooks_sent_total", {"condition": condition, "type": "rollup"})
                    return True
                else:
                    structured_logger.log_event(
                        "discord.webhook.rollup_failed",
                        level="ERROR",
                        condition=condition,
                        http_code=response.status_code
                    )
                    return False
        
        except Exception as e:
            structured_logger.log_event(
                "discord.webhook.rollup_error",
                level="ERROR",
                condition=condition,
                error=str(e)
            )
            return False
    
    async def send_recovery(
        self,
        condition: str,
        device_id: str,
        alias: str
    ) -> bool:
        if not self.webhook_url:
            return False
        
        if not self._is_enabled():
            structured_logger.log_event(
                "discord.webhook.disabled",
                level="INFO",
                device_id=device_id,
                condition=condition,
                type="recovery"
            )
            return False
        
        embed = {
            "title": f"✅ Recovered: {condition.replace('_', ' ').title()}",
            "color": 0x00FF00,
            "timestamp": datetime.utcnow().isoformat(),
            "fields": [
                {"name": "Device", "value": alias, "inline": True},
                {"name": "Device ID", "value": device_id, "inline": True},
                {"name": "Status", "value": "Recovered", "inline": True},
            ]
        }
        
        device_url = f"{alert_config.DASHBOARD_BASE_URL}/?device={device_id}"
        embed["fields"].append({
            "name": "Dashboard Link",
            "value": f"[View Device]({device_url})",
            "inline": False
        })
        
        payload = {"embeds": [embed]}
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(self.webhook_url, json=payload)
                
                if response.status_code in (200, 204):
                    structured_logger.log_event(
                        "discord.webhook.recovery_sent",
                        level="INFO",
                        device_id=device_id,
                        condition=condition
                    )
                    metrics.inc_counter("discord_webhooks_sent_total", {"condition": condition, "type": "recovery"})
                    return True
                else:
                    return False
        
        except Exception:
            return False

discord_client = DiscordWebhookClient()
