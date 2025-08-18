"""
VOXAR Enterprise Observability - Performance Monitor
Real-time performance monitoring and alerting for AR operations
"""

import time
import logging
from typing import Dict, Optional
from dataclasses import dataclass, field

from core.service_types import PerformanceTier

logger = logging.getLogger(__name__)

@dataclass
class PerformanceMetrics:
    """Performance tracking metrics"""
    operation_name: str
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    duration_ms: Optional[float] = None
    target_duration_ms: int = 16
    sla_met: Optional[bool] = None
    
    def complete(self) -> 'PerformanceMetrics':
        """Mark operation as complete and calculate metrics"""
        self.end_time = time.time()
        self.duration_ms = (self.end_time - self.start_time) * 1000
        self.sla_met = self.duration_ms <= self.target_duration_ms
        return self

class PerformanceMonitor:
    """Real-time performance monitoring for AR operations"""
    
    def __init__(self, performance_tier: PerformanceTier):
        self.performance_tier = performance_tier
        self.active_operations: Dict[str, PerformanceMetrics] = {}
        self.performance_history: Dict[str, list] = {}
        
        # Set default targets based on performance tier
        self.default_targets = {
            PerformanceTier.CRITICAL_60FPS: 16,      # <16ms for 60fps
            PerformanceTier.HIGH_PERFORMANCE: 100,   # <100ms
            PerformanceTier.STANDARD: 500,           # <500ms
            PerformanceTier.BACKGROUND: 5000         # <5s
        }
    
    def start_operation(
        self, 
        operation_id: str, 
        operation_name: str,
        target_duration_ms: Optional[int] = None
    ) -> PerformanceMetrics:
        """Start tracking a performance-critical operation"""
        
        target = target_duration_ms or self.default_targets.get(
            self.performance_tier, 
            self.default_targets[PerformanceTier.STANDARD]
        )
        
        metrics = PerformanceMetrics(
            operation_name=operation_name,
            target_duration_ms=target
        )
        
        self.active_operations[operation_id] = metrics
        logger.debug(f"Started tracking operation: {operation_name} (target: {target}ms)")
        
        return metrics
    
    def complete_operation(self, operation_id: str) -> Optional[PerformanceMetrics]:
        """Complete tracking an operation and return metrics"""
        
        metrics = self.active_operations.pop(operation_id, None)
        if not metrics:
            logger.warning(f"Attempted to complete unknown operation: {operation_id}")
            return None
        
        metrics.complete()
        
        # Store in history for trend analysis
        if metrics.operation_name not in self.performance_history:
            self.performance_history[metrics.operation_name] = []
        
        self.performance_history[metrics.operation_name].append({
            'duration_ms': metrics.duration_ms,
            'sla_met': metrics.sla_met,
            'timestamp': metrics.end_time
        })
        
        # Keep only last 100 measurements
        if len(self.performance_history[metrics.operation_name]) > 100:
            self.performance_history[metrics.operation_name] = \
                self.performance_history[metrics.operation_name][-100:]
        
        # Log SLA violations for critical operations
        if not metrics.sla_met:
            logger.warning(
                f"SLA violation: {metrics.operation_name} took {metrics.duration_ms:.2f}ms "
                f"(target: {metrics.target_duration_ms}ms)"
            )
        
        return metrics
    
    def get_operation_stats(self, operation_name: str) -> Optional[Dict]:
        """Get performance statistics for an operation"""
        
        history = self.performance_history.get(operation_name, [])
        if not history:
            return None
        
        durations = [h['duration_ms'] for h in history]
        sla_violations = sum(1 for h in history if not h['sla_met'])
        
        return {
            'operation_name': operation_name,
            'total_operations': len(history),
            'avg_duration_ms': sum(durations) / len(durations),
            'min_duration_ms': min(durations),
            'max_duration_ms': max(durations),
            'sla_compliance_rate': (len(history) - sla_violations) / len(history),
            'total_sla_violations': sla_violations
        }