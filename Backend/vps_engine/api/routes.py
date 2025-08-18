"""
VPS Engine API Routes
RESTful API endpoints for visual positioning system
"""

import logging
import asyncio
from datetime import datetime
from typing import Optional, List, Dict, Any
import numpy as np
import cv2
import base64
from io import BytesIO
from PIL import Image

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, BackgroundTasks, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, validator

# Import from parent modules (will be available when running)
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from core.vps_engine import VPSEngine
from utils.auth import verify_api_key
from utils.config import settings

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(tags=["VPS Engine"])

# Pydantic models
class LocalizationRequest(BaseModel):
    """Request model for VPS localization"""
    image_base64: str = Field(..., description="Base64 encoded image")
    camera_intrinsics: List[List[float]] = Field(..., description="3x3 camera intrinsic matrix")
    approximate_latitude: Optional[float] = Field(None, description="Approximate GPS latitude")
    approximate_longitude: Optional[float] = Field(None, description="Approximate GPS longitude")
    map_id: Optional[str] = Field(None, description="Specific map ID to localize against")
    quality_threshold: Optional[float] = Field(0.7, description="Minimum quality threshold")

    @validator('camera_intrinsics')
    def validate_camera_intrinsics(cls, v):
        if len(v) != 3 or any(len(row) != 3 for row in v):
            raise ValueError('Camera intrinsics must be 3x3 matrix')
        return v

class LocalizationResponse(BaseModel):
    """Response model for VPS localization"""
    success: bool
    pose: Optional[Dict[str, Any]] = None
    confidence: Optional[float] = None
    error_estimate: Optional[float] = None
    processing_time: Optional[float] = None
    map_id: Optional[str] = None
    feature_matches: Optional[int] = None
    quality_score: Optional[float] = None
    timestamp: str
    message: Optional[str] = None

class MapUploadRequest(BaseModel):
    """Request model for map upload"""
    map_name: str = Field(..., description="Name for the map")
    location_latitude: Optional[float] = Field(None, description="Map location latitude")
    location_longitude: Optional[float] = Field(None, description="Map location longitude")
    description: Optional[str] = Field(None, description="Map description")

class StatusResponse(BaseModel):
    """Response model for service status"""
    status: str
    uptime: float
    performance_stats: Dict[str, Any]
    engine_health: bool
    timestamp: str

# Global VPS engine reference (will be injected)
vps_engine: Optional[VPSEngine] = None

def get_vps_engine():
    """Dependency to get VPS engine instance"""
    global vps_engine
    if not vps_engine:
        raise HTTPException(status_code=503, detail="VPS Engine not initialized")
    return vps_engine

@router.post("/localize", response_model=LocalizationResponse)
async def localize_image(
    request: LocalizationRequest,
    engine: VPSEngine = Depends(get_vps_engine),
    api_key: str = Depends(verify_api_key)
):
    """
    Perform visual localization on uploaded image
    Returns 6DOF camera pose with confidence metrics
    """
    try:
        start_time = datetime.utcnow()
        
        # Decode base64 image
        try:
            image_data = base64.b64decode(request.image_base64)
            image = Image.open(BytesIO(image_data))
            image_np = np.array(image.convert('RGB'))
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid image data: {e}")
        
        # Convert camera intrinsics to numpy array
        camera_intrinsics = np.array(request.camera_intrinsics, dtype=np.float32)
        
        # Prepare approximate location
        approximate_location = None
        if request.approximate_latitude is not None and request.approximate_longitude is not None:
            approximate_location = (request.approximate_latitude, request.approximate_longitude)
        
        # Perform localization
        result = await engine.localize(
            image=image_np,
            camera_intrinsics=camera_intrinsics,
            approximate_location=approximate_location,
            map_id=request.map_id
        )
        
        # Check quality threshold
        if result.quality_score < request.quality_threshold:
            logger.warning(f"Localization quality below threshold: {result.quality_score}")
        
        # Convert pose to readable format
        from core.pose_estimator import PoseEstimator
        pose_estimator = PoseEstimator()
        pose_components = pose_estimator.matrix_to_pose_components(result.pose)
        
        processing_time = (datetime.utcnow() - start_time).total_seconds()
        
        return LocalizationResponse(
            success=True,
            pose=pose_components,
            confidence=result.confidence,
            error_estimate=result.error_estimate,
            processing_time=processing_time,
            map_id=result.map_id,
            feature_matches=result.feature_matches,
            quality_score=result.quality_score,
            timestamp=datetime.utcnow().isoformat(),
            message="Localization successful"
        )
        
    except ValueError as e:
        logger.warning(f"Localization failed: {e}")
        return LocalizationResponse(
            success=False,
            timestamp=datetime.utcnow().isoformat(),
            message=str(e)
        )
    except Exception as e:
        logger.error(f"Localization error: {e}")
        raise HTTPException(status_code=500, detail=f"Localization failed: {e}")

@router.post("/localize/upload", response_model=LocalizationResponse)
async def localize_upload(
    image: UploadFile = File(..., description="Image file for localization"),
    camera_intrinsics: str = Form(..., description="JSON string of 3x3 camera intrinsic matrix"),
    approximate_latitude: Optional[float] = Form(None),
    approximate_longitude: Optional[float] = Form(None),
    map_id: Optional[str] = Form(None),
    quality_threshold: float = Form(0.7),
    engine: VPSEngine = Depends(get_vps_engine),
    api_key: str = Depends(verify_api_key)
):
    """
    Perform visual localization with file upload
    Alternative endpoint for direct file upload
    """
    try:
        import json
        
        # Validate file type
        if not image.content_type.startswith('image/'):
            raise HTTPException(status_code=400, detail="File must be an image")
        
        # Read and process image
        image_data = await image.read()
        image_pil = Image.open(BytesIO(image_data))
        image_np = np.array(image_pil.convert('RGB'))
        
        # Parse camera intrinsics
        try:
            intrinsics_data = json.loads(camera_intrinsics)
            camera_intrinsics_np = np.array(intrinsics_data, dtype=np.float32)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid camera intrinsics: {e}")
        
        # Prepare approximate location
        approximate_location = None
        if approximate_latitude is not None and approximate_longitude is not None:
            approximate_location = (approximate_latitude, approximate_longitude)
        
        # Perform localization
        result = await engine.localize(
            image=image_np,
            camera_intrinsics=camera_intrinsics_np,
            approximate_location=approximate_location,
            map_id=map_id
        )
        
        # Convert pose to readable format
        from core.pose_estimator import PoseEstimator
        pose_estimator = PoseEstimator()
        pose_components = pose_estimator.matrix_to_pose_components(result.pose)
        
        return LocalizationResponse(
            success=True,
            pose=pose_components,
            confidence=result.confidence,
            error_estimate=result.error_estimate,
            processing_time=result.processing_time,
            map_id=result.map_id,
            feature_matches=result.feature_matches,
            quality_score=result.quality_score,
            timestamp=datetime.utcnow().isoformat(),
            message="Localization successful"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upload localization error: {e}")
        raise HTTPException(status_code=500, detail=f"Localization failed: {e}")

@router.get("/status", response_model=StatusResponse)
async def get_status(
    engine: VPSEngine = Depends(get_vps_engine),
    api_key: str = Depends(verify_api_key)
):
    """Get VPS engine status and performance metrics"""
    try:
        performance_stats = await engine.get_performance_stats()
        engine_health = await engine.health_check()
        
        return StatusResponse(
            status="operational" if engine_health else "degraded",
            uptime=performance_stats.get('uptime', 0),
            performance_stats=performance_stats,
            engine_health=engine_health,
            timestamp=datetime.utcnow().isoformat()
        )
        
    except Exception as e:
        logger.error(f"Status check error: {e}")
        raise HTTPException(status_code=500, detail=f"Status check failed: {e}")

@router.get("/maps")
async def list_maps(
    engine: VPSEngine = Depends(get_vps_engine),
    api_key: str = Depends(verify_api_key)
):
    """List available maps for localization"""
    try:
        # This would query the database for available maps
        maps = await engine.db_service.get_available_maps()
        
        return {
            "maps": maps,
            "total_count": len(maps),
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"List maps error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list maps: {e}")

@router.post("/maps/upload")
async def upload_map(
    background_tasks: BackgroundTasks,
    request: MapUploadRequest,
    point_cloud: UploadFile = File(..., description="Point cloud file (.ply or .pcd)"),
    images: List[UploadFile] = File(..., description="Reference images"),
    engine: VPSEngine = Depends(get_vps_engine),
    api_key: str = Depends(verify_api_key)
):
    """
    Upload a new map for VPS localization
    Processes point cloud and reference images
    """
    try:
        # Validate files
        if not point_cloud.content_type.endswith(('ply', 'pcd', 'pts')):
            raise HTTPException(status_code=400, detail="Point cloud must be .ply, .pcd, or .pts file")
        
        for image_file in images:
            if not image_file.content_type.startswith('image/'):
                raise HTTPException(status_code=400, detail="All reference files must be images")
        
        # Generate map ID
        map_id = f"map_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        
        # Store files and start background processing
        background_tasks.add_task(
            _process_map_upload,
            map_id,
            request,
            point_cloud,
            images,
            engine
        )
        
        return {
            "message": "Map upload started",
            "map_id": map_id,
            "status": "processing",
            "estimated_completion": "5-15 minutes",
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Map upload error: {e}")
        raise HTTPException(status_code=500, detail=f"Map upload failed: {e}")

async def _process_map_upload(
    map_id: str,
    request: MapUploadRequest,
    point_cloud: UploadFile,
    images: List[UploadFile],
    engine: VPSEngine
):
    """Background task to process uploaded map"""
    try:
        logger.info(f"Processing map upload: {map_id}")
        
        # Store point cloud
        point_cloud_data = await point_cloud.read()
        await engine.storage_service.store_point_cloud(map_id, point_cloud_data)
        
        # Store reference images
        for i, image_file in enumerate(images):
            image_data = await image_file.read()
            await engine.storage_service.store_reference_image(map_id, f"ref_{i}", image_data)
        
        # Process map (extract features, build index)
        await engine.map_matcher.process_new_map(map_id, request)
        
        logger.info(f"Map processing completed: {map_id}")
        
    except Exception as e:
        logger.error(f"Map processing failed for {map_id}: {e}")

@router.get("/maps/{map_id}")
async def get_map_info(
    map_id: str,
    engine: VPSEngine = Depends(get_vps_engine),
    api_key: str = Depends(verify_api_key)
):
    """Get information about a specific map"""
    try:
        map_info = await engine.db_service.get_map_info(map_id)
        
        if not map_info:
            raise HTTPException(status_code=404, detail="Map not found")
        
        return map_info
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get map info error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get map info: {e}")

@router.delete("/maps/{map_id}")
async def delete_map(
    map_id: str,
    engine: VPSEngine = Depends(get_vps_engine),
    api_key: str = Depends(verify_api_key)
):
    """Delete a map and all associated data"""
    try:
        # Delete from database and storage
        await engine.db_service.delete_map(map_id)
        await engine.storage_service.delete_map_data(map_id)
        
        return {
            "message": f"Map {map_id} deleted successfully",
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Delete map error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete map: {e}")

@router.get("/performance")
async def get_performance_metrics(
    engine: VPSEngine = Depends(get_vps_engine),
    api_key: str = Depends(verify_api_key)
):
    """Get detailed performance metrics"""
    try:
        metrics = await engine.get_metrics()
        return metrics
        
    except Exception as e:
        logger.error(f"Performance metrics error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get metrics: {e}")

# Set the global engine reference (called from main.py)
def set_vps_engine(engine: VPSEngine):
    """Set the global VPS engine reference"""
    global vps_engine
    vps_engine = engine