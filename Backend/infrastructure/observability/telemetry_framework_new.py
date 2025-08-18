"""
VOXAR Enterprise Observability Framework - Modular Version
Comprehensive OpenTelemetry implementation for spatial AR platform
"""

import os
import logging
from typing import Dict, Optional

from .core import (
    ServiceType, PerformanceTier, ARSessionContext, SpatialMetrics,
    create_resource, get_default_resource_attributes
)
from .tracing import (
    setup_tracing, get_sampling_strategy, create_span_processors, 
    add_span_processors_to_provider, setup_propagation
)
from .metrics import (
    setup_metrics, create_metric_exporters, create_base_metrics, create_ar_metrics
)
from .instrumentation import (
    setup_auto_instrumentation, trace_ar_session, trace_performance_critical,
    PerformanceMonitor
)

logger = logging.getLogger(__name__)

class VoxarObservabilityFramework:
    """Enterprise-grade observability framework for VOXAR Platform"""
    
    def __init__(
        self,
        service_type: ServiceType,
        service_version: str = "1.0.0",
        environment: str = None,
        performance_tier: PerformanceTier = PerformanceTier.STANDARD
    ):
        self.service_type = service_type
        self.service_name = service_type.value
        self.service_version = service_version
        self.environment = environment or os.getenv("ENVIRONMENT", "development")
        self.performance_tier = performance_tier
        
        # Configuration
        self.otel_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4317")
        self.enable_console_export = os.getenv("OTEL_ENABLE_CONSOLE", "false").lower() == "true"
        
        # Active sessions tracking
        self.active_sessions: Dict[str, ARSessionContext] = {}
        
        # Initialize observability components
        self._initialize_framework()
        
        logger.info(f"VOXAR Observability Framework initialized for {self.service_name}")
    
    def _initialize_framework(self):
        """Initialize all observability components"""
        
        # 1. Create resource
        self.resource = create_resource(
            self.service_type,
            self.service_name,
            self.service_version,
            self.environment,
            self.performance_tier
        )
        
        # 2. Setup tracing
        sampler = get_sampling_strategy(self.performance_tier, self.environment)
        self.tracer = setup_tracing(self.resource, sampler, self.service_name, self.service_version)
        
        # Add span processors
        span_processors = create_span_processors(
            self.performance_tier,
            self.otel_endpoint,
            self.enable_console_export
        )
        add_span_processors_to_provider(span_processors)
        
        # 3. Setup metrics
        metric_readers = create_metric_exporters(
            self.performance_tier,
            self.otel_endpoint,
            self.enable_console_export
        )
        self.meter = setup_metrics(self.resource, metric_readers, self.service_name, self.service_version)
        
        # Create metrics
        self.base_metrics = create_base_metrics(self.meter)
        self.ar_metrics = create_ar_metrics(self.meter)
        
        # 4. Setup propagation
        setup_propagation()
        
        # 5. Setup auto-instrumentation
        setup_auto_instrumentation()
        
        # 6. Initialize performance monitoring
        self.performance_monitor = PerformanceMonitor(self.performance_tier)
    
    async def trace_ar_session_context(
        self, 
        session_context: ARSessionContext,
        operation_name: str = None
    ):
        """Trace an AR session with comprehensive context"""
        
        return trace_ar_session(
            self.tracer,
            session_context,
            self.active_sessions,
            self.ar_metrics.get('ar_session_duration'),
            self.base_metrics.get('active_sessions'),
            self.base_metrics.get('error_rate'),
            self.service_name,
            self.performance_tier,
            operation_name
        )
    
    async def trace_critical_operation_context(
        self,
        operation_name: str,
        target_duration_ms: int = 16,
        **attributes
    ):
        """Trace performance-critical operations with SLA monitoring"""
        
        return trace_performance_critical(
            self.tracer,
            operation_name,
            self.performance_tier,
            self.base_metrics.get('request_duration'),
            self.service_name,
            target_duration_ms,
            **attributes
        )
    
    def get_session_context(self, session_id: str) -> Optional[ARSessionContext]:
        """Get AR session context"""
        return self.active_sessions.get(session_id)
    
    def get_tracer(self):
        """Get configured tracer"""
        return self.tracer
    
    def get_meter(self):
        """Get configured meter"""
        return self.meter
    
    def get_performance_monitor(self) -> PerformanceMonitor:
        """Get performance monitor"""
        return self.performance_monitor
    
    def shutdown(self):
        """Shutdown observability framework"""
        logger.info(f"Shutting down observability framework for {self.service_name}")

# Global framework instance management
_observability_framework: Optional[VoxarObservabilityFramework] = None

def get_observability() -> Optional[VoxarObservabilityFramework]:
    """Get global observability framework instance"""
    return _observability_framework

def set_observability(framework: VoxarObservabilityFramework):
    """Set global observability framework instance"""
    global _observability_framework
    _observability_framework = framework

# Convenience functions for backward compatibility
def create_service_instrumentation(service_type: ServiceType, **kwargs):
    """Create service instrumentation (backward compatibility)"""
    framework = VoxarObservabilityFramework(service_type, **kwargs)
    set_observability(framework)
    return framework

def create_ar_instrumentation(service_type: ServiceType, **kwargs):
    """Create AR instrumentation (backward compatibility)"""
    return create_service_instrumentation(service_type, **kwargs)

def create_enterprise_monitoring(service_type: ServiceType, **kwargs):
    """Create enterprise monitoring (backward compatibility)"""
    return create_service_instrumentation(service_type, **kwargs)