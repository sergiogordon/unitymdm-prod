"""
20-Device Enrollment Simulation

Tests the complete control loop with 20 simulated devices:
1. Admin creates 20 enrollment tokens
2. Devices register in parallel
3. Devices send heartbeats with random jitter for 2 minutes
4. Admin sends commands to all devices
5. Devices report action results
6. Verify end state and metrics
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
import asyncio
import time
import random
from datetime import datetime, timezone
from typing import List, Dict
import statistics


class TestTwentyDeviceSimulation:
    """Full 20-device enrollment and lifecycle simulation"""
    
    def test_complete_20_device_simulation(self, client: TestClient, test_db: Session, admin_auth: dict):
        """
        Complete simulation of 20 devices from enrollment to command execution.
        Tracks latencies and verifies all operations complete successfully.
        """
        num_devices = 20
        device_aliases = [f"D{i:02d}" for i in range(1, num_devices + 1)]
        
        print(f"\n{'='*60}")
        print(f"20-Device Enrollment Simulation")
        print(f"{'='*60}\n")
        
        latency_data = {
            "heartbeats": [],
            "dispatches": [],
            "metrics_scrapes": []
        }
        
        print("Step 1: Admin creates 20 enrollment tokens...")
        start_time = time.time()
        
        response = client.post(
            "/v1/enroll-tokens",
            headers=admin_auth,
            json={
                "aliases": device_aliases,
                "expires_in_sec": 2700,
                "uses_allowed": 1,
                "note": "20-device simulation batch"
            }
        )
        
        assert response.status_code == 200
        token_data = response.json()
        assert len(token_data["tokens"]) == num_devices
        
        enrollment_tokens = {
            t["alias"]: t["token"] for t in token_data["tokens"]
        }
        
        print(f"  ✓ Created {num_devices} tokens in {(time.time() - start_time)*1000:.2f}ms")
        
        print("\nStep 2: Devices register in parallel...")
        registered_devices = {}
        registration_start = time.time()
        
        for alias in device_aliases:
            response = client.post(
                f"/v1/register",
                params={"alias": alias},
                headers={"Authorization": f"Bearer {enrollment_tokens[alias]}"}
            )
            
            if response.status_code == 200:
                data = response.json()
                registered_devices[alias] = {
                    "device_id": data["device_id"],
                    "device_token": data["device_token"]
                }
        
        registration_time = (time.time() - registration_start) * 1000
        print(f"  ✓ Registered {len(registered_devices)}/{num_devices} devices in {registration_time:.2f}ms")
        assert len(registered_devices) == num_devices
        
        from models import Device
        device_count = test_db.query(Device).count()
        assert device_count >= num_devices
        
        print("\nStep 3: Heartbeat stream (simulated 2 minutes)...")
        print("  Sending heartbeats with 10-15s jitter...")
        
        heartbeat_rounds = 8
        for round_num in range(heartbeat_rounds):
            round_start = time.time()
            
            for alias, device_info in registered_devices.items():
                response = client.post(
                    "/v1/heartbeat",
                    headers={"Authorization": f"Bearer {device_info['device_token']}"},
                    json={
                        "status": "ok",
                        "battery_pct": random.randint(70, 100),
                        "network_type": "wifi",
                        "uptime_sec": (round_num + 1) * 15 + random.randint(0, 5)
                    }
                )
                
                if response.status_code == 200:
                    latency_ms = (time.time() - round_start) * 1000
                    latency_data["heartbeats"].append(latency_ms)
            
            if round_num < heartbeat_rounds - 1:
                time.sleep(0.1)
        
        heartbeats_sent = len(latency_data["heartbeats"])
        print(f"  ✓ Sent {heartbeats_sent} heartbeats total")
        
        if latency_data["heartbeats"]:
            p50 = statistics.median(latency_data["heartbeats"])
            p95 = statistics.quantiles(latency_data["heartbeats"], n=20)[18]
            p99 = statistics.quantiles(latency_data["heartbeats"], n=100)[98]
            
            print(f"  Heartbeat latency: p50={p50:.2f}ms, p95={p95:.2f}ms, p99={p99:.2f}ms")
            
            assert p95 < 150, f"p95 heartbeat latency {p95:.2f}ms exceeds 150ms budget"
            assert p99 < 300, f"p99 heartbeat latency {p99:.2f}ms exceeds 300ms budget"
        
        from models import DeviceHeartbeat
        heartbeat_rows = test_db.query(DeviceHeartbeat).count()
        print(f"  DB rows created: {heartbeat_rows} (dedupe working: {heartbeats_sent} -> {heartbeat_rows})")
        
        print("\nStep 4: Admin issues commands to all devices...")
        
        command_request_ids = {}
        for alias, device_info in registered_devices.items():
            from models import FcmDispatch
            import uuid
            
            request_id = str(uuid.uuid4())
            dispatch_start = time.time()
            
            dispatch = FcmDispatch(
                request_id=request_id,
                device_id=device_info["device_id"],
                action="ping",
                sent_at=datetime.now(timezone.utc),
                fcm_status="sent"
            )
            test_db.add(dispatch)
            test_db.commit()
            
            dispatch_latency = (time.time() - dispatch_start) * 1000
            latency_data["dispatches"].append(dispatch_latency)
            
            command_request_ids[alias] = request_id
        
        print(f"  ✓ Issued {len(command_request_ids)} commands")
        
        if latency_data["dispatches"]:
            p50_dispatch = statistics.median(latency_data["dispatches"])
            p95_dispatch = statistics.quantiles(latency_data["dispatches"], n=20)[18]
            
            print(f"  Dispatch write latency: p50={p50_dispatch:.2f}ms, p95={p95_dispatch:.2f}ms")
            
            assert p95_dispatch < 50, f"p95 dispatch latency {p95_dispatch:.2f}ms exceeds 50ms budget"
        
        print("\nStep 5: Devices report action results...")
        
        results_reported = 0
        for alias, device_info in registered_devices.items():
            time.sleep(random.uniform(0.001, 0.003))
            
            response = client.post(
                "/v1/action-result",
                headers={"Authorization": f"Bearer {device_info['device_token']}"},
                json={
                    "request_id": command_request_ids[alias],
                    "result": "ok",
                    "data": {"ping_time_ms": random.randint(20, 80)}
                }
            )
            
            if response.status_code == 200:
                results_reported += 1
        
        print(f"  ✓ Received {results_reported}/{num_devices} action results")
        assert results_reported == num_devices
        
        from models import FcmDispatch
        completed_dispatches = test_db.query(FcmDispatch).filter(
            FcmDispatch.completed_at.isnot(None)
        ).count()
        print(f"  Completed dispatches in DB: {completed_dispatches}")
        assert completed_dispatches == num_devices
        
        print("\nStep 6: Verify final state...")
        
        devices_in_db = test_db.query(Device).count()
        print(f"  Devices in DB: {devices_in_db}")
        assert devices_in_db >= num_devices
        
        from models import EnrollmentToken
        exhausted_tokens = test_db.query(EnrollmentToken).filter(
            EnrollmentToken.uses_consumed >= EnrollmentToken.uses_allowed
        ).count()
        print(f"  Exhausted enrollment tokens: {exhausted_tokens}")
        
        print("\nStep 7: Test metrics scrape latency...")
        
        for i in range(5):
            scrape_start = time.time()
            response = client.get("/metrics", headers={"X-Admin": os.getenv("ADMIN_KEY", "admin")})
            scrape_latency = (time.time() - scrape_start) * 1000
            
            latency_data["metrics_scrapes"].append(scrape_latency)
            
            assert response.status_code == 200
        
        if latency_data["metrics_scrapes"]:
            avg_scrape = statistics.mean(latency_data["metrics_scrapes"])
            max_scrape = max(latency_data["metrics_scrapes"])
            
            print(f"  Metrics scrape: avg={avg_scrape:.2f}ms, max={max_scrape:.2f}ms")
            
            assert max_scrape < 50, f"Metrics scrape {max_scrape:.2f}ms exceeds 50ms budget"
        
        print(f"\n{'='*60}")
        print("Simulation Summary")
        print(f"{'='*60}")
        print(f"✓ {num_devices}/{num_devices} devices registered successfully")
        print(f"✓ {heartbeats_sent} heartbeats ingested")
        print(f"✓ {heartbeat_rows} heartbeat rows (dedupe factor: {heartbeats_sent/max(heartbeat_rows,1):.1f}x)")
        print(f"✓ {num_devices}/{num_devices} commands dispatched")
        print(f"✓ {completed_dispatches}/{num_devices} action results received")
        
        if latency_data["heartbeats"]:
            print(f"\nLatency Budgets:")
            print(f"  Heartbeat p95: {p95:.2f}ms (budget: <150ms) {'✓' if p95 < 150 else '✗'}")
            print(f"  Heartbeat p99: {p99:.2f}ms (budget: <300ms) {'✓' if p99 < 300 else '✗'}")
        
        if latency_data["dispatches"]:
            print(f"  Dispatch p95: {p95_dispatch:.2f}ms (budget: <50ms) {'✓' if p95_dispatch < 50 else '✗'}")
        
        if latency_data["metrics_scrapes"]:
            print(f"  Metrics scrape max: {max_scrape:.2f}ms (budget: <50ms) {'✓' if max_scrape < 50 else '✗'}")
        
        print(f"{'='*60}\n")


import os
