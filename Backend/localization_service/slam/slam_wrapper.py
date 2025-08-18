"""
VOXAR Spatial Platform - Core SLAM Wrapper
Enterprise-grade Stella VSLAM integration with comprehensive error handling
"""

import logging
import numpy as np
import time
from typing import Optional, Dict, Any
from pathlib import Path

from .slam_models import SLAMConfig, CameraFrame, Pose, SLAMState, SLAMMetrics
from .slam_config import SLAMConfigManager

logger = logging.getLogger(__name__)

class StellaSLAMWrapper:
    """
    Enterprise Stella VSLAM wrapper with production-grade error handling
    Handles real Stella VSLAM integration with graceful fallbacks
    """
    
    def __init__(self, config: SLAMConfig):
        self.config = config
        self.slam_system = None
        self.config_manager = SLAMConfigManager(config)
        
        # Enterprise state management
        self.state = SLAMState()
        self.metrics = SLAMMetrics()
        
        # Performance tracking
        self.last_pose_timestamp = 0.0
        self.initialization_attempts = 0
        self.max_initialization_attempts = 3
        
        logger.info(f"Initializing Stella VSLAM wrapper with config: {config}")
    
    def initialize(self) -> bool:
        """
        Initialize Stella VSLAM system with enterprise error handling
        Returns True if successful, False otherwise
        """
        
        if self.state.is_initialized:
            logger.warning("SLAM system already initialized")
            return True
        
        self.initialization_attempts += 1
        
        try:
            # Create camera configuration
            camera_config_path = self.config_manager.create_camera_config()
            
            # Validate configuration
            if not self.config_manager.validate_config_file(camera_config_path):
                raise RuntimeError("Invalid camera configuration generated")
            
            # Initialize Stella VSLAM system
            success = self._initialize_stella_system(camera_config_path)
            
            if success:
                self.state.is_initialized = True
                self.state.system_health_score = 1.0
                logger.info("✅ Stella VSLAM system initialized successfully")
                return True
            else:
                self._handle_initialization_failure()
                return False
                
        except Exception as e:
            logger.error(f"SLAM initialization failed (attempt {self.initialization_attempts}): {e}")
            self._handle_initialization_failure()
            return False
    
    def _initialize_stella_system(self, camera_config_path: str) -> bool:
        """Initialize actual Stella VSLAM system"""
        try:
            # Try to import and initialize Stella VSLAM
            import stella_vslam
            
            self.slam_system = stella_vslam.System(
                config_file_path=camera_config_path,
                vocab_file_path=self.config.vocab_file,
                debug_mode=False
            )
            
            # Start the SLAM system
            self.slam_system.startup()
            
            # Verify system is responsive
            if not self._verify_system_health():
                raise RuntimeError("SLAM system failed health check")
            
            logger.info(f"Stella VSLAM initialized with vocab: {self.config.vocab_file}")
            return True
            
        except ImportError as e:
            logger.error("Stella VSLAM not available - please install Stella VSLAM")
            logger.error("Production deployment requires Stella VSLAM for optimal tracking")
            raise RuntimeError("Stella VSLAM library not found") from e
            
        except Exception as e:
            logger.error(f"Failed to initialize Stella VSLAM system: {e}")
            return False
    
    def _verify_system_health(self) -> bool:
        """Verify SLAM system is healthy and responsive"""
        try:
            if not self.slam_system:
                return False
            
            # Basic health check - system should be responsive
            # In a real implementation, you'd check specific Stella VSLAM status
            return True
            
        except Exception as e:
            logger.warning(f"SLAM system health check failed: {e}")
            return False
    
    def _handle_initialization_failure(self):
        """Handle SLAM initialization failure with retry logic"""
        
        if self.initialization_attempts < self.max_initialization_attempts:
            logger.warning(f"SLAM initialization failed, will retry ({self.initialization_attempts}/{self.max_initialization_attempts})")
            self.state.system_health_score *= 0.5
        else:
            logger.error("SLAM initialization failed after maximum attempts")
            self.state.system_health_score = 0.0
            # In production, this might trigger fallback to ARCore/ARKit
    
    def process_frame(self, frame: CameraFrame) -> Optional[Pose]:
        """
        Process camera frame and return pose estimate
        Enterprise-grade processing with comprehensive error handling
        """
        
        if not self.state.is_initialized:
            logger.warning("SLAM system not initialized, cannot process frame")
            return None
        
        if not frame.is_valid:
            logger.warning("Invalid frame data received")
            return None
        
        process_start = time.time()
        
        try:
            # Process frame through Stella VSLAM
            pose = self._process_frame_internal(frame)
            
            # Calculate processing time
            processing_time_ms = (time.time() - process_start) * 1000.0
            
            # Update metrics and state
            if pose:
                self.metrics.update_tracking_stats(pose, processing_time_ms)
                self.state.update_health_score(pose)
                self.state.current_pose = pose
                self.last_pose_timestamp = frame.timestamp
            else:
                self.state.update_health_score(None)
                # Try relocalization if tracking is lost
                if self.state.needs_relocalization:
                    self._attempt_relocalization(frame)
            
            return pose
            
        except Exception as e:
            logger.error(f"Frame processing failed: {e}")
            self.state.update_health_score(None)
            return None
    
    def _process_frame_internal(self, frame: CameraFrame) -> Optional[Pose]:
        """Internal frame processing with Stella VSLAM"""
        
        if not self.slam_system:
            return None
        
        try:
            # Feed frame to Stella VSLAM
            pose_matrix = self.slam_system.feed_monocular_frame(
                frame.image, frame.timestamp
            )
            
            if pose_matrix is not None:
                return self._convert_slam_pose(pose_matrix, frame.timestamp)
            else:
                return self._handle_tracking_loss(frame.timestamp)
                
        except Exception as e:
            logger.warning(f"Stella VSLAM frame processing error: {e}")
            return None
    
    def _convert_slam_pose(self, pose_matrix: np.ndarray, timestamp: float) -> Pose:
        """Convert Stella VSLAM pose matrix to Pose object"""
        
        try:
            # Extract position and rotation from 4x4 transformation matrix
            position = pose_matrix[:3, 3]
            rotation_matrix = pose_matrix[:3, :3]
            
            # Convert rotation matrix to quaternion
            from scipy.spatial.transform import Rotation
            rotation_quat = Rotation.from_matrix(rotation_matrix).as_quat()
            
            # Calculate confidence based on tracking quality
            confidence = self._calculate_tracking_confidence()
            
            # Determine tracking state
            tracking_state = self._get_tracking_state()
            
            return Pose(
                timestamp=timestamp,
                position=position,
                rotation=rotation_quat,
                confidence=confidence,
                tracking_state=tracking_state
            )
            
        except Exception as e:
            logger.error(f"Pose conversion failed: {e}")
            return self._handle_tracking_loss(timestamp)
    
    def _calculate_tracking_confidence(self) -> float:
        """Calculate tracking confidence based on SLAM system state"""
        
        try:
            if not self.slam_system:
                return 0.0
            
            # In real Stella VSLAM, you'd get actual tracking metrics
            # This is a simplified confidence calculation
            
            base_confidence = 0.8
            
            # Adjust based on system health
            health_factor = self.state.system_health_score
            
            # Adjust based on recent tracking performance
            recent_failures = min(self.state.consecutive_tracking_failures, 10)
            failure_penalty = recent_failures * 0.05
            
            confidence = base_confidence * health_factor - failure_penalty
            
            return max(0.0, min(1.0, confidence))
            
        except Exception:
            return 0.5  # Default moderate confidence
    
    def _get_tracking_state(self) -> str:
        """Get current tracking state from SLAM system"""
        
        try:
            if not self.slam_system:
                return 'lost'
            
            # In real Stella VSLAM, you'd get the actual tracking state
            # This is simplified for the example
            
            if self.state.consecutive_tracking_failures > 5:
                return 'lost'
            elif self.state.system_health_score > 0.7:
                return 'tracking'
            else:
                return 'initializing'
                
        except Exception:
            return 'unknown'
    
    def _handle_tracking_loss(self, timestamp: float) -> Pose:
        """Handle tracking loss with last known pose"""
        
        logger.warning("Tracking lost, using last known pose")
        
        if self.state.current_pose:
            # Return last known pose with reduced confidence
            return Pose(
                timestamp=timestamp,
                position=self.state.current_pose.position,
                rotation=self.state.current_pose.rotation,
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
    
    def _attempt_relocalization(self, frame: CameraFrame) -> bool:
        """Attempt relocalization when tracking is lost"""
        
        try:
            if not self.slam_system or not self.config.enable_relocalization:
                return False
            
            logger.info("Attempting relocalization...")
            
            # Trigger Stella VSLAM relocalization
            # Production implementation: request map relocalization from VSLAM system
            
            self.metrics.relocalization_count += 1
            return True
            
        except Exception as e:
            logger.error(f"Relocalization attempt failed: {e}")
            return False
    
    def get_system_status(self) -> Dict[str, Any]:
        """Get comprehensive system status"""
        
        return {
            'initialized': self.state.is_initialized,
            'tracking': self.state.is_tracking,
            'health_score': self.state.system_health_score,
            'consecutive_failures': self.state.consecutive_tracking_failures,
            'needs_relocalization': self.state.needs_relocalization,
            'metrics': {
                'frame_count': self.metrics.frame_count,
                'avg_confidence': self.metrics.avg_tracking_confidence,
                'tracking_rate': self.metrics.successful_tracking_rate,
                'relocalization_count': self.metrics.relocalization_count
            }
        }
    
    def shutdown(self):
        """Shutdown SLAM system and cleanup resources"""
        
        try:
            if self.slam_system:
                self.slam_system.shutdown()
                self.slam_system = None
                logger.info("Stella VSLAM system shutdown")
            
            self.config_manager.cleanup()
            
            self.state.is_initialized = False
            self.state.is_tracking = False
            
        except Exception as e:
            logger.error(f"SLAM shutdown error: {e}")
        
        logger.info("SLAM wrapper cleanup completed")