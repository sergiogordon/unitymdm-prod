"""
Environment configuration for NexMDM server.

Automatically detects whether running in development or production and
configures the server URL accordingly using Replit's environment variables.
"""
import os
from typing import Optional


class Config:
    """Application configuration with automatic environment detection"""
    
    def __init__(self):
        self._server_url: Optional[str] = None
        self._backend_url: Optional[str] = None
        self._is_production: Optional[bool] = None
        
    @property
    def is_production(self) -> bool:
        """Check if running in production deployment"""
        if self._is_production is None:
            self._is_production = os.getenv("REPLIT_DEPLOYMENT") == "1"
        return self._is_production
    
    @property
    def server_url(self) -> str:
        """
        Get the server URL with automatic environment detection.
        
        Priority:
        1. Manual override via SERVER_URL environment variable
        2. Production: Uses REPLIT_DOMAINS (first domain from comma-separated list)
        3. Development: Uses REPLIT_DEV_DOMAIN
        4. Fallback: http://localhost:5000
        
        Returns:
            str: The server URL with https:// prefix (or http:// for localhost)
        """
        if self._server_url is not None:
            return self._server_url
            
        # Check for manual override first
        manual_url = os.getenv("SERVER_URL")
        if manual_url:
            self._server_url = self._normalize_url(manual_url)
            print(f"[CONFIG] Using manual SERVER_URL: {self._server_url}")
            return self._server_url
        
        # Automatic detection based on environment
        if self.is_production:
            # Production: Use REPLIT_DOMAINS
            domains = os.getenv("REPLIT_DOMAINS", "")
            if domains:
                # REPLIT_DOMAINS is comma-separated, take the first one
                domain = domains.split(",")[0].strip()
                self._server_url = self._normalize_url(domain)
                print(f"[CONFIG] Production mode detected, using: {self._server_url}")
            else:
                print("[CONFIG] WARNING: Production mode but no REPLIT_DOMAINS found")
                self._server_url = "http://localhost:5000"
        else:
            # Development: Use REPLIT_DEV_DOMAIN
            dev_domain = os.getenv("REPLIT_DEV_DOMAIN")
            if dev_domain:
                self._server_url = self._normalize_url(dev_domain)
                print(f"[CONFIG] Development mode detected, using: {self._server_url}")
            else:
                print("[CONFIG] WARNING: Development mode but no REPLIT_DEV_DOMAIN found")
                self._server_url = "http://localhost:5000"
        
        return self._server_url
    
    @property
    def backend_url(self) -> str:
        """
        Get the backend URL for direct API access (bypasses Next.js proxy).
        Used for large file downloads to avoid proxy timeout/streaming issues.
        
        Priority:
        1. Manual override via BACKEND_URL environment variable
        2. Production: Same as server_url (backend accessible at same domain)
        3. Development: http://localhost:8000 (default FastAPI port)
        
        Returns:
            str: The backend URL with https:// prefix (or http:// for localhost)
        """
        if self._backend_url is not None:
            return self._backend_url
        
        # Check for manual override first
        manual_backend_url = os.getenv("BACKEND_URL")
        if manual_backend_url:
            self._backend_url = self._normalize_url(manual_backend_url)
            # Force HTTPS in production (Android blocks cleartext HTTP)
            if self.is_production and self._backend_url.startswith("http://"):
                # Replace http:// with https:// for production
                self._backend_url = self._backend_url.replace("http://", "https://", 1)
                print(f"[CONFIG] WARNING: BACKEND_URL was HTTP, forced to HTTPS for production: {self._backend_url}")
            print(f"[CONFIG] Using manual BACKEND_URL: {self._backend_url}")
            return self._backend_url
        
        # If no explicit backend URL, use server_url (backend accessible at same domain)
        # In most deployments, backend and frontend share the same domain
        # For Replit, backend typically runs on the same domain
        server_url = self.server_url
        
        # In development, backend typically runs on localhost:8000
        if not self.is_production:
            # Check if there's a specific backend port configured
            backend_port = os.getenv("BACKEND_PORT", "8000")
            if "localhost" in server_url or "127.0.0.1" in server_url:
                self._backend_url = f"http://localhost:{backend_port}"
            else:
                # Development but with custom domain - assume backend on same domain
                # Ensure HTTPS for non-localhost in development too (Android security)
                if server_url.startswith("http://") and "localhost" not in server_url and "127.0.0.1" not in server_url:
                    self._backend_url = server_url.replace("http://", "https://", 1)
                else:
                    self._backend_url = server_url
        else:
            # Production: backend accessible at same domain as frontend
            # In Replit, backend and frontend typically share the same domain
            # Force HTTPS in production (Android blocks cleartext HTTP)
            if server_url.startswith("http://"):
                self._backend_url = server_url.replace("http://", "https://", 1)
                print(f"[CONFIG] WARNING: server_url was HTTP, backend_url forced to HTTPS: {self._backend_url}")
            else:
                self._backend_url = server_url
        
        return self._backend_url
    
    @staticmethod
    def _normalize_url(url: str) -> str:
        """
        Normalize URL to ensure it has a protocol prefix and no trailing slash.
        
        Args:
            url: URL that may or may not have a protocol
            
        Returns:
            str: URL with https:// prefix (or http:// for localhost), without trailing slash
        """
        url = url.strip()
        
        # Already has protocol
        if url.startswith("http://") or url.startswith("https://"):
            # Strip trailing slash
            return url.rstrip("/")
        
        # Use http for localhost, https for everything else
        if "localhost" in url or url.startswith("127.0.0.1"):
            return f"http://{url}".rstrip("/")
        else:
            return f"https://{url}".rstrip("/")
    
    def get_admin_key(self) -> Optional[str]:
        """Get the admin API key from environment"""
        return os.getenv("ADMIN_KEY")
    
    def get_jwt_secret(self) -> str:
        """Get the JWT secret key from environment"""
        return os.getenv("SESSION_SECRET", "dev-secret-change-in-production")
    
    def get_database_url(self) -> str:
        """Get the database URL from environment"""
        return os.getenv("DATABASE_URL", "sqlite:///./data.db")
    
    def validate(self) -> tuple[bool, list[str], list[str]]:
        """
        Validate that required configuration is present.
        
        Returns:
            tuple: (is_valid, list_of_errors, list_of_warnings)
        """
        errors = []
        warnings = []
        
        # Check SERVER_URL is available
        try:
            url = self.server_url
            if not url or url == "http://localhost:5000":
                if self.is_production:
                    warnings.append("Production deployment using localhost - set REPLIT_DOMAINS or SERVER_URL")
                else:
                    warnings.append("Using default localhost URL - set REPLIT_DEV_DOMAIN for proper development setup")
        except Exception as e:
            warnings.append(f"Error getting server URL (non-critical): {str(e)}")
        
        # Check ADMIN_KEY (required)
        admin_key = self.get_admin_key()
        if not admin_key:
            warnings.append("ADMIN_KEY environment variable not set - using default (insecure)")
        elif len(admin_key) < 16:
            warnings.append("ADMIN_KEY should be at least 16 characters for security")
        elif admin_key == "admin" or admin_key == "changeme":
            warnings.append("ADMIN_KEY using default/insecure value - change for production")
        
        # Check SESSION_SECRET (required for production)
        jwt_secret = self.get_jwt_secret()
        if jwt_secret == "dev-secret-change-in-production":
            if self.is_production:
                warnings.append("SESSION_SECRET using default value - set SESSION_SECRET for production security")
            else:
                warnings.append("Using default SESSION_SECRET - set SESSION_SECRET for production")
        elif len(jwt_secret) < 32:
            warnings.append("SESSION_SECRET should be at least 32 characters for security")
        
        # Check DATABASE_URL
        db_url = self.get_database_url()
        if db_url == "sqlite:///./data.db":
            if self.is_production:
                warnings.append("Using SQLite database - PostgreSQL recommended for production")
        elif "sqlite" in db_url.lower():
            warnings.append("SQLite database detected - PostgreSQL recommended for production scale")
        
        # Check for Firebase credentials (optional but recommended)
        firebase_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")
        if not firebase_json:
            warnings.append("FIREBASE_SERVICE_ACCOUNT_JSON not set - FCM push notifications will not work")
        else:
            # Validate JSON format
            try:
                import json
                json.loads(firebase_json)
            except json.JSONDecodeError:
                errors.append("FIREBASE_SERVICE_ACCOUNT_JSON is not valid JSON")
        
        # Check for optional but recommended services
        if not os.getenv("DISCORD_WEBHOOK_URL"):
            warnings.append("DISCORD_WEBHOOK_URL not set - Discord alerts will not work")
        
        return (len(errors) == 0, errors, warnings)
    
    def print_config_summary(self):
        """Print configuration summary for debugging"""
        print("\n" + "="*60)
        print("NexMDM Configuration")
        print("="*60)
        print(f"Environment: {'Production' if self.is_production else 'Development'}")
        print(f"Server URL: {self.server_url}")
        print(f"Backend URL: {self.backend_url}")
        print(f"Admin Key: {'✓ Set' if self.get_admin_key() else '✗ Missing'}")
        print(f"Database: {self.get_database_url()}")
        
        # Validation
        is_valid, errors, warnings = self.validate()
        if is_valid:
            print(f"Status: ✓ All required configuration present")
            if warnings:
                print(f"Warnings: {len(warnings)} configuration warnings")
        else:
            print(f"Status: ✗ Configuration issues detected:")
            for error in errors:
                print(f"  - {error}")
        print("="*60 + "\n")


# Global config instance
config = Config()
