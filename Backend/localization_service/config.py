"""
Configuration management
Environment-based settings
"""

import os
from typing import Optional
from pydantic import BaseSettings


class Settings(BaseSettings):
    """Application settings from environment"""
    
    # Service configuration
    service_host: str = "0.0.0.0"
    service_port: int = 8080
    debug_mode: bool = False
    
    # Logging
    log_level: str = "INFO"
    
    # SLAM configuration
    slam_maps_directory: str = "/app/maps"
    slam_vocab_path: str = "/app/vocab/orb_vocab.dbow2"
    
    # VIO configuration
    vio_imu_frequency: float = 100.0  # Hz
    vio_camera_frequency: float = 30.0  # Hz
    
    # Performance settings
    max_concurrent_tracking: int = 10
    pose_history_size: int = 30
    
    # External services
    nakama_host: Optional[str] = None
    nakama_port: int = 7350
    redis_host: str = "localhost"
    redis_port: int = 6379
    
    class Config:
        env_file = ".env"
        env_prefix = "LOCALIZATION_"


# Global settings instance
_settings = None

def get_settings() -> Settings:
    """Get application settings (singleton)"""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings