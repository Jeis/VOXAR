#!/usr/bin/env python3
"""
Spatial Platform - VIO Integration Module
Visual-Inertial Odometry processing for enhanced tracking stability
"""

import os
import sys
import json
import numpy as np
import cv2
import threading
import time
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, asdict
from pathlib import Path
import logging
from scipy.spatial.transform import Rotation as R
from collections import deque
import base64

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class IMUReading:
    """IMU sensor reading"""
    timestamp: float
    acceleration: np.ndarray  # [x, y, z] m/s²
    gyroscope: np.ndarray     # [x, y, z] rad/s
    magnetometer: np.ndarray  # [x, y, z] μT
    temperature: float = 0.0
    is_valid: bool = True

@dataclass
class CameraIntrinsics:
    """Camera calibration parameters"""
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

@dataclass
class VIOState:
    """VIO system state estimate"""
    timestamp: float
    position: np.ndarray      # [x, y, z] meters
    rotation: np.ndarray      # [qw, qx, qy, qz] quaternion
    velocity: np.ndarray      # [x, y, z] m/s
    angular_velocity: np.ndarray  # [x, y, z] rad/s
    confidence: float         # 0.0 to 1.0
    tracking_state: str       # "initializing", "tracking", "lost"
    covariance: np.ndarray    # 15x15 state covariance matrix

@dataclass
class VIODataPacket:
    """Input data packet for VIO processing"""
    timestamp: float
    imu_readings: List[IMUReading]
    camera_frame_base64: Optional[str]
    camera_params: CameraIntrinsics
    sequence_number: int

class ExtendedKalmanFilter:
    """
    Extended Kalman Filter for VIO state estimation
    State vector: [position(3), rotation(4), velocity(3), bias_accel(3), bias_gyro(3)]
    """
    
    def __init__(self):
        # State dimensions
        self.state_dim = 16  # pos(3) + quat(4) + vel(3) + ba(3) + bg(3)
        self.obs_dim = 6     # accelerometer(3) + gyroscope(3)
        
        # State vector [px, py, pz, qw, qx, qy, qz, vx, vy, vz, bax, bay, baz, bgx, bgy, bgz]
        self.state = np.zeros(self.state_dim)
        self.state[3] = 1.0  # Initialize quaternion to identity
        
        # Covariance matrix
        self.P = np.eye(self.state_dim) * 0.1
        
        # Process noise covariance
        self.Q = np.eye(self.state_dim) * 0.01
        self.Q[0:3, 0:3] *= 0.1   # Position noise
        self.Q[3:7, 3:7] *= 0.01  # Rotation noise
        self.Q[7:10, 7:10] *= 0.1 # Velocity noise
        self.Q[10:13, 10:13] *= 0.001  # Accel bias noise
        self.Q[13:16, 13:16] *= 0.001  # Gyro bias noise
        
        # Measurement noise covariance
        self.R = np.eye(self.obs_dim) * 0.1
        
        # Gravity vector (NED frame)
        self.gravity = np.array([0, 0, 9.81])
        
        # Initialization state
        self.is_initialized = False
        self.initialization_samples = []
        self.init_sample_count = 100
        
    def initialize(self, imu_readings: List[IMUReading]):
        """Initialize filter with static IMU readings"""
        if len(imu_readings) < self.init_sample_count:
            self.initialization_samples.extend(imu_readings)
            return False
            
        all_samples = self.initialization_samples + imu_readings
        
        # Calculate initial biases
        accel_samples = np.array([reading.acceleration for reading in all_samples])
        gyro_samples = np.array([reading.gyroscope for reading in all_samples])
        
        # Initial accelerometer bias (assuming stationary)
        accel_mean = np.mean(accel_samples, axis=0)
        # Gravity alignment - assume initial Z-axis points down
        self.state[10:13] = accel_mean - self.gravity
        
        # Initial gyroscope bias
        self.state[13:16] = np.mean(gyro_samples, axis=0)
        
        # Initial orientation from accelerometer (gravity alignment)
        gravity_normalized = accel_mean / np.linalg.norm(accel_mean)
        initial_rotation = self._align_with_gravity(gravity_normalized)
        self.state[3:7] = initial_rotation
        
        self.is_initialized = True
        logger.info("VIO filter initialized")
        logger.info(f"Initial accel bias: {self.state[10:13]}")
        logger.info(f"Initial gyro bias: {self.state[13:16]}")
        
        return True
        
    def _align_with_gravity(self, gravity_vector: np.ndarray) -> np.ndarray:
        """Calculate initial orientation from gravity vector"""
        # Align Z-axis with gravity
        z_axis = gravity_vector / np.linalg.norm(gravity_vector)
        
        # Create arbitrary X-axis perpendicular to gravity
        if abs(z_axis[0]) < 0.9:
            x_axis = np.array([1, 0, 0])
        else:
            x_axis = np.array([0, 1, 0])
            
        x_axis = x_axis - np.dot(x_axis, z_axis) * z_axis
        x_axis = x_axis / np.linalg.norm(x_axis)
        
        # Y-axis from cross product
        y_axis = np.cross(z_axis, x_axis)
        
        # Create rotation matrix and convert to quaternion
        rotation_matrix = np.column_stack([x_axis, y_axis, z_axis])
        rotation = R.from_matrix(rotation_matrix)
        return rotation.as_quat()  # [x, y, z, w]
        
    def predict(self, imu_reading: IMUReading, dt: float):
        """Prediction step using IMU measurements"""
        if not self.is_initialized:
            return
            
        # Extract state components
        position = self.state[0:3]
        quaternion = self.state[3:7]
        velocity = self.state[7:10]
        bias_accel = self.state[10:13]
        bias_gyro = self.state[13:16]
        
        # Correct IMU measurements
        accel_corrected = imu_reading.acceleration - bias_accel
        gyro_corrected = imu_reading.gyroscope - bias_gyro
        
        # Rotate acceleration to world frame and remove gravity
        rotation = R.from_quat(quaternion)
        accel_world = rotation.apply(accel_corrected) - self.gravity
        
        # Update state using kinematic equations
        # Position: p = p + v*dt + 0.5*a*dt²
        new_position = position + velocity * dt + 0.5 * accel_world * dt**2
        
        # Velocity: v = v + a*dt
        new_velocity = velocity + accel_world * dt
        
        # Rotation: integrate angular velocity
        rotation_delta = R.from_rotvec(gyro_corrected * dt)
        new_rotation = rotation * rotation_delta
        new_quaternion = new_rotation.as_quat()
        
        # Update state
        self.state[0:3] = new_position
        self.state[3:7] = new_quaternion
        self.state[7:10] = new_velocity
        # Biases remain constant in prediction
        
        # Update covariance (simplified - should use proper Jacobians)
        self.P += self.Q * dt
        
    def update_visual(self, visual_features: np.ndarray):
        """Update step using visual measurements (simplified)"""
        # This is a placeholder for visual updates
        # In a full implementation, this would use visual features
        # to correct drift and provide absolute pose updates
        pass
        
    def get_pose(self) -> VIOState:
        """Get current pose estimate"""
        confidence = self._calculate_confidence()
        tracking_state = self._determine_tracking_state(confidence)
        
        return VIOState(
            timestamp=time.time(),
            position=self.state[0:3].copy(),
            rotation=self.state[3:7].copy(),
            velocity=self.state[7:10].copy(),
            angular_velocity=np.zeros(3),  # Would need additional state for this
            confidence=confidence,
            tracking_state=tracking_state,
            covariance=self.P.copy()
        )
        
    def _calculate_confidence(self) -> float:
        """Calculate tracking confidence based on covariance"""
        # Simple confidence based on position covariance trace
        position_uncertainty = np.trace(self.P[0:3, 0:3])
        confidence = 1.0 / (1.0 + position_uncertainty)
        return np.clip(confidence, 0.0, 1.0)
        
    def _determine_tracking_state(self, confidence: float) -> str:
        """Determine tracking state based on confidence"""
        if not self.is_initialized:
            return "initializing"
        elif confidence > 0.7:
            return "tracking"
        elif confidence > 0.3:
            return "tracking_degraded"
        else:
            return "lost"

class VIOProcessor:
    """
    Main VIO processing class combining visual and inertial data
    """
    
    def __init__(self):
        self.ekf = ExtendedKalmanFilter()
        self.last_imu_timestamp = None
        self.last_visual_timestamp = None
        
        # Feature tracking for visual updates
        self.feature_tracker = None
        self.previous_frame = None
        self.current_features = None
        
        # Performance monitoring
        self.processing_times = deque(maxlen=100)
        self.frame_count = 0
        
        logger.info("VIO processor initialized")
        
    def process_packet(self, packet: VIODataPacket) -> VIOState:
        """Process VIO data packet and return state estimate"""
        start_time = time.time()
        
        try:
            # Process IMU readings
            for imu_reading in packet.imu_readings:
                self._process_imu_reading(imu_reading)
            
            # Process visual frame if available
            if packet.camera_frame_base64:
                self._process_visual_frame(packet.camera_frame_base64, packet.camera_params)
            
            # Get current state estimate
            state = self.ekf.get_pose()
            state.timestamp = packet.timestamp
            
            # Update performance metrics
            processing_time = time.time() - start_time
            self.processing_times.append(processing_time)
            self.frame_count += 1
            
            if self.frame_count % 100 == 0:
                avg_time = np.mean(self.processing_times)
                logger.info(f"VIO Performance: {avg_time*1000:.1f}ms avg processing time")
            
            return state
            
        except Exception as e:
            logger.error(f"VIO processing error: {e}")
            # Return default state on error
            return VIOState(
                timestamp=packet.timestamp,
                position=np.zeros(3),
                rotation=np.array([1, 0, 0, 0]),
                velocity=np.zeros(3),
                angular_velocity=np.zeros(3),
                confidence=0.0,
                tracking_state="lost",
                covariance=np.eye(15)
            )
    
    def _process_imu_reading(self, reading: IMUReading):
        """Process individual IMU reading"""
        if not reading.is_valid:
            return
            
        # Calculate time delta
        dt = 0.01  # Default 100Hz
        if self.last_imu_timestamp is not None:
            dt = reading.timestamp - self.last_imu_timestamp
            dt = np.clip(dt, 0.001, 0.1)  # Clamp to reasonable range
        
        # Initialize or predict
        if not self.ekf.is_initialized:
            self.ekf.initialize([reading])
        else:
            self.ekf.predict(reading, dt)
        
        self.last_imu_timestamp = reading.timestamp
        
    def _process_visual_frame(self, frame_base64: str, camera_params: CameraIntrinsics):
        """Process visual frame for feature tracking"""
        try:
            # Decode image
            image_bytes = base64.b64decode(frame_base64)
            image_array = np.frombuffer(image_bytes, dtype=np.uint8)
            frame = cv2.imdecode(image_array, cv2.IMREAD_GRAYSCALE)
            
            if frame is None:
                logger.warning("Failed to decode visual frame")
                return
            
            # Feature tracking (simplified implementation)
            if self.previous_frame is not None:
                # This is where you would implement feature tracking
                # For now, just update the frame
                pass
            
            self.previous_frame = frame.copy()
            
        except Exception as e:
            logger.error(f"Visual frame processing error: {e}")
    
    def reset(self):
        """Reset VIO processor state"""
        self.ekf = ExtendedKalmanFilter()
        self.last_imu_timestamp = None
        self.last_visual_timestamp = None
        self.previous_frame = None
        self.current_features = None
        logger.info("VIO processor reset")
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get processing statistics"""
        if not self.processing_times:
            return {}
            
        return {
            "frame_count": self.frame_count,
            "avg_processing_time_ms": np.mean(self.processing_times) * 1000,
            "max_processing_time_ms": np.max(self.processing_times) * 1000,
            "is_initialized": self.ekf.is_initialized,
            "current_confidence": self.ekf._calculate_confidence() if self.ekf.is_initialized else 0.0
        }

# Factory function for easy instantiation
def create_vio_processor() -> VIOProcessor:
    """Factory function to create configured VIO processor"""
    return VIOProcessor()

# Testing utilities
def test_vio_processor():
    """Test VIO processor with mock data"""
    logger.info("Testing VIO processor...")
    
    processor = create_vio_processor()
    
    # Generate mock IMU data
    for i in range(200):
        # Simulate stationary device with gravity
        imu_reading = IMUReading(
            timestamp=time.time() + i * 0.01,
            acceleration=np.array([0, 0, 9.81]) + np.random.normal(0, 0.1, 3),
            gyroscope=np.random.normal(0, 0.01, 3),
            magnetometer=np.array([25, 0, -45]) + np.random.normal(0, 1, 3),
            is_valid=True
        )
        
        # Create test packet
        packet = VIODataPacket(
            timestamp=imu_reading.timestamp,
            imu_readings=[imu_reading],
            camera_frame_base64=None,
            camera_params=CameraIntrinsics(800, 800, 320, 240),
            sequence_number=i
        )
        
        # Process packet
        state = processor.process_packet(packet)
        
        if i % 50 == 0:
            logger.info(f"Frame {i}: pos={state.position}, conf={state.confidence:.2f}, state={state.tracking_state}")
    
    # Get final statistics
    stats = processor.get_statistics()
    logger.info(f"VIO test completed: {stats}")
    
    return True

if __name__ == "__main__":
    test_vio_processor()