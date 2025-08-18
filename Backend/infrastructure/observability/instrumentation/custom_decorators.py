"""
VOXAR Enterprise Observability - Custom Decorators
AR session tracing and performance-critical operation monitoring
"""

import time
import logging
from contextlib import asynccontextmanager
from typing import Optional, Dict, Any

from opentelemetry import trace, baggage

from core.session_context import ARSessionContext
from core.service_types import PerformanceTier

logger = logging.getLogger(__name__)

@asynccontextmanager
async def trace_ar_session(
    tracer: trace.Tracer,
    session_context: ARSessionContext,
    active_sessions: Dict[str, ARSessionContext],
    ar_session_duration_metric,
    active_sessions_metric,
    error_rate_metric,
    service_name: str,
    performance_tier: PerformanceTier,
    operation_name: str = None
):
    """Trace an AR session with comprehensive context"""
    operation_name = operation_name or f"{service_name}.ar_session"
    
    with tracer.start_as_current_span(operation_name) as span:
        try:
            # Add AR session context to span
            span.set_attributes({
                "ar.session.id": session_context.session_id,
                "ar.user.id": session_context.user_id,
                "ar.device.id": session_context.device_id,
                "ar.platform": session_context.platform,
                "ar.framework": session_context.ar_framework,
                "ar.tracking.state": session_context.tracking_state,
                "ar.quality.score": session_context.quality_score,
                "ar.fps.target": session_context.fps_target
            })
            
            if session_context.map_id:
                span.set_attribute("spatial.map.id", session_context.map_id)
            
            # Add to baggage for cross-service context
            baggage.set_baggage("ar.session.id", session_context.session_id)
            baggage.set_baggage("ar.performance.tier", performance_tier.value)
            
            # Track active session
            active_sessions[session_context.session_id] = session_context
            active_sessions_metric.add(1, {"service": service_name})
            
            yield span
            
        except Exception as e:
            span.record_exception(e)
            span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
            error_rate_metric.add(1, {
                "service": service_name,
                "error_type": type(e).__name__,
                "session_id": session_context.session_id
            })
            raise
        finally:
            # Cleanup session tracking
            if session_context.session_id in active_sessions:
                session_duration = time.time() - session_context.started_at
                ar_session_duration_metric.record(session_duration, {
                    "service": service_name,
                    "platform": session_context.platform,
                    "ar_framework": session_context.ar_framework
                })
                
                del active_sessions[session_context.session_id]
                active_sessions_metric.add(-1, {"service": service_name})

@asynccontextmanager
async def trace_performance_critical(
    tracer: trace.Tracer,
    operation_name: str,
    performance_tier: PerformanceTier,
    request_duration_metric,
    service_name: str,
    target_duration_ms: int = 16,  # 60fps target
    **attributes
):
    """Trace performance-critical operations with SLA monitoring"""
    start_time = time.time()
    
    with tracer.start_as_current_span(operation_name) as span:
        try:
            # Mark as performance critical
            span.set_attributes({
                "voxar.performance.critical": True,
                "voxar.performance.target_ms": target_duration_ms,
                "voxar.service.tier": performance_tier.value,
                **{f"voxar.{k}": v for k, v in attributes.items()}
            })
            
            yield span
            
        except Exception as e:
            span.record_exception(e)
            span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
            raise
        finally:
            # Calculate and record performance metrics
            duration_ms = (time.time() - start_time) * 1000
            span.set_attribute("voxar.performance.actual_ms", duration_ms)
            
            # Record SLA compliance
            sla_met = duration_ms <= target_duration_ms
            span.set_attribute("voxar.performance.sla_met", sla_met)
            
            # Record metrics
            request_duration_metric.record(duration_ms / 1000, {
                "service": service_name,
                "operation": operation_name,
                "sla_met": str(sla_met)
            })