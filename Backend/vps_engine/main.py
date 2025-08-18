#!/usr/bin/env python3
"""
VOXAR VPS Engine - Visual Positioning System
High-precision spatial localization service for AR applications
"""

import os
import asyncio
import logging
from fastapi import FastAPI, HTTPException, UploadFile, File, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn
from contextlib import asynccontextmanager

from core.vps_engine import VPSEngine
from core.pose_estimator import PoseEstimator
from core.map_matcher import MapMatcher
from api.routes import router as api_router
from utils.config import settings
from utils.logging_config import setup_logging
from utils.metrics import setup_metrics

# Setup logging
setup_logging()
logger = logging.getLogger(__name__)

# Global VPS engine instance
vps_engine = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan management"""
    global vps_engine
    
    # Startup
    logger.info("🚀 Starting VOXAR VPS Engine...")
    try:
        # Initialize VPS engine
        vps_engine = VPSEngine()
        await vps_engine.initialize()
        
        # Setup metrics
        setup_metrics()
        
        logger.info("✅ VPS Engine initialized successfully")
        yield
        
    except Exception as e:
        logger.error(f"❌ Failed to initialize VPS Engine: {e}")
        raise
    finally:
        # Shutdown
        logger.info("🛑 Shutting down VPS Engine...")
        if vps_engine:
            await vps_engine.shutdown()

# Create FastAPI app
app = FastAPI(
    title="VOXAR VPS Engine",
    description="Visual Positioning System for centimeter-level AR localization",
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
        if vps_engine and await vps_engine.health_check():
            return {
                "status": "healthy",
                "service": "vps-engine",
                "version": "1.0.0",
                "timestamp": settings.get_timestamp(),
                "engine_status": "operational"
            }
        else:
            return JSONResponse(
                status_code=503,
                content={
                    "status": "unhealthy",
                    "service": "vps-engine",
                    "error": "VPS engine not ready"
                }
            )
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy", 
                "service": "vps-engine",
                "error": str(e)
            }
        )

# Metrics endpoint
@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    if vps_engine:
        return await vps_engine.get_metrics()
    return {"error": "VPS engine not initialized"}

# Root endpoint
@app.get("/")
async def root():
    """Root endpoint with service information"""
    return {
        "service": "VOXAR VPS Engine",
        "description": "Visual Positioning System for AR applications",
        "version": "1.0.0",
        "status": "operational" if vps_engine else "initializing",
        "docs": "/docs" if settings.ENVIRONMENT == "development" else "disabled",
        "health": "/health",
        "metrics": "/metrics"
    }

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