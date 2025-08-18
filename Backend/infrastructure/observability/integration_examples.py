# VOXAR Observability Framework Integration Examples
# Demonstrates enterprise-grade OpenTelemetry integration patterns

import asyncio
import logging
from fastapi import FastAPI, Request
from typing import Optional
import uvicorn

from telemetry_framework import (
    ServiceType,
    PerformanceTier,
    ARSessionContext,
    SpatialMetrics,
    create_service_instrumentation,
    create_ar_instrumentation,
    create_enterprise_monitoring
)

logger = logging.getLogger(__name__)

# =================== API GATEWAY INTEGRATION ===================

def create_instrumented_gateway_app() -> FastAPI:
    """Create fully instrumented API Gateway with enterprise observability"""
    
    # Initialize enterprise observability
    framework, instrumentation = create_service_instrumentation(
        service_type=ServiceType.API_GATEWAY,
        service_version="2.0.0",
        environment="production",
        performance_tier=PerformanceTier.HIGH_PERFORMANCE
    )
    
    # Create FastAPI app
    app = FastAPI(
        title="VOXAR API Gateway",
        version="2.0.0",
        description="Enterprise AR Platform Gateway with OpenTelemetry"
    )
    
    # Instrument with enterprise telemetry
    instrumentation.instrument_fastapi_app(app)
    
    # Create AR-specific instrumentors
    ar_instrumentor, spatial_instrumentor = create_ar_instrumentation(framework)
    
    # Create enterprise monitoring
    alert_manager = create_enterprise_monitoring(framework)
    
    @app.get("/health")
    async def health_check():
        """Health check endpoint"""
        return {"status": "healthy", "service": "api-gateway"}
    
    @app.post("/ar/sessions/{session_id}/localize")
    async def localize_ar_session(
        session_id: str,
        request: Request,
        map_id: str,
        image_data: bytes
    ):
        """AR localization with comprehensive tracing"""
        
        # Extract AR session context
        session_context = ARSessionContext(
            session_id=session_id,
            user_id=request.headers.get("X-User-ID", "unknown"),
            device_id=request.headers.get("X-Device-ID", "unknown"),
            platform=request.headers.get("X-Platform", "unknown"),
            ar_framework=request.headers.get("X-AR-Framework", "unknown"),
            map_id=map_id
        )
        
        # Track AR session with enterprise monitoring
        async with framework.trace_ar_session(session_context, "ar.localization.request"):
            # Track localization attempt
            async with ar_instrumentor.track_localization_attempt(
                session_id=session_id,
                map_id=map_id,
                localization_type="visual"
            ):
                # Simulate localization processing
                await asyncio.sleep(0.1)  # Simulate processing time
                
                # Record spatial metrics
                spatial_metrics = SpatialMetrics(
                    pose_accuracy=0.15,  # 15cm accuracy
                    tracking_confidence=0.92,
                    feature_points=2840,
                    anchor_count=5,
                    map_quality=0.88,
                    localization_time=0.1,
                    reconstruction_progress=1.0
                )
                
                framework.record_spatial_metrics(session_id, spatial_metrics)
                
                # Check for performance alerts
                alert_manager.check_ar_performance_alerts([spatial_metrics], session_context)
                
                return {
                    "session_id": session_id,
                    "localized": True,
                    "pose": {
                        "position": [1.2, 0.5, -0.8],
                        "rotation": [0.0, 0.1, 0.0, 1.0]
                    },
                    "confidence": spatial_metrics.tracking_confidence
                }
    
    return app

# =================== LOCALIZATION SERVICE INTEGRATION ===================

def create_instrumented_localization_service() -> FastAPI:
    """Create fully instrumented Localization Service"""
    
    # Initialize with critical performance tier
    framework, instrumentation = create_service_instrumentation(
        service_type=ServiceType.LOCALIZATION,
        service_version="2.0.0",
        environment="production",
        performance_tier=PerformanceTier.CRITICAL_60FPS
    )
    
    app = FastAPI(
        title="VOXAR Localization Service",
        version="2.0.0",
        description="6DOF AR Tracking with 60fps Performance"
    )
    
    # Instrument with enterprise telemetry
    instrumentation.instrument_fastapi_app(app)
    
    # Create AR instrumentors
    ar_instrumentor, spatial_instrumentor = create_ar_instrumentation(framework)
    
    # Database operation decorator
    db_decorator = instrumentation.instrument_database_operations()
    
    @app.get("/health")
    async def health_check():
        return {"status": "healthy", "service": "localization"}
    
    @app.post("/track")
    @framework.create_service_span_decorator("localization.track_pose")
    async def track_pose(request: Request):
        """Track 6DOF pose with 60fps target"""
        
        # Use critical operation tracking for 60fps requirement
        async with framework.trace_critical_operation(
            "localization.pose_tracking",
            target_duration_ms=16  # 60fps = 16.67ms per frame
        ):
            # Simulate pose tracking
            await asyncio.sleep(0.012)  # 12ms processing (under 16ms target)
            
            return {
                "pose": {
                    "position": [0.1, 0.2, 0.3],
                    "rotation": [0.0, 0.0, 0.0, 1.0]
                },
                "tracking_state": "tracking",
                "confidence": 0.95
            }
    
    @db_decorator("select")
    async def get_map_features(map_id: str):
        """Database operation with instrumentation"""
        # Simulate database query
        await asyncio.sleep(0.005)
        return {"features": [], "count": 0}
    
    return app

# =================== VPS ENGINE INTEGRATION ===================

def create_instrumented_vps_engine() -> FastAPI:
    """Create fully instrumented VPS Engine"""
    
    framework, instrumentation = create_service_instrumentation(
        service_type=ServiceType.VPS_ENGINE,
        service_version="2.0.0",
        environment="production",
        performance_tier=PerformanceTier.HIGH_PERFORMANCE
    )
    
    app = FastAPI(
        title="VOXAR VPS Engine",
        version="2.0.0",
        description="Visual Positioning System"
    )
    
    # Instrument with enterprise telemetry
    instrumentation.instrument_fastapi_app(app)
    
    # Create spatial computing instrumentor
    _, spatial_instrumentor = create_ar_instrumentation(framework)
    
    @app.get("/health")
    async def health_check():
        return {"status": "healthy", "service": "vps-engine"}
    
    @app.post("/reconstruct")
    async def create_3d_reconstruction(
        images: list,
        quality: str = "balanced"
    ):
        """3D reconstruction with comprehensive tracking"""
        
        reconstruction_id = f"recon_{len(images)}_{quality}"
        
        # Track 3D reconstruction process
        async with spatial_instrumentor.track_3d_reconstruction(
            reconstruction_id=reconstruction_id,
            image_count=len(images),
            quality_preset=quality
        ):
            # Simulate reconstruction processing
            processing_time = len(images) * 0.1  # 100ms per image
            await asyncio.sleep(processing_time)
            
            return {
                "reconstruction_id": reconstruction_id,
                "status": "completed",
                "point_count": len(images) * 1000,
                "processing_time": processing_time
            }
    
    @app.post("/extract-features")
    async def extract_image_features(
        image_id: str,
        algorithm: str = "sift"
    ):
        """Feature extraction with tracking"""
        
        # Track feature extraction
        async with spatial_instrumentor.track_feature_extraction(
            image_id=image_id,
            algorithm=algorithm
        ):
            # Simulate feature extraction
            await asyncio.sleep(0.05)  # 50ms processing
            
            return {
                "image_id": image_id,
                "features": [{"x": 100, "y": 200}] * 500,  # 500 features
                "algorithm": algorithm
            }
    
    return app

# =================== USAGE EXAMPLE ===================

async def demonstrate_enterprise_observability():
    """Demonstrate the enterprise observability framework"""
    
    logger.info("Starting VOXAR Enterprise Observability Demonstration")
    
    # Create instrumented services
    gateway_app = create_instrumented_gateway_app()
    localization_app = create_instrumented_localization_service()
    vps_app = create_instrumented_vps_engine()
    
    logger.info("All services instrumented with enterprise-grade OpenTelemetry")
    logger.info("Telemetry flowing to:")
    logger.info("  - OpenTelemetry Collector (OTLP)")
    logger.info("  - Jaeger (Distributed Tracing)")
    logger.info("  - Prometheus (Metrics)")
    logger.info("  - Grafana Loki (Logs)")
    logger.info("  - Grafana (Dashboards)")
    
    # Services are ready for production deployment with:
    # - Distributed tracing across AR workflows
    # - AR-specific performance metrics (60fps monitoring)
    # - Spatial computing metrics (pose accuracy, tracking quality)
    # - Enterprise alerting (SLA violations, quality degradation)
    # - Comprehensive error tracking and recovery
    
    return {
        "gateway": gateway_app,
        "localization": localization_app,
        "vps": vps_app
    }

if __name__ == "__main__":
    # Run the instrumented API Gateway
    app = create_instrumented_gateway_app()
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )