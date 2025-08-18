"""
Metrics collection for Cloud Anchor Service
Simple metrics without external dependencies
"""

import time
import logging
from typing import Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)

class SimpleMetrics:
    """Simple metrics collector for cloud anchor service"""
    
    def __init__(self):
        self.counters = {}
        self.gauges = {}
        self.start_time = time.time()
        
    def increment_counter(self, name: str, value: int = 1):
        """Increment a counter metric"""
        self.counters[name] = self.counters.get(name, 0) + value
        
    def set_gauge(self, name: str, value: float):
        """Set a gauge metric value"""
        self.gauges[name] = value
        
    def get_metrics(self) -> Dict[str, Any]:
        """Get all metrics"""
        return {
            'counters': self.counters,
            'gauges': self.gauges,
            'uptime_seconds': time.time() - self.start_time,
            'timestamp': datetime.utcnow().isoformat()
        }

# Global metrics instance
metrics = SimpleMetrics()

def setup_metrics():
    """Setup metrics collection"""
    logger.info("📊 Cloud Anchor Service metrics initialized")
    return metrics