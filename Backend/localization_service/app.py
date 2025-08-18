#!/usr/bin/env python3
"""
AR Localization Service with Enterprise Observability
Main FastAPI application for spatial tracking with 60fps performance monitoring
"""

import sys
import os
import logging

# Add observability framework to Python path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'infrastructure', 'observability'))

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, List, Optional, Any
import uvicorn
from datetime import datetime

from core.slam_tracker import SlamTracker
from core.vio_tracker import VioTracker
from core.pose_manager import PoseManager
from api.routes import setup_routes
from integrations.nakama_client import NakamaClient

# Import VOXAR enterprise observability
from service_instrumentation import (
    initialize_service_observability,
    ServiceType,
    PerformanceTier
)

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="AR Localization Service",
    description="Spatial tracking with SLAM and VIO - 60fps performance monitoring",
    version="2.1.0"
)

# Initialize enterprise observability with critical 60fps performance tier
framework, instrumentation = initialize_service_observability(
    app=app,
    service_type=ServiceType.LOCALIZATION,
    custom_performance_tier=PerformanceTier.CRITICAL_60FPS
)

# Add CORS for Unity clients
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global tracking components
slam_tracker = SlamTracker()
vio_tracker = VioTracker()
pose_manager = PoseManager()
nakama_client = NakamaClient()


@app.on_event("startup")
async def startup_event():
    """Initialize tracking systems on startup"""
    logger.info("Starting AR localization service")
    
    # Initialize VIO (doesn't need camera config)
    if vio_tracker.initialize():
        logger.info("VIO system ready")
    else:
        logger.warning("VIO initialization failed")
    
    # Initialize Nakama integration
    try:
        await nakama_client.initialize()
        logger.info("Nakama integration ready")
    except Exception as e:
        logger.warning(f"Nakama integration failed: {e}")


@app.on_event("shutdown")
async def shutdown_event():
    """Clean shutdown of tracking systems"""
    logger.info("Shutting down localization service")
    
    slam_tracker.stop_tracking()
    pose_manager.reset_tracking()
    await nakama_client.shutdown()


# Add all API routes
setup_routes(app, slam_tracker, vio_tracker, pose_manager, nakama_client)


if __name__ == "__main__":
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8080,
        reload=True
    )