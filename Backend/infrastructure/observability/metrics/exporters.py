"""
VOXAR Enterprise Observability - Metric Exporters
OTLP and console metric exporters with performance tuning
"""

import os
import logging
from typing import List
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader

from core.service_types import PerformanceTier
from metrics.meter_setup import get_export_interval, create_console_metric_reader

logger = logging.getLogger(__name__)

def create_metric_exporters(
    performance_tier: PerformanceTier,
    otel_endpoint: str = None,
    enable_console_export: bool = False
) -> List[PeriodicExportingMetricReader]:
    """Create metric exporters with performance-appropriate configuration"""
    
    readers = []
    otel_endpoint = otel_endpoint or os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4317")
    enable_console_export = enable_console_export or os.getenv("OTEL_ENABLE_CONSOLE", "false").lower() == "true"
    
    try:
        # OTLP metric exporter
        metric_exporter = OTLPMetricExporter(
            endpoint=otel_endpoint,
            insecure=True
        )
        
        # Performance-appropriate export interval
        export_interval = get_export_interval(performance_tier)
        
        metric_reader = PeriodicExportingMetricReader(
            exporter=metric_exporter,
            export_interval_millis=export_interval
        )
        readers.append(metric_reader)
        
        # Console exporter for development
        if enable_console_export:
            console_reader = create_console_metric_reader(export_interval=30000)
            readers.append(console_reader)
        
        logger.info(f"Created {len(readers)} metric exporters (OTLP{', Console' if enable_console_export else ''})")
        logger.info(f"Export interval: {export_interval}ms for {performance_tier.value}")
        
    except Exception as e:
        logger.error(f"Failed to create metric exporters: {e}")
    
    return readers

def create_otlp_metric_exporter(
    endpoint: str = None,
    insecure: bool = True
) -> OTLPMetricExporter:
    """Create OTLP metric exporter with standard configuration"""
    
    endpoint = endpoint or os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4317")
    
    return OTLPMetricExporter(
        endpoint=endpoint,
        insecure=insecure
    )