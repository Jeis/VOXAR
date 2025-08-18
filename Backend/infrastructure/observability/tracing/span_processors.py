"""
VOXAR Enterprise Observability - Span Processors
OTLP, Jaeger, and console span processors with performance tuning
"""

import os
import logging
from typing import List
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

from core.service_types import PerformanceTier

logger = logging.getLogger(__name__)

def create_span_processors(
    performance_tier: PerformanceTier,
    otel_endpoint: str = None,
    enable_console_export: bool = False
) -> List[BatchSpanProcessor]:
    """Create span processors with performance-appropriate configuration"""
    
    processors = []
    otel_endpoint = otel_endpoint or os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4317")
    enable_console_export = enable_console_export or os.getenv("OTEL_ENABLE_CONSOLE", "false").lower() == "true"
    
    try:
        # OTLP exporter (primary)
        otlp_exporter = OTLPSpanExporter(
            endpoint=otel_endpoint,
            insecure=True,
            compression="gzip"
        )
        
        # Performance-tuned batch processor
        schedule_delay = 1000 if performance_tier == PerformanceTier.CRITICAL_60FPS else 5000
        
        otlp_processor = BatchSpanProcessor(
            otlp_exporter,
            max_queue_size=2048,
            export_timeout_millis=30000,
            schedule_delay_millis=schedule_delay
        )
        processors.append(otlp_processor)
        
        # Jaeger exporter (backup/compatibility)
        jaeger_exporter = JaegerExporter(
            agent_host_name="jaeger",
            agent_port=6831
        )
        jaeger_processor = BatchSpanProcessor(jaeger_exporter)
        processors.append(jaeger_processor)
        
        # Console exporter for development
        if enable_console_export:
            console_processor = BatchSpanProcessor(ConsoleSpanExporter())
            processors.append(console_processor)
        
        logger.info(f"Created {len(processors)} span processors (OTLP, Jaeger{', Console' if enable_console_export else ''})")
        
    except Exception as e:
        logger.error(f"Failed to create span processors: {e}")
    
    return processors

def add_span_processors_to_provider(processors: List[BatchSpanProcessor]):
    """Add span processors to the current tracer provider"""
    
    try:
        provider = trace.get_tracer_provider()
        
        for processor in processors:
            provider.add_span_processor(processor)
        
        logger.info(f"Added {len(processors)} span processors to tracer provider")
        
    except Exception as e:
        logger.error(f"Failed to add span processors: {e}")