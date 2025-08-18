"""
Cloud Anchor Service Configuration
Environment-based configuration management
"""

import os
from typing import List, Optional
from datetime import datetime
from pydantic_settings import BaseSettings
from pydantic import Field

class Settings(BaseSettings):
    """Cloud Anchor Service configuration settings"""
    
    # Environment
    ENVIRONMENT: str = Field(default="development", description="Environment (development/staging/production)")
    DEBUG: bool = Field(default=False, description="Debug mode")
    LOG_LEVEL: str = Field(default="INFO", description="Logging level")
    
    # Server configuration
    HOST: str = Field(default="0.0.0.0", description="Server host")
    PORT: int = Field(default=9001, description="Server port")
    WORKERS: int = Field(default=1, description="Number of worker processes")
    
    # Database configuration
    DATABASE_URL: str = Field(..., description="PostgreSQL database URL")
    DATABASE_POOL_SIZE: int = Field(default=10, description="Database connection pool size")
    DATABASE_MAX_OVERFLOW: int = Field(default=20, description="Database max overflow connections")
    
    # Redis configuration (for caching and sessions)
    REDIS_URL: str = Field(..., description="Redis URL for caching")
    REDIS_MAX_CONNECTIONS: int = Field(default=50, description="Redis max connections")
    REDIS_SOCKET_KEEPALIVE: bool = Field(default=True, description="Redis socket keepalive")
    
    # Security
    JWT_SECRET: str = Field(..., description="JWT secret key")
    JWT_ALGORITHM: str = Field(default="HS256", description="JWT algorithm")
    JWT_EXPIRATION: int = Field(default=3600, description="JWT expiration in seconds")
    API_KEY_HEADER: str = Field(default="X-API-Key", description="API key header name")
    
    # CORS configuration
    CORS_ORIGINS: List[str] = Field(
        default=["http://localhost:3000", "http://localhost:8080"],
        description="Allowed CORS origins"
    )
    
    # Anchor service specific settings
    MAX_ANCHORS_PER_SESSION: int = Field(default=100, description="Maximum anchors per session")
    DEFAULT_ANCHOR_LIFETIME_HOURS: int = Field(default=24, description="Default anchor lifetime in hours")
    ANCHOR_CLEANUP_INTERVAL: int = Field(default=300, description="Anchor cleanup interval in seconds")
    SPATIAL_INDEX_RESOLUTION: float = Field(default=1.0, description="Spatial index resolution in meters")
    MIN_CONFIDENCE_THRESHOLD: float = Field(default=0.5, description="Minimum confidence threshold")
    
    # WebSocket settings
    WS_HEARTBEAT_INTERVAL: int = Field(default=30, description="WebSocket heartbeat interval in seconds")
    WS_CLIENT_TIMEOUT: int = Field(default=90, description="WebSocket client timeout in seconds")
    MAX_CLIENTS_PER_SESSION: int = Field(default=50, description="Maximum WebSocket clients per session")
    SYNC_BATCH_SIZE: int = Field(default=100, description="Synchronization batch size")
    
    # Performance settings
    MAX_QUERY_RADIUS: float = Field(default=1000.0, description="Maximum query radius in meters")
    MAX_QUERY_RESULTS: int = Field(default=1000, description="Maximum query results")
    ENABLE_METRICS: bool = Field(default=True, description="Enable Prometheus metrics")
    
    class Config:
        env_file = ".env"
        case_sensitive = True
    
    @property
    def is_development(self) -> bool:
        """Check if running in development mode"""
        return self.ENVIRONMENT.lower() == "development"
    
    @property
    def is_production(self) -> bool:
        """Check if running in production mode"""
        return self.ENVIRONMENT.lower() == "production"
    
    def get_timestamp(self) -> str:
        """Get current timestamp in ISO format"""
        return datetime.utcnow().isoformat()
    
    def get_database_config(self) -> dict:
        """Get database configuration for SQLAlchemy"""
        return {
            "pool_size": self.DATABASE_POOL_SIZE,
            "max_overflow": self.DATABASE_MAX_OVERFLOW,
            "pool_pre_ping": True,
            "pool_recycle": 3600,  # 1 hour
            "echo": self.is_development and self.DEBUG
        }
    
    def get_redis_config(self) -> dict:
        """Get Redis configuration"""
        return {
            "max_connections": self.REDIS_MAX_CONNECTIONS,
            "socket_keepalive": self.REDIS_SOCKET_KEEPALIVE,
            "socket_keepalive_options": {},
            "health_check_interval": 30
        }

# Global settings instance
settings = Settings()

# Validate required settings
def validate_settings():
    """Validate required configuration settings"""
    required_vars = [
        "DATABASE_URL",
        "REDIS_URL",
        "JWT_SECRET"
    ]
    
    missing_vars = []
    for var in required_vars:
        if not getattr(settings, var, None):
            missing_vars.append(var)
    
    if missing_vars:
        raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")

# Development settings override
def apply_development_overrides():
    """Apply development-specific settings"""
    if settings.is_development:
        # Enable debug features
        settings.DEBUG = True
        settings.LOG_LEVEL = "DEBUG"
        
        # Relaxed security for development
        if not settings.JWT_SECRET or settings.JWT_SECRET == "your_super_secure_jwt_secret_key_here_32_chars_min":
            settings.JWT_SECRET = "dev_jwt_secret_key_change_in_production_this_is_not_secure"
        
        # Development CORS
        settings.CORS_ORIGINS.extend([
            "http://localhost:3000",
            "http://localhost:8080", 
            "http://localhost:8081",
            "http://127.0.0.1:3000"
        ])

# Initialize settings
if settings.is_development:
    apply_development_overrides()

# Validate settings on import
try:
    validate_settings()
except ValueError as e:
    if not settings.is_development:
        raise e
    else:
        print(f"⚠️  Development mode: {e}")

# Export settings
__all__ = ["settings", "Settings", "validate_settings"]