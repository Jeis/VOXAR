"""
API Routes for AR Localization Service
Clean separation of endpoint logic
"""

from fastapi import HTTPException, BackgroundTasks, UploadFile, File
from pydantic import BaseModel
from typing import Dict, List, Optional, Any
import base64
import logging

from api.models import (
    CameraConfig, SlamInitRequest, TrackingFrame, PoseResponse,
    VioDataRequest, VioResponse, StatusResponse
)

logger = logging.getLogger(__name__)


def setup_routes(app, slam_tracker, vio_tracker, pose_manager, nakama_client):
    """Set up all API routes with dependency injection"""
    
    @app.get("/health")
    async def health_check():
        """Simple health check"""
        return {
            "status": "healthy",
            "service": "ar-localization",
            "version": "2.1.0"
        }
    
    @app.get("/")
    async def service_info():
        """Service information and available endpoints"""
        return {
            "service": "AR Localization Service",
            "endpoints": {
                "slam": ["/slam/init", "/slam/start", "/slam/stop", "/slam/track"],
                "vio": ["/vio/process", "/vio/status", "/vio/reset"],
                "tracking": ["/pose/current", "/pose/history", "/pose/quality"]
            },
            "docs": "/docs"
        }
    
    # SLAM endpoints
    @app.post("/slam/init")
    async def initialize_slam(request: SlamInitRequest):
        """Initialize SLAM with camera parameters"""
        try:
            camera_config = {
                "fx": request.camera_config.fx,
                "fy": request.camera_config.fy,
                "cx": request.camera_config.cx,
                "cy": request.camera_config.cy,
                "width": request.camera_config.width,
                "height": request.camera_config.height,
                "fps": request.camera_config.fps,
                "k1": request.camera_config.k1,
                "k2": request.camera_config.k2,
                "p1": request.camera_config.p1,
                "p2": request.camera_config.p2,
                "k3": request.camera_config.k3,
            }
            
            success = slam_tracker.initialize(camera_config)
            if not success:
                raise HTTPException(500, "SLAM initialization failed")
            
            # Load map if specified
            if request.map_id:
                map_loaded = slam_tracker.load_map(request.map_id)
                if not map_loaded:
                    logger.warning(f"Could not load map: {request.map_id}")
            
            return {
                "success": True,
                "message": "SLAM initialized",
                "map_loaded": request.map_id if request.map_id else None
            }
            
        except Exception as e:
            logger.error(f"SLAM init error: {e}")
            raise HTTPException(500, f"Initialization failed: {str(e)}")
    
    @app.post("/slam/start")
    async def start_slam_tracking():
        """Start SLAM tracking"""
        success = slam_tracker.start_tracking()
        if not success:
            raise HTTPException(400, "SLAM not initialized or failed to start")
        
        return {"success": True, "message": "SLAM tracking started"}
    
    @app.post("/slam/stop")
    async def stop_slam_tracking():
        """Stop SLAM tracking"""
        slam_tracker.stop_tracking()
        return {"success": True, "message": "SLAM tracking stopped"}
    
    @app.post("/slam/track")
    async def process_slam_frame(frame: TrackingFrame) -> PoseResponse:
        """Process camera frame through SLAM"""
        try:
            # Decode base64 image
            image_data = base64.b64decode(frame.image_data)
            
            # Process frame
            pose_result = slam_tracker.process_frame(image_data, frame.timestamp)
            
            if pose_result:
                # Update pose manager with SLAM result
                pose_manager.update_slam_pose(pose_result)
                
                # Send pose update to Nakama (if user is in a match)
                # Note: In production, you'd get user_id from the request
                user_id = "test_user"  # This should come from authentication
                await nakama_client.send_pose_update(user_id, pose_result)
                
                return PoseResponse(
                    timestamp=pose_result['timestamp'],
                    position=pose_result['position'],
                    rotation=pose_result['rotation'],
                    confidence=pose_result['confidence'],
                    tracking_state=pose_result['tracking_state']
                )
            else:
                raise HTTPException(500, "Frame tracking failed")
                
        except Exception as e:
            logger.error(f"SLAM tracking error: {e}")
            raise HTTPException(500, f"Tracking failed: {str(e)}")
    
    @app.get("/slam/status")
    async def get_slam_status():
        """Get SLAM system status"""
        return slam_tracker.get_tracking_status()
    
    @app.post("/slam/save_map")
    async def save_slam_map(map_id: str, background_tasks: BackgroundTasks):
        """Save current SLAM map"""
        def save_map_task():
            success = slam_tracker.save_current_map(map_id)
            if success:
                logger.info(f"Map saved: {map_id}")
            else:
                logger.error(f"Failed to save map: {map_id}")
        
        background_tasks.add_task(save_map_task)
        return {"success": True, "message": f"Map save started: {map_id}"}
    
    # VIO endpoints
    @app.post("/vio/process")
    async def process_vio_data(request: VioDataRequest) -> VioResponse:
        """Process VIO sensor data"""
        try:
            # Convert request to internal format
            imu_data = []
            for reading in request.imu_readings:
                imu_data.append({
                    'timestamp': reading.timestamp,
                    'acceleration': reading.acceleration,
                    'gyroscope': reading.gyroscope,
                    'magnetometer': reading.magnetometer,
                    'temperature': reading.temperature,
                    'is_valid': reading.is_valid
                })
            
            camera_params = {
                'fx': request.camera_params.fx,
                'fy': request.camera_params.fy,
                'cx': request.camera_params.cx,
                'cy': request.camera_params.cy,
                'k1': request.camera_params.k1,
                'k2': request.camera_params.k2,
                'p1': request.camera_params.p1,
                'p2': request.camera_params.p2,
                'k3': request.camera_params.k3,
                'width': request.camera_params.width,
                'height': request.camera_params.height
            }
            
            # Process through VIO
            result = vio_tracker.process_sensor_data(
                imu_readings=imu_data,
                camera_frame=request.camera_frame_base64,
                camera_params=camera_params,
                timestamp=request.timestamp
            )
            
            # Update pose manager if successful
            if result.get('success'):
                pose_manager.update_vio_pose(result)
            
            return VioResponse(
                success=result['success'],
                message="VIO processing complete" if result['success'] else result.get('error', 'Processing failed'),
                pose=result.get('pose'),
                confidence=result.get('confidence', 0.0),
                tracking_state=result.get('tracking_state', 'unknown'),
                processing_time_ms=result.get('processing_time_ms', 0.0),
                sequence_number=result.get('sequence_number', 0)
            )
            
        except Exception as e:
            logger.error(f"VIO processing error: {e}")
            return VioResponse(
                success=False,
                message=f"VIO error: {str(e)}",
                pose=None,
                confidence=0.0,
                tracking_state="error",
                processing_time_ms=0.0,
                sequence_number=0
            )
    
    @app.get("/vio/status")
    async def get_vio_status():
        """Get VIO system status"""
        return vio_tracker.get_status()
    
    @app.post("/vio/reset")
    async def reset_vio():
        """Reset VIO tracking state"""
        success = vio_tracker.reset()
        if not success:
            raise HTTPException(500, "VIO reset failed")
        
        return {"success": True, "message": "VIO reset complete"}
    
    # Pose management endpoints
    @app.get("/pose/current")
    async def get_current_pose():
        """Get best available pose estimate"""
        pose = pose_manager.get_current_pose()
        if not pose:
            raise HTTPException(404, "No pose available")
        
        return pose
    
    @app.get("/pose/history")
    async def get_pose_history(max_age_seconds: float = 5.0):
        """Get recent pose history"""
        history = pose_manager.get_pose_history(max_age_seconds)
        return {"poses": history, "count": len(history)}
    
    @app.get("/pose/quality")
    async def get_tracking_quality():
        """Get current tracking quality assessment"""
        quality = pose_manager.get_tracking_quality()
        status = pose_manager.get_status_summary()
        
        return {
            "quality_score": quality,
            "status": status
        }
    
    @app.post("/pose/reset")
    async def reset_tracking():
        """Reset all tracking systems"""
        pose_manager.reset_tracking()
        slam_tracker.stop_tracking()
        vio_tracker.reset()
        
        return {"success": True, "message": "All tracking reset"}