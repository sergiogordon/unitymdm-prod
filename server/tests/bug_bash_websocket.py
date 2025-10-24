"""
WebSocket Scalability Bug Bash
Tests WebSocket connections at scale with 100+ concurrent clients
"""

import asyncio
import websockets
import json
import time
import argparse
from datetime import datetime
from typing import List, Dict, Any
from collections import defaultdict


class WebSocketBugBash:
    """Test WebSocket functionality at scale"""
    
    def __init__(self, ws_url: str, auth_token: str):
        self.ws_url = ws_url
        self.auth_token = auth_token
        self.bugs_found = []
        self.warnings = []
        self.metrics = defaultdict(list)
        
    def log(self, message: str, level: str = "INFO"):
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        print(f"[{timestamp}] [{level}] {message}")
        
    def record_bug(self, severity: str, description: str, details: Dict = None):
        bug = {
            "severity": severity,
            "description": description,
            "details": details or {},
            "timestamp": datetime.now().isoformat()
        }
        self.bugs_found.append(bug)
        self.log(f"🐛 BUG [{severity}] {description}", "ERROR")
        
    def record_warning(self, description: str, details: Dict = None):
        warning = {
            "description": description,
            "details": details or {},
            "timestamp": datetime.now().isoformat()
        }
        self.warnings.append(warning)
        self.log(f"⚠️  WARNING {description}", "WARN")
    
    async def test_websocket_client(self, client_id: int, duration_seconds: int = 30):
        """Simulate a single WebSocket client"""
        messages_received = 0
        errors = []
        connection_time = None
        
        try:
            # Add auth token to URL
            full_url = f"{self.ws_url}?token={self.auth_token}"
            
            start = time.time()
            async with websockets.connect(full_url, ping_interval=20, ping_timeout=10) as ws:
                connection_time = (time.time() - start) * 1000
                self.log(f"Client {client_id} connected in {connection_time:.2f}ms")
                
                end_time = time.time() + duration_seconds
                
                while time.time() < end_time:
                    try:
                        # Wait for messages with timeout
                        message = await asyncio.wait_for(ws.recv(), timeout=5.0)
                        messages_received += 1
                        
                        # Try to parse as JSON
                        try:
                            data = json.loads(message)
                            
                            # Validate message structure
                            if not isinstance(data, dict):
                                self.record_warning(
                                    f"Client {client_id}: Received non-dict message",
                                    {"message_type": type(data).__name__}
                                )
                        except json.JSONDecodeError:
                            self.record_warning(
                                f"Client {client_id}: Received non-JSON message",
                                {"message": message[:100]}
                            )
                    
                    except asyncio.TimeoutError:
                        # No message received in 5s, continue waiting
                        continue
                    except Exception as e:
                        errors.append(str(e))
                        break
                
                # Close cleanly
                await ws.close()
                
        except Exception as e:
            errors.append(f"Connection error: {str(e)}")
            
        return {
            "client_id": client_id,
            "connection_time_ms": connection_time,
            "messages_received": messages_received,
            "errors": errors,
            "duration_seconds": duration_seconds
        }
    
    async def test_concurrent_connections(self, num_clients: int = 100, duration: int = 30):
        """Test multiple concurrent WebSocket connections"""
        self.log(f"\n{'='*60}")
        self.log(f"Testing {num_clients} concurrent WebSocket connections")
        self.log(f"{'='*60}")
        
        # Start all clients concurrently
        start = time.time()
        tasks = [
            self.test_websocket_client(i, duration)
            for i in range(num_clients)
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        total_time = time.time() - start
        
        # Analyze results
        successful = 0
        failed = 0
        total_messages = 0
        connection_times = []
        
        for result in results:
            if isinstance(result, Exception):
                failed += 1
                self.record_bug(
                    "HIGH",
                    f"WebSocket client crashed: {str(result)}",
                    {}
                )
            elif result.get("errors"):
                failed += 1
            else:
                successful += 1
                total_messages += result["messages_received"]
                if result["connection_time_ms"]:
                    connection_times.append(result["connection_time_ms"])
        
        self.log(f"\n✓ Results:")
        self.log(f"  Successful connections: {successful}/{num_clients}")
        self.log(f"  Failed connections: {failed}/{num_clients}")
        self.log(f"  Total messages received: {total_messages}")
        self.log(f"  Test duration: {total_time:.2f}s")
        
        if connection_times:
            import statistics
            avg_conn_time = statistics.mean(connection_times)
            max_conn_time = max(connection_times)
            self.log(f"  Avg connection time: {avg_conn_time:.2f}ms")
            self.log(f"  Max connection time: {max_conn_time:.2f}ms")
            
            if max_conn_time > 5000:
                self.record_bug(
                    "MEDIUM",
                    f"WebSocket connection time too high: {max_conn_time:.2f}ms",
                    {"max_time": max_conn_time, "threshold": 5000}
                )
        
        if failed > 0:
            failure_rate = (failed / num_clients) * 100
            if failure_rate > 10:
                self.record_bug(
                    "HIGH",
                    f"High WebSocket failure rate: {failure_rate:.1f}%",
                    {"failed": failed, "total": num_clients}
                )
        
        return {
            "successful": successful,
            "failed": failed,
            "total_messages": total_messages,
            "connection_times": connection_times
        }
    
    async def test_connection_stability(self, duration: int = 60):
        """Test WebSocket connection stability over time"""
        self.log(f"\n{'='*60}")
        self.log(f"Testing WebSocket stability for {duration}s")
        self.log(f"{'='*60}")
        
        disconnects = 0
        reconnects = 0
        messages_received = 0
        
        start_time = time.time()
        
        while time.time() - start_time < duration:
            try:
                full_url = f"{self.ws_url}?token={self.auth_token}"
                async with websockets.connect(full_url, ping_interval=10, ping_timeout=5) as ws:
                    reconnects += 1
                    self.log(f"Connected (attempt {reconnects})")
                    
                    # Stay connected for random duration
                    connection_duration = min(30, duration - (time.time() - start_time))
                    end_time = time.time() + connection_duration
                    
                    while time.time() < end_time:
                        try:
                            message = await asyncio.wait_for(ws.recv(), timeout=5.0)
                            messages_received += 1
                        except asyncio.TimeoutError:
                            continue
                    
                    # Close and reconnect
                    await ws.close()
                    disconnects += 1
                    self.log(f"Disconnected (total: {disconnects})")
                    
                    await asyncio.sleep(1)  # Brief pause before reconnect
                    
            except Exception as e:
                self.record_warning(
                    f"Connection error during stability test: {str(e)}",
                    {}
                )
                await asyncio.sleep(2)  # Wait before retry
        
        self.log(f"\n✓ Stability test results:")
        self.log(f"  Reconnects: {reconnects}")
        self.log(f"  Disconnects: {disconnects}")
        self.log(f"  Messages received: {messages_received}")
        
        return {
            "reconnects": reconnects,
            "disconnects": disconnects,
            "messages_received": messages_received
        }
    
    async def run_all_tests(self, num_clients: int = 100):
        """Run all WebSocket bug bash tests"""
        self.log(f"\n{'#'*60}")
        self.log(f"# WebSocket Scalability Bug Bash")
        self.log(f"# URL: {self.ws_url}")
        self.log(f"# Clients: {num_clients}")
        self.log(f"{'#'*60}\n")
        
        # Test 1: Concurrent connections
        await self.test_concurrent_connections(num_clients, duration=30)
        
        # Test 2: Connection stability
        await self.test_connection_stability(duration=60)
        
        # Summary
        self.log(f"\n{'='*60}")
        self.log(f"WEBSOCKET BUG BASH SUMMARY")
        self.log(f"{'='*60}")
        self.log(f"Bugs Found: {len(self.bugs_found)}")
        self.log(f"Warnings: {len(self.warnings)}")
        
        if self.bugs_found:
            self.log(f"\nBUGS:")
            for bug in self.bugs_found:
                self.log(f"  [{bug['severity']}] {bug['description']}")
        
        if self.warnings:
            self.log(f"\nWARNINGS:")
            for warning in self.warnings:
                self.log(f"  {warning['description']}")
        
        # Save report
        report = {
            "timestamp": datetime.now().isoformat(),
            "ws_url": self.ws_url,
            "num_clients": num_clients,
            "bugs_found": self.bugs_found,
            "warnings": self.warnings
        }
        
        report_filename = f"bug_bash_websocket_{int(time.time())}.json"
        with open(report_filename, 'w') as f:
            json.dump(report, f, indent=2)
        
        self.log(f"\n✓ Report saved to {report_filename}")


async def main():
    parser = argparse.ArgumentParser(description="WebSocket Bug Bash")
    parser.add_argument("--ws-url", default="ws://localhost:5000/ws", help="WebSocket URL")
    parser.add_argument("--token", required=True, help="Auth token")
    parser.add_argument("--clients", type=int, default=100, help="Number of concurrent clients")
    
    args = parser.parse_args()
    
    runner = WebSocketBugBash(ws_url=args.ws_url, auth_token=args.token)
    await runner.run_all_tests(num_clients=args.clients)


if __name__ == "__main__":
    asyncio.run(main())
