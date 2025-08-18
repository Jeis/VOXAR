"""
VOXAR Spatial Platform - SLAM Data Models
Enterprise-grade data structures for SLAM operations
"""

import numpy as np
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

@dataclass
class CameraFrame:
    """Camera frame data structure for SLAM processing"""
    timestamp: float
    image: np.ndarray
    camera_id: int = 0
    intrinsics: Optional[np.ndarray] = None
    frame_width: int = 0
    frame_height: int = 0
    
    def __post_init__(self):
        """Validate frame data on initialization"""
        if self.image is not None:
            self.frame_height, self.frame_width = self.image.shape[:2]
            
        if self.timestamp <= 0:
            raise ValueError("Frame timestamp must be positive")
            
        if self.intrinsics is not None and self.intrinsics.shape != (3, 3):
            raise ValueError("Camera intrinsics must be 3x3 matrix")
    
    @property
    def is_valid(self) -> bool:
        """Check if frame data is valid for SLAM processing"""
        return (self.image is not None and 
                self.image.size > 0 and
                self.timestamp > 0)

@dataclass 
class Pose:
    """6DOF pose representation with enterprise validation"""
    timestamp: float
    position: np.ndarray  # [x, y, z]
    rotation: np.ndarray  # [qw, qx, qy, qz] quaternion
    confidence: float
    tracking_state: str
    
    def __post_init__(self):
        """Validate pose data"""
        if self.position.shape != (3,):
            raise ValueError("Position must be 3D vector")
            
        if self.rotation.shape != (4,):
            raise ValueError("Rotation must be quaternion (4D vector)")
            
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError("Confidence must be between 0.0 and 1.0")
    
    @property
    def is_valid_tracking(self) -> bool:
        """Check if pose represents valid tracking"""
        return (self.tracking_state in ['tracking', 'good'] and
                self.confidence > 0.3)
    
    def to_matrix(self) -> np.ndarray:
        """Convert pose to 4x4 transformation matrix"""
        from scipy.spatial.transform import Rotation
        
        T = np.eye(4)
        T[:3, :3] = Rotation.from_quat(self.rotation).as_matrix()
        T[:3, 3] = self.position
        return T

@dataclass
class SLAMConfig:
    """Enterprise SLAM configuration with validation"""
    vocab_file: str
    camera_config: Dict[str, Any]
    map_db_path: Optional[str] = None
    enable_loop_closure: bool = True
    enable_relocalization: bool = True
    log_level: str = "info"
    
    # Performance settings
    max_features: int = 2000
    tracking_quality_threshold: float = 0.5
    reloc_attempts: int = 5
    
    # Real-world camera parameters
    fps: float = 30.0
    image_width: int = 1920
    image_height: int = 1080
    
    def __post_init__(self):
        """Validate configuration"""
        if not self.vocab_file or not self.vocab_file.endswith('.fbow'):
            raise ValueError("Valid vocabulary file (.fbow) required")
            
        required_cam_params = ['Camera.fx', 'Camera.fy', 'Camera.cx', 'Camera.cy']
        for param in required_cam_params:
            if param not in self.camera_config:
                raise ValueError(f"Missing required camera parameter: {param}")
        
        if not (10.0 <= self.fps <= 120.0):
            raise ValueError("FPS must be between 10 and 120")
            
        if self.log_level not in ['debug', 'info', 'warning', 'error']:
            raise ValueError("Invalid log level")

@dataclass
class SLAMMetrics:
    """Performance metrics for SLAM system"""
    frame_count: int = 0
    tracking_time_ms: float = 0.0
    mapping_time_ms: float = 0.0
    loop_closure_count: int = 0
    relocalization_count: int = 0
    map_points: int = 0
    keyframes: int = 0
    
    # Quality metrics
    avg_tracking_confidence: float = 0.0
    tracking_loss_count: int = 0
    successful_tracking_rate: float = 0.0
    
    def update_tracking_stats(self, pose: Pose, processing_time_ms: float):
        """Update tracking statistics with new pose"""
        self.frame_count += 1
        self.tracking_time_ms = processing_time_ms
        
        if pose.is_valid_tracking:
            # Running average of confidence
            alpha = 0.1  # Smoothing factor
            self.avg_tracking_confidence = (
                alpha * pose.confidence + 
                (1 - alpha) * self.avg_tracking_confidence
            )
            
        if pose.tracking_state == 'lost':
            self.tracking_loss_count += 1
        
        self.successful_tracking_rate = (
            max(0, self.frame_count - self.tracking_loss_count) / 
            max(1, self.frame_count)
        )

@dataclass
class SLAMState:
    """Current state of SLAM system"""
    is_initialized: bool = False
    is_tracking: bool = False
    current_pose: Optional[Pose] = None
    map_loaded: bool = False
    loop_closure_enabled: bool = True
    
    # System health
    last_successful_tracking: float = 0.0
    consecutive_tracking_failures: int = 0
    system_health_score: float = 1.0
    
    def update_health_score(self, pose: Optional[Pose]):
        """Update system health based on tracking performance"""
        if pose and pose.is_valid_tracking:
            self.consecutive_tracking_failures = 0
            self.last_successful_tracking = pose.timestamp
            self.system_health_score = min(1.0, self.system_health_score + 0.1)
        else:
            self.consecutive_tracking_failures += 1
            # Exponential decay for health score
            decay_factor = min(0.9, 1.0 - (self.consecutive_tracking_failures * 0.1))
            self.system_health_score *= decay_factor
    
    @property
    def needs_relocalization(self) -> bool:
        """Check if system needs relocalization"""
        return (self.consecutive_tracking_failures > 10 or
                self.system_health_score < 0.3)