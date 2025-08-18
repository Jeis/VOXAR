"""
VOXAR Enterprise Observability - Tracer Setup
OpenTelemetry tracer provider configuration with performance-aware sampling
"""

import os
import logging
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.sampling import TraceIdRatioBased, ParentBased
from opentelemetry.sdk.resources import Resource

from core.service_types import PerformanceTier

logger = logging.getLogger(__name__)

def get_sampling_strategy(
    performance_tier: PerformanceTier, 
    environment: str = None
) -> ParentBased:
    """Configure intelligent sampling based on performance tier and environment"""
    
    environment = environment or os.getenv("ENVIRONMENT", "development")
    
    if performance_tier == PerformanceTier.CRITICAL_60FPS:
        # High sampling for critical AR operations
        return ParentBased(root=TraceIdRatioBased(0.1))  # 10% sampling
    elif performance_tier == PerformanceTier.HIGH_PERFORMANCE:
        return ParentBased(root=TraceIdRatioBased(0.05))  # 5% sampling
    elif environment == "production":
        return ParentBased(root=TraceIdRatioBased(0.01))  # 1% sampling
    else:
        return ParentBased(root=TraceIdRatioBased(1.0))   # 100% sampling in dev

def setup_tracing(
    resource: Resource,
    sampler: ParentBased,
    service_name: str,
    service_version: str = "1.0.0"
) -> trace.Tracer:
    """Configure distributed tracing with sampling strategy"""
    
    try:
        # Create tracer provider with sampling
        trace.set_tracer_provider(TracerProvider(
            resource=resource,
            sampler=sampler
        ))
        
        # Create tracer with proper naming
        tracer = trace.get_tracer(
            instrumenting_module_name=f"voxar.{service_name}",
            instrumenting_library_version=service_version
        )
        
        logger.info(f"Tracer configured for {service_name} with sampling strategy")
        return tracer
        
    except Exception as e:
        logger.error(f"Failed to setup tracing: {e}")
        # Fallback to no-op tracer
        trace.set_tracer_provider(TracerProvider(resource=resource))
        return trace.get_tracer(__name__)