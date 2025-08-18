"""
Metrics collection and monitoring for VPS Engine
Prometheus metrics integration
"""

import time
import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import defaultdict, deque

logger = logging.getLogger(__name__)

@dataclass
class MetricSample:
    """Individual metric sample"""
    value: float
    timestamp: datetime
    labels: Dict[str, str] = field(default_factory=dict)

class VPSMetrics:
    """VPS Engine metrics collector"""
    
    def __init__(self):
        self.metrics = defaultdict(list)
        self.counters = defaultdict(int)
        self.histograms = defaultdict(lambda: deque(maxlen=1000))
        self.gauges = defaultdict(float)
        
        # Track window (last 24 hours)
        self.window_hours = 24
        self.cleanup_interval = 3600  # 1 hour
        self.last_cleanup = time.time()
        
        # Performance tracking
        self.localization_times = deque(maxlen=1000)
        self.localization_successes = 0
        self.localization_failures = 0
        self.feature_extraction_times = deque(maxlen=1000)
        
        logger.info("📊 VPS Metrics initialized")

    def record_localization(self, success: bool, processing_time: float,
                           confidence: Optional[float] = None,
                           feature_matches: Optional[int] = None,
                           error: Optional[str] = None):
        """Record localization attempt metrics"""
        
        timestamp = datetime.utcnow()
        
        # Update counters
        if success:
            self.counters['localization_success_total'] += 1
            self.localization_successes += 1
        else:
            self.counters['localization_failure_total'] += 1
            self.localization_failures += 1
        
        # Record processing time
        self.localization_times.append(processing_time)
        self.histograms['localization_processing_time'].append(
            MetricSample(processing_time, timestamp)
        )
        
        # Record confidence if available
        if confidence is not None:
            self.histograms['localization_confidence'].append(
                MetricSample(confidence, timestamp)
            )
        
        # Record feature matches if available
        if feature_matches is not None:
            self.histograms['localization_feature_matches'].append(
                MetricSample(feature_matches, timestamp)
            )
        
        # Update gauges
        self._update_success_rate()
        self._update_average_processing_time()
        
        # Cleanup old metrics periodically
        self._cleanup_old_metrics()

    def record_feature_extraction(self, feature_count: int, extraction_time: float):
        """Record feature extraction metrics"""
        
        timestamp = datetime.utcnow()
        
        self.counters['feature_extraction_total'] += 1
        self.feature_extraction_times.append(extraction_time)
        
        self.histograms['feature_extraction_time'].append(
            MetricSample(extraction_time, timestamp)
        )
        
        self.histograms['feature_count'].append(
            MetricSample(feature_count, timestamp)
        )

    def record_map_operation(self, operation: str, map_id: str, duration: float):
        """Record map-related operations"""
        
        timestamp = datetime.utcnow()
        
        self.counters[f'map_{operation}_total'] += 1
        self.histograms[f'map_{operation}_duration'].append(
            MetricSample(duration, timestamp, {'map_id': map_id})
        )

    def set_gauge(self, name: str, value: float, labels: Optional[Dict[str, str]] = None):
        """Set gauge value"""
        key = name
        if labels:
            key = f"{name}_{hash(frozenset(labels.items()))}"
        self.gauges[key] = value

    def increment_counter(self, name: str, value: int = 1, labels: Optional[Dict[str, str]] = None):
        """Increment counter"""
        key = name
        if labels:
            key = f"{name}_{hash(frozenset(labels.items()))}"
        self.counters[key] += value

    def _update_success_rate(self):
        """Update overall success rate gauge"""
        total = self.localization_successes + self.localization_failures
        if total > 0:
            success_rate = self.localization_successes / total
            self.gauges['localization_success_rate'] = success_rate

    def _update_average_processing_time(self):
        """Update average processing time gauge"""
        if self.localization_times:
            avg_time = sum(self.localization_times) / len(self.localization_times)
            self.gauges['localization_avg_processing_time'] = avg_time

    def _cleanup_old_metrics(self):
        """Remove metrics older than window"""
        
        current_time = time.time()
        if current_time - self.last_cleanup < self.cleanup_interval:
            return
        
        cutoff_time = datetime.utcnow() - timedelta(hours=self.window_hours)
        
        # Clean up histograms
        for metric_name, samples in self.histograms.items():
            # Remove old samples
            while samples and samples[0].timestamp < cutoff_time:
                samples.popleft()
        
        self.last_cleanup = current_time
        logger.debug("🧹 Cleaned up old metrics")

    def get_metrics(self) -> Dict[str, Any]:
        """Get all current metrics"""
        
        self._cleanup_old_metrics()
        
        # Calculate statistics
        localization_stats = self._calculate_histogram_stats('localization_processing_time')
        confidence_stats = self._calculate_histogram_stats('localization_confidence')
        feature_stats = self._calculate_histogram_stats('feature_count')
        
        return {
            'timestamp': datetime.utcnow().isoformat(),
            'counters': dict(self.counters),
            'gauges': dict(self.gauges),
            'statistics': {
                'localization_processing_time': localization_stats,
                'localization_confidence': confidence_stats,
                'feature_extraction': feature_stats,
            },
            'recent_performance': {
                'total_localizations': self.localization_successes + self.localization_failures,
                'success_rate': self.gauges.get('localization_success_rate', 0.0),
                'avg_processing_time': self.gauges.get('localization_avg_processing_time', 0.0),
                'window_hours': self.window_hours
            }
        }

    def _calculate_histogram_stats(self, metric_name: str) -> Dict[str, float]:
        """Calculate statistics for histogram data"""
        
        samples = self.histograms.get(metric_name, [])
        if not samples:
            return {'count': 0}
        
        values = [sample.value for sample in samples]
        values.sort()
        
        count = len(values)
        total = sum(values)
        avg = total / count if count > 0 else 0
        
        stats = {
            'count': count,
            'sum': total,
            'avg': avg,
            'min': min(values) if values else 0,
            'max': max(values) if values else 0
        }
        
        # Calculate percentiles
        if count > 0:
            stats['p50'] = values[int(count * 0.5)]
            stats['p90'] = values[int(count * 0.9)] if count >= 10 else values[-1]
            stats['p95'] = values[int(count * 0.95)] if count >= 20 else values[-1]
            stats['p99'] = values[int(count * 0.99)] if count >= 100 else values[-1]
        
        return stats

    def get_prometheus_metrics(self) -> str:
        """Export metrics in Prometheus format"""
        
        lines = []
        
        # Counters
        for name, value in self.counters.items():
            lines.append(f"# TYPE vps_{name} counter")
            lines.append(f"vps_{name} {value}")
        
        # Gauges
        for name, value in self.gauges.items():
            lines.append(f"# TYPE vps_{name} gauge")
            lines.append(f"vps_{name} {value}")
        
        # Histograms (simplified)
        for metric_name, samples in self.histograms.items():
            if not samples:
                continue
            
            values = [sample.value for sample in samples]
            stats = self._calculate_histogram_stats(metric_name)
            
            lines.append(f"# TYPE vps_{metric_name}_histogram histogram")
            lines.append(f"vps_{metric_name}_histogram_count {stats['count']}")
            lines.append(f"vps_{metric_name}_histogram_sum {stats['sum']}")
            
            # Buckets (predefined)
            buckets = [0.1, 0.5, 1.0, 2.0, 5.0, 10.0, float('inf')]
            bucket_counts = []
            
            for bucket in buckets:
                count = sum(1 for v in values if v <= bucket)
                bucket_counts.append(count)
                bucket_label = bucket if bucket != float('inf') else '+Inf'
                lines.append(f'vps_{metric_name}_histogram_bucket{{le="{bucket_label}"}} {count}')
        
        return '\n'.join(lines) + '\n'

    def reset_metrics(self):
        """Reset all metrics (for testing)"""
        self.metrics.clear()
        self.counters.clear()
        self.histograms.clear()
        self.gauges.clear()
        self.localization_times.clear()
        self.feature_extraction_times.clear()
        self.localization_successes = 0
        self.localization_failures = 0
        
        logger.info("🔄 Metrics reset")

# Global metrics instance
def setup_metrics() -> VPSMetrics:
    """Setup and return global metrics instance"""
    return VPSMetrics()

# Metrics decorator
def track_processing_time(metric_name: str):
    """Decorator to track function processing time"""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                processing_time = time.time() - start_time
                
                # Find metrics instance in args (VPS engine typically)
                for arg in args:
                    if hasattr(arg, 'metrics'):
                        arg.metrics.histograms[f'{metric_name}_processing_time'].append(
                            MetricSample(processing_time, datetime.utcnow())
                        )
                        break
                
                return result
            except Exception as e:
                processing_time = time.time() - start_time
                # Still record the time even on failure
                for arg in args:
                    if hasattr(arg, 'metrics'):
                        arg.metrics.increment_counter(f'{metric_name}_error_total')
                        break
                raise
        return wrapper
    return decorator