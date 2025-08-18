#!/usr/bin/env python3
"""
3D Mapping Service
COLMAP-based reconstruction pipeline
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="3D Mapping Service",
    description="COLMAP-based reconstruction pipeline",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "mapping-pipeline",
        "version": "1.0.0"
    }

@app.get("/")
async def service_info():
    """Service information"""
    return {
        "service": "3D Mapping Pipeline",
        "description": "COLMAP-based 3D reconstruction",
        "endpoints": ["/health", "/maps", "/reconstruction"],
        "docs": "/docs"
    }

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8080,
        reload=True
    )