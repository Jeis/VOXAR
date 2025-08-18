"""
Metrics collection for spatial mapping
"""

import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


class MetricsCollector:
    """Collect and track metrics for mapping operations"""
    
    def __init__(self):
        self.metrics = {}
        logger.info("MetricsCollector initialized")
    
    def record_stage_transition(self, stage: str) -> None:
        """Record a stage transition"""
        logger.info(f"Stage transition recorded: {stage}")
        self.metrics[f"stage_{stage}"] = self.metrics.get(f"stage_{stage}", 0) + 1
    
    def record_metric(self, name: str, value: Any) -> None:
        """Record a metric value"""
        self.metrics[name] = value
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get all collected metrics"""
        return self.metrics.copy()