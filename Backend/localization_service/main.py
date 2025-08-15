#!/usr/bin/env python3
"""
Spatial Platform - Localization Service
AR tracking and positioning service with SLAM integration
"""

from fastapi import FastAPI, HTTPException, File, UploadFile, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, List, Optional, Any
import uvicorn
import os
import json
import time
import numpy as np
import cv2
import asyncio
import logging
from datetime import datetime

# Import our SLAM integration
from slam_integration import (
    create_slam_system, 
    StellaSLAMWrapper, 
    CameraFrame, 
    Pose, 
    SLAMConfig
)

# Import VIO integration
from vio_integration import (
    create_vio_processor,
    VIOProcessor,
    VIODataPacket,
    VIOState,
    IMUReading,
    CameraIntrinsics as VIOCameraIntrinsics
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Spatial Platform Localization Service",
    description="AR tracking and positioning service with SLAM",
    version="2.0.0"
)

# CORS middleware for Unity integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global system instances
slam_system: Optional[StellaSLAMWrapper] = None
vio_processor: Optional[VIOProcessor] = None

# Data models
class CameraIntrinsics(BaseModel):
    fx: float
    fy: float
    cx: float
    cy: float
    width: int
    height: int
    fps: float = 30.0
    k1: float = 0.0
    k2: float = 0.0
    p1: float = 0.0
    p2: float = 0.0
    k3: float = 0.0

class SLAMInitRequest(BaseModel):
    camera_intrinsics: CameraIntrinsics
    enable_loop_closure: bool = True
    enable_relocalization: bool = True
    map_id: Optional[str] = None

class TrackingFrame(BaseModel):
    timestamp: float
    image_data: str  # Base64 encoded image
    camera_id: int = 0

class PoseResponse(BaseModel):
    timestamp: float
    position: List[float]  # [x, y, z]
    rotation: List[float]  # [qw, qx, qy, qz]
    confidence: float
    tracking_state: str

class SLAMStatus(BaseModel):
    is_initialized: bool
    is_tracking: bool
    frame_count: int
    fps: float
    last_pose_time: float
    current_pose: Optional[PoseResponse]

# VIO Data Models
class IMUReadingModel(BaseModel):
    timestamp: float
    acceleration: List[float]  # [x, y, z] m/s²
    gyroscope: List[float]     # [x, y, z] rad/s
    magnetometer: List[float]  # [x, y, z] μT
    temperature: float = 0.0
    is_valid: bool = True

class VIOCameraIntrinsics(BaseModel):
    fx: float
    fy: float
    cx: float
    cy: float
    k1: float = 0.0
    k2: float = 0.0
    p1: float = 0.0
    p2: float = 0.0
    k3: float = 0.0
    width: int = 640
    height: int = 480

class VIODataPacketModel(BaseModel):
    timestamp: float
    imu_readings: List[IMUReadingModel]
    camera_frame_base64: Optional[str] = None
    camera_params: VIOCameraIntrinsics
    sequence_number: int

class VIOPoseResponse(BaseModel):
    timestamp: float
    position: List[float]        # [x, y, z]
    rotation: List[float]        # [qw, qx, qy, qz]
    velocity: List[float]        # [x, y, z]
    angular_velocity: List[float] # [x, y, z]
    confidence: float
    tracking_state: str
    covariance: List[List[float]]  # Flattened covariance matrix

class VIOResponse(BaseModel):
    success: bool
    message: str
    pose_estimate: Optional[VIOPoseResponse]
    processing_time: float
    sequence_number: int

class VIOStatus(BaseModel):
    is_initialized: bool
    frame_count: int
    avg_processing_time_ms: float
    current_confidence: float
    tracking_state: str

# API Endpoints

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "localization-service",
        "version": "2.0.0",
        "slam_available": slam_system is not None,
        "slam_tracking": slam_system.is_tracking if slam_system else False
    }

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Spatial Platform Localization Service with SLAM",
        "docs": "/docs",
        "health": "/health",
        "slam_endpoints": [
            "/slam/initialize",
            "/slam/start",
            "/slam/stop",
            "/slam/track",
            "/slam/status",
            "/slam/save_map",
            "/slam/load_map"
        ]
    }

@app.post("/slam/initialize")
async def initialize_slam(request: SLAMInitRequest):
    """Initialize SLAM system with camera parameters"""
    global slam_system
    
    try:
        logger.info("Initializing SLAM system")
        
        # Convert camera intrinsics to config format
        camera_config = {
            "fx": request.camera_intrinsics.fx,
            "fy": request.camera_intrinsics.fy,
            "cx": request.camera_intrinsics.cx,
            "cy": request.camera_intrinsics.cy,
            "width": request.camera_intrinsics.width,
            "height": request.camera_intrinsics.height,
            "fps": request.camera_intrinsics.fps,
            "k1": request.camera_intrinsics.k1,
            "k2": request.camera_intrinsics.k2,
            "p1": request.camera_intrinsics.p1,
            "p2": request.camera_intrinsics.p2,
            "k3": request.camera_intrinsics.k3,
        }
        
        # Create SLAM system
        slam_system = create_slam_system(
            camera_config=camera_config,
            enable_loop_closure=request.enable_loop_closure,
            enable_relocalization=request.enable_relocalization
        )
        
        # Initialize the system
        if not slam_system.initialize():
            raise HTTPException(status_code=500, detail="Failed to initialize SLAM system")
        
        # Load existing map if provided
        if request.map_id:
            map_path = f"/app/maps/{request.map_id}.map"
            if os.path.exists(map_path):
                slam_system.load_map(map_path)
                logger.info(f"Loaded existing map: {request.map_id}")
        
        return {
            "status": "success",
            "message": "SLAM system initialized successfully",
            "camera_config": camera_config,
            "map_loaded": request.map_id if request.map_id and os.path.exists(f"/app/maps/{request.map_id}.map") else None
        }
        
    except Exception as e:
        logger.error(f"SLAM initialization failed: {e}")
        raise HTTPException(status_code=500, detail=f"SLAM initialization failed: {str(e)}")

@app.post("/slam/start")
async def start_tracking():
    """Start SLAM tracking"""
    global slam_system
    
    if not slam_system:
        raise HTTPException(status_code=400, detail="SLAM system not initialized")
    
    try:
        if slam_system.start_tracking():
            return {
                "status": "success",
                "message": "SLAM tracking started"
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to start SLAM tracking")
    except Exception as e:
        logger.error(f"Failed to start tracking: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start tracking: {str(e)}")

@app.post("/slam/stop")
async def stop_tracking():
    """Stop SLAM tracking"""
    global slam_system
    
    if not slam_system:
        raise HTTPException(status_code=400, detail="SLAM system not initialized")
    
    try:
        slam_system.stop_tracking()
        return {
            "status": "success",
            "message": "SLAM tracking stopped"
        }
    except Exception as e:
        logger.error(f"Failed to stop tracking: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to stop tracking: {str(e)}")

@app.post("/slam/track")
async def track_frame(frame: TrackingFrame) -> PoseResponse:
    """Process camera frame and return pose estimate"""
    global slam_system
    
    if not slam_system or not slam_system.is_tracking:
        raise HTTPException(status_code=400, detail="SLAM system not tracking")
    
    try:
        # Decode base64 image
        import base64
        image_bytes = base64.b64decode(frame.image_data)
        image_array = np.frombuffer(image_bytes, dtype=np.uint8)
        image = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
        
        if image is None:
            raise HTTPException(status_code=400, detail="Invalid image data")
        
        # Create camera frame
        camera_frame = CameraFrame(
            timestamp=frame.timestamp,
            image=image,
            camera_id=frame.camera_id
        )
        
        # Process frame
        pose = slam_system.process_frame(camera_frame)
        
        if pose is None:
            raise HTTPException(status_code=500, detail="Failed to track frame")
        
        return PoseResponse(
            timestamp=pose.timestamp,
            position=pose.position.tolist(),
            rotation=pose.rotation.tolist(),
            confidence=pose.confidence,
            tracking_state=pose.tracking_state
        )
        
    except Exception as e:
        error_msg = str(e) if str(e) else f"{type(e).__name__}: Unknown error"
        logger.error(f"Frame tracking failed: {error_msg}")
        logger.exception("Full traceback:")
        raise HTTPException(status_code=500, detail=f"Frame tracking failed: {error_msg}")

@app.get("/slam/status")
async def get_slam_status() -> SLAMStatus:
    """Get current SLAM system status"""
    global slam_system
    
    if not slam_system:
        return SLAMStatus(
            is_initialized=False,
            is_tracking=False,
            frame_count=0,
            fps=0.0,
            last_pose_time=0.0,
            current_pose=None
        )
    
    try:
        status = slam_system.get_tracking_state()
        
        current_pose = None
        if status["current_pose"] and status["current_pose"]["position"]:
            current_pose = PoseResponse(
                timestamp=status["current_pose"]["timestamp"],
                position=status["current_pose"]["position"],
                rotation=status["current_pose"]["rotation"],
                confidence=status["current_pose"]["confidence"],
                tracking_state=status["current_pose"]["tracking_state"]
            )
        
        return SLAMStatus(
            is_initialized=status["is_initialized"],
            is_tracking=status["is_tracking"],
            frame_count=status["frame_count"],
            fps=status["fps"],
            last_pose_time=status["last_pose_time"],
            current_pose=current_pose
        )
        
    except Exception as e:
        logger.error(f"Failed to get SLAM status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get SLAM status: {str(e)}")

@app.post("/slam/save_map")
async def save_map(map_id: str, background_tasks: BackgroundTasks):
    """Save current SLAM map"""
    global slam_system
    
    if not slam_system:
        raise HTTPException(status_code=400, detail="SLAM system not initialized")
    
    try:
        # Create maps directory if it doesn't exist
        os.makedirs("/app/maps", exist_ok=True)
        
        map_path = f"/app/maps/{map_id}.map"
        
        # Save map in background
        def save_map_task():
            slam_system.save_map(map_path)
            logger.info(f"Map saved: {map_id}")
        
        background_tasks.add_task(save_map_task)
        
        return {
            "status": "success",
            "message": f"Map save initiated: {map_id}",
            "map_path": map_path
        }
        
    except Exception as e:
        logger.error(f"Failed to save map: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to save map: {str(e)}")

@app.post("/slam/load_map")
async def load_map(map_id: str):
    """Load existing SLAM map"""
    global slam_system
    
    if not slam_system:
        raise HTTPException(status_code=400, detail="SLAM system not initialized")
    
    try:
        map_path = f"/app/maps/{map_id}.map"
        
        if not os.path.exists(map_path):
            raise HTTPException(status_code=404, detail=f"Map not found: {map_id}")
        
        if slam_system.load_map(map_path):
            return {
                "status": "success",
                "message": f"Map loaded successfully: {map_id}",
                "map_path": map_path
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to load map")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to load map: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to load map: {str(e)}")

@app.get("/slam/maps")
async def list_maps():
    """List available SLAM maps"""
    try:
        maps_dir = "/app/maps"
        if not os.path.exists(maps_dir):
            return {"maps": []}
        
        maps = []
        for filename in os.listdir(maps_dir):
            if filename.endswith('.map'):
                map_id = filename[:-4]  # Remove .map extension
                map_path = os.path.join(maps_dir, filename)
                stat = os.stat(map_path)
                
                maps.append({
                    "map_id": map_id,
                    "size_bytes": stat.st_size,
                    "created_at": datetime.fromtimestamp(stat.st_ctime).isoformat(),
                    "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat()
                })
        
        return {"maps": maps}
        
    except Exception as e:
        logger.error(f"Failed to list maps: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list maps: {str(e)}")

# VIO API Endpoints

@app.post("/vio/initialize")
async def initialize_vio():
    """Initialize VIO processor"""
    global vio_processor
    
    try:
        vio_processor = create_vio_processor()
        logger.info("VIO processor initialized")
        
        return {
            "status": "success",
            "message": "VIO processor initialized successfully"
        }
        
    except Exception as e:
        logger.error(f"VIO initialization failed: {e}")
        raise HTTPException(status_code=500, detail=f"VIO initialization failed: {str(e)}")

@app.post("/vio/process")
async def process_vio_data(packet: VIODataPacketModel) -> VIOResponse:
    """Process VIO data packet and return pose estimate"""
    global vio_processor
    
    if not vio_processor:
        # Auto-initialize if not already done
        vio_processor = create_vio_processor()
        logger.info("VIO processor auto-initialized")
    
    try:
        start_time = time.time()
        
        # Convert API model to internal format
        imu_readings = []
        for imu_model in packet.imu_readings:
            imu_reading = IMUReading(
                timestamp=imu_model.timestamp,
                acceleration=np.array(imu_model.acceleration),
                gyroscope=np.array(imu_model.gyroscope),
                magnetometer=np.array(imu_model.magnetometer),
                temperature=imu_model.temperature,
                is_valid=imu_model.is_valid
            )
            imu_readings.append(imu_reading)
        
        # Convert camera intrinsics
        camera_params = VIOCameraIntrinsics(
            fx=packet.camera_params.fx,
            fy=packet.camera_params.fy,
            cx=packet.camera_params.cx,
            cy=packet.camera_params.cy,
            k1=packet.camera_params.k1,
            k2=packet.camera_params.k2,
            p1=packet.camera_params.p1,
            p2=packet.camera_params.p2,
            k3=packet.camera_params.k3,
            width=packet.camera_params.width,
            height=packet.camera_params.height
        )
        
        # Create internal VIO packet
        vio_packet = VIODataPacket(
            timestamp=packet.timestamp,
            imu_readings=imu_readings,
            camera_frame_base64=packet.camera_frame_base64,
            camera_params=camera_params,
            sequence_number=packet.sequence_number
        )
        
        # Process VIO data
        state = vio_processor.process_packet(vio_packet)
        
        processing_time = (time.time() - start_time) * 1000  # Convert to ms
        
        # Convert state to response format
        pose_response = VIOPoseResponse(
            timestamp=state.timestamp,
            position=state.position.tolist(),
            rotation=state.rotation.tolist(),
            velocity=state.velocity.tolist(),
            angular_velocity=state.angular_velocity.tolist(),
            confidence=state.confidence,
            tracking_state=state.tracking_state,
            covariance=state.covariance.tolist()
        )
        
        return VIOResponse(
            success=True,
            message="VIO processing completed",
            pose_estimate=pose_response,
            processing_time=processing_time,
            sequence_number=packet.sequence_number
        )
        
    except Exception as e:
        error_msg = str(e) if str(e) else f"{type(e).__name__}: Unknown error"
        logger.error(f"VIO processing failed: {error_msg}")
        logger.exception("Full traceback:")
        
        return VIOResponse(
            success=False,
            message=f"VIO processing failed: {error_msg}",
            pose_estimate=None,
            processing_time=0.0,
            sequence_number=packet.sequence_number
        )

@app.get("/vio/status")
async def get_vio_status() -> VIOStatus:
    """Get current VIO system status"""
    global vio_processor
    
    if not vio_processor:
        return VIOStatus(
            is_initialized=False,
            frame_count=0,
            avg_processing_time_ms=0.0,
            current_confidence=0.0,
            tracking_state="not_initialized"
        )
    
    try:
        stats = vio_processor.get_statistics()
        
        return VIOStatus(
            is_initialized=stats.get("is_initialized", False),
            frame_count=stats.get("frame_count", 0),
            avg_processing_time_ms=stats.get("avg_processing_time_ms", 0.0),
            current_confidence=stats.get("current_confidence", 0.0),
            tracking_state=stats.get("tracking_state", "unknown")
        )
        
    except Exception as e:
        logger.error(f"Failed to get VIO status: {e}")
        return VIOStatus(
            is_initialized=False,
            frame_count=0,
            avg_processing_time_ms=0.0,
            current_confidence=0.0,
            tracking_state="error"
        )

@app.post("/vio/reset")
async def reset_vio():
    """Reset VIO processor state"""
    global vio_processor
    
    try:
        if vio_processor:
            vio_processor.reset()
        else:
            vio_processor = create_vio_processor()
        
        return {
            "status": "success",
            "message": "VIO processor reset successfully"
        }
        
    except Exception as e:
        logger.error(f"VIO reset failed: {e}")
        raise HTTPException(status_code=500, detail=f"VIO reset failed: {str(e)}")

# Cleanup on shutdown
@app.on_event("shutdown")
async def shutdown_event():
    """Clean shutdown of systems"""
    global slam_system, vio_processor
    
    if slam_system:
        slam_system.shutdown()
        logger.info("SLAM system shutdown completed")
        
    if vio_processor:
        vio_processor.reset()
        vio_processor = None
        logger.info("VIO processor shutdown completed")

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8080,
        reload=True
    )