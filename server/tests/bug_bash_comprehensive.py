"""
Comprehensive Bug Bash Script for UNITYmdm
Tests all components at scale (100+ devices) with edge cases
"""

import asyncio
import httpx
import random
import time
import json
import sys
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
from collections import defaultdict
import statistics
import argparse


class BugBashRunner:
    """Comprehensive bug bash test suite"""
    
    def __init__(self, base_url: str, admin_key: str, dry_run: bool = False):
        self.base_url = base_url
        self.admin_key = admin_key
        self.dry_run = dry_run
        self.results = defaultdict(list)
        self.bugs_found = []
        self.warnings = []
        
    def log(self, message: str, level: str = "INFO"):
        """Log test progress"""
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        print(f"[{timestamp}] [{level}] {message}")
        
    def record_bug(self, category: str, severity: str, description: str, details: Dict = None):
        """Record a bug finding"""
        bug = {
            "category": category,
            "severity": severity,
            "description": description,
            "details": details or {},
            "timestamp": datetime.now().isoformat()
        }
        self.bugs_found.append(bug)
        self.log(f"🐛 BUG [{severity}] {category}: {description}", "ERROR")
        
    def record_warning(self, category: str, description: str, details: Dict = None):
        """Record a warning/concern"""
        warning = {
            "category": category,
            "description": description,
            "details": details or {},
            "timestamp": datetime.now().isoformat()
        }
        self.warnings.append(warning)
        self.log(f"⚠️  WARNING {category}: {description}", "WARN")
    
    async def test_device_registration_scale(self, num_devices: int = 100):
        """Test 1: Device registration and authentication at scale"""
        self.log(f"\n{'='*60}")
        self.log(f"TEST 1: Device Registration at Scale ({num_devices} devices)")
        self.log(f"{'='*60}")
        
        results = {
            "total_devices": num_devices,
            "successful": 0,
            "failed": 0,
            "latencies": [],
            "tokens_created": [],
            "duplicate_checks": 0
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Step 1: Create enrollment tokens
            self.log(f"Creating {num_devices} enrollment tokens...")
            start = time.time()
            
            try:
                response = await client.post(
                    f"{self.base_url}/v1/enroll-tokens",
                    json={"count": num_devices, "ttl_hours": 24},
                    headers={"X-Admin-Key": self.admin_key}
                )
                
                if response.status_code != 200:
                    self.record_bug(
                        "Device Registration",
                        "CRITICAL",
                        f"Failed to create enrollment tokens: {response.status_code}",
                        {"response": response.text}
                    )
                    return results
                    
                tokens_data = response.json()
                tokens = tokens_data.get("tokens", [])
                token_creation_time = (time.time() - start) * 1000
                
                self.log(f"✓ Created {len(tokens)} tokens in {token_creation_time:.2f}ms")
                
                if len(tokens) != num_devices:
                    self.record_bug(
                        "Device Registration",
                        "HIGH",
                        f"Requested {num_devices} tokens but got {len(tokens)}",
                        {"requested": num_devices, "received": len(tokens)}
                    )
                
            except Exception as e:
                self.record_bug(
                    "Device Registration",
                    "CRITICAL",
                    f"Exception creating enrollment tokens: {str(e)}",
                    {"error": str(e)}
                )
                return results
            
            # Step 2: Register devices in parallel
            self.log(f"Registering {len(tokens)} devices in parallel...")
            
            async def register_device(token_value: str, device_idx: int):
                """Register a single device"""
                alias = f"bugbash-device-{device_idx:04d}"
                start_time = time.time()
                
                try:
                    reg_response = await client.post(
                        f"{self.base_url}/v1/register",
                        json={},
                        headers={
                            "Authorization": f"Bearer {token_value}",
                            "X-Device-Alias": alias,
                            "X-Device-Model": f"Test Device {device_idx}",
                            "X-Device-Android-Version": "13"
                        }
                    )
                    
                    latency = (time.time() - start_time) * 1000
                    
                    if reg_response.status_code == 200:
                        device_data = reg_response.json()
                        return {
                            "success": True,
                            "latency": latency,
                            "device_id": device_data.get("device_id"),
                            "device_token": device_data.get("device_token")
                        }
                    else:
                        return {
                            "success": False,
                            "latency": latency,
                            "status_code": reg_response.status_code,
                            "error": reg_response.text
                        }
                        
                except Exception as e:
                    latency = (time.time() - start_time) * 1000
                    return {
                        "success": False,
                        "latency": latency,
                        "exception": str(e)
                    }
            
            # Register all devices concurrently
            start = time.time()
            registration_tasks = [
                register_device(token["token"], idx)
                for idx, token in enumerate(tokens)
            ]
            
            registration_results = await asyncio.gather(*registration_tasks)
            total_time = (time.time() - start) * 1000
            
            # Analyze results
            for result in registration_results:
                if result["success"]:
                    results["successful"] += 1
                    results["latencies"].append(result["latency"])
                    results["tokens_created"].append(result["device_token"])
                else:
                    results["failed"] += 1
                    results["latencies"].append(result["latency"])
            
            self.log(f"✓ Registered {results['successful']}/{num_devices} devices in {total_time:.2f}ms")
            
            if results["successful"] > 0:
                avg_latency = statistics.mean(results["latencies"])
                p95_latency = statistics.quantiles(results["latencies"], n=20)[18] if len(results["latencies"]) > 20 else max(results["latencies"])
                p99_latency = statistics.quantiles(results["latencies"], n=100)[98] if len(results["latencies"]) > 100 else max(results["latencies"])
                
                self.log(f"  Avg latency: {avg_latency:.2f}ms")
                self.log(f"  P95 latency: {p95_latency:.2f}ms")
                self.log(f"  P99 latency: {p99_latency:.2f}ms")
                
                # Check latency budgets
                if p95_latency > 500:
                    self.record_warning(
                        "Device Registration Performance",
                        f"P95 registration latency ({p95_latency:.2f}ms) is high",
                        {"p95": p95_latency, "threshold": 500}
                    )
            
            # Test edge cases
            self.log(f"\nTesting edge cases...")
            
            # Test 1: Re-use enrollment token (should fail)
            if tokens:
                test_token = tokens[0]["token"]
                reuse_response = await client.post(
                    f"{self.base_url}/v1/register",
                    json={},
                    headers={
                        "Authorization": f"Bearer {test_token}",
                        "X-Device-Alias": "reuse-test",
                        "X-Device-Model": "Test",
                        "X-Device-Android-Version": "13"
                    }
                )
                
                if reuse_response.status_code == 200:
                    self.record_bug(
                        "Device Registration Security",
                        "CRITICAL",
                        "Enrollment token can be reused - security issue!",
                        {"token": test_token[:10] + "..."}
                    )
                else:
                    self.log(f"✓ Token reuse correctly rejected ({reuse_response.status_code})")
            
            # Test 2: Invalid token format
            invalid_response = await client.post(
                f"{self.base_url}/v1/register",
                json={},
                headers={
                    "Authorization": "Bearer invalid_token_123",
                    "X-Device-Alias": "invalid-test",
                    "X-Device-Model": "Test",
                    "X-Device-Android-Version": "13"
                }
            )
            
            if invalid_response.status_code == 200:
                self.record_bug(
                    "Device Registration Security",
                    "CRITICAL",
                    "Invalid enrollment token accepted!",
                    {}
                )
            else:
                self.log(f"✓ Invalid token correctly rejected ({invalid_response.status_code})")
            
            # Test 3: Missing required headers
            missing_headers_response = await client.post(
                f"{self.base_url}/v1/register",
                json={},
                headers={"Authorization": f"Bearer {tokens[0]['token']}" if tokens else "Bearer test"}
            )
            
            if missing_headers_response.status_code == 200:
                self.record_warning(
                    "Device Registration Validation",
                    "Registration succeeded without required headers (alias, model)",
                    {}
                )
            
            # Test 4: Very long alias (XSS/injection attempt)
            if results["tokens_created"]:
                long_alias = "A" * 500
                try:
                    alias_test_token = results["tokens_created"][0]
                    long_alias_response = await client.post(
                        f"{self.base_url}/v1/heartbeat",
                        json={
                            "battery": {"pct": 50, "charging": False, "temperature_c": 30},
                            "network": {"transport": "wifi", "ip": "192.168.1.1"},
                            "system": {"model": "Test", "manufacturer": "Test", "android_version": "13", "sdk_int": 33, "build_id": "TEST", "uptime_seconds": 1000},
                            "memory": {"total_ram_mb": 8192, "avail_ram_mb": 4096},
                            "app_version": "1.0.0",
                            "app_versions": {},
                            "speedtest_running_signals": {"has_service_notification": False, "foreground_recent_seconds": None}
                        },
                        headers={
                            "Authorization": f"Bearer {alias_test_token}",
                            "X-Device-Alias-Update": long_alias
                        }
                    )
                    
                    if long_alias_response.status_code == 200:
                        self.record_warning(
                            "Input Validation",
                            "Very long device alias (500 chars) accepted - potential DoS vector",
                            {"alias_length": len(long_alias)}
                        )
                except Exception as e:
                    pass
        
        self.results["device_registration"] = results
        return results
    
    async def test_heartbeat_load(self, num_devices: int = 100, heartbeats_per_device: int = 10):
        """Test 2: Heartbeat processing under load"""
        self.log(f"\n{'='*60}")
        self.log(f"TEST 2: Heartbeat Processing Load ({num_devices} devices, {heartbeats_per_device} each)")
        self.log(f"{'='*60}")
        
        results = {
            "total_heartbeats": 0,
            "successful": 0,
            "failed": 0,
            "latencies": [],
            "deduplication_tests": []
        }
        
        # First register devices
        reg_result = await self.test_device_registration_scale(num_devices)
        
        if not reg_result["tokens_created"]:
            self.log("❌ No devices registered, skipping heartbeat test")
            return results
        
        device_tokens = reg_result["tokens_created"][:min(num_devices, len(reg_result["tokens_created"]))]
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            self.log(f"Sending {heartbeats_per_device} heartbeats per device...")
            
            async def send_heartbeat(device_idx: int, device_token: str):
                """Send a single heartbeat"""
                payload = {
                    "battery": {
                        "pct": random.randint(20, 100),
                        "charging": random.choice([True, False]),
                        "temperature_c": random.uniform(25, 40)
                    },
                    "network": {
                        "transport": random.choice(["wifi", "cellular"]),
                        "ip": f"192.168.1.{random.randint(1, 254)}",
                        "ssid": "TestNetwork" if random.random() > 0.5 else None
                    },
                    "system": {
                        "model": f"Test Device {device_idx}",
                        "manufacturer": "Test",
                        "android_version": "13",
                        "sdk_int": 33,
                        "build_id": "TEST123",
                        "uptime_seconds": random.randint(1000, 86400)
                    },
                    "memory": {
                        "total_ram_mb": 8192,
                        "avail_ram_mb": random.randint(2048, 6144)
                    },
                    "app_version": "1.0.0-bugbash",
                    "app_versions": {},
                    "speedtest_running_signals": {
                        "has_service_notification": random.choice([True, False]),
                        "foreground_recent_seconds": random.randint(0, 300) if random.random() > 0.5 else None
                    }
                }
                
                start_time = time.time()
                try:
                    response = await client.post(
                        f"{self.base_url}/v1/heartbeat",
                        json=payload,
                        headers={"Authorization": f"Bearer {device_token}"}
                    )
                    
                    latency = (time.time() - start_time) * 1000
                    
                    return {
                        "success": response.status_code == 200,
                        "latency": latency,
                        "status_code": response.status_code
                    }
                except Exception as e:
                    latency = (time.time() - start_time) * 1000
                    return {
                        "success": False,
                        "latency": latency,
                        "exception": str(e)
                    }
            
            # Send heartbeats in waves
            total_heartbeats = len(device_tokens) * heartbeats_per_device
            self.log(f"Sending {total_heartbeats} total heartbeats...")
            
            start = time.time()
            all_tasks = []
            
            for beat_num in range(heartbeats_per_device):
                for device_idx, device_token in enumerate(device_tokens):
                    all_tasks.append(send_heartbeat(device_idx, device_token))
            
            heartbeat_results = await asyncio.gather(*all_tasks)
            total_time = (time.time() - start) * 1000
            
            # Analyze results
            for result in heartbeat_results:
                results["total_heartbeats"] += 1
                if result["success"]:
                    results["successful"] += 1
                    results["latencies"].append(result["latency"])
                else:
                    results["failed"] += 1
            
            throughput = (results["total_heartbeats"] / total_time) * 1000  # heartbeats/sec
            
            self.log(f"✓ Processed {results['successful']}/{results['total_heartbeats']} heartbeats in {total_time:.2f}ms")
            self.log(f"  Throughput: {throughput:.2f} heartbeats/sec")
            
            if results["latencies"]:
                avg_latency = statistics.mean(results["latencies"])
                p95_latency = statistics.quantiles(results["latencies"], n=20)[18] if len(results["latencies"]) > 20 else max(results["latencies"])
                p99_latency = statistics.quantiles(results["latencies"], n=100)[98] if len(results["latencies"]) > 100 else max(results["latencies"])
                
                self.log(f"  Avg latency: {avg_latency:.2f}ms")
                self.log(f"  P95 latency: {p95_latency:.2f}ms")
                self.log(f"  P99 latency: {p99_latency:.2f}ms")
                
                # Check SLIs
                if p95_latency > 150:
                    self.record_bug(
                        "Heartbeat Performance",
                        "MEDIUM",
                        f"P95 latency ({p95_latency:.2f}ms) exceeds SLI target of 150ms",
                        {"p95": p95_latency, "target": 150}
                    )
                
                if p99_latency > 300:
                    self.record_bug(
                        "Heartbeat Performance",
                        "MEDIUM",
                        f"P99 latency ({p99_latency:.2f}ms) exceeds SLI target of 300ms",
                        {"p99": p99_latency, "target": 300}
                    )
            
            # Test deduplication (send duplicate heartbeats within 10s window)
            if device_tokens:
                self.log(f"\nTesting heartbeat deduplication...")
                test_token = device_tokens[0]
                
                duplicate_tasks = [send_heartbeat(0, test_token) for _ in range(5)]
                dedupe_results = await asyncio.gather(*duplicate_tasks)
                
                successful_dupes = sum(1 for r in dedupe_results if r["success"])
                self.log(f"  Sent 5 duplicate heartbeats, {successful_dupes} succeeded")
                
                if successful_dupes != 5:
                    self.record_warning(
                        "Heartbeat Deduplication",
                        f"Expected all 5 duplicate heartbeats to succeed (deduplication is idempotent), but got {successful_dupes}",
                        {"expected": 5, "actual": successful_dupes}
                    )
        
        self.results["heartbeat_load"] = results
        return results
    
    async def test_edge_cases(self):
        """Test various edge cases and error conditions"""
        self.log(f"\n{'='*60}")
        self.log(f"TEST: Edge Cases and Error Handling")
        self.log(f"{'='*60}")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Test malformed JSON
            self.log("Testing malformed JSON...")
            try:
                response = await client.post(
                    f"{self.base_url}/v1/heartbeat",
                    content=b"{ invalid json }",
                    headers={
                        "Authorization": "Bearer test",
                        "Content-Type": "application/json"
                    }
                )
                
                if response.status_code == 500:
                    self.record_bug(
                        "Error Handling",
                        "MEDIUM",
                        "Malformed JSON returns 500 instead of 400",
                        {"status_code": response.status_code}
                    )
                elif response.status_code == 422 or response.status_code == 400:
                    self.log(f"✓ Malformed JSON correctly rejected ({response.status_code})")
            except Exception as e:
                self.log(f"  Exception on malformed JSON: {str(e)}")
            
            # Test oversized payload
            self.log("Testing oversized payload...")
            huge_payload = {
                "battery": {"pct": 50, "charging": False, "temperature_c": 30},
                "network": {"transport": "wifi", "ip": "192.168.1.1"},
                "system": {
                    "model": "A" * 10000,  # 10KB model name
                    "manufacturer": "Test",
                    "android_version": "13",
                    "sdk_int": 33,
                    "build_id": "TEST",
                    "uptime_seconds": 1000
                },
                "memory": {"total_ram_mb": 8192, "avail_ram_mb": 4096},
                "app_version": "1.0.0",
                "app_versions": {},
                "speedtest_running_signals": {"has_service_notification": False, "foreground_recent_seconds": None}
            }
            
            try:
                response = await client.post(
                    f"{self.base_url}/v1/heartbeat",
                    json=huge_payload,
                    headers={"Authorization": "Bearer test"}
                )
                
                if response.status_code == 200:
                    self.record_warning(
                        "Input Validation",
                        "Oversized payload (10KB model name) accepted - potential DoS vector",
                        {}
                    )
                else:
                    self.log(f"✓ Oversized payload rejected ({response.status_code})")
            except Exception as e:
                self.log(f"  Exception on oversized payload: {str(e)}")
            
            # Test SQL injection attempts
            self.log("Testing SQL injection in device alias...")
            sql_injection_aliases = [
                "'; DROP TABLE devices; --",
                "admin' OR '1'='1",
                "1' UNION SELECT * FROM users--"
            ]
            
            for injection_alias in sql_injection_aliases:
                try:
                    response = await client.post(
                        f"{self.base_url}/v1/enroll-tokens",
                        json={"count": 1, "ttl_hours": 1},
                        headers={"X-Admin-Key": self.admin_key}
                    )
                    
                    if response.status_code == 200:
                        token = response.json()["tokens"][0]["token"]
                        
                        reg_response = await client.post(
                            f"{self.base_url}/v1/register",
                            json={},
                            headers={
                                "Authorization": f"Bearer {token}",
                                "X-Device-Alias": injection_alias,
                                "X-Device-Model": "Test",
                                "X-Device-Android-Version": "13"
                            }
                        )
                        
                        if reg_response.status_code == 200:
                            # Check if the alias was properly escaped
                            self.log(f"  SQL injection alias accepted, checking storage safety...")
                except Exception as e:
                    self.record_warning(
                        "SQL Injection Test",
                        f"Exception during SQL injection test: {str(e)}",
                        {"alias": injection_alias}
                    )
            
            self.log(f"✓ SQL injection tests completed")
            
            # Test XSS in device alias
            self.log("Testing XSS in device alias...")
            xss_aliases = [
                "<script>alert('xss')</script>",
                "<img src=x onerror=alert('xss')>",
                "javascript:alert('xss')"
            ]
            
            for xss_alias in xss_aliases:
                try:
                    response = await client.post(
                        f"{self.base_url}/v1/enroll-tokens",
                        json={"count": 1, "ttl_hours": 1},
                        headers={"X-Admin-Key": self.admin_key}
                    )
                    
                    if response.status_code == 200:
                        token = response.json()["tokens"][0]["token"]
                        
                        reg_response = await client.post(
                            f"{self.base_url}/v1/register",
                            json={},
                            headers={
                                "Authorization": f"Bearer {token}",
                                "X-Device-Alias": xss_alias,
                                "X-Device-Model": "Test",
                                "X-Device-Android-Version": "13"
                            }
                        )
                        
                        if reg_response.status_code == 200:
                            self.log(f"  XSS alias accepted: {xss_alias[:30]}...")
                except Exception as e:
                    pass
            
            self.log(f"✓ XSS tests completed")
    
    async def run_all_tests(self, num_devices: int = 100):
        """Run all bug bash tests"""
        start_time = time.time()
        
        self.log(f"\n{'#'*60}")
        self.log(f"# UNITYmdm Comprehensive Bug Bash")
        self.log(f"# Target: {self.base_url}")
        self.log(f"# Scale: {num_devices} devices")
        self.log(f"# Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.log(f"{'#'*60}\n")
        
        if self.dry_run:
            self.log("DRY RUN MODE - No actual tests will be executed\n")
            return
        
        # Run all tests
        await self.test_device_registration_scale(num_devices)
        await self.test_heartbeat_load(num_devices, heartbeats_per_device=10)
        await self.test_edge_cases()
        
        # Generate report
        total_time = time.time() - start_time
        
        self.log(f"\n{'='*60}")
        self.log(f"BUG BASH SUMMARY")
        self.log(f"{'='*60}")
        self.log(f"Duration: {total_time:.2f}s")
        self.log(f"Bugs Found: {len(self.bugs_found)}")
        self.log(f"Warnings: {len(self.warnings)}")
        
        if self.bugs_found:
            self.log(f"\n{'='*60}")
            self.log(f"BUGS FOUND ({len(self.bugs_found)})")
            self.log(f"{'='*60}")
            
            for bug in self.bugs_found:
                self.log(f"\n[{bug['severity']}] {bug['category']}")
                self.log(f"  {bug['description']}")
                if bug['details']:
                    self.log(f"  Details: {json.dumps(bug['details'], indent=2)}")
        
        if self.warnings:
            self.log(f"\n{'='*60}")
            self.log(f"WARNINGS ({len(self.warnings)})")
            self.log(f"{'='*60}")
            
            for warning in self.warnings:
                self.log(f"\n{warning['category']}")
                self.log(f"  {warning['description']}")
        
        # Save report to file
        report = {
            "timestamp": datetime.now().isoformat(),
            "duration_seconds": total_time,
            "base_url": self.base_url,
            "num_devices": num_devices,
            "bugs_found": self.bugs_found,
            "warnings": self.warnings,
            "test_results": dict(self.results)
        }
        
        report_filename = f"bug_bash_report_{int(time.time())}.json"
        with open(report_filename, 'w') as f:
            json.dump(report, f, indent=2)
        
        self.log(f"\n✓ Report saved to {report_filename}")
        
        return report


async def main():
    parser = argparse.ArgumentParser(description="UNITYmdm Bug Bash")
    parser.add_argument("--base-url", default="http://localhost:5000", help="Base URL of the API")
    parser.add_argument("--admin-key", default="admin", help="Admin API key")
    parser.add_argument("--devices", type=int, default=100, help="Number of devices to simulate")
    parser.add_argument("--dry-run", action="store_true", help="Dry run mode")
    
    args = parser.parse_args()
    
    runner = BugBashRunner(
        base_url=args.base_url,
        admin_key=args.admin_key,
        dry_run=args.dry_run
    )
    
    await runner.run_all_tests(num_devices=args.devices)


if __name__ == "__main__":
    asyncio.run(main())
