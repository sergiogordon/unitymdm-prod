"""
WebSocket Manager for Real-time Device Communication
Handles 100+ concurrent device connections efficiently
"""

import asyncio
import json
import logging
from typing import Dict, List, Any, Optional
from fastapi import WebSocket, WebSocketDisconnect
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

class WebSocketManager:
    """
    Manages WebSocket connections for real-time device communication
    """
    
    def __init__(self):
        # Device ID -> WebSocket connection mapping
        self.device_connections: Dict[str, WebSocket] = {}
        
        # Admin/Dashboard connections (can subscribe to device updates)
        self.admin_connections: List[WebSocket] = []
        
        # Message queue for reliable delivery
        self.message_queue: Dict[str, List[Dict[str, Any]]] = {}
        
        # Connection statistics
        self.stats = {
            "total_connections": 0,
            "messages_sent": 0,
            "messages_received": 0,
            "errors": 0
        }
    
    @property
    def active_connections(self) -> Dict[str, WebSocket]:
        """Get all active connections"""
        return {**self.device_connections}
    
    async def connect(self, client_id: str, websocket: WebSocket, is_admin: bool = False):
        """
        Accept a new WebSocket connection
        """
        await websocket.accept()
        
        if is_admin:
            self.admin_connections.append(websocket)
            logger.info(f"Admin connected. Total admins: {len(self.admin_connections)}")
        else:
            self.device_connections[client_id] = websocket
            logger.info(f"Device {client_id} connected. Total devices: {len(self.device_connections)}")
            
            # Send any queued messages
            if client_id in self.message_queue:
                for message in self.message_queue[client_id]:
                    try:
                        await websocket.send_json(message)
                        self.stats["messages_sent"] += 1
                    except Exception as e:
                        logger.error(f"Error sending queued message to {client_id}: {e}")
                        break
                else:
                    # Clear queue if all messages sent successfully
                    del self.message_queue[client_id]
        
        self.stats["total_connections"] += 1
    
    def disconnect(self, client_id: str, is_admin: bool = False):
        """
        Remove a WebSocket connection
        """
        if is_admin:
            # Remove from admin connections
            self.admin_connections = [
                ws for ws in self.admin_connections 
                if ws.client_state.name != "DISCONNECTED"
            ]
            logger.info(f"Admin disconnected. Remaining admins: {len(self.admin_connections)}")
        else:
            if client_id in self.device_connections:
                del self.device_connections[client_id]
                logger.info(f"Device {client_id} disconnected. Remaining devices: {len(self.device_connections)}")
    
    async def send_to_device(self, device_id: str, message: Dict[str, Any]) -> bool:
        """
        Send a message to a specific device
        """
        if device_id in self.device_connections:
            websocket = self.device_connections[device_id]
            try:
                await websocket.send_json(message)
                self.stats["messages_sent"] += 1
                logger.debug(f"Message sent to device {device_id}")
                return True
            except WebSocketDisconnect:
                self.disconnect(device_id)
                self._queue_message(device_id, message)
                return False
            except Exception as e:
                logger.error(f"Error sending to device {device_id}: {e}")
                self.stats["errors"] += 1
                self._queue_message(device_id, message)
                return False
        else:
            # Queue message for when device reconnects
            self._queue_message(device_id, message)
            return False
    
    async def send_to_admins(self, message: Dict[str, Any]):
        """
        Send a message to all connected admin clients
        """
        if not self.admin_connections:
            return
        
        # Send to all admin connections in parallel
        disconnected = []
        tasks = []
        
        for i, websocket in enumerate(self.admin_connections):
            async def send_to_admin(ws, idx):
                try:
                    await ws.send_json(message)
                    self.stats["messages_sent"] += 1
                except:
                    disconnected.append(idx)
            
            tasks.append(send_to_admin(websocket, i))
        
        await asyncio.gather(*tasks, return_exceptions=True)
        
        # Remove disconnected clients
        if disconnected:
            self.admin_connections = [
                ws for i, ws in enumerate(self.admin_connections)
                if i not in disconnected
            ]
            logger.info(f"Removed {len(disconnected)} disconnected admins")
    
    async def broadcast(self, message: Dict[str, Any], exclude: Optional[List[str]] = None):
        """
        Broadcast a message to all connected clients (devices and admins)
        """
        exclude = exclude or []
        
        # Add timestamp if not present
        if "timestamp" not in message:
            message["timestamp"] = datetime.now(timezone.utc).isoformat()
        
        # Send to admins
        await self.send_to_admins(message)
        
        # Send to devices
        tasks = []
        for device_id, websocket in self.device_connections.items():
            if device_id not in exclude:
                tasks.append(self.send_to_device(device_id, message))
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        
        logger.info(f"Broadcast sent to {len(tasks)} devices and {len(self.admin_connections)} admins")
    
    async def broadcast_device_status(self, device_id: str, status: str, details: Optional[Dict] = None):
        """
        Broadcast device status update to all admin clients
        """
        message = {
            "type": "device_status",
            "device_id": device_id,
            "status": status,
            "details": details or {},
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        await self.send_to_admins(message)
    
    async def handle_device_message(self, device_id: str, message: Dict[str, Any]):
        """
        Process a message received from a device
        """
        self.stats["messages_received"] += 1
        message_type = message.get("type")
        
        # Process based on message type
        if message_type == "heartbeat":
            await self.broadcast_device_status(device_id, "online", {
                "battery": message.get("battery"),
                "memory": message.get("memory")
            })
        elif message_type == "event":
            # Forward event to admins
            await self.send_to_admins({
                "type": "device_event",
                "device_id": device_id,
                "event": message.get("event"),
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
        elif message_type == "alert":
            # High-priority alert - broadcast to all admins
            await self.send_to_admins({
                "type": "device_alert",
                "device_id": device_id,
                "alert": message.get("alert"),
                "severity": message.get("severity", "warning"),
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
        elif message_type == "response":
            # Command response - forward to admins
            await self.send_to_admins({
                "type": "command_response",
                "device_id": device_id,
                "command_id": message.get("command_id"),
                "result": message.get("result"),
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
    
    def _queue_message(self, device_id: str, message: Dict[str, Any]):
        """
        Queue a message for offline device
        """
        if device_id not in self.message_queue:
            self.message_queue[device_id] = []
        
        # Limit queue size to prevent memory issues
        if len(self.message_queue[device_id]) < 100:
            self.message_queue[device_id].append(message)
            logger.info(f"Message queued for offline device {device_id}")
        else:
            logger.warning(f"Message queue full for device {device_id}")
    
    async def disconnect_all(self):
        """
        Disconnect all WebSocket connections (for shutdown)
        """
        # Disconnect devices
        for device_id, websocket in self.device_connections.items():
            try:
                await websocket.close()
            except:
                pass
        
        # Disconnect admins
        for websocket in self.admin_connections:
            try:
                await websocket.close()
            except:
                pass
        
        self.device_connections.clear()
        self.admin_connections.clear()
        logger.info("All WebSocket connections closed")
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get WebSocket connection statistics
        """
        return {
            **self.stats,
            "active_devices": len(self.device_connections),
            "active_admins": len(self.admin_connections),
            "queued_messages": sum(len(msgs) for msgs in self.message_queue.values()),
            "devices_with_queued_messages": len(self.message_queue)
        }
    
    async def ping_all_connections(self):
        """
        Send ping to all connections to keep them alive
        """
        ping_message = {"type": "ping", "timestamp": datetime.now(timezone.utc).isoformat()}
        
        # Ping devices
        disconnected_devices = []
        for device_id, websocket in self.device_connections.items():
            try:
                await websocket.send_json(ping_message)
            except:
                disconnected_devices.append(device_id)
        
        # Remove disconnected devices
        for device_id in disconnected_devices:
            self.disconnect(device_id)
        
        # Ping admins
        disconnected_admins = []
        for i, websocket in enumerate(self.admin_connections):
            try:
                await websocket.send_json(ping_message)
            except:
                disconnected_admins.append(i)
        
        # Remove disconnected admins
        if disconnected_admins:
            self.admin_connections = [
                ws for i, ws in enumerate(self.admin_connections)
                if i not in disconnected_admins
            ]
        
        if disconnected_devices or disconnected_admins:
            logger.info(f"Cleaned up {len(disconnected_devices)} device and {len(disconnected_admins)} admin connections")