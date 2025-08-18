"""
Enterprise OpenTelemetry Instrumentation for VOXAR Localization Service
Production-ready observability with auto-instrumentation and custom metrics.
"""

import os
import logging
from typing import Optional
from opentelemetry import trace, metrics
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.psycopg2 import Psycopg2Instrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor

# Configure logging first
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Optional instrumentations - import with error handling
try:
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False
    logger.warning("HTTPXClientInstrumentor not available")

try:
    from opentelemetry.instrumentation.logging import LoggingInstrumentor
    LOGGING_AVAILABLE = True
except ImportError:
    LOGGING_AVAILABLE = False
    logger.warning("LoggingInstrumentor not available")

try:
    from opentelemetry.instrumentation.aiohttp_client import AioHttpClientInstrumentor
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False
    logger.warning("AioHttpClientInstrumentor not available")

try:
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
    SQLALCHEMY_AVAILABLE = True
except ImportError:
    SQLALCHEMY_AVAILABLE = False
    logger.warning("SQLAlchemyInstrumentor not available")

# Service configuration
SERVICE_NAME = "localization-service"
SERVICE_VERSION = "2.1.0"
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
OTEL_ENDPOINT = os.getenv("OTEL_ENDPOINT", "http://otel-collector:4317")

def create_resource() -> Resource:
    """Create OpenTelemetry resource with service metadata."""
    return Resource.create({
        "service.name": SERVICE_NAME,
        "service.version": SERVICE_VERSION,
        "service.instance.id": f"{SERVICE_NAME}-{os.getenv('HOSTNAME', 'unknown')}",
        "deployment.environment": ENVIRONMENT,
        "platform.type": "ar-localization",
        "component.type": "slam-vio-tracker"
    })

def setup_tracing() -> trace.Tracer:
    """Configure distributed tracing with OTLP export."""
    try:
        # Create resource
        resource = create_resource()
        
        # Configure tracer provider
        tracer_provider = TracerProvider(resource=resource)
        trace.set_tracer_provider(tracer_provider)
        
        # Configure OTLP span exporter
        span_exporter = OTLPSpanExporter(endpoint=OTEL_ENDPOINT, insecure=True)
        span_processor = BatchSpanProcessor(span_exporter)
        tracer_provider.add_span_processor(span_processor)
        
        logger.info(f"Tracing configured for {SERVICE_NAME} → {OTEL_ENDPOINT}")
        return trace.get_tracer(SERVICE_NAME, SERVICE_VERSION)
        
    except Exception as e:
        logger.error(f"Failed to setup tracing: {e}")
        return trace.get_tracer(SERVICE_NAME, SERVICE_VERSION)

def setup_metrics() -> metrics.Meter:
    """Configure metrics collection with OTLP export."""
    try:
        # Create resource
        resource = create_resource()
        
        # Configure metric exporter
        metric_exporter = OTLPMetricExporter(endpoint=OTEL_ENDPOINT, insecure=True)
        metric_reader = PeriodicExportingMetricReader(exporter=metric_exporter, export_interval_millis=10000)
        
        # Configure meter provider
        meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
        metrics.set_meter_provider(meter_provider)
        
        logger.info(f"Metrics configured for {SERVICE_NAME} → {OTEL_ENDPOINT}")
        return metrics.get_meter(SERVICE_NAME, SERVICE_VERSION)
        
    except Exception as e:
        logger.error(f"Failed to setup metrics: {e}")
        return metrics.get_meter(SERVICE_NAME, SERVICE_VERSION)

def setup_auto_instrumentation():
    """Configure automatic instrumentation for common libraries."""
    try:
        # Database instrumentation
        Psycopg2Instrumentor().instrument()
        logger.info("PostgreSQL instrumentation configured")
        
        # Redis instrumentation  
        RedisInstrumentor().instrument()
        logger.info("Redis instrumentation configured")
        
        # HTTP client instrumentation
        RequestsInstrumentor().instrument()
        logger.info("Requests instrumentation configured")
        
        # Optional instrumentations
        if HTTPX_AVAILABLE:
            HTTPXClientInstrumentor().instrument()
            logger.info("HTTPX instrumentation configured")
        
        if LOGGING_AVAILABLE:
            LoggingInstrumentor().instrument(set_logging_format=True)
            logger.info("Logging instrumentation configured")
            
        if AIOHTTP_AVAILABLE:
            AioHttpClientInstrumentor().instrument()
            logger.info("AIOHTTP client instrumentation configured")
            
        if SQLALCHEMY_AVAILABLE:
            SQLAlchemyInstrumentor().instrument()
            logger.info("SQLAlchemy instrumentation configured")
        
        logger.info("Auto-instrumentation configured successfully")
        
    except Exception as e:
        logger.error(f"Failed to setup auto-instrumentation: {e}")

def instrument_fastapi_app(app):
    """Instrument FastAPI application with OpenTelemetry."""
    try:
        FastAPIInstrumentor.instrument_app(app, tracer_provider=trace.get_tracer_provider())
        logger.info(f"FastAPI app instrumented for {SERVICE_NAME}")
    except Exception as e:
        logger.error(f"Failed to instrument FastAPI app: {e}")

def create_localization_metrics(meter: metrics.Meter):
    """Create AR localization-specific metrics."""
    try:
        # SLAM tracking metrics
        slam_updates = meter.create_counter(
            name="slam_updates_total",
            description="Total number of SLAM pose updates",
            unit="1"
        )
        
        slam_accuracy = meter.create_histogram(
            name="slam_accuracy_meters",
            description="SLAM tracking accuracy in meters",
            unit="m"
        )
        
        # VIO tracking metrics
        vio_updates = meter.create_counter(
            name="vio_updates_total", 
            description="Total number of VIO pose updates",
            unit="1"
        )
        
        vio_confidence = meter.create_histogram(
            name="vio_confidence_score",
            description="VIO tracking confidence score (0-1)",
            unit="1"
        )
        
        # Localization session metrics
        active_sessions = meter.create_up_down_counter(
            name="localization_sessions_active",
            description="Number of active localization sessions",
            unit="1"
        )
        
        processing_duration = meter.create_histogram(
            name="localization_processing_duration_seconds",
            description="Time taken to process localization requests",
            unit="s"
        )
        
        # Feature extraction metrics
        features_extracted = meter.create_counter(
            name="features_extracted_total",
            description="Total number of features extracted from images",
            unit="1"
        )
        
        feature_matching_accuracy = meter.create_histogram(
            name="feature_matching_accuracy_percentage", 
            description="Feature matching accuracy percentage",
            unit="%"
        )
        
        logger.info("AR localization metrics created successfully")
        
        return {
            "slam_updates": slam_updates,
            "slam_accuracy": slam_accuracy,
            "vio_updates": vio_updates,
            "vio_confidence": vio_confidence,
            "active_sessions": active_sessions,
            "processing_duration": processing_duration,
            "features_extracted": features_extracted,
            "feature_matching_accuracy": feature_matching_accuracy
        }
        
    except Exception as e:
        logger.error(f"Failed to create localization metrics: {e}")
        return {}

# Service type enumeration for observability
class ServiceType:
    LOCALIZATION = "ar-localization"  # Primary service type for app.py compatibility
    AR_LOCALIZATION = "ar-localization"
    VPS_ENGINE = "vps-engine"
    CLOUD_ANCHORS = "cloud-anchors"
    API_GATEWAY = "api-gateway"
    MAPPING_PROCESSOR = "mapping-processor"

# Performance tier enumeration
class PerformanceTier:
    CRITICAL_60FPS = "critical-60fps"  # Primary tier for app.py compatibility
    REALTIME_60FPS = "realtime-60fps"
    INTERACTIVE_30FPS = "interactive-30fps"
    BACKGROUND = "background"

# Global instances
_tracer: Optional[trace.Tracer] = None
_meter: Optional[metrics.Meter] = None
_localization_metrics: dict = {}

def initialize_observability():
    """Initialize complete observability stack for localization service."""
    global _tracer, _meter, _localization_metrics
    
    try:
        logger.info(f"Initializing observability for {SERVICE_NAME}")
        
        # Setup auto-instrumentation first
        setup_auto_instrumentation()
        
        # Setup tracing and metrics
        _tracer = setup_tracing()
        _meter = setup_metrics()
        
        # Create service-specific metrics
        _localization_metrics = create_localization_metrics(_meter)
        
        logger.info(f"Observability initialization complete for {SERVICE_NAME}")
        
    except Exception as e:
        logger.error(f"Failed to initialize observability: {e}")

def initialize_service_observability(app=None, 
                                   service_type: str = ServiceType.LOCALIZATION, 
                                   custom_performance_tier: str = PerformanceTier.CRITICAL_60FPS):
    """Initialize service observability with specific service type and performance tier."""
    logger.info(f"Initializing {service_type} observability with {custom_performance_tier} performance tier")
    
    # Initialize core observability
    initialize_observability()
    
    # Instrument FastAPI app if provided
    if app is not None:
        instrument_fastapi_app(app)
        logger.info(f"FastAPI application instrumented for {service_type}")
    
    # Return framework and instrumentation objects for app.py compatibility
    framework = {
        "tracer": get_tracer(),
        "meter": get_meter(),
        "service_type": service_type,
        "performance_tier": custom_performance_tier
    }
    
    instrumentation = {
        "metrics": get_localization_metrics(),
        "record_slam_update": record_slam_update,
        "record_vio_update": record_vio_update,
        "record_session_start": record_session_start,
        "record_session_end": record_session_end,
        "record_processing_time": record_processing_time,
        "record_features_extracted": record_features_extracted,
        "record_feature_matching_accuracy": record_feature_matching_accuracy
    }
    
    return framework, instrumentation

def get_tracer() -> trace.Tracer:
    """Get the configured tracer instance."""
    global _tracer
    if _tracer is None:
        _tracer = setup_tracing()
    return _tracer

def get_meter() -> metrics.Meter:
    """Get the configured meter instance."""
    global _meter
    if _meter is None:
        _meter = setup_metrics()
    return _meter

def get_localization_metrics() -> dict:
    """Get AR localization-specific metrics."""
    global _localization_metrics
    if not _localization_metrics:
        meter = get_meter()
        _localization_metrics = create_localization_metrics(meter)
    return _localization_metrics

# Convenience functions for common operations
def record_slam_update(accuracy: float = None):
    """Record a SLAM pose update with optional accuracy."""
    metrics = get_localization_metrics()
    if "slam_updates" in metrics:
        metrics["slam_updates"].add(1)
    if accuracy is not None and "slam_accuracy" in metrics:
        metrics["slam_accuracy"].record(accuracy)

def record_vio_update(confidence: float = None):
    """Record a VIO pose update with optional confidence score."""
    metrics = get_localization_metrics()
    if "vio_updates" in metrics:
        metrics["vio_updates"].add(1)
    if confidence is not None and "vio_confidence" in metrics:
        metrics["vio_confidence"].record(confidence)

def record_session_start():
    """Record the start of a localization session."""
    metrics = get_localization_metrics()
    if "active_sessions" in metrics:
        metrics["active_sessions"].add(1)

def record_session_end():
    """Record the end of a localization session."""
    metrics = get_localization_metrics()
    if "active_sessions" in metrics:
        metrics["active_sessions"].add(-1)

def record_processing_time(duration_seconds: float):
    """Record localization processing duration."""
    metrics = get_localization_metrics()
    if "processing_duration" in metrics:
        metrics["processing_duration"].record(duration_seconds)

def record_features_extracted(count: int):
    """Record number of features extracted."""
    metrics = get_localization_metrics()
    if "features_extracted" in metrics:
        metrics["features_extracted"].add(count)

def record_feature_matching_accuracy(accuracy_percentage: float):
    """Record feature matching accuracy."""
    metrics = get_localization_metrics()
    if "feature_matching_accuracy" in metrics:
        metrics["feature_matching_accuracy"].record(accuracy_percentage)

# Service registry for compatibility with gateway telemetry
class ServiceRegistry:
    """Simple service registry for telemetry compatibility"""
    def __init__(self):
        self.services = {}
    
    def register_service(self, name: str, service_info: dict):
        """Register a service"""
        self.services[name] = service_info
        logger.info(f"Service registered: {name}")
    
    def get_service(self, name: str):
        """Get service information"""
        return self.services.get(name)

# Global service registry instance
service_registry = ServiceRegistry()