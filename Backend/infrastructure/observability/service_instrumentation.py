# VOXAR Service Instrumentation
# Service-specific OpenTelemetry integration for each VOXAR component

import os
import logging
from typing import Dict, Any
from fastapi import FastAPI

from telemetry_framework import (
    ServiceType,
    PerformanceTier,
    create_service_instrumentation,
    create_ar_instrumentation,
    create_enterprise_monitoring
)

logger = logging.getLogger(__name__)

# =================== SERVICE INSTRUMENTATION REGISTRY ===================

class VoxarServiceRegistry:
    """Registry for all VOXAR service instrumentations"""
    
    def __init__(self):
        self.services: Dict[str, Any] = {}
        self.frameworks: Dict[str, Any] = {}
    
    def register_service(
        self,
        service_type: ServiceType,
        app: FastAPI,
        performance_tier: PerformanceTier = PerformanceTier.STANDARD
    ):
        """Register and instrument a VOXAR service"""
        
        service_name = service_type.value
        environment = os.getenv("ENVIRONMENT", "development")
        
        # Create enterprise instrumentation
        framework, instrumentation = create_service_instrumentation(
            service_type=service_type,
            service_version="2.0.0",
            environment=environment,
            performance_tier=performance_tier
        )
        
        # Instrument the FastAPI app
        instrumentation.instrument_fastapi_app(app)
        
        # Create AR-specific instrumentors if applicable
        ar_instrumentor = None
        spatial_instrumentor = None
        if service_type in [ServiceType.LOCALIZATION, ServiceType.VPS_ENGINE, ServiceType.API_GATEWAY]:
            ar_instrumentor, spatial_instrumentor = create_ar_instrumentation(framework)
        
        # Create enterprise monitoring
        alert_manager = create_enterprise_monitoring(framework)
        
        # Store in registry
        self.services[service_name] = {
            "framework": framework,
            "instrumentation": instrumentation,
            "ar_instrumentor": ar_instrumentor,
            "spatial_instrumentor": spatial_instrumentor,
            "alert_manager": alert_manager,
            "app": app
        }
        
        self.frameworks[service_name] = framework
        
        logger.info(f"✅ Registered enterprise instrumentation for {service_name}")
        
        return framework, instrumentation
    
    def get_service_framework(self, service_name: str):
        """Get observability framework for a service"""
        return self.frameworks.get(service_name)
    
    def get_service_instrumentation(self, service_name: str):
        """Get full instrumentation suite for a service"""
        return self.services.get(service_name)
    
    def shutdown_all(self):
        """Gracefully shutdown all service instrumentations"""
        for service_name, service_data in self.services.items():
            try:
                service_data["framework"].shutdown()
                logger.info(f"✅ Shutdown telemetry for {service_name}")
            except Exception as e:
                logger.error(f"❌ Error shutting down {service_name}: {e}")

# Global service registry
service_registry = VoxarServiceRegistry()

# =================== SERVICE-SPECIFIC CONFIGURATIONS ===================

def configure_api_gateway(app: FastAPI) -> tuple:
    """Configure API Gateway with enterprise observability"""
    
    return service_registry.register_service(
        service_type=ServiceType.API_GATEWAY,
        app=app,
        performance_tier=PerformanceTier.HIGH_PERFORMANCE
    )

def configure_localization_service(app: FastAPI) -> tuple:
    """Configure Localization Service with critical performance monitoring"""
    
    return service_registry.register_service(
        service_type=ServiceType.LOCALIZATION,
        app=app,
        performance_tier=PerformanceTier.CRITICAL_60FPS
    )

def configure_vps_engine(app: FastAPI) -> tuple:
    """Configure VPS Engine with high performance monitoring"""
    
    return service_registry.register_service(
        service_type=ServiceType.VPS_ENGINE,
        app=app,
        performance_tier=PerformanceTier.HIGH_PERFORMANCE
    )

def configure_cloud_anchors(app: FastAPI) -> tuple:
    """Configure Cloud Anchors service with standard monitoring"""
    
    return service_registry.register_service(
        service_type=ServiceType.CLOUD_ANCHORS,
        app=app,
        performance_tier=PerformanceTier.STANDARD
    )

def configure_mapping_processor(app: FastAPI) -> tuple:
    """Configure Mapping Processor with background tier monitoring"""
    
    return service_registry.register_service(
        service_type=ServiceType.MAPPING_PROCESSOR,
        app=app,
        performance_tier=PerformanceTier.BACKGROUND
    )

def configure_multiplayer_service(app: FastAPI) -> tuple:
    """Configure Multiplayer service with high performance monitoring"""
    
    return service_registry.register_service(
        service_type=ServiceType.MULTIPLAYER,
        app=app,
        performance_tier=PerformanceTier.HIGH_PERFORMANCE
    )

# =================== ENVIRONMENT-SPECIFIC CONFIGURATIONS ===================

def get_performance_tier_for_environment(service_type: ServiceType) -> PerformanceTier:
    """Get appropriate performance tier based on environment and service"""
    
    environment = os.getenv("ENVIRONMENT", "development").lower()
    
    if environment == "production":
        # Production performance tiers
        if service_type == ServiceType.LOCALIZATION:
            return PerformanceTier.CRITICAL_60FPS
        elif service_type in [ServiceType.API_GATEWAY, ServiceType.VPS_ENGINE, ServiceType.MULTIPLAYER]:
            return PerformanceTier.HIGH_PERFORMANCE
        else:
            return PerformanceTier.STANDARD
    
    elif environment == "staging":
        # Staging performance tiers (slightly relaxed)
        if service_type == ServiceType.LOCALIZATION:
            return PerformanceTier.HIGH_PERFORMANCE
        else:
            return PerformanceTier.STANDARD
    
    else:
        # Development performance tiers (relaxed for debugging)
        return PerformanceTier.STANDARD

def get_sampling_rate_for_environment() -> float:
    """Get appropriate trace sampling rate based on environment"""
    
    environment = os.getenv("ENVIRONMENT", "development").lower()
    
    sampling_rates = {
        "production": 0.01,    # 1% sampling in production
        "staging": 0.1,        # 10% sampling in staging
        "development": 1.0     # 100% sampling in development
    }
    
    return sampling_rates.get(environment, 1.0)

# =================== INSTRUMENTATION HELPERS ===================

def add_custom_metrics_endpoint(app: FastAPI, service_name: str):
    """Add custom metrics endpoint for Prometheus scraping"""
    
    @app.get("/metrics")
    async def get_prometheus_metrics():
        """Prometheus metrics endpoint"""
        try:
            # Import prometheus_client here to avoid import issues
            import prometheus_client
            from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
            
            # Generate Prometheus metrics
            metrics_data = generate_latest()
            
            return Response(
                content=metrics_data,
                media_type=CONTENT_TYPE_LATEST
            )
        except ImportError:
            return {"error": "Prometheus client not available"}
        except Exception as e:
            logger.error(f"Error generating metrics: {e}")
            return {"error": "Metrics generation failed"}

def add_health_check_with_telemetry(app: FastAPI, service_name: str):
    """Add health check endpoint with telemetry"""
    
    @app.get("/health")
    async def health_check_with_telemetry():
        """Health check with observability status"""
        
        framework = service_registry.get_service_framework(service_name)
        
        health_status = {
            "status": "healthy",
            "service": service_name,
            "version": "2.0.0",
            "observability": {
                "telemetry_enabled": framework is not None,
                "tracing_configured": True,
                "metrics_configured": True,
                "environment": os.getenv("ENVIRONMENT", "development")
            }
        }
        
        return health_status

def add_observability_endpoints(app: FastAPI, service_name: str):
    """Add comprehensive observability endpoints"""
    
    add_health_check_with_telemetry(app, service_name)
    add_custom_metrics_endpoint(app, service_name)
    
    @app.get("/ready")
    async def readiness_check():
        """Kubernetes readiness probe"""
        return {"status": "ready", "service": service_name}
    
    @app.get("/live")
    async def liveness_check():
        """Kubernetes liveness probe"""
        return {"status": "alive", "service": service_name}

# =================== INITIALIZATION HELPER ===================

def initialize_service_observability(
    app: FastAPI,
    service_type: ServiceType,
    custom_performance_tier: PerformanceTier = None
) -> tuple:
    """
    One-stop initialization for VOXAR service observability
    
    This function handles:
    - Environment-specific configuration
    - Performance tier selection
    - Service registration
    - Endpoint creation
    - Enterprise monitoring setup
    """
    
    # Determine performance tier
    performance_tier = custom_performance_tier or get_performance_tier_for_environment(service_type)
    
    # Register and configure service
    framework, instrumentation = service_registry.register_service(
        service_type=service_type,
        app=app,
        performance_tier=performance_tier
    )
    
    # Add observability endpoints
    add_observability_endpoints(app, service_type.value)
    
    logger.info(f"🚀 Enterprise observability initialized for {service_type.value}")
    logger.info(f"📊 Performance tier: {performance_tier.value}")
    logger.info(f"🌍 Environment: {os.getenv('ENVIRONMENT', 'development')}")
    
    return framework, instrumentation

# =================== CLEANUP HANDLERS ===================

import atexit
import signal

def setup_graceful_shutdown():
    """Setup graceful shutdown for all services"""
    
    def shutdown_handler(signum=None, frame=None):
        logger.info("🔄 Gracefully shutting down VOXAR observability...")
        service_registry.shutdown_all()
        logger.info("✅ VOXAR observability shutdown complete")
    
    # Register shutdown handlers
    atexit.register(shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)
    signal.signal(signal.SIGINT, shutdown_handler)

# Initialize shutdown handlers
setup_graceful_shutdown()