"""
SLAM Tracking System
Handles visual SLAM processing and map management
"""

import os
import cv2
import numpy as np
import logging
from typing import Optional, Dict, Any
from datetime import datetime

from slam_integration import (
    create_slam_system, 
    StellaSLAMWrapper, 
    CameraFrame, 
    Pose, 
    SLAMConfig
)

logger = logging.getLogger(__name__)


class SlamTracker:
    """Manages SLAM tracking with map loading and pose estimation"""
    
    def __init__(self):
        self.slam_system: Optional[StellaSLAMWrapper] = None
        self.is_tracking = False
        self.current_map_id = None
        self.tracking_stats = {
            'frames_processed': 0,
            'successful_poses': 0,
            'lost_tracking_count': 0
        }
        
    def initialize(self, camera_config: Dict[str, Any]) -> bool:
        """Set up SLAM system with camera parameters"""
        try:
            logger.info("Starting SLAM initialization")
            
            self.slam_system = create_slam_system(
                camera_config=camera_config,
                enable_loop_closure=True,
                enable_relocalization=True
            )
            
            if not self.slam_system.initialize():
                raise RuntimeError("SLAM system failed to start")
                
            logger.info("SLAM system ready")
            return True
            
        except Exception as e:
            logger.error(f"SLAM initialization failed: {e}")
            return False
    
    def load_map(self, map_id: str, map_data: bytes = None) -> bool:
        """Load a SLAM map for localization"""
        if not self.slam_system:
            logger.error("SLAM system not initialized")
            return False
            
        try:
            map_path = f"/app/maps/{map_id}.map"
            
            # Save map data if provided
            if map_data:
                os.makedirs("/app/maps", exist_ok=True)
                with open(map_path, 'wb') as f:
                    f.write(map_data)
            
            # Check if map exists
            if not os.path.exists(map_path):
                logger.warning(f"Map file not found: {map_path}")
                return False
                
            # Load into SLAM system
            success = self.slam_system.load_map(map_path)
            if success:
                self.current_map_id = map_id
                logger.info(f"Loaded map: {map_id}")
            
            return success
            
        except Exception as e:
            logger.error(f"Failed to load map {map_id}: {e}")
            return False
    
    def start_tracking(self) -> bool:
        """Begin pose tracking"""
        if not self.slam_system:
            return False
            
        try:
            self.slam_system.start_tracking()
            self.is_tracking = True
            logger.info("SLAM tracking started")
            return True
        except Exception as e:
            logger.error(f"Failed to start tracking: {e}")
            return False
    
    def stop_tracking(self):
        """Stop pose tracking"""
        if self.slam_system:
            self.slam_system.stop_tracking()
            
        self.is_tracking = False
        logger.info("SLAM tracking stopped")
    
    def process_frame(self, image_data: bytes, timestamp: float) -> Optional[Dict[str, Any]]:
        """Process camera frame and return pose if successful"""
        if not self.slam_system or not self.is_tracking:
            return None
            
        try:
            # Decode image
            image_array = np.frombuffer(image_data, dtype=np.uint8)
            image = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
            
            if image is None:
                logger.warning("Failed to decode image")
                return None
            
            # Create camera frame
            camera_frame = CameraFrame(
                timestamp=timestamp,
                image=image,
                camera_id=0
            )
            
            # Process through SLAM
            pose = self.slam_system.process_frame(camera_frame)
            self.tracking_stats['frames_processed'] += 1
            
            if pose is not None:
                self.tracking_stats['successful_poses'] += 1
                
                return {
                    'timestamp': pose.timestamp,
                    'position': pose.position.tolist(),
                    'rotation': pose.rotation.tolist(),
                    'confidence': pose.confidence,
                    'tracking_state': pose.tracking_state
                }
            else:
                self.tracking_stats['lost_tracking_count'] += 1
                return None
                
        except Exception as e:
            logger.error(f"Frame processing error: {e}")
            return None
    
    def get_tracking_status(self) -> Dict[str, Any]:
        """Get current tracking state and statistics"""
        if not self.slam_system:
            return {
                'is_initialized': False,
                'is_tracking': False,
                'current_map': None,
                'stats': self.tracking_stats
            }
        
        try:
            slam_status = self.slam_system.get_tracking_state()
            
            return {
                'is_initialized': slam_status.get('is_initialized', False),
                'is_tracking': self.is_tracking,
                'current_map': self.current_map_id,
                'frame_count': slam_status.get('frame_count', 0),
                'fps': slam_status.get('fps', 0.0),
                'stats': self.tracking_stats
            }
            
        except Exception as e:
            logger.error(f"Failed to get SLAM status: {e}")
            return {
                'is_initialized': False,
                'is_tracking': False,
                'current_map': self.current_map_id,
                'stats': self.tracking_stats
            }
    
    def save_current_map(self, map_id: str) -> bool:
        """Save current SLAM map to disk"""
        if not self.slam_system:
            return False
            
        try:
            os.makedirs("/app/maps", exist_ok=True)
            map_path = f"/app/maps/{map_id}.map"
            
            success = self.slam_system.save_map(map_path)
            if success:
                logger.info(f"Map saved as {map_id}")
                
            return success
            
        except Exception as e:
            logger.error(f"Failed to save map: {e}")
            return False