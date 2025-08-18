#!/usr/bin/env python3
"""
VOXAR Cloud Anchor Service - Persistent spatial anchors for AR
Cross-platform anchor persistence and synchronization
"""

import os
import asyncio
import logging
from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Dict, List, Optional, Any

from core.anchor_manager import AnchorManager
from core.persistence_engine import PersistenceEngine
from core.synchronization_manager import SynchronizationManager
from api.routes import router as api_router, set_services
from utils.config import settings
from utils.logging_config import setup_logging
from utils.metrics import setup_metrics

# Setup logging
setup_logging()
logger = logging.getLogger(__name__)

# Global services
anchor_manager = None
persistence_engine = None
sync_manager = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan management"""
    global anchor_manager, persistence_engine, sync_manager
    
    # Startup
    logger.info("🚀 Starting VOXAR Cloud Anchor Service...")
    try:
        # Initialize persistence engine
        persistence_engine = PersistenceEngine()
        await persistence_engine.initialize()
        
        # Initialize anchor manager
        anchor_manager = AnchorManager(persistence_engine)
        await anchor_manager.initialize()
        
        # Initialize synchronization manager
        sync_manager = SynchronizationManager(anchor_manager)
        await sync_manager.initialize()
        
        # Setup metrics
        setup_metrics()
        
        # Set services in routes module
        set_services(anchor_manager, persistence_engine, sync_manager)
        
        logger.info("✅ Cloud Anchor Service initialized successfully")
        yield
        
    except Exception as e:
        logger.error(f"❌ Failed to initialize Cloud Anchor Service: {e}")
        raise
    finally:
        # Shutdown
        logger.info("🛑 Shutting down Cloud Anchor Service...")
        if sync_manager:
            await sync_manager.shutdown()
        if anchor_manager:
            await anchor_manager.shutdown()
        if persistence_engine:
            await persistence_engine.shutdown()

# Create FastAPI app
app = FastAPI(
    title="VOXAR Cloud Anchor Service",
    description="Persistent spatial anchors for cross-platform AR experiences",
    version="1.0.0",
    docs_url="/docs" if settings.ENVIRONMENT == "development" else None,
    redoc_url="/redoc" if settings.ENVIRONMENT == "development" else None,
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(api_router, prefix="/api/v1")

# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        services_healthy = True
        services_status = {}
        
        if anchor_manager:
            services_status['anchor_manager'] = await anchor_manager.health_check()
        else:
            services_status['anchor_manager'] = False
        
        if persistence_engine:
            services_status['persistence_engine'] = await persistence_engine.health_check()
        else:
            services_status['persistence_engine'] = False
        
        if sync_manager:
            services_status['sync_manager'] = await sync_manager.health_check()
        else:
            services_status['sync_manager'] = False
        
        services_healthy = all(services_status.values())
        
        if services_healthy:
            return {
                "status": "healthy",
                "service": "cloud-anchor-service",
                "version": "1.0.0",
                "timestamp": datetime.utcnow().isoformat(),
                "services": services_status
            }
        else:
            return JSONResponse(
                status_code=503,
                content={
                    "status": "unhealthy",
                    "service": "cloud-anchor-service",
                    "services": services_status,
                    "timestamp": datetime.utcnow().isoformat()
                }
            )
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy", 
                "service": "cloud-anchor-service",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
        )

# Metrics endpoint
@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    try:
        metrics_data = {}
        
        if anchor_manager:
            metrics_data['anchors'] = await anchor_manager.get_metrics()
        
        if persistence_engine:
            metrics_data['persistence'] = await persistence_engine.get_metrics()
        
        if sync_manager:
            metrics_data['synchronization'] = await sync_manager.get_metrics()
        
        return {
            "service": "cloud-anchor-service",
            "timestamp": datetime.utcnow().isoformat(),
            "metrics": metrics_data
        }
        
    except Exception as e:
        logger.error(f"Metrics collection failed: {e}")
        return {"error": str(e)}

# Root endpoint
@app.get("/")
async def root():
    """Root endpoint with service information"""
    return {
        "service": "VOXAR Cloud Anchor Service",
        "description": "Persistent spatial anchors for AR applications",
        "version": "1.0.0",
        "status": "operational",
        "features": [
            "Cross-platform anchor persistence",
            "Real-time synchronization",
            "Spatial indexing and queries",
            "Anchor sharing and collaboration",
            "Quality tracking and optimization"
        ],
        "docs": "/docs" if settings.ENVIRONMENT == "development" else "disabled",
        "health": "/health",
        "metrics": "/metrics"
    }

# Dependency injection for services
def get_anchor_manager():
    """Get anchor manager instance"""
    if not anchor_manager:
        raise HTTPException(status_code=503, detail="Anchor manager not initialized")
    return anchor_manager

def get_persistence_engine():
    """Get persistence engine instance"""
    if not persistence_engine:
        raise HTTPException(status_code=503, detail="Persistence engine not initialized")
    return persistence_engine

def get_sync_manager():
    """Get synchronization manager instance"""
    if not sync_manager:
        raise HTTPException(status_code=503, detail="Synchronization manager not initialized")
    return sync_manager

if __name__ == "__main__":
    # Development server
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.PORT,
        reload=settings.ENVIRONMENT == "development",
        log_level=settings.LOG_LEVEL.lower(),
        access_log=True
    )