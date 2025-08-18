#!/usr/bin/env python3
"""
API Gateway - Intelligent Service Router with Enterprise Observability
Routes requests to appropriate backend services with comprehensive telemetry
"""

import sys
import os
import logging

# Add observability framework to Python path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'infrastructure', 'observability'))

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn

from services import ServiceRegistry, RequestRouter

# Import VOXAR enterprise observability
from service_instrumentation import (
    initialize_service_observability,
    ServiceType
)

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="VOXAR API Gateway",
    description="Intelligent routing for AR platform services with enterprise observability",
    version="2.0.0"
)

# Initialize enterprise observability
framework, instrumentation = initialize_service_observability(
    app=app,
    service_type=ServiceType.API_GATEWAY
)

# Import and initialize enterprise telemetry
from telemetry import (
    initialize_gateway_telemetry,
    get_gateway_telemetry,
    EnterpriseTelemetryMiddleware,
    trace_api_route,
    trace_backend_call
)

# Initialize enterprise API Gateway telemetry
gateway_telemetry = initialize_gateway_telemetry()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add enterprise telemetry middleware
if gateway_telemetry:
    app.add_middleware(EnterpriseTelemetryMiddleware, telemetry_manager=gateway_telemetry)

# Initialize service components
service_registry = ServiceRegistry()
request_router = RequestRouter(service_registry)


@app.on_event("startup")
async def startup_event():
    """Initialize routing components"""
    logger.info("Starting API Gateway")
    await service_registry.initialize()
    await request_router.initialize()
    logger.info("API Gateway ready")


@app.on_event("shutdown")
async def shutdown_event():
    """Clean shutdown"""
    logger.info("Shutting down API Gateway")
    await request_router.shutdown()
    await service_registry.shutdown()


@app.get("/health")
async def health_check():
    """Gateway health check"""
    service_status = service_registry.get_status_summary()
    
    return {
        "status": "healthy",
        "service": "api-gateway",
        "version": "2.0.0",
        "backend_services": service_status
    }


@app.get("/")
async def gateway_info():
    """Gateway information and routing rules"""
    routing_info = request_router.get_routing_info()
    
    return {
        "service": "VOXAR API Gateway", 
        "version": "2.0.0",
        "description": "Intelligent routing for AR platform services",
        "endpoints": {
            "localization": "/api/localization, /api/slam, /api/vio, /api/pose",
            "mapping": "/api/maps, /api/reconstruction", 
            "multiplayer": "/api/multiplayer, /api/auth"
        },
        "routing_info": routing_info,
        "docs": "/docs"
    }


@app.get("/services")
async def list_services():
    """List all registered services and their health status"""
    return service_registry.get_status_summary()


@app.get("/telemetry/performance")
async def get_performance_metrics():
    """Get enterprise telemetry performance summary"""
    if not gateway_telemetry:
        return {"error": "Enterprise telemetry not available"}
    
    return {
        "route_performance": gateway_telemetry.get_route_performance_summary(),
        "service_health": gateway_telemetry.get_service_health_summary(),
        "observability_status": {
            "framework_active": framework is not None,
            "telemetry_active": gateway_telemetry is not None,
            "service_name": "api-gateway",
            "performance_tier": "high_performance"
        }
    }


@app.get("/telemetry/health")
async def get_telemetry_health():
    """Get observability framework health status"""
    if not framework:
        return {"status": "error", "message": "Observability framework not initialized"}
    
    if not gateway_telemetry:
        return {"status": "warning", "message": "Gateway telemetry not available"}
    
    return {
        "status": "healthy",
        "framework": {
            "service_type": "api-gateway",
            "version": "2.0.0",
            "environment": os.getenv("ENVIRONMENT", "development"),
            "performance_tier": "high_performance"
        },
        "telemetry": {
            "active_sessions": len(framework.active_sessions),
            "service_health": gateway_telemetry.get_service_health_summary()
        },
        "exporters": {
            "otlp_collector": "http://otel-collector:4317",
            "jaeger_tracing": "http://jaeger:14250",
            "prometheus_metrics": "http://otel-collector:8889",
            "loki_logs": "http://loki:3100"
        }
    }


@app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
@trace_api_route("api_routing", "dynamic")
async def route_api_request(path: str, request: Request):
    """Route API requests to backend services with enterprise telemetry"""
    full_path = f"/api/{path}"
    
    # Determine target service for telemetry
    target_service = "unknown"
    if path.startswith("localization") or path.startswith("slam") or path.startswith("vio") or path.startswith("pose"):
        target_service = "localization"
    elif path.startswith("maps") or path.startswith("reconstruction"):
        target_service = "mapping"
    elif path.startswith("multiplayer") or path.startswith("auth"):
        target_service = "multiplayer"
    elif path.startswith("vps"):
        target_service = "vps-engine"
    elif path.startswith("anchors"):
        target_service = "cloud-anchors"
    
    # Use enterprise telemetry for routing
    if gateway_telemetry:
        async with gateway_telemetry.trace_route_operation(
            request=request,
            route_name=f"api.{path.split('/')[0]}",
            target_service=target_service,
            operation_type="dynamic_route"
        ):
            return await request_router.route_request(request, full_path)
    else:
        return await request_router.route_request(request, full_path)


if __name__ == "__main__":
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )