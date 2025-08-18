"""
Logging Configuration for Cloud Anchor Service
Structured logging with performance monitoring
"""

import logging
import logging.config
import sys
from pathlib import Path
from datetime import datetime

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
                'filename': logs_dir / 'cloud_anchor_service.log',
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
    logger.info(f"🚀 Cloud Anchor Service logging initialized - Level: {settings.LOG_LEVEL}, Environment: {settings.ENVIRONMENT}")