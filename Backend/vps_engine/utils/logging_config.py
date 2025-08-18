"""
Logging Configuration for VPS Engine
Structured logging with performance monitoring
"""

import logging
import logging.config
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any

from .config import settings

def setup_logging():
    """Setup application logging configuration"""
    
    # Create logs directory
    logs_dir = Path("/app/logs")
    logs_dir.mkdir(exist_ok=True)
    
    # Logging configuration
    config = {
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'detailed': {
                'format': '[%(asctime)s] %(levelname)s [%(name)s:%(lineno)d] %(message)s',
                'datefmt': '%Y-%m-%d %H:%M:%S'
            },
            'simple': {
                'format': '%(levelname)s %(message)s'
            },
            'json': {
                'format': '{"timestamp": "%(asctime)s", "level": "%(levelname)s", "logger": "%(name)s", "message": "%(message)s"}',
                'datefmt': '%Y-%m-%dT%H:%M:%S'
            }
        },
        'handlers': {
            'console': {
                'level': settings.LOG_LEVEL,
                'class': 'logging.StreamHandler',
                'formatter': 'detailed',
                'stream': sys.stdout
            },
            'file': {
                'level': 'INFO',
                'class': 'logging.handlers.RotatingFileHandler',
                'formatter': 'detailed',
                'filename': logs_dir / 'vps_engine.log',
                'maxBytes': 10 * 1024 * 1024,  # 10MB
                'backupCount': 5,
                'encoding': 'utf-8'
            },
            'error_file': {
                'level': 'ERROR',
                'class': 'logging.handlers.RotatingFileHandler',
                'formatter': 'detailed',
                'filename': logs_dir / 'errors.log',
                'maxBytes': 10 * 1024 * 1024,  # 10MB
                'backupCount': 3,
                'encoding': 'utf-8'
            }
        },
        'loggers': {
            '': {  # Root logger
                'level': settings.LOG_LEVEL,
                'handlers': ['console', 'file', 'error_file'],
                'propagate': False
            },
            'uvicorn': {
                'level': 'INFO',
                'handlers': ['console'],
                'propagate': False
            },
            'uvicorn.error': {
                'level': 'INFO',
                'handlers': ['console', 'error_file'],
                'propagate': False
            },
            'uvicorn.access': {
                'level': 'INFO',
                'handlers': ['console'],
                'propagate': False
            }
        }
    }
    
    # Apply configuration
    logging.config.dictConfig(config)
    
    # Set specific loggers to appropriate levels
    logging.getLogger('asyncio').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    
    # Log startup message
    logger = logging.getLogger(__name__)
    logger.info(f"🚀 VPS Engine logging initialized - Level: {settings.LOG_LEVEL}, Environment: {settings.ENVIRONMENT}")

class PerformanceLogger:
    """Performance monitoring logger"""
    
    def __init__(self):
        self.logger = logging.getLogger('performance')
    
    def log_localization(self, success: bool, processing_time: float, 
                        confidence: float = None, feature_matches: int = None,
                        error: str = None):
        """Log localization performance metrics"""
        
        metrics = {
            'operation': 'localization',
            'success': success,
            'processing_time': processing_time,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        if confidence is not None:
            metrics['confidence'] = confidence
        if feature_matches is not None:
            metrics['feature_matches'] = feature_matches
        if error is not None:
            metrics['error'] = error
        
        if success:
            self.logger.info(f"Localization success: {metrics}")
        else:
            self.logger.warning(f"Localization failed: {metrics}")
    
    def log_feature_extraction(self, feature_count: int, extraction_time: float):
        """Log feature extraction performance"""
        
        metrics = {
            'operation': 'feature_extraction',
            'feature_count': feature_count,
            'extraction_time': extraction_time,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        self.logger.info(f"Feature extraction: {metrics}")
    
    def log_map_processing(self, map_id: str, processing_time: float, 
                          point_count: int = None, feature_count: int = None):
        """Log map processing performance"""
        
        metrics = {
            'operation': 'map_processing',
            'map_id': map_id,
            'processing_time': processing_time,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        if point_count is not None:
            metrics['point_count'] = point_count
        if feature_count is not None:
            metrics['feature_count'] = feature_count
        
        self.logger.info(f"Map processing: {metrics}")

# Global performance logger instance
performance_logger = PerformanceLogger()