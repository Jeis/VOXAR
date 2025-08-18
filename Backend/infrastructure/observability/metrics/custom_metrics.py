"""
VOXAR Enterprise Observability - Custom AR Metrics
AR-specific performance metrics for spatial computing applications
"""

import logging
from typing import Dict, Any
from opentelemetry import metrics

logger = logging.getLogger(__name__)

def create_base_metrics(meter: metrics.Meter) -> Dict[str, Any]:
    """Create base enterprise metrics for all VOXAR services"""
    
    base_metrics = {}
    
    try:
        # Performance metrics
        base_metrics['request_duration'] = meter.create_histogram(
            name="voxar_request_duration_seconds",
            description="Request processing duration",
            unit="s"
        )
        
        base_metrics['request_count'] = meter.create_counter(
            name="voxar_requests_total",
            description="Total number of requests processed"
        )
        
        # System health metrics
        base_metrics['service_availability'] = meter.create_up_down_counter(
            name="voxar_service_availability",
            description="Service availability status (1=up, 0=down)"
        )
        
        base_metrics['error_rate'] = meter.create_counter(
            name="voxar_errors_total",
            description="Total number of errors"
        )
        
        # Business metrics
        base_metrics['active_sessions'] = meter.create_up_down_counter(
            name="voxar_active_sessions_current",
            description="Currently active AR sessions"
        )
        
        base_metrics['data_transfer'] = meter.create_counter(
            name="voxar_data_transfer_bytes",
            description="Total data transferred",
            unit="By"
        )
        
        logger.info(f"Created {len(base_metrics)} base enterprise metrics")
        
    except Exception as e:
        logger.error(f"Failed to create base metrics: {e}")
    
    return base_metrics

def create_ar_metrics(meter: metrics.Meter) -> Dict[str, Any]:
    """Create AR-specific metrics for spatial computing"""
    
    ar_metrics = {}
    
    try:
        # AR session metrics
        ar_metrics['ar_session_duration'] = meter.create_histogram(
            name="voxar_ar_session_duration_seconds",
            description="AR session duration",
            unit="s"
        )
        
        ar_metrics['ar_fps_actual'] = meter.create_histogram(
            name="voxar_ar_fps_actual",
            description="Actual AR frames per second achieved",
            unit="fps"
        )
        
        # Tracking quality metrics
        ar_metrics['tracking_quality'] = meter.create_histogram(
            name="voxar_tracking_quality_score",
            description="AR tracking quality score (0-1)",
            unit="1"
        )
        
        ar_metrics['pose_accuracy'] = meter.create_histogram(
            name="voxar_pose_accuracy_meters",
            description="Pose estimation accuracy in meters",
            unit="m"
        )
        
        # Spatial computing metrics
        ar_metrics['anchor_operations'] = meter.create_counter(
            name="voxar_anchor_operations_total",
            description="Total anchor operations (create/update/delete)"
        )
        
        ar_metrics['map_processing_time'] = meter.create_histogram(
            name="voxar_map_processing_seconds",
            description="3D map processing duration",
            unit="s"
        )
        
        ar_metrics['feature_extraction_time'] = meter.create_histogram(
            name="voxar_feature_extraction_seconds",
            description="Feature extraction processing time",
            unit="s"
        )
        
        logger.info(f"Created {len(ar_metrics)} AR-specific metrics")
        
    except Exception as e:
        logger.error(f"Failed to create AR metrics: {e}")
    
    return ar_metrics