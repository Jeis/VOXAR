"""
VOXAR API Gateway - Route Performance Monitor
Enterprise-grade route monitoring with real-time performance tracking
"""

import time
import logging
from typing import Dict, List, Optional, Any
from collections import defaultdict, deque
import statistics

logger = logging.getLogger(__name__)

class RoutePerformanceMonitor:
    """Enterprise route performance monitoring with intelligent analytics"""
    
    def __init__(self, max_samples: int = 1000):
        self.max_samples = max_samples
        
        # Performance tracking per route
        self.route_metrics: Dict[str, Dict[str, deque]] = defaultdict(
            lambda: {
                'response_times': deque(maxlen=max_samples),
                'status_codes': deque(maxlen=max_samples),
                'timestamps': deque(maxlen=max_samples),
                'error_count': 0,
                'total_requests': 0
            }
        )
        
        # Real-time performance thresholds
        self.performance_thresholds = {
            'localization': 100.0,  # ms - AR localization must be <100ms
            'mapping': 2000.0,      # ms - 3D mapping can be slower
            'multiplayer': 50.0,    # ms - Real-time multiplayer needs <50ms
            'auth': 200.0,          # ms - Authentication reasonable
            'default': 500.0        # ms - General API calls
        }
        
        # Performance degradation detection
        self.degradation_window = 50  # Last N requests to analyze
        
        logger.info("✅ Route Performance Monitor initialized")
    
    def record_route_performance(self, route_name: str, response_time_ms: float, 
                                status_code: int, timestamp: float = None):
        """Record route performance with intelligent analysis"""
        
        if timestamp is None:
            timestamp = time.time()
        
        metrics = self.route_metrics[route_name]
        
        # Record metrics
        metrics['response_times'].append(response_time_ms)
        metrics['status_codes'].append(status_code)
        metrics['timestamps'].append(timestamp)
        metrics['total_requests'] += 1
        
        # Track errors
        if status_code >= 400:
            metrics['error_count'] += 1
        
        # Check for performance degradation
        self._check_performance_degradation(route_name, response_time_ms)
        
        # Log slow requests for AR-critical routes
        threshold = self._get_route_threshold(route_name)
        if response_time_ms > threshold:
            logger.warning(f"Slow route {route_name}: {response_time_ms:.1f}ms "
                          f"(threshold: {threshold}ms)")
    
    def _get_route_threshold(self, route_name: str) -> float:
        """Get performance threshold for specific route type"""
        
        route_lower = route_name.lower()
        
        if 'localiz' in route_lower or 'pose' in route_lower:
            return self.performance_thresholds['localization']
        elif 'map' in route_lower or 'reconstruct' in route_lower:
            return self.performance_thresholds['mapping']
        elif 'multiplayer' in route_lower or 'sync' in route_lower:
            return self.performance_thresholds['multiplayer']
        elif 'auth' in route_lower or 'login' in route_lower:
            return self.performance_thresholds['auth']
        else:
            return self.performance_thresholds['default']
    
    def _check_performance_degradation(self, route_name: str, current_time: float):
        """Check for performance degradation using statistical analysis"""
        
        metrics = self.route_metrics[route_name]
        response_times = list(metrics['response_times'])
        
        if len(response_times) < self.degradation_window:
            return
        
        # Get recent performance vs historical baseline
        recent_times = response_times[-self.degradation_window//2:]
        baseline_times = response_times[-self.degradation_window:-self.degradation_window//2]
        
        if len(baseline_times) < 10:  # Need minimum samples
            return
        
        try:
            recent_avg = statistics.mean(recent_times)
            baseline_avg = statistics.mean(baseline_times)
            
            # Alert if performance degraded by >50%
            if recent_avg > baseline_avg * 1.5:
                logger.warning(f"Performance degradation detected for {route_name}: "
                              f"recent {recent_avg:.1f}ms vs baseline {baseline_avg:.1f}ms")
                
        except statistics.StatisticsError:
            pass  # Not enough data points
    
    def get_route_summary(self, route_name: str) -> Dict[str, Any]:
        """Get comprehensive route performance summary"""
        
        if route_name not in self.route_metrics:
            return {}
        
        metrics = self.route_metrics[route_name]
        response_times = list(metrics['response_times'])
        status_codes = list(metrics['status_codes'])
        
        if not response_times:
            return {'route': route_name, 'total_requests': 0}
        
        try:
            # Calculate statistics
            avg_response_time = statistics.mean(response_times)
            median_response_time = statistics.median(response_times)
            p95_response_time = statistics.quantiles(response_times, n=20)[18]  # 95th percentile
            
            # Error rate
            error_rate = metrics['error_count'] / metrics['total_requests']
            
            # Recent performance (last 100 requests)
            recent_times = response_times[-100:] if len(response_times) >= 100 else response_times
            recent_avg = statistics.mean(recent_times)
            
            # Health status
            threshold = self._get_route_threshold(route_name)
            is_healthy = avg_response_time < threshold and error_rate < 0.05
            
            return {
                'route': route_name,
                'total_requests': metrics['total_requests'],
                'error_count': metrics['error_count'],
                'error_rate': error_rate,
                'avg_response_time_ms': avg_response_time,
                'median_response_time_ms': median_response_time,
                'p95_response_time_ms': p95_response_time,
                'recent_avg_response_time_ms': recent_avg,
                'threshold_ms': threshold,
                'is_healthy': is_healthy,
                'performance_score': self._calculate_performance_score(
                    avg_response_time, threshold, error_rate
                )
            }
            
        except statistics.StatisticsError:
            return {
                'route': route_name,
                'total_requests': metrics['total_requests'],
                'error': 'Insufficient data for statistics'
            }
    
    def _calculate_performance_score(self, avg_time: float, threshold: float, 
                                   error_rate: float) -> float:
        """Calculate performance score (0-100)"""
        
        # Time score (0-70 points)
        if avg_time <= threshold * 0.5:
            time_score = 70
        elif avg_time <= threshold:
            time_score = 70 - ((avg_time - threshold * 0.5) / (threshold * 0.5)) * 35
        else:
            time_score = max(0, 35 - ((avg_time - threshold) / threshold) * 35)
        
        # Error rate score (0-30 points)
        if error_rate <= 0.01:  # <1% error rate
            error_score = 30
        elif error_rate <= 0.05:  # <5% error rate
            error_score = 30 - ((error_rate - 0.01) / 0.04) * 15
        else:
            error_score = max(0, 15 - ((error_rate - 0.05) / 0.05) * 15)
        
        return min(100, time_score + error_score)
    
    def get_all_routes_summary(self) -> Dict[str, Dict[str, Any]]:
        """Get performance summary for all monitored routes"""
        
        summary = {}
        for route_name in self.route_metrics.keys():
            summary[route_name] = self.get_route_summary(route_name)
        
        return summary
    
    def get_slow_routes(self, threshold_multiplier: float = 2.0) -> List[Dict[str, Any]]:
        """Get routes that are performing slower than their thresholds"""
        
        slow_routes = []
        
        for route_name in self.route_metrics.keys():
            summary = self.get_route_summary(route_name)
            
            if (summary and 
                'avg_response_time_ms' in summary and
                summary['avg_response_time_ms'] > summary['threshold_ms'] * threshold_multiplier):
                
                slow_routes.append(summary)
        
        # Sort by performance score (worst first)
        slow_routes.sort(key=lambda x: x.get('performance_score', 0))
        
        return slow_routes
    
    def reset_route_metrics(self, route_name: str = None):
        """Reset metrics for a specific route or all routes"""
        
        if route_name:
            if route_name in self.route_metrics:
                del self.route_metrics[route_name]
                logger.info(f"Reset metrics for route: {route_name}")
        else:
            self.route_metrics.clear()
            logger.info("Reset all route metrics")
    
    def get_real_time_health_status(self) -> Dict[str, Any]:
        """Get real-time health status for monitoring dashboards"""
        
        total_routes = len(self.route_metrics)
        healthy_routes = 0
        total_requests = 0
        total_errors = 0
        
        for route_name in self.route_metrics.keys():
            summary = self.get_route_summary(route_name)
            if summary.get('is_healthy', False):
                healthy_routes += 1
            
            total_requests += summary.get('total_requests', 0)
            total_errors += summary.get('error_count', 0)
        
        overall_error_rate = total_errors / max(total_requests, 1)
        health_percentage = (healthy_routes / max(total_routes, 1)) * 100
        
        return {
            'total_routes_monitored': total_routes,
            'healthy_routes': healthy_routes,
            'overall_health_percentage': health_percentage,
            'total_requests': total_requests,
            'total_errors': total_errors,
            'overall_error_rate': overall_error_rate,
            'status': 'healthy' if health_percentage >= 90 else 
                     'degraded' if health_percentage >= 70 else 'unhealthy'
        }