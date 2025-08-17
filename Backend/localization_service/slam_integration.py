#!/usr/bin/env python3
"""
Spatial Platform - SLAM Integration Module
Stella VSLAM integration for real-time tracking and localization
"""

import os
import sys
import json
import yaml
import numpy as np
import cv2
import threading
import time
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from pathlib import Path
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class CameraFrame:
    """Camera frame data structure"""
    timestamp: float
    image: np.ndarray
    camera_id: int = 0
    intrinsics: Optional[np.ndarray] = None
    
@dataclass 
class Pose:
    """6DOF pose representation"""
    timestamp: float
    position: np.ndarray  # [x, y, z]
    rotation: np.ndarray  # [qw, qx, qy, qz] quaternion
    confidence: float
    tracking_state: str

@dataclass
class SLAMConfig:
    """SLAM configuration parameters"""
    vocab_file: str
    camera_config: Dict[str, Any]
    map_db_path: Optional[str] = None
    enable_loop_closure: bool = True
    enable_relocalization: bool = True
    log_level: str = "info"

class StellaSLAMWrapper:
    """
    Python wrapper for Stella VSLAM
    Provides high-level interface for real-time tracking
    """
    
    def __init__(self, config: SLAMConfig):
        self.config = config
        self.slam_system = None
        self.is_initialized = False
        self.is_tracking = False
        self.current_pose = None
        self.tracking_thread = None
        self.frame_queue = []
        self.queue_lock = threading.Lock()
        
        # Performance metrics
        self.frame_count = 0
        self.start_time = None
        self.last_pose_time = 0
        
        logger.info(f"Initializing Stella VSLAM with config: {config}")
        
    def initialize(self) -> bool:
        """Initialize SLAM system"""
        try:
            # Create camera config file
            camera_config_path = self._create_camera_config()
            
            # Initialize actual Stella VSLAM system
            try:
                import stella_vslam
                self.slam_system = stella_vslam.System(
                    config_file_path=camera_config_path,
                    vocab_file_path=self.config.vocab_file,
                    debug_mode=False
                )
                self.slam_system.startup()
                logger.info("Stella VSLAM system initialized successfully")
            except ImportError:
                logger.error("Stella VSLAM not available - please install Stella VSLAM")
                logger.error("Production deployment requires Stella VSLAM for optimal performance")
                raise RuntimeError("Stella VSLAM is required for production deployment")
            logger.info(f"Vocabulary file: {self.config.vocab_file}")
            logger.info(f"Camera config: {camera_config_path}")
            
            self.is_initialized = True
            self.start_time = time.time()
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize SLAM system: {e}")
            return False
    
    def _create_camera_config(self) -> str:
        """Create camera configuration file for Stella VSLAM"""
        config_path = "/tmp/camera_config.yaml"
        
        # Default monocular camera configuration
        camera_config = {
            "Camera.name": "Spatial Platform Camera",
            "Camera.setup": "monocular",
            "Camera.model": "perspective",
            
            # Camera intrinsics (will be updated from client)
            "Camera.fx": self.config.camera_config.get("fx", 800.0),
            "Camera.fy": self.config.camera_config.get("fy", 800.0),
            "Camera.cx": self.config.camera_config.get("cx", 320.0),
            "Camera.cy": self.config.camera_config.get("cy", 240.0),
            
            # Distortion parameters
            "Camera.k1": self.config.camera_config.get("k1", 0.0),
            "Camera.k2": self.config.camera_config.get("k2", 0.0),
            "Camera.p1": self.config.camera_config.get("p1", 0.0),
            "Camera.p2": self.config.camera_config.get("p2", 0.0),
            "Camera.k3": self.config.camera_config.get("k3", 0.0),
            
            # Image properties
            "Camera.fps": self.config.camera_config.get("fps", 30.0),
            "Camera.cols": self.config.camera_config.get("width", 640),
            "Camera.rows": self.config.camera_config.get("height", 480),
            
            # Feature extraction
            "Feature.max_num_keypoints": 2000,
            "Feature.scale_factor": 1.2,
            "Feature.num_levels": 8,
            "Feature.ini_fast_threshold": 20,
            "Feature.min_fast_threshold": 7,
            
            # Tracking
            "Tracking.enable_auto_relocalization": self.config.enable_relocalization,
            
            # Mapping
            "Mapping.baseline_dist_thr_ratio": 0.02,
            
            # Loop closure
            "LoopClosing.enable": self.config.enable_loop_closure,
            "LoopClosing.min_num_shared_keypoints": 20,
        }
        
        with open(config_path, 'w') as f:
            yaml.dump(camera_config, f, default_flow_style=False)
            
        return config_path
    
    def start_tracking(self) -> bool:
        """Start SLAM tracking in separate thread"""
        if not self.is_initialized:
            logger.error("SLAM system not initialized")
            return False
            
        if self.is_tracking:
            logger.warning("SLAM tracking already running")
            return True
            
        self.is_tracking = True
        self.tracking_thread = threading.Thread(target=self._tracking_loop, daemon=True)
        self.tracking_thread.start()
        
        logger.info("SLAM tracking started")
        return True
    
    def stop_tracking(self):
        """Stop SLAM tracking"""
        self.is_tracking = False
        if self.tracking_thread:
            self.tracking_thread.join(timeout=5.0)
        logger.info("SLAM tracking stopped")
    
    def process_frame(self, frame: CameraFrame) -> Optional[Pose]:
        """
        Process camera frame and return pose estimate
        Thread-safe method for real-time tracking
        """
        if not self.is_tracking:
            return None
            
        # Add frame to processing queue
        with self.queue_lock:
            self.frame_queue.append(frame)
            # Keep queue size manageable
            if len(self.frame_queue) > 10:
                self.frame_queue.pop(0)
        
        return self.current_pose
    
    def _tracking_loop(self):
        """Main tracking loop running in separate thread"""
        logger.info("SLAM tracking loop started")
        
        while self.is_tracking:
            try:
                # Get next frame from queue
                frame = None
                with self.queue_lock:
                    if self.frame_queue:
                        frame = self.frame_queue.pop(0)
                
                if frame is None:
                    time.sleep(0.001)  # 1ms sleep to prevent busy waiting
                    continue
                
                # Process frame with Stella VSLAM
                pose = self._process_frame_internal(frame)
                
                if pose:
                    self.current_pose = pose
                    self.last_pose_time = time.time()
                
                self.frame_count += 1
                
                # Log performance metrics every 100 frames
                if self.frame_count % 100 == 0:
                    elapsed = time.time() - self.start_time
                    fps = self.frame_count / elapsed if elapsed > 0 else 0
                    logger.info(f"SLAM Performance: {fps:.1f} FPS, {self.frame_count} frames processed")
                
            except Exception as e:
                logger.error(f"Error in tracking loop: {e}")
                time.sleep(0.1)
    
    def _process_frame_internal(self, frame: CameraFrame) -> Optional[Pose]:
        """
        Internal frame processing with Stella VSLAM
        This is where the actual SLAM magic happens
        """
        try:
            # Validate frame data
            if frame.image is None:
                logger.error("Invalid frame: image data is None")
                return None
                
            # Convert image to grayscale if needed
            if len(frame.image.shape) == 3:
                gray_image = cv2.cvtColor(frame.image, cv2.COLOR_BGR2GRAY)
            else:
                gray_image = frame.image
            
            # Validate image dimensions
            if gray_image.shape[0] < 10 or gray_image.shape[1] < 10:
                logger.error(f"Invalid frame dimensions: {gray_image.shape}")
                return None
            
            # Process frame with actual SLAM system
            if hasattr(self.slam_system, 'track_monocular_image'):
                # Stella VSLAM interface
                pose_matrix = self.slam_system.track_monocular_image(
                    gray_image, frame.timestamp
                )
            # Note: Only Stella VSLAM supported in production
            else:
                logger.error("Unknown SLAM system interface")
                return None
            
            # Convert SLAM pose matrix to our format
            if pose_matrix is not None:
                slam_pose = self._convert_slam_pose(pose_matrix, frame.timestamp)
            else:
                # Tracking lost - use last known pose with degraded confidence
                slam_pose = self._handle_tracking_loss(frame.timestamp)
            
            # Log frame processing stats occasionally
            if self.frame_count % 100 == 0:
                logger.info(f"Processed frame {self.frame_count}: "
                          f"size={gray_image.shape}, "
                          f"confidence={slam_pose.confidence:.2f}, "
                          f"state={slam_pose.tracking_state}")
            
            return slam_pose
            
        except cv2.error as e:
            logger.error(f"OpenCV error in frame processing: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error in frame processing: {e}")
            return None
    
    def _convert_slam_pose(self, pose_matrix: np.ndarray, timestamp: float) -> Pose:
        """
        Convert SLAM pose matrix to our Pose format
        SLAM systems typically return 4x4 transformation matrices
        """
        try:
            # Extract position from translation vector
            position = pose_matrix[:3, 3]
            
            # Extract rotation matrix and convert to quaternion
            rotation_matrix = pose_matrix[:3, :3]
            
            # Convert rotation matrix to quaternion using Rodrigues formula
            from scipy.spatial.transform import Rotation as R
            rotation_obj = R.from_matrix(rotation_matrix)
            quaternion = rotation_obj.as_quat()  # [x, y, z, w]
            
            # Reorder to [w, x, y, z] for our format
            rotation = np.array([quaternion[3], quaternion[0], quaternion[1], quaternion[2]])
            
            # Calculate confidence based on SLAM system state
            confidence = self._calculate_slam_confidence()
            
            # Determine tracking state from SLAM system
            tracking_state = self._get_slam_tracking_state()
            
            return Pose(
                timestamp=timestamp,
                position=position,
                rotation=rotation,
                confidence=confidence,
                tracking_state=tracking_state
            )
            
        except Exception as e:
            logger.error(f"Error converting SLAM pose: {e}")
            return self._handle_tracking_loss(timestamp)
    
    def _calculate_slam_confidence(self) -> float:
        """
        Calculate tracking confidence based on SLAM system metrics
        """
        try:
            if hasattr(self.slam_system, 'get_tracking_state'):
                state = self.slam_system.get_tracking_state()
                
                # Map SLAM tracking states to confidence values
                if state == 'TRACKING':
                    # Get number of tracked features
                    num_features = getattr(self.slam_system, 'get_num_tracked_features', lambda: 100)()
                    # More features = higher confidence
                    base_confidence = 0.7 + min(num_features / 200.0, 0.25)
                    
                    # Factor in map quality if available
                    if hasattr(self.slam_system, 'get_num_keyframes'):
                        num_keyframes = self.slam_system.get_num_keyframes()
                        keyframe_bonus = min(num_keyframes / 50.0, 0.05)
                        base_confidence += keyframe_bonus
                    
                    return min(base_confidence, 0.99)
                    
                elif state == 'LOST':
                    return 0.1
                elif state == 'RELOCALIZING':
                    return 0.3
                elif state == 'INITIALIZING':
                    return 0.5
                else:
                    return 0.6  # Unknown state
            else:
                # Fallback confidence calculation
                return 0.8
                
        except Exception as e:
            logger.warning(f"Error calculating SLAM confidence: {e}")
            return 0.5
    
    def _get_slam_tracking_state(self) -> str:
        """
        Get tracking state from SLAM system
        """
        try:
            if hasattr(self.slam_system, 'get_tracking_state'):
                state = self.slam_system.get_tracking_state()
                
                # Map SLAM states to our format
                state_mapping = {
                    'TRACKING': 'tracking',
                    'LOST': 'lost', 
                    'RELOCALIZING': 'relocalizing',
                    'INITIALIZING': 'initializing',
                    'NOT_INITIALIZED': 'not_initialized'
                }
                
                return state_mapping.get(state, 'unknown')
            else:
                return 'tracking'  # Assume tracking if no state available
                
        except Exception as e:
            logger.warning(f"Error getting SLAM tracking state: {e}")
            return 'unknown'
    
    def _handle_tracking_loss(self, timestamp: float) -> Pose:
        """
        Handle tracking loss by returning degraded pose estimate
        """
        if self.current_pose is not None:
            # Return last known pose with very low confidence
            return Pose(
                timestamp=timestamp,
                position=self.current_pose.position.copy(),
                rotation=self.current_pose.rotation.copy(),
                confidence=0.1,
                tracking_state='lost'
            )
        else:
            # No previous pose available
            return Pose(
                timestamp=timestamp,
                position=np.zeros(3),
                rotation=np.array([1.0, 0.0, 0.0, 0.0]),  # Identity quaternion
                confidence=0.0,
                tracking_state='lost'
            )
    
    
    def save_map(self, filepath: str) -> bool:
        """Save current map to file"""
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            
            # Save actual SLAM map data
            if hasattr(self.slam_system, 'save_map_database'):
                # Stella VSLAM format
                temp_map_path = f"{filepath}.tmp"
                self.slam_system.save_map_database(temp_map_path)
                
                # Load binary map data
                with open(temp_map_path, 'rb') as f:
                    map_binary = f.read()
                
                # Create metadata wrapper
                map_data = {
                    "version": "2.0",
                    "slam_system": "stella_vslam",
                    "created_at": time.time(),
                    "frame_count": self.frame_count,
                    "camera_config": self.config.camera_config,
                    "tracking_stats": {
                        "total_frames": self.frame_count,
                        "tracking_time": time.time() - (self.start_time or time.time()),
                        "num_keyframes": getattr(self.slam_system, 'get_num_keyframes', lambda: 0)(),
                        "num_landmarks": getattr(self.slam_system, 'get_num_landmarks', lambda: 0)()
                    },
                    "map_binary_size": len(map_binary)
                }
                
                # Clean up temp file
                os.remove(temp_map_path)
                
            elif hasattr(self.slam_system, 'save_map'):
                # OpenVSLAM format
                temp_map_path = f"{filepath}.msg"
                self.slam_system.save_map(temp_map_path)
                
                # Load MessagePack map data
                with open(temp_map_path, 'rb') as f:
                    map_binary = f.read()
                
                map_data = {
                    "version": "2.0", 
                    "slam_system": "stella_vslam",
                    "created_at": time.time(),
                    "frame_count": self.frame_count,
                    "camera_config": self.config.camera_config,
                    "tracking_stats": {
                        "total_frames": self.frame_count,
                        "tracking_time": time.time() - (self.start_time or time.time())
                    },
                    "map_binary_size": len(map_binary)
                }
                
                # Clean up temp file
                os.remove(temp_map_path)
                
            else:
                logger.warning("SLAM system does not support map saving")
                # Fallback to basic metadata
                map_data = {
                    "version": "2.0",
                    "slam_system": "unknown",
                    "created_at": time.time(),
                    "frame_count": self.frame_count,
                    "camera_config": self.config.camera_config,
                    "tracking_stats": {
                        "total_frames": self.frame_count,
                        "tracking_time": time.time() - (self.start_time or time.time())
                    },
                    "map_binary_size": 0
                }
            
            # Save metadata as JSON and binary data separately if available
            metadata_path = f"{filepath}.meta"
            with open(metadata_path, 'w') as f:
                json.dump(map_data, f, indent=2)
            
            # Save binary map data if available
            if 'map_binary_size' in map_data and map_data['map_binary_size'] > 0:
                binary_path = f"{filepath}.map"
                with open(binary_path, 'wb') as f:
                    f.write(map_binary)
                logger.info(f"Saved binary map data: {binary_path} ({map_data['map_binary_size']} bytes)")
            
            # Create combined file for compatibility
            combined_data = map_data.copy()
            if 'map_binary_size' in map_data and map_data['map_binary_size'] > 0:
                import base64
                combined_data['map_binary_base64'] = base64.b64encode(map_binary).decode('utf-8')
            
            with open(filepath, 'w') as f:
                json.dump(combined_data, f, indent=2)
            
            logger.info(f"Map saved successfully: {filepath} ({os.path.getsize(filepath)} bytes)")
            return True
            
        except PermissionError as e:
            logger.error(f"Permission denied saving map to {filepath}: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to save map: {e}")
            return False
    
    def load_map(self, filepath: str) -> bool:
        """Load map from file"""
        try:
            if not os.path.exists(filepath):
                logger.error(f"Map file not found: {filepath}")
                return False
            
            if not os.access(filepath, os.R_OK):
                logger.error(f"Cannot read map file: {filepath}")
                return False
                
            # Load map data
            with open(filepath, 'r') as f:
                map_data = json.load(f)
            
            # Validate map data
            if "version" not in map_data:
                logger.error(f"Invalid map file format: {filepath}")
                return False
            
            # Load actual SLAM map if available
            binary_path = f"{filepath}.map"
            metadata_path = f"{filepath}.meta"
            
            # Try to load from separate files first
            if os.path.exists(metadata_path) and os.path.exists(binary_path):
                with open(metadata_path, 'r') as f:
                    metadata = json.load(f)
                
                slam_system = metadata.get('slam_system', 'unknown')
                
                if slam_system == 'stella_vslam' and hasattr(self.slam_system, 'load_map_database'):
                    self.slam_system.load_map_database(binary_path)
                    logger.info("Loaded Stella VSLAM map from binary data")
                elif slam_system == 'openvslam' and hasattr(self.slam_system, 'load_map'):
                    self.slam_system.load_map(binary_path) 
                    logger.info("Loaded OpenVSLAM map from binary data")
                else:
                    logger.warning(f"Cannot load map for SLAM system: {slam_system}")
                    
            # Try to load from combined file with base64 data
            elif 'map_binary_base64' in map_data:
                import base64
                map_binary = base64.b64decode(map_data['map_binary_base64'])
                
                # Write to temporary file for SLAM system
                temp_map_path = f"/tmp/slam_map_{int(time.time())}"
                with open(temp_map_path, 'wb') as f:
                    f.write(map_binary)
                
                slam_system = map_data.get('slam_system', 'unknown')
                if slam_system == 'stella_vslam' and hasattr(self.slam_system, 'load_map_database'):
                    self.slam_system.load_map_database(temp_map_path)
                else:
                    logger.warning(f"Map format '{slam_system}' not supported. Only Stella VSLAM maps supported.")
                
                # Clean up
                os.remove(temp_map_path)
                logger.info(f"Loaded {slam_system} map from base64 data")
                
            else:
                logger.info("Map file contains only metadata - no binary map data to load")
            
            logger.info(f"Map loaded successfully: {filepath}")
            logger.info(f"Map stats - Frames: {map_data.get('frame_count', 0)}, "
                       f"Created: {time.ctime(map_data.get('created_at', 0))}")
            
            return True
            
        except json.JSONDecodeError as e:
            logger.error(f"Corrupted map file {filepath}: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to load map: {e}")
            return False
    
    def get_tracking_state(self) -> Dict[str, Any]:
        """Get current tracking state and statistics"""
        elapsed = time.time() - self.start_time if self.start_time else 0
        fps = self.frame_count / elapsed if elapsed > 0 else 0
        
        return {
            "is_initialized": self.is_initialized,
            "is_tracking": self.is_tracking,
            "frame_count": self.frame_count,
            "fps": round(fps, 2),
            "last_pose_time": self.last_pose_time,
            "current_pose": {
                "timestamp": self.current_pose.timestamp if self.current_pose else None,
                "position": self.current_pose.position.tolist() if self.current_pose else None,
                "rotation": self.current_pose.rotation.tolist() if self.current_pose else None,
                "confidence": self.current_pose.confidence if self.current_pose else None,
                "tracking_state": self.current_pose.tracking_state if self.current_pose else "not_tracking"
            } if self.current_pose else None
        }
    
    def shutdown(self):
        """Clean shutdown of SLAM system"""
        logger.info("Shutting down SLAM system")
        self.stop_tracking()
        self.is_initialized = False

# Factory function for easy instantiation
def create_slam_system(
    vocab_file: str = "/app/vocab/orb_vocab.fbow",
    camera_config: Optional[Dict[str, Any]] = None,
    **kwargs
) -> StellaSLAMWrapper:
    """
    Factory function to create configured SLAM system
    """
    if camera_config is None:
        # Default camera configuration for development
        camera_config = {
            "fx": 800.0, "fy": 800.0,
            "cx": 320.0, "cy": 240.0,
            "width": 640, "height": 480,
            "fps": 30.0
        }
    
    config = SLAMConfig(
        vocab_file=vocab_file,
        camera_config=camera_config,
        **kwargs
    )
    
    return StellaSLAMWrapper(config)

# Production validation only - no mock testing
if __name__ == "__main__":
    logger.error("This module should not be run directly in production.")
    logger.info("Use the production validation script: test_production_implementation.py")
    sys.exit(1)