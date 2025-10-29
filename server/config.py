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
        return os.getenv("JWT_SECRET", "dev-secret-change-in-production")
    
    def get_database_url(self) -> str:
        """Get the database URL from environment"""
        return os.getenv("DATABASE_URL", "sqlite:///./data.db")
    
    def validate(self) -> tuple[bool, list[str]]:
        """
        Validate that required configuration is present.
        
        Returns:
            tuple: (is_valid, list_of_errors)
        """
        errors = []
        
        # Check SERVER_URL is available
        try:
            url = self.server_url
            if not url or url == "http://localhost:5000":
                if self.is_production:
                    errors.append("Production deployment requires REPLIT_DOMAINS or SERVER_URL to be set")
        except Exception as e:
            errors.append(f"Error getting server URL: {str(e)}")
        
        # Check ADMIN_KEY
        if not self.get_admin_key():
            errors.append("ADMIN_KEY environment variable is required")
        
        return (len(errors) == 0, errors)
    
    def print_config_summary(self):
        """Print configuration summary for debugging"""
        print("\n" + "="*60)
        print("NexMDM Configuration")
        print("="*60)
        print(f"Environment: {'Production' if self.is_production else 'Development'}")
        print(f"Server URL: {self.server_url}")
        print(f"Admin Key: {'✓ Set' if self.get_admin_key() else '✗ Missing'}")
        print(f"Database: {self.get_database_url()}")
        
        # Validation
        is_valid, errors = self.validate()
        if is_valid:
            print(f"Status: ✓ All required configuration present")
        else:
            print(f"Status: ✗ Configuration issues detected:")
            for error in errors:
                print(f"  - {error}")
        print("="*60 + "\n")


# Global config instance
config = Config()
