"""
Load Test: 2,000 Devices with Realistic Heartbeat Jitter

Simulates a production fleet with:
- 2,000 devices sending heartbeats concurrently
- 60s ±15s jitter per device (45-75s intervals)
- Realistic payload variation (battery, network, etc.)
- Performance metrics collection

Target SLIs:
- p95 latency <150ms
- p99 latency <300ms
- DB CPU <70%
- Pool saturation <80%

Usage:
    python load_test.py --devices 2000 --duration 600 --admin-key YOUR_KEY
    python load_test.py --devices 100 --duration 60 --dry-run
"""

import asyncio
import httpx
import random
import time
import argparse
import json
import sys
from datetime import datetime, timezone
from typing import List, Dict, Any
from collections import defaultdict
import statistics


class DeviceSimulator:
    """Simulates a single device sending heartbeats with jitter"""
    
    def __init__(self, device_id: int, base_url: str, token: str, jitter_seconds: int = 15):
        self.device_id = device_id
        self.alias = f"load-test-{device_id:04d}"
        self.base_url = base_url
        self.token = token
        self.jitter_seconds = jitter_seconds
        
        # Random device characteristics
        self.battery_pct = random.randint(20, 100)
        self.battery_drain_rate = random.uniform(-0.1, -0.5)  # % per minute
        self.network_type = random.choice(["wifi", "wifi", "cellular", "ethernet"])
        self.manufacturer = random.choice(["Samsung", "Google", "Xiaomi", "OnePlus"])
        
        # Metrics
        self.heartbeats_sent = 0
        self.latencies_ms = []
        self.errors = 0
    
    async def send_heartbeat(self, client: httpx.AsyncClient) -> Dict[str, Any]:
        """Send a single heartbeat and track latency"""
        
        # Update battery with drain
        self.battery_pct = max(10, min(100, self.battery_pct + (self.battery_drain_rate / 60)))
        
        payload = {
            "battery": {
                "pct": int(self.battery_pct),
                "charging": random.choice([True, False]),
                "temperature_c": random.uniform(25, 40)
            },
            "network": {
                "transport": self.network_type,
                "ip": f"192.168.1.{random.randint(100, 254)}",
                "ssid": "TestNetwork" if self.network_type == "wifi" else None,
                "carrier": "TestCarrier" if self.network_type == "cellular" else None
            },
            "system": {
                "model": f"{self.manufacturer} Test Device",
                "manufacturer": self.manufacturer,
                "android_version": "13",
                "sdk_int": 33,
                "build_id": "TEST123",
                "uptime_seconds": random.randint(3600, 86400)
            },
            "memory": {
                "total_ram_mb": 8192,
                "avail_ram_mb": random.randint(2048, 6144)
            },
            "app_version": "1.0.0-loadtest",
            "app_versions": {},
            "speedtest_running_signals": {
                "has_service_notification": False,
                "foreground_recent_seconds": None
            }
        }
        
        start_time = time.time()
        try:
            response = await client.post(
                f"{self.base_url}/v1/heartbeat",
                json=payload,
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=30.0
            )
            
            latency_ms = (time.time() - start_time) * 1000
            self.latencies_ms.append(latency_ms)
            self.heartbeats_sent += 1
            
            return {
                "success": response.status_code == 200,
                "latency_ms": latency_ms,
                "status_code": response.status_code
            }
        
        except Exception as e:
            self.errors += 1
            latency_ms = (time.time() - start_time) * 1000
            return {
                "success": False,
                "latency_ms": latency_ms,
                "error": str(e)
            }
    
    async def run(self, client: httpx.AsyncClient, duration_seconds: int):
        """Run heartbeat loop with jitter for specified duration"""
        end_time = time.time() + duration_seconds
        
        while time.time() < end_time:
            # Send heartbeat
            await self.send_heartbeat(client)
            
            # Sleep with jitter: base 60s ± jitter_seconds
            sleep_seconds = 60 + random.uniform(-self.jitter_seconds, self.jitter_seconds)
            await asyncio.sleep(sleep_seconds)


class LoadTestRunner:
    """Orchestrates load test for multiple devices"""
    
    def __init__(self, base_url: str, admin_key: str, num_devices: int, duration: int):
        self.base_url = base_url.rstrip('/')
        self.admin_key = admin_key
        self.num_devices = num_devices
        self.duration = duration
        
        self.devices: List[DeviceSimulator] = []
        self.enrollment_tokens = []
        self.start_time = None
        self.end_time = None
    
    async def register_devices(self, client: httpx.AsyncClient):
        """Register all test devices"""
        print(f"\n=== Registering {self.num_devices} devices ===")
        
        # Create enrollment tokens
        batch_size = 100
        for i in range(0, self.num_devices, batch_size):
            count = min(batch_size, self.num_devices - i)
            
            response = await client.post(
                f"{self.base_url}/api/enrollment-tokens",
                json={"uses_allowed": count, "expires_in_hours": 24},
                headers={"x-admin": self.admin_key}
            )
            
            if response.status_code != 200:
                raise Exception(f"Failed to create enrollment token: {response.text}")
            
            token_data = response.json()
            self.enrollment_tokens.append(token_data["token"])
        
        # Register devices
        tasks = []
        for i in range(self.num_devices):
            token = self.enrollment_tokens[i // batch_size]
            tasks.append(self._register_single_device(client, i, token))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        successful = sum(1 for r in results if not isinstance(r, Exception))
        print(f"✓ Registered {successful}/{self.num_devices} devices")
        
        if successful < self.num_devices:
            print(f"⚠ {self.num_devices - successful} devices failed to register")
    
    async def _register_single_device(self, client: httpx.AsyncClient, device_id: int, enrollment_token: str):
        """Register a single device"""
        try:
            response = await client.post(
                f"{self.base_url}/v1/register",
                json={
                    "alias": f"load-test-{device_id:04d}",
                    "hardware_id": f"hw-{device_id:08x}"
                },
                headers={"Authorization": f"Bearer {enrollment_token}"}
            )
            
            if response.status_code != 200:
                raise Exception(f"Registration failed: {response.text}")
            
            data = response.json()
            device = DeviceSimulator(
                device_id=device_id,
                base_url=self.base_url,
                token=data["device_token"]
            )
            self.devices.append(device)
            
        except Exception as e:
            print(f"Device {device_id} registration failed: {e}")
            raise
    
    async def run_load_test(self):
        """Execute the load test"""
        print(f"\n=== Starting Load Test ===")
        print(f"Devices: {self.num_devices}")
        print(f"Duration: {self.duration}s")
        print(f"Jitter: ±15s (45-75s intervals)")
        print(f"Target SLIs: p95 <150ms, p99 <300ms")
        print("")
        
        self.start_time = time.time()
        
        # Create concurrent httpx client with connection pool
        limits = httpx.Limits(
            max_keepalive_connections=200,
            max_connections=500,
            keepalive_expiry=30.0
        )
        
        async with httpx.AsyncClient(limits=limits) as client:
            # Register devices
            await self.register_devices(client)
            
            # Start heartbeat loops for all devices
            print(f"Starting heartbeat loops for {len(self.devices)} devices...")
            tasks = [device.run(client, self.duration) for device in self.devices]
            
            # Run with progress updates
            progress_task = asyncio.create_task(self._print_progress())
            await asyncio.gather(*tasks, progress_task)
        
        self.end_time = time.time()
    
    async def _print_progress(self):
        """Print progress updates during test"""
        interval = 10  # Print every 10s
        
        for elapsed in range(0, self.duration, interval):
            await asyncio.sleep(interval)
            
            total_hbs = sum(d.heartbeats_sent for d in self.devices)
            total_errors = sum(d.errors for d in self.devices)
            
            print(f"[{elapsed}s] Heartbeats sent: {total_hbs}, Errors: {total_errors}")
    
    def generate_report(self) -> Dict[str, Any]:
        """Generate performance report"""
        
        # Collect all latencies
        all_latencies = []
        for device in self.devices:
            all_latencies.extend(device.latencies_ms)
        
        if not all_latencies:
            return {"error": "No latency data collected"}
        
        all_latencies.sort()
        
        # Calculate percentiles
        p50 = all_latencies[len(all_latencies) // 2]
        p95 = all_latencies[int(len(all_latencies) * 0.95)]
        p99 = all_latencies[int(len(all_latencies) * 0.99)]
        p999 = all_latencies[int(len(all_latencies) * 0.999)]
        
        total_hbs = sum(d.heartbeats_sent for d in self.devices)
        total_errors = sum(d.errors for d in self.devices)
        error_rate = (total_errors / (total_hbs + total_errors)) * 100 if (total_hbs + total_errors) > 0 else 0
        
        elapsed = self.end_time - self.start_time
        throughput = total_hbs / elapsed
        
        # Pass/Fail checks
        p95_pass = p95 < 150
        p99_pass = p99 < 300
        error_rate_pass = error_rate < 0.5
        
        report = {
            "test_config": {
                "devices": self.num_devices,
                "duration": self.duration,
                "jitter": "±15s"
            },
            "summary": {
                "total_heartbeats": total_hbs,
                "total_errors": total_errors,
                "error_rate_pct": round(error_rate, 2),
                "throughput_hb_per_sec": round(throughput, 2),
                "duration_seconds": round(elapsed, 2)
            },
            "latency": {
                "p50_ms": round(p50, 2),
                "p95_ms": round(p95, 2),
                "p99_ms": round(p99, 2),
                "p999_ms": round(p999, 2),
                "mean_ms": round(statistics.mean(all_latencies), 2),
                "min_ms": round(min(all_latencies), 2),
                "max_ms": round(max(all_latencies), 2)
            },
            "sli_checks": {
                "p95_target_150ms": "PASS" if p95_pass else "FAIL",
                "p99_target_300ms": "PASS" if p99_pass else "FAIL",
                "error_rate_target_0.5pct": "PASS" if error_rate_pass else "FAIL",
                "overall": "PASS" if (p95_pass and p99_pass and error_rate_pass) else "FAIL"
            }
        }
        
        return report
    
    def print_report(self, report: Dict[str, Any]):
        """Print formatted report"""
        print("\n" + "="*60)
        print("LOAD TEST REPORT")
        print("="*60)
        
        print(f"\nTest Configuration:")
        print(f"  Devices: {report['test_config']['devices']}")
        print(f"  Duration: {report['test_config']['duration']}s")
        print(f"  Jitter: {report['test_config']['jitter']}")
        
        print(f"\nSummary:")
        print(f"  Total Heartbeats: {report['summary']['total_heartbeats']}")
        print(f"  Total Errors: {report['summary']['total_errors']}")
        print(f"  Error Rate: {report['summary']['error_rate_pct']}%")
        print(f"  Throughput: {report['summary']['throughput_hb_per_sec']:.1f} hb/s")
        
        print(f"\nLatency Metrics:")
        print(f"  p50:  {report['latency']['p50_ms']:.1f}ms")
        print(f"  p95:  {report['latency']['p95_ms']:.1f}ms  [target: <150ms]")
        print(f"  p99:  {report['latency']['p99_ms']:.1f}ms  [target: <300ms]")
        print(f"  p999: {report['latency']['p999_ms']:.1f}ms")
        print(f"  mean: {report['latency']['mean_ms']:.1f}ms")
        print(f"  max:  {report['latency']['max_ms']:.1f}ms")
        
        print(f"\nSLI Checks:")
        for check, result in report['sli_checks'].items():
            emoji = "✓" if result == "PASS" else "✗"
            print(f"  {emoji} {check}: {result}")
        
        print("\n" + "="*60)
        
        overall = report['sli_checks']['overall']
        if overall == "PASS":
            print("✓ ALL SLI TARGETS MET")
        else:
            print("✗ SOME SLI TARGETS NOT MET")
        print("="*60 + "\n")


async def main():
    parser = argparse.ArgumentParser(description="NexMDM Load Test")
    parser.add_argument("--devices", type=int, default=100, help="Number of devices to simulate")
    parser.add_argument("--duration", type=int, default=300, help="Test duration in seconds")
    parser.add_argument("--base-url", type=str, default="http://localhost:8000", help="API base URL")
    parser.add_argument("--admin-key", type=str, required=True, help="Admin key for enrollment")
    parser.add_argument("--output", type=str, help="Save report to JSON file")
    parser.add_argument("--dry-run", action="store_true", help="Test with minimal load")
    
    args = parser.parse_args()
    
    # Dry run overrides
    if args.dry_run:
        args.devices = 10
        args.duration = 30
        print("\n⚠ DRY RUN MODE: 10 devices, 30 seconds")
    
    # Run test
    runner = LoadTestRunner(
        base_url=args.base_url,
        admin_key=args.admin_key,
        num_devices=args.devices,
        duration=args.duration
    )
    
    try:
        await runner.run_load_test()
        report = runner.generate_report()
        runner.print_report(report)
        
        # Save report if requested
        if args.output:
            with open(args.output, 'w') as f:
                json.dump(report, f, indent=2)
            print(f"Report saved to {args.output}")
        
        # Exit with status based on SLI checks
        sys.exit(0 if report['sli_checks']['overall'] == "PASS" else 1)
    
    except KeyboardInterrupt:
        print("\n\nLoad test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nLoad test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
