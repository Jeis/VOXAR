"""
VPS Engine Configuration
Environment-based configuration management
"""

import os
from typing import List, Optional
from datetime import datetime
from pydantic_settings import BaseSettings
from pydantic import Field

class Settings(BaseSettings):
    """VPS Engine configuration settings"""
    
    # Environment
    ENVIRONMENT: str = Field(default="development", description="Environment (development/staging/production)")
    DEBUG: bool = Field(default=False, description="Debug mode")
    LOG_LEVEL: str = Field(default="INFO", description="Logging level")
    
    # Server configuration
    HOST: str = Field(default="0.0.0.0", description="Server host")
    PORT: int = Field(default=9000, description="Server port")
    WORKERS: int = Field(default=1, description="Number of worker processes")
    
    # Database configuration
    DATABASE_URL: str = Field(..., description="PostgreSQL database URL")
    DATABASE_POOL_SIZE: int = Field(default=10, description="Database connection pool size")
    DATABASE_MAX_OVERFLOW: int = Field(default=20, description="Database max overflow connections")
    
    # Redis configuration
    REDIS_URL: str = Field(..., description="Redis URL for caching")
    REDIS_MAX_CONNECTIONS: int = Field(default=50, description="Redis max connections")
    REDIS_SOCKET_KEEPALIVE: bool = Field(default=True, description="Redis socket keepalive")
    
    # Object storage (MinIO/S3)
    STORAGE_ENDPOINT: str = Field(default="minio:9000", description="Object storage endpoint")
    STORAGE_ACCESS_KEY: str = Field(..., description="Storage access key")
    STORAGE_SECRET_KEY: str = Field(..., description="Storage secret key")
    STORAGE_BUCKET: str = Field(default="vps-maps", description="Storage bucket name")
    STORAGE_SECURE: bool = Field(default=False, description="Use HTTPS for storage")
    
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
    
    # VPS Engine specific settings
    VPS_FEATURE_CACHE_TTL: int = Field(default=3600, description="Feature cache TTL in seconds")
    VPS_MAX_IMAGE_SIZE: int = Field(default=2048, description="Maximum image dimension")
    VPS_MIN_FEATURE_MATCHES: int = Field(default=50, description="Minimum feature matches required")
    VPS_RANSAC_ITERATIONS: int = Field(default=10000, description="RANSAC iterations")
    VPS_RANSAC_THRESHOLD: float = Field(default=2.0, description="RANSAC threshold in pixels")
    VPS_CONFIDENCE_THRESHOLD: float = Field(default=0.7, description="Minimum confidence threshold")
    
    # Processing limits
    MAX_CONCURRENT_LOCALIZATIONS: int = Field(default=10, description="Max concurrent localizations")
    PROCESSING_TIMEOUT: int = Field(default=30, description="Processing timeout in seconds")
    MAX_UPLOAD_SIZE: int = Field(default=50 * 1024 * 1024, description="Max upload size in bytes")  # 50MB
    
    # Monitoring
    ENABLE_METRICS: bool = Field(default=True, description="Enable Prometheus metrics")
    METRICS_PORT: int = Field(default=9001, description="Metrics server port")
    ENABLE_TRACING: bool = Field(default=False, description="Enable distributed tracing")
    
    # Performance tuning
    FEATURE_DETECTOR: str = Field(default="ORB", description="Feature detector (ORB/SIFT/SURF)")
    MAX_FEATURES: int = Field(default=5000, description="Maximum features to extract")
    MATCHER_TYPE: str = Field(default="BF", description="Feature matcher type (BF/FLANN)")
    MATCHER_DISTANCE_THRESHOLD: float = Field(default=0.7, description="Feature matching distance threshold")
    
    # Map processing
    MAP_PROCESSING_WORKERS: int = Field(default=2, description="Map processing worker threads")
    POINT_CLOUD_DOWNSAMPLE_VOXEL: float = Field(default=0.01, description="Point cloud voxel size for downsampling")
    
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
    
    def get_storage_config(self) -> dict:
        """Get object storage configuration"""
        return {
            "endpoint": self.STORAGE_ENDPOINT,
            "access_key": self.STORAGE_ACCESS_KEY,
            "secret_key": self.STORAGE_SECRET_KEY,
            "secure": self.STORAGE_SECURE,
            "region": "us-east-1"  # Default region
        }
    
    def get_vps_config(self) -> dict:
        """Get VPS engine specific configuration"""
        return {
            "feature_detector": self.FEATURE_DETECTOR,
            "max_features": self.MAX_FEATURES,
            "matcher_type": self.MATCHER_TYPE,
            "matcher_distance_threshold": self.MATCHER_DISTANCE_THRESHOLD,
            "min_feature_matches": self.VPS_MIN_FEATURE_MATCHES,
            "ransac_iterations": self.VPS_RANSAC_ITERATIONS,
            "ransac_threshold": self.VPS_RANSAC_THRESHOLD,
            "confidence_threshold": self.VPS_CONFIDENCE_THRESHOLD,
            "max_image_size": self.VPS_MAX_IMAGE_SIZE,
            "processing_timeout": self.PROCESSING_TIMEOUT,
            "cache_ttl": self.VPS_FEATURE_CACHE_TTL
        }

# Global settings instance
settings = Settings()

# Validate required settings
def validate_settings():
    """Validate required configuration settings"""
    required_vars = [
        "DATABASE_URL",
        "REDIS_URL", 
        "STORAGE_ACCESS_KEY",
        "STORAGE_SECRET_KEY",
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