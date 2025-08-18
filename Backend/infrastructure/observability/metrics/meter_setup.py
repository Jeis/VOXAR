"""
VOXAR Enterprise Observability - Meter Setup
OpenTelemetry meter provider configuration with performance-tuned intervals
"""

import os
import logging
from typing import List
from opentelemetry import metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader, ConsoleMetricExporter
from opentelemetry.sdk.resources import Resource

from core.service_types import PerformanceTier

logger = logging.getLogger(__name__)

def get_export_interval(performance_tier: PerformanceTier) -> int:
    """Get performance-appropriate metric export interval in milliseconds"""
    
    intervals = {
        PerformanceTier.CRITICAL_60FPS: 5000,    # 5 seconds
        PerformanceTier.HIGH_PERFORMANCE: 10000,  # 10 seconds
        PerformanceTier.STANDARD: 15000,         # 15 seconds
        PerformanceTier.BACKGROUND: 30000        # 30 seconds
    }
    
    return intervals.get(performance_tier, 15000)

def setup_metrics(
    resource: Resource,
    metric_readers: List[PeriodicExportingMetricReader],
    service_name: str,
    service_version: str = "1.0.0"
) -> metrics.Meter:
    """Configure comprehensive metrics collection"""
    
    try:
        # Set meter provider
        metrics.set_meter_provider(MeterProvider(
            resource=resource,
            metric_readers=metric_readers
        ))
        
        # Create meter with proper naming
        meter = metrics.get_meter(
            instrumenting_module_name=f"voxar.{service_name}",
            instrumenting_library_version=service_version
        )
        
        logger.info(f"Metrics collection configured for {service_name} with {len(metric_readers)} readers")
        return meter
        
    except Exception as e:
        logger.error(f"Failed to setup metrics: {e}")
        # Fallback meter provider
        metrics.set_meter_provider(MeterProvider(resource=resource))
        return metrics.get_meter(__name__)

def create_console_metric_reader(
    export_interval: int = 30000
) -> PeriodicExportingMetricReader:
    """Create console metric reader for development"""
    
    return PeriodicExportingMetricReader(
        exporter=ConsoleMetricExporter(),
        export_interval_millis=export_interval
    )