"""
Security Bug Bash
Tests authentication, authorization, input validation, and security edge cases
"""

import asyncio
import httpx
import json
import time
import argparse
from datetime import datetime, timedelta
from typing import List, Dict


class SecurityBugBash:
    """Comprehensive security testing"""
    
    def __init__(self, base_url: str, admin_key: str):
        self.base_url = base_url
        self.admin_key = admin_key
        self.bugs_found = []
        self.warnings = []
        
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
        self.log(f"🐛 SECURITY BUG [{severity}] {description}", "ERROR")
        
    def record_warning(self, description: str, details: Dict = None):
        warning = {
            "description": description,
            "details": details or {},
            "timestamp": datetime.now().isoformat()
        }
        self.warnings.append(warning)
        self.log(f"⚠️  WARNING {description}", "WARN")
    
    async def test_authentication_bypass(self):
        """Test various authentication bypass attempts"""
        self.log(f"\n{'='*60}")
        self.log(f"Testing Authentication Bypass Attempts")
        self.log(f"{'='*60}")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Test 1: No authorization header
            self.log("Test: Accessing protected endpoint without auth...")
            response = await client.post(
                f"{self.base_url}/v1/heartbeat",
                json={"battery": {"pct": 50, "charging": False, "temperature_c": 30}}
            )
            
            if response.status_code == 200:
                self.record_bug(
                    "CRITICAL",
                    "Protected endpoint accessible without authentication",
                    {"endpoint": "/v1/heartbeat", "status": 200}
                )
            else:
                self.log(f"  ✓ Correctly rejected ({response.status_code})")
            
            # Test 2: Invalid token format
            self.log("Test: Invalid token format...")
            invalid_tokens = [
                "Bearer ",
                "Bearer invalid",
                "Basic dGVzdDp0ZXN0",  # Basic auth instead of Bearer
                "Bearer ' OR '1'='1",  # SQL injection attempt
                "Bearer <script>alert(1)</script>",  # XSS attempt
            ]
            
            for token in invalid_tokens:
                response = await client.post(
                    f"{self.base_url}/v1/heartbeat",
                    json={"battery": {"pct": 50, "charging": False, "temperature_c": 30}},
                    headers={"Authorization": token}
                )
                
                if response.status_code == 200:
                    self.record_bug(
                        "CRITICAL",
                        f"Invalid token accepted: {token[:50]}",
                        {"token_prefix": token[:50]}
                    )
            
            self.log("  ✓ Invalid token formats rejected")
            
            # Test 3: Admin key brute force (rate limiting test)
            self.log("Test: Admin key brute force rate limiting...")
            attempts = 0
            rate_limited = False
            
            for i in range(20):  # Try 20 invalid admin keys
                response = await client.post(
                    f"{self.base_url}/v1/enroll-tokens",
                    json={"count": 1, "ttl_hours": 1},
                    headers={"X-Admin-Key": f"invalid_key_{i}"}
                )
                
                attempts += 1
                
                if response.status_code == 429:  # Too Many Requests
                    rate_limited = True
                    self.log(f"  ✓ Rate limited after {attempts} attempts")
                    break
            
            if not rate_limited:
                self.record_warning(
                    "No rate limiting detected for admin key brute force",
                    {"attempts": attempts}
                )
            
            # Test 4: JWT token manipulation
            self.log("Test: JWT token manipulation...")
            
            # First get a valid token
            response = await client.post(
                f"{self.base_url}/v1/enroll-tokens",
                json={"count": 1, "ttl_hours": 1},
                headers={"X-Admin-Key": self.admin_key}
            )
            
            if response.status_code == 200:
                token = response.json()["tokens"][0]["token"]
                
                # Try to modify the token
                if "." in token:  # JWT format
                    parts = token.split(".")
                    if len(parts) == 3:
                        # Tamper with payload
                        tampered_token = parts[0] + "." + "eyJhbGd0IjoiSFMyNTYifQ" + "." + parts[2]
                        
                        response = await client.post(
                            f"{self.base_url}/v1/register",
                            json={},
                            headers={
                                "Authorization": f"Bearer {tampered_token}",
                                "X-Device-Alias": "tampered",
                                "X-Device-Model": "Test",
                                "X-Device-Android-Version": "13"
                            }
                        )
                        
                        if response.status_code == 200:
                            self.record_bug(
                                "CRITICAL",
                                "Tampered JWT token accepted",
                                {}
                            )
                        else:
                            self.log(f"  ✓ Tampered token rejected ({response.status_code})")
    
    async def test_input_validation(self):
        """Test input validation and injection attacks"""
        self.log(f"\n{'='*60}")
        self.log(f"Testing Input Validation")
        self.log(f"{'='*60}")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            # SQL injection payloads
            sql_payloads = [
                "'; DROP TABLE devices; --",
                "1' OR '1'='1",
                "admin'--",
                "1' UNION SELECT NULL, NULL, NULL--"
            ]
            
            # Test SQL injection in various fields
            self.log("Test: SQL injection in device alias...")
            for payload in sql_payloads:
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
                                "X-Device-Alias": payload,
                                "X-Device-Model": "Test",
                                "X-Device-Android-Version": "13"
                            }
                        )
                        
                        # Even if accepted, check if it causes errors
                        if reg_response.status_code == 500:
                            self.record_bug(
                                "HIGH",
                                f"SQL injection caused server error: {payload}",
                                {"payload": payload}
                            )
                except Exception as e:
                    self.record_warning(
                        f"Exception during SQL injection test: {str(e)}",
                        {"payload": payload}
                    )
            
            self.log("  ✓ SQL injection tests completed")
            
            # XSS payloads
            xss_payloads = [
                "<script>alert('XSS')</script>",
                "<img src=x onerror=alert('XSS')>",
                "javascript:alert('XSS')",
                "<svg/onload=alert('XSS')>",
                "'\"><script>alert(String.fromCharCode(88,83,83))</script>"
            ]
            
            self.log("Test: XSS in device alias...")
            for payload in xss_payloads:
                try:
                    response = await client.post(
                        f"{self.base_url}/v1/enroll-tokens",
                        json={"count": 1, "ttl_hours": 1},
                        headers={"X-Admin-Key": self.admin_key}
                    )
                    
                    if response.status_code == 200:
                        token = response.json()["tokens"][0]["token"]
                        
                        await client.post(
                            f"{self.base_url}/v1/register",
                            json={},
                            headers={
                                "Authorization": f"Bearer {token}",
                                "X-Device-Alias": payload,
                                "X-Device-Model": "Test",
                                "X-Device-Android-Version": "13"
                            }
                        )
                except Exception:
                    pass
            
            self.log("  ✓ XSS tests completed (check frontend rendering)")
            
            # Test oversized inputs
            self.log("Test: Oversized inputs...")
            oversized_tests = [
                ("alias", "A" * 10000),
                ("model", "M" * 10000),
                ("build_id", "B" * 10000)
            ]
            
            for field, value in oversized_tests:
                try:
                    response = await client.post(
                        f"{self.base_url}/v1/enroll-tokens",
                        json={"count": 1, "ttl_hours": 1},
                        headers={"X-Admin-Key": self.admin_key}
                    )
                    
                    if response.status_code == 200:
                        token = response.json()["tokens"][0]["token"]
                        
                        headers = {
                            "Authorization": f"Bearer {token}",
                            "X-Device-Alias": value if field == "alias" else "test",
                            "X-Device-Model": value if field == "model" else "test",
                            "X-Device-Android-Version": "13"
                        }
                        
                        reg_response = await client.post(
                            f"{self.base_url}/v1/register",
                            json={},
                            headers=headers
                        )
                        
                        if reg_response.status_code == 200:
                            self.record_warning(
                                f"Oversized {field} accepted (10KB) - potential DoS",
                                {"field": field, "size": len(value)}
                            )
                except Exception:
                    pass
            
            self.log("  ✓ Oversized input tests completed")
    
    async def test_authorization(self):
        """Test authorization and privilege escalation"""
        self.log(f"\n{'='*60}")
        self.log(f"Testing Authorization")
        self.log(f"{'='*60}")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Test: Device trying to access admin endpoints
            self.log("Test: Device token accessing admin endpoints...")
            
            # First create a device
            response = await client.post(
                f"{self.base_url}/v1/enroll-tokens",
                json={"count": 1, "ttl_hours": 1},
                headers={"X-Admin-Key": self.admin_key}
            )
            
            if response.status_code == 200:
                enroll_token = response.json()["tokens"][0]["token"]
                
                # Register device
                reg_response = await client.post(
                    f"{self.base_url}/v1/register",
                    json={},
                    headers={
                        "Authorization": f"Bearer {enroll_token}",
                        "X-Device-Alias": "authz-test",
                        "X-Device-Model": "Test",
                        "X-Device-Android-Version": "13"
                    }
                )
                
                if reg_response.status_code == 200:
                    device_token = reg_response.json()["device_token"]
                    
                    # Try to access admin endpoints with device token
                    admin_endpoints = [
                        ("/admin/devices", "GET"),
                        ("/v1/enroll-tokens", "POST")
                    ]
                    
                    for endpoint, method in admin_endpoints:
                        if method == "GET":
                            authz_response = await client.get(
                                f"{self.base_url}{endpoint}",
                                headers={"Authorization": f"Bearer {device_token}"}
                            )
                        else:
                            authz_response = await client.post(
                                f"{self.base_url}{endpoint}",
                                json={"count": 1, "ttl_hours": 1},
                                headers={"Authorization": f"Bearer {device_token}"}
                            )
                        
                        if authz_response.status_code == 200:
                            self.record_bug(
                                "CRITICAL",
                                f"Device token can access admin endpoint: {endpoint}",
                                {"endpoint": endpoint}
                            )
                        else:
                            self.log(f"  ✓ Device token rejected from {endpoint}")
    
    async def run_all_tests(self):
        """Run all security tests"""
        self.log(f"\n{'#'*60}")
        self.log(f"# Security Bug Bash")
        self.log(f"# Target: {self.base_url}")
        self.log(f"{'#'*60}\n")
        
        await self.test_authentication_bypass()
        await self.test_input_validation()
        await self.test_authorization()
        
        # Summary
        self.log(f"\n{'='*60}")
        self.log(f"SECURITY BUG BASH SUMMARY")
        self.log(f"{'='*60}")
        self.log(f"Critical Bugs: {sum(1 for b in self.bugs_found if b['severity'] == 'CRITICAL')}")
        self.log(f"High Bugs: {sum(1 for b in self.bugs_found if b['severity'] == 'HIGH')}")
        self.log(f"Warnings: {len(self.warnings)}")
        
        if self.bugs_found:
            self.log(f"\nBUGS FOUND:")
            for bug in self.bugs_found:
                self.log(f"  [{bug['severity']}] {bug['description']}")
        
        if self.warnings:
            self.log(f"\nWARNINGS:")
            for warning in self.warnings:
                self.log(f"  {warning['description']}")
        
        # Save report
        report = {
            "timestamp": datetime.now().isoformat(),
            "base_url": self.base_url,
            "bugs_found": self.bugs_found,
            "warnings": self.warnings
        }
        
        report_filename = f"bug_bash_security_{int(time.time())}.json"
        with open(report_filename, 'w') as f:
            json.dump(report, f, indent=2)
        
        self.log(f"\n✓ Report saved to {report_filename}")


async def main():
    parser = argparse.ArgumentParser(description="Security Bug Bash")
    parser.add_argument("--base-url", default="http://localhost:5000", help="Base URL")
    parser.add_argument("--admin-key", default="admin", help="Admin API key")
    
    args = parser.parse_args()
    
    runner = SecurityBugBash(base_url=args.base_url, admin_key=args.admin_key)
    await runner.run_all_tests()


if __name__ == "__main__":
    asyncio.run(main())
