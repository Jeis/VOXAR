"""
VOXAR Spatial Platform - VIO Data Models
Enterprise-grade data structures for Visual-Inertial Odometry
"""

import numpy as np
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict

@dataclass
class IMUReading:
    """IMU sensor reading with enterprise validation"""
    timestamp: float
    acceleration: np.ndarray  # [x, y, z] m/s²
    gyroscope: np.ndarray     # [x, y, z] rad/s
    magnetometer: np.ndarray  # [x, y, z] μT
    temperature: float = 0.0
    is_valid: bool = True
    
    def __post_init__(self):
        """Validate IMU data on initialization"""
        if self.timestamp <= 0:
            raise ValueError("IMU timestamp must be positive")
            
        if self.acceleration.shape != (3,):
            raise ValueError("Acceleration must be 3D vector")
            
        if self.gyroscope.shape != (3,):
            raise ValueError("Gyroscope must be 3D vector")
            
        if self.magnetometer.shape != (3,):
            raise ValueError("Magnetometer must be 3D vector")
    
    @property
    def acceleration_magnitude(self) -> float:
        """Get acceleration magnitude"""
        return np.linalg.norm(self.acceleration)
    
    @property
    def angular_velocity_magnitude(self) -> float:
        """Get angular velocity magnitude"""
        return np.linalg.norm(self.gyroscope)
    
    def is_stationary(self, accel_threshold: float = 0.5, gyro_threshold: float = 0.1) -> bool:
        """Check if device is approximately stationary"""
        gravity = 9.81
        accel_variance = abs(self.acceleration_magnitude - gravity)
        return (accel_variance < accel_threshold and 
                self.angular_velocity_magnitude < gyro_threshold)

@dataclass
class CameraIntrinsics:
    """Camera calibration parameters with enterprise validation"""
    fx: float  # Focal length x
    fy: float  # Focal length y
    cx: float  # Principal point x
    cy: float  # Principal point y
    k1: float = 0.0  # Radial distortion
    k2: float = 0.0  # Radial distortion
    p1: float = 0.0  # Tangential distortion
    p2: float = 0.0  # Tangential distortion
    k3: float = 0.0  # Radial distortion
    width: int = 640
    height: int = 480
    
    def __post_init__(self):
        """Validate camera parameters"""
        if self.fx <= 0 or self.fy <= 0:
            raise ValueError("Focal lengths must be positive")
            
        if not (0 <= self.cx <= self.width):
            raise ValueError("Principal point cx out of bounds")
            
        if not (0 <= self.cy <= self.height):
            raise ValueError("Principal point cy out of bounds")
    
    def to_matrix(self) -> np.ndarray:
        """Convert to 3x3 intrinsic matrix"""
        return np.array([
            [self.fx, 0, self.cx],
            [0, self.fy, self.cy],
            [0, 0, 1]
        ])
    
    def get_distortion_coeffs(self) -> np.ndarray:
        """Get distortion coefficients for OpenCV"""
        return np.array([self.k1, self.k2, self.p1, self.p2, self.k3])

@dataclass
class VIOState:
    """VIO system state with comprehensive pose and uncertainty"""
    timestamp: float
    position: np.ndarray        # [x, y, z] world position
    orientation: np.ndarray     # [qw, qx, qy, qz] quaternion
    velocity: np.ndarray        # [vx, vy, vz] world velocity
    angular_velocity: np.ndarray # [wx, wy, wz] body angular velocity
    imu_bias_accel: np.ndarray  # [bax, bay, baz] accelerometer bias
    imu_bias_gyro: np.ndarray   # [bgx, bgy, bgz] gyroscope bias
    
    # Uncertainty and quality metrics
    position_covariance: np.ndarray     # 3x3 position uncertainty
    orientation_covariance: np.ndarray  # 3x3 orientation uncertainty
    confidence: float = 1.0
    tracking_state: str = "unknown"
    
    def __post_init__(self):
        """Validate VIO state"""
        if self.position.shape != (3,):
            raise ValueError("Position must be 3D vector")
            
        if self.orientation.shape != (4,):
            raise ValueError("Orientation must be quaternion (4D)")
            
        if self.velocity.shape != (3,):
            raise ValueError("Velocity must be 3D vector")
    
    @property
    def is_valid_pose(self) -> bool:
        """Check if pose is valid for tracking"""
        return (self.tracking_state in ['tracking', 'good'] and
                self.confidence > 0.3 and
                not np.any(np.isnan(self.position)) and
                not np.any(np.isnan(self.orientation)))
    
    def to_transformation_matrix(self) -> np.ndarray:
        """Convert to 4x4 transformation matrix"""
        from scipy.spatial.transform import Rotation
        
        T = np.eye(4)
        T[:3, :3] = Rotation.from_quat(self.orientation).as_matrix()
        T[:3, 3] = self.position
        return T
    
    def get_pose_uncertainty(self) -> float:
        """Get overall pose uncertainty metric"""
        pos_uncertainty = np.trace(self.position_covariance)
        ori_uncertainty = np.trace(self.orientation_covariance)
        return np.sqrt(pos_uncertainty + ori_uncertainty)

@dataclass
class VIODataPacket:
    """Combined VIO data packet for processing"""
    timestamp: float
    imu_reading: Optional[IMUReading] = None
    camera_frame: Optional[str] = None  # Base64 encoded image
    camera_intrinsics: Optional[CameraIntrinsics] = None
    
    @property
    def has_imu_data(self) -> bool:
        """Check if packet contains IMU data"""
        return self.imu_reading is not None and self.imu_reading.is_valid
    
    @property
    def has_visual_data(self) -> bool:
        """Check if packet contains visual data"""
        return (self.camera_frame is not None and 
                self.camera_intrinsics is not None)
    
    @property
    def packet_type(self) -> str:
        """Get packet type based on contents"""
        if self.has_imu_data and self.has_visual_data:
            return "vio_full"
        elif self.has_imu_data:
            return "imu_only"
        elif self.has_visual_data:
            return "visual_only"
        else:
            return "empty"

@dataclass
class VIOCalibration:
    """VIO system calibration parameters"""
    # Camera-IMU extrinsics (transformation from IMU to camera)
    T_cam_imu: np.ndarray  # 4x4 transformation matrix
    
    # Temporal calibration
    temporal_offset: float = 0.0  # Camera-IMU time offset (seconds)
    
    # IMU noise characteristics
    accel_noise_std: float = 0.1      # m/s² standard deviation
    gyro_noise_std: float = 0.01      # rad/s standard deviation
    accel_bias_std: float = 0.05      # m/s² bias standard deviation
    gyro_bias_std: float = 0.001      # rad/s bias standard deviation
    
    # Visual noise characteristics
    pixel_noise_std: float = 1.0      # pixel standard deviation
    
    def __post_init__(self):
        """Validate calibration parameters"""
        if self.T_cam_imu.shape != (4, 4):
            raise ValueError("Camera-IMU extrinsics must be 4x4 matrix")
            
        # Check if transformation matrix is valid
        if not np.allclose(self.T_cam_imu[3, :], [0, 0, 0, 1]):
            raise ValueError("Invalid transformation matrix format")
    
    @classmethod
    def create_default(cls) -> 'VIOCalibration':
        """Create default calibration for typical mobile device"""
        # Default: camera and IMU roughly aligned
        T_cam_imu = np.eye(4)
        
        return cls(
            T_cam_imu=T_cam_imu,
            temporal_offset=0.0,
            accel_noise_std=0.1,
            gyro_noise_std=0.01,
            accel_bias_std=0.05,
            gyro_bias_std=0.001,
            pixel_noise_std=1.0
        )

@dataclass
class VIOMetrics:
    """VIO performance metrics"""
    total_packets_processed: int = 0
    imu_packets_processed: int = 0
    visual_packets_processed: int = 0
    
    # Processing times
    avg_processing_time_ms: float = 0.0
    max_processing_time_ms: float = 0.0
    
    # Quality metrics
    avg_confidence: float = 0.0
    tracking_lost_count: int = 0
    initialization_count: int = 0
    
    # Feature tracking metrics
    avg_features_tracked: float = 0.0
    feature_tracking_failures: int = 0
    
    def update_processing_time(self, time_ms: float):
        """Update processing time statistics"""
        if self.total_packets_processed == 0:
            self.avg_processing_time_ms = time_ms
        else:
            # Running average
            alpha = 0.1
            self.avg_processing_time_ms = (
                alpha * time_ms + 
                (1 - alpha) * self.avg_processing_time_ms
            )
        
        self.max_processing_time_ms = max(self.max_processing_time_ms, time_ms)
    
    def update_confidence(self, confidence: float):
        """Update confidence statistics"""
        if self.total_packets_processed == 0:
            self.avg_confidence = confidence
        else:
            # Running average
            alpha = 0.1
            self.avg_confidence = (
                alpha * confidence + 
                (1 - alpha) * self.avg_confidence
            )
    
    @property
    def tracking_success_rate(self) -> float:
        """Calculate tracking success rate"""
        if self.total_packets_processed == 0:
            return 0.0
        
        failed_packets = self.tracking_lost_count + self.feature_tracking_failures
        success_packets = self.total_packets_processed - failed_packets
        
        return success_packets / self.total_packets_processed