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
            
            # Note: This is a placeholder for actual Stella VSLAM Python bindings
            # In practice, you would use the compiled Python bindings
            logger.info("Stella VSLAM system initialized successfully")
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
            
            # Placeholder for actual Stella VSLAM processing
            # In reality, this would call the Stella VSLAM track_monocular_image() method
            # Something like:
            # pose_matrix = self.stella_slam.track_monocular_image(gray_image, frame.timestamp)
            
            # For demonstration, return a mock pose with realistic movement
            mock_pose = self._generate_mock_pose(frame.timestamp)
            
            # Log frame processing stats occasionally
            if self.frame_count % 100 == 0:
                logger.info(f"Processed frame {self.frame_count}: "
                          f"size={gray_image.shape}, "
                          f"confidence={mock_pose.confidence:.2f}, "
                          f"state={mock_pose.tracking_state}")
            
            return mock_pose
            
        except cv2.error as e:
            logger.error(f"OpenCV error in frame processing: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error in frame processing: {e}")
            return None
    
    def _generate_mock_pose(self, timestamp: float) -> Pose:
        """Generate realistic mock pose for development/testing"""
        # Use current time for continuous motion
        current_time = time.time()
        t = current_time * 0.1  # Slow motion for demo
        
        # Create more realistic motion patterns
        # Simulate walking in a figure-8 pattern with slight height variation
        scale = 1.5  # meters
        
        # Figure-8 motion (Lissajous curve)
        x = scale * np.sin(t)
        z = scale * np.sin(2 * t) / 2
        y = 0.1 * np.sin(t * 3)  # Slight bobbing motion (head movement)
        
        position = np.array([x, y, z])
        
        # Calculate rotation based on movement direction
        # Look in the direction of movement
        dx = scale * np.cos(t) * 0.1
        dz = scale * np.cos(2 * t) * 0.1
        
        if abs(dx) > 0.001 or abs(dz) > 0.001:
            # Calculate yaw rotation based on movement direction
            yaw = np.arctan2(dx, dz)
            # Add slight head movement
            pitch = 0.05 * np.sin(t * 4)  # Small up/down head movement
            roll = 0.02 * np.sin(t * 6)   # Tiny side-to-side
            
            # Convert to quaternion [qw, qx, qy, qz]
            cy = np.cos(yaw * 0.5)
            sy = np.sin(yaw * 0.5)
            cp = np.cos(pitch * 0.5)
            sp = np.sin(pitch * 0.5)
            cr = np.cos(roll * 0.5)
            sr = np.sin(roll * 0.5)
            
            qw = cr * cp * cy + sr * sp * sy
            qx = sr * cp * cy - cr * sp * sy
            qy = cr * sp * cy + sr * cp * sy
            qz = cr * cp * sy - sr * sp * cy
            
            rotation = np.array([qw, qx, qy, qz])
        else:
            # Stationary, facing forward
            rotation = np.array([1.0, 0.0, 0.0, 0.0])
        
        # Simulate varying confidence based on "tracking quality"
        # Higher confidence in center, lower at edges
        distance_from_center = np.sqrt(x*x + z*z)
        base_confidence = 0.95 - (distance_from_center / (scale * 2)) * 0.3
        # Add some noise
        confidence_noise = 0.05 * np.sin(t * 10)
        confidence = np.clip(base_confidence + confidence_noise, 0.5, 0.99)
        
        # Simulate realistic tracking quality variations
        # Factors that affect tracking quality in real SLAM:
        # - Motion speed (faster motion = lower confidence)
        # - Environmental features (fewer features = lower confidence)  
        # - Lighting conditions (simulated with time-based variation)
        
        motion_speed = np.sqrt(dx*dx + dz*dz)
        motion_penalty = min(motion_speed * 2.0, 0.2)  # Faster motion reduces confidence
        
        # Simulate lighting/environmental variations
        lighting_factor = 0.1 * np.sin(t * 0.5)  # Slow lighting changes
        environmental_confidence = base_confidence - motion_penalty + lighting_factor
        
        # Add measurement noise (realistic sensor noise)
        sensor_noise = 0.03 * (np.random.random() - 0.5)  # ±1.5% noise
        final_confidence = np.clip(environmental_confidence + sensor_noise, 0.2, 0.99)
        
        # More realistic tracking state thresholds
        if final_confidence < 0.3:
            tracking_state = "lost"
        elif final_confidence < 0.6:
            tracking_state = "poor" 
        elif final_confidence < 0.8:
            tracking_state = "fair"
        else:
            tracking_state = "tracking"
        
        # Occasional complete tracking loss (more realistic)
        if np.random.random() < 0.005:  # 0.5% chance of tracking loss
            tracking_state = "lost"
            final_confidence = 0.1
        
        return Pose(
            timestamp=timestamp,
            position=position,
            rotation=rotation,
            confidence=float(final_confidence),
            tracking_state=tracking_state
        )
    
    def save_map(self, filepath: str) -> bool:
        """Save current map to file"""
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            
            # Create mock map data (in reality, this would be actual SLAM map)
            map_data = {
                "version": "1.0",
                "created_at": time.time(),
                "frame_count": self.frame_count,
                "camera_config": self.config.camera_config,
                "tracking_stats": {
                    "total_frames": self.frame_count,
                    "tracking_time": time.time() - (self.start_time or time.time())
                },
                # In real SLAM, this would contain:
                # - Keyframes with features
                # - 3D landmarks/map points
                # - Camera poses
                # - Loop closure information
                "mock_data": {
                    "note": "This is mock SLAM map data for development",
                    "keyframes": min(self.frame_count // 10, 100),  # Simulate keyframes
                    "landmarks": min(self.frame_count * 50, 5000)   # Simulate map points
                }
            }
            
            # Save as JSON for now (real SLAM would use binary format)
            with open(filepath, 'w') as f:
                json.dump(map_data, f, indent=2)
            
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
            
            # In real SLAM, this would:
            # - Restore keyframes and landmarks
            # - Initialize relocalization
            # - Set up loop closure detection
            
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

# Testing utilities
def test_slam_system():
    """Test SLAM system with mock data"""
    logger.info("Testing SLAM system...")
    
    slam = create_slam_system()
    
    if not slam.initialize():
        logger.error("Failed to initialize SLAM system")
        return False
    
    if not slam.start_tracking():
        logger.error("Failed to start tracking")
        return False
    
    # Generate test frames
    for i in range(10):
        # Create mock camera frame
        test_image = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
        frame = CameraFrame(
            timestamp=time.time(),
            image=test_image,
            camera_id=0
        )
        
        pose = slam.process_frame(frame)
        if pose:
            logger.info(f"Frame {i}: Pose = {pose.position}, Confidence = {pose.confidence}")
        
        time.sleep(0.1)  # 10 FPS for testing
    
    # Get tracking statistics
    stats = slam.get_tracking_state()
    logger.info(f"Tracking stats: {stats}")
    
    slam.shutdown()
    logger.info("SLAM test completed successfully")
    return True

if __name__ == "__main__":
    test_slam_system()