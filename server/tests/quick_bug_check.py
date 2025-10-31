"""
Quick Bug Check - Comprehensive application health check
"""

import asyncio
import httpx
import json
from datetime import datetime
import os

class BugChecker:
    def __init__(self):
        self.base_url = "http://localhost:8000"
        self.admin_key = os.getenv("ADMIN_KEY", "")
        self.bugs = []
        self.warnings = []
        
    def log(self, msg, level="INFO"):
        print(f"[{level}] {msg}")
        
    def bug(self, severity, description, details=None):
        self.bugs.append({
            "severity": severity,
            "description": description,
            "details": details or {}
        })
        self.log(f"🐛 BUG [{severity}]: {description}", "ERROR")
        
    def warn(self, description, details=None):
        self.warnings.append({
            "description": description,
            "details": details or {}
        })
        self.log(f"⚠️  WARNING: {description}", "WARN")
    
    async def check_health_endpoints(self, client):
        """Check basic health and monitoring endpoints"""
        self.log("\n=== Health & Monitoring Endpoints ===")
        
        # Health check
        try:
            resp = await client.get(f"{self.base_url}/healthz")
            if resp.status_code != 200:
                self.bug("HIGH", f"/healthz returned {resp.status_code}")
            else:
                self.log("✓ /healthz responding")
        except Exception as e:
            self.bug("CRITICAL", f"/healthz failed: {e}")
        
        # Readiness check
        try:
            resp = await client.get(f"{self.base_url}/readyz")
            if resp.status_code not in [200, 503]:
                self.bug("HIGH", f"/readyz returned unexpected {resp.status_code}")
            else:
                data = resp.json()
                if not data.get("ready"):
                    self.warn(f"System not ready: {data.get('errors')}")
                else:
                    self.log("✓ /readyz - system ready")
        except Exception as e:
            self.bug("CRITICAL", f"/readyz failed: {e}")
        
        # Metrics endpoint (requires admin key)
        try:
            resp = await client.get(
                f"{self.base_url}/metrics",
                headers={"X-Admin": self.admin_key}
            )
            if resp.status_code != 200:
                self.bug("MEDIUM", f"/metrics returned {resp.status_code}")
            else:
                self.log("✓ /metrics accessible")
        except Exception as e:
            self.warn(f"/metrics check failed: {e}")
    
    async def check_auth_endpoints(self, client):
        """Check authentication endpoints"""
        self.log("\n=== Authentication Endpoints ===")
        
        # Test signup
        test_user = f"testuser_{int(datetime.now().timestamp())}"
        try:
            resp = await client.post(
                f"{self.base_url}/api/auth/signup",
                json={
                    "username": test_user,
                    "password": "testpass123",
                    "email": f"{test_user}@test.com"
                }
            )
            
            if resp.status_code == 200:
                self.log("✓ User signup works")
                data = resp.json()
                if "access_token" not in data:
                    self.bug("HIGH", "Signup doesn't return access_token")
                else:
                    token = data["access_token"]
                    
                    # Test authenticated endpoint
                    resp2 = await client.get(
                        f"{self.base_url}/api/auth/user",
                        headers={"Authorization": f"Bearer {token}"}
                    )
                    
                    if resp2.status_code == 200:
                        self.log("✓ JWT authentication works")
                    else:
                        self.bug("HIGH", f"JWT auth failed: {resp2.status_code}")
            else:
                self.bug("MEDIUM", f"Signup failed: {resp.status_code} - {resp.text}")
        except Exception as e:
            self.bug("HIGH", f"Auth signup error: {e}")
        
        # Test login with invalid credentials
        try:
            resp = await client.post(
                f"{self.base_url}/api/auth/login",
                json={"username": "invalid", "password": "invalid"}
            )
            
            if resp.status_code == 200:
                self.bug("CRITICAL", "Invalid credentials accepted!")
            elif resp.status_code == 401:
                self.log("✓ Invalid credentials rejected")
            else:
                self.warn(f"Unexpected login response: {resp.status_code}")
        except Exception as e:
            self.warn(f"Login test error: {e}")
    
    async def check_device_endpoints(self, client):
        """Check device management endpoints"""
        self.log("\n=== Device Management Endpoints ===")
        
        # Register a test device
        try:
            resp = await client.post(
                f"{self.base_url}/v1/register",
                json={"alias": "test-device-bug-check"},
                headers={"X-Admin-Key": self.admin_key}
            )
            
            if resp.status_code == 200:
                self.log("✓ Device registration works")
                data = resp.json()
                
                if "device_token" not in data:
                    self.bug("CRITICAL", "Device registration doesn't return token")
                    return
                
                device_token = data["device_token"]
                device_id = data.get("device_id")
                
                # Test heartbeat
                resp2 = await client.post(
                    f"{self.base_url}/v1/heartbeat",
                    json={
                        "battery": {
                            "pct": 85,
                            "charging": False,
                            "temperature_c": 30
                        },
                        "app_versions": {},
                        "metadata": {}
                    },
                    headers={"Authorization": f"Bearer {device_token}"}
                )
                
                if resp2.status_code == 200:
                    self.log("✓ Heartbeat processing works")
                else:
                    self.bug("HIGH", f"Heartbeat failed: {resp2.status_code}")
                
            elif resp.status_code == 401:
                self.warn("Admin key not configured or invalid")
            else:
                self.bug("HIGH", f"Device registration failed: {resp.status_code}")
        except Exception as e:
            self.bug("HIGH", f"Device endpoints error: {e}")
    
    async def check_input_validation(self, client):
        """Check input validation and edge cases"""
        self.log("\n=== Input Validation ===")
        
        # Test malformed JSON
        try:
            resp = await client.post(
                f"{self.base_url}/v1/heartbeat",
                content=b"{invalid json}",
                headers={"Content-Type": "application/json"}
            )
            
            if resp.status_code in [400, 422]:
                self.log("✓ Malformed JSON rejected")
            elif resp.status_code == 401:
                self.log("✓ Auth check before JSON parsing")
            else:
                self.warn(f"Unexpected malformed JSON response: {resp.status_code}")
        except Exception as e:
            self.warn(f"Malformed JSON test error: {e}")
        
        # Test SQL injection attempts
        try:
            resp = await client.post(
                f"{self.base_url}/api/auth/login",
                json={
                    "username": "admin' OR '1'='1",
                    "password": "anything"
                }
            )
            
            if resp.status_code == 200:
                self.bug("CRITICAL", "SQL injection vulnerability detected!")
            else:
                self.log("✓ SQL injection attempt blocked")
        except Exception as e:
            self.warn(f"SQL injection test error: {e}")
    
    async def check_cors_and_security_headers(self, client):
        """Check CORS and security headers"""
        self.log("\n=== Security Headers ===")
        
        try:
            resp = await client.get(f"{self.base_url}/healthz")
            headers = resp.headers
            
            # Check for CORS headers
            if "access-control-allow-origin" in headers:
                origin = headers["access-control-allow-origin"]
                if origin == "*":
                    self.warn("CORS allows all origins (*)")
                else:
                    self.log(f"✓ CORS configured: {origin}")
            
            # Check for security headers
            security_headers = [
                "x-content-type-options",
                "x-frame-options",
                "strict-transport-security"
            ]
            
            missing_headers = []
            for header in security_headers:
                if header not in headers:
                    missing_headers.append(header)
            
            if missing_headers:
                self.warn(f"Missing security headers: {', '.join(missing_headers)}")
            else:
                self.log("✓ Security headers present")
                
        except Exception as e:
            self.warn(f"Security headers check error: {e}")
    
    async def check_rate_limiting(self, client):
        """Check rate limiting"""
        self.log("\n=== Rate Limiting ===")
        
        # Try rapid registration attempts
        try:
            rate_limited = False
            for i in range(10):
                resp = await client.post(
                    f"{self.base_url}/api/auth/signup",
                    json={
                        "username": f"spam{i}",
                        "password": "test123",
                        "email": f"spam{i}@test.com"
                    }
                )
                
                if resp.status_code == 429:
                    rate_limited = True
                    self.log(f"✓ Rate limiting active (hit at request {i+1})")
                    break
            
            if not rate_limited:
                self.warn("No rate limiting detected for signup endpoint")
        except Exception as e:
            self.warn(f"Rate limiting test error: {e}")
    
    async def run_all_checks(self):
        """Run all bug checks"""
        self.log("=" * 60)
        self.log("COMPREHENSIVE BUG CHECK")
        self.log(f"Target: {self.base_url}")
        self.log(f"Time: {datetime.now()}")
        self.log("=" * 60)
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            await self.check_health_endpoints(client)
            await self.check_auth_endpoints(client)
            await self.check_device_endpoints(client)
            await self.check_input_validation(client)
            await self.check_cors_and_security_headers(client)
            await self.check_rate_limiting(client)
        
        # Summary
        self.log("\n" + "=" * 60)
        self.log("SUMMARY")
        self.log("=" * 60)
        self.log(f"Bugs Found: {len(self.bugs)}")
        self.log(f"Warnings: {len(self.warnings)}")
        
        if self.bugs:
            self.log("\n🐛 BUGS DETECTED:")
            for bug in self.bugs:
                self.log(f"  [{bug['severity']}] {bug['description']}")
        
        if self.warnings:
            self.log("\n⚠️  WARNINGS:")
            for warning in self.warnings:
                self.log(f"  {warning['description']}")
        
        if not self.bugs and not self.warnings:
            self.log("\n✅ NO BUGS OR WARNINGS FOUND!")
        
        # Save report
        report = {
            "timestamp": datetime.now().isoformat(),
            "bugs": self.bugs,
            "warnings": self.warnings,
            "summary": {
                "total_bugs": len(self.bugs),
                "total_warnings": len(self.warnings)
            }
        }
        
        filename = f"bug_report_{int(datetime.now().timestamp())}.json"
        with open(filename, "w") as f:
            json.dump(report, f, indent=2)
        
        self.log(f"\n✓ Report saved to {filename}")
        
        return len(self.bugs)

if __name__ == "__main__":
    checker = BugChecker()
    exit_code = asyncio.run(checker.run_all_checks())
    exit(exit_code)
