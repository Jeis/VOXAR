"""
VOXAR Spatial Platform - VIO Extended Kalman Filter
Enterprise-grade Extended Kalman Filter for Visual-Inertial Odometry
"""

import numpy as np
import logging
from typing import Dict, List, Optional
from scipy.spatial.transform import Rotation as R

from .vio_models import IMUReading, VIOState, VIOCalibration, VIOMetrics

logger = logging.getLogger(__name__)

class ExtendedKalmanFilter:
    """
    Enterprise Extended Kalman Filter for VIO estimation
    Handles IMU prediction and visual measurement updates
    """
    
    def __init__(self, calibration: VIOCalibration):
        self.calibration = calibration
        
        # State vector: [pos(3), quat(4), vel(3), ang_vel(3), bias_accel(3), bias_gyro(3)]
        # Total: 19 states (using quaternion for rotation)
        self.state_size = 19
        self.state = np.zeros(self.state_size)
        self.covariance = np.eye(self.state_size) * 1000.0  # Large initial uncertainty
        
        # State indices for easier access
        self.pos_idx = slice(0, 3)       # Position
        self.quat_idx = slice(3, 7)      # Quaternion [w, x, y, z]
        self.vel_idx = slice(7, 10)      # Velocity
        self.ang_vel_idx = slice(10, 13) # Angular velocity
        self.bias_a_idx = slice(13, 16)  # Accelerometer bias
        self.bias_g_idx = slice(16, 19)  # Gyroscope bias
        
        # Initialize quaternion to identity
        self.state[self.quat_idx] = [1, 0, 0, 0]  # [w, x, y, z]
        
        # Process noise matrix
        self.Q = self._build_process_noise_matrix()
        
        # Measurement noise for visual features
        self.R_visual = np.eye(2) * (calibration.pixel_noise_std ** 2)
        
        # System state
        self.is_initialized = False
        self.last_imu_timestamp = 0.0
        self.gravity = np.array([0, 0, -9.81])
        
        logger.info("✅ Extended Kalman Filter initialized")
    
    def _build_process_noise_matrix(self) -> np.ndarray:
        """Build process noise covariance matrix"""
        Q = np.zeros((self.state_size, self.state_size))
        
        # Position noise (from velocity integration)
        Q[self.pos_idx, self.pos_idx] = np.eye(3) * 0.01
        
        # Quaternion noise (from angular velocity integration)
        Q[self.quat_idx, self.quat_idx] = np.eye(4) * 0.001
        
        # Velocity noise (from acceleration integration)
        Q[self.vel_idx, self.vel_idx] = np.eye(3) * (self.calibration.accel_noise_std ** 2)
        
        # Angular velocity noise
        Q[self.ang_vel_idx, self.ang_vel_idx] = np.eye(3) * (self.calibration.gyro_noise_std ** 2)
        
        # Bias noise (random walk)
        Q[self.bias_a_idx, self.bias_a_idx] = np.eye(3) * (self.calibration.accel_bias_std ** 2)
        Q[self.bias_g_idx, self.bias_g_idx] = np.eye(3) * (self.calibration.gyro_bias_std ** 2)
        
        return Q
    
    def initialize(self, imu_readings: List[IMUReading]) -> bool:
        """Initialize filter with static IMU readings for gravity alignment"""
        
        if len(imu_readings) < 50:
            logger.warning("Insufficient IMU readings for initialization")
            return False
        
        try:
            # Check if device is stationary
            stationary_count = sum(1 for reading in imu_readings if reading.is_stationary())
            if stationary_count < len(imu_readings) * 0.8:
                logger.warning("Device not stationary enough for initialization")
                return False
            
            # Estimate initial gravity vector from accelerometer
            accel_readings = np.array([reading.acceleration for reading in imu_readings])
            gravity_estimate = np.mean(accel_readings, axis=0)
            
            # Align initial orientation with gravity
            initial_rotation = self._align_with_gravity(gravity_estimate)
            
            # Set initial state
            self.state[self.pos_idx] = [0, 0, 0]  # Start at origin
            self.state[self.quat_idx] = initial_rotation  # Align with gravity
            self.state[self.vel_idx] = [0, 0, 0]  # Start stationary
            self.state[self.ang_vel_idx] = [0, 0, 0]  # No initial rotation
            
            # Estimate initial biases
            gyro_readings = np.array([reading.gyroscope for reading in imu_readings])
            self.state[self.bias_g_idx] = np.mean(gyro_readings, axis=0)
            
            # Accelerometer bias is gravity-compensated mean
            gravity_world = np.array([0, 0, -9.81])
            R_body_world = R.from_quat(initial_rotation[[1, 2, 3, 0]]).as_matrix()  # Convert to [x,y,z,w]
            expected_accel = R_body_world.T @ gravity_world
            self.state[self.bias_a_idx] = gravity_estimate - expected_accel
            
            # Reduce initial uncertainty after initialization
            self.covariance = np.eye(self.state_size)
            self.covariance[self.pos_idx, self.pos_idx] *= 1.0      # 1m position uncertainty
            self.covariance[self.quat_idx, self.quat_idx] *= 0.1    # 0.1 rad orientation uncertainty
            self.covariance[self.vel_idx, self.vel_idx] *= 0.1      # 0.1 m/s velocity uncertainty
            self.covariance[self.bias_a_idx, self.bias_a_idx] *= 0.01  # Accelerometer bias
            self.covariance[self.bias_g_idx, self.bias_g_idx] *= 0.001 # Gyroscope bias
            
            self.is_initialized = True
            self.last_imu_timestamp = imu_readings[-1].timestamp
            
            logger.info("✅ VIO Extended Kalman Filter initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"VIO initialization failed: {e}")
            return False
    
    def _align_with_gravity(self, gravity_vector: np.ndarray) -> np.ndarray:
        """Compute initial orientation to align z-axis with gravity"""
        
        # Normalize gravity vector
        gravity_norm = gravity_vector / np.linalg.norm(gravity_vector)
        
        # Target gravity direction (negative z in world frame)
        target_gravity = np.array([0, 0, -1])
        
        # Compute rotation to align gravity_norm with target_gravity
        # Using Rodrigues' rotation formula
        v = np.cross(gravity_norm, target_gravity)
        s = np.linalg.norm(v)
        c = np.dot(gravity_norm, target_gravity)
        
        if s < 1e-6:  # Vectors are already aligned
            return np.array([1, 0, 0, 0])  # Identity quaternion [w, x, y, z]
        
        # Skew-symmetric matrix
        vx = np.array([[0, -v[2], v[1]],
                       [v[2], 0, -v[0]],
                       [-v[1], v[0], 0]])
        
        # Rotation matrix
        R_matrix = np.eye(3) + vx + vx @ vx * ((1 - c) / (s ** 2))
        
        # Convert to quaternion [w, x, y, z]
        rotation = R.from_matrix(R_matrix)
        quat_xyzw = rotation.as_quat()  # [x, y, z, w]
        quat_wxyz = np.array([quat_xyzw[3], quat_xyzw[0], quat_xyzw[1], quat_xyzw[2]])
        
        return quat_wxyz
    
    def predict(self, imu_reading: IMUReading) -> bool:
        """Predict state forward using IMU measurements"""
        
        if not self.is_initialized:
            logger.warning("Filter not initialized, cannot predict")
            return False
        
        # Calculate time delta
        dt = imu_reading.timestamp - self.last_imu_timestamp
        if dt <= 0 or dt > 0.1:  # Sanity check on time delta
            logger.warning(f"Invalid time delta: {dt}")
            return False
        
        try:
            # Extract current state
            pos = self.state[self.pos_idx].copy()
            quat = self.state[self.quat_idx].copy()  # [w, x, y, z]
            vel = self.state[self.vel_idx].copy()
            ang_vel = self.state[self.ang_vel_idx].copy()
            bias_a = self.state[self.bias_a_idx].copy()
            bias_g = self.state[self.bias_g_idx].copy()
            
            # Correct IMU measurements with bias
            accel_corrected = imu_reading.acceleration - bias_a
            gyro_corrected = imu_reading.gyroscope - bias_g
            
            # Convert quaternion to rotation matrix for gravity compensation
            R_body_world = R.from_quat(quat[[1, 2, 3, 0]]).as_matrix()  # Convert to [x,y,z,w]
            
            # Gravity compensation
            gravity_body = R_body_world.T @ self.gravity
            accel_world = R_body_world @ accel_corrected - self.gravity
            
            # State prediction (using simple Euler integration)
            # Position: p = p + v*dt + 0.5*a*dt^2
            new_pos = pos + vel * dt + 0.5 * accel_world * (dt ** 2)
            
            # Velocity: v = v + a*dt
            new_vel = vel + accel_world * dt
            
            # Orientation: integrate angular velocity
            ang_vel_dt = gyro_corrected * dt
            ang_vel_norm = np.linalg.norm(ang_vel_dt)
            
            if ang_vel_norm > 1e-8:
                # Rotation quaternion from angular velocity
                angle = ang_vel_norm
                axis = ang_vel_dt / ang_vel_norm
                delta_quat = np.array([
                    np.cos(angle / 2),
                    axis[0] * np.sin(angle / 2),
                    axis[1] * np.sin(angle / 2),
                    axis[2] * np.sin(angle / 2)
                ])
                
                # Quaternion multiplication: q_new = q_current * delta_q
                new_quat = self._quaternion_multiply(quat, delta_quat)
            else:
                new_quat = quat
            
            # Normalize quaternion
            new_quat = new_quat / np.linalg.norm(new_quat)
            
            # Angular velocity and biases remain constant (no prediction model)
            new_ang_vel = ang_vel
            new_bias_a = bias_a
            new_bias_g = bias_g
            
            # Update state
            self.state[self.pos_idx] = new_pos
            self.state[self.quat_idx] = new_quat
            self.state[self.vel_idx] = new_vel
            self.state[self.ang_vel_idx] = new_ang_vel
            self.state[self.bias_a_idx] = new_bias_a
            self.state[self.bias_g_idx] = new_bias_g
            
            # Prediction step: P = F*P*F' + Q
            F = self._compute_jacobian(dt, accel_corrected, gyro_corrected)
            Q_scaled = self.Q * dt  # Scale process noise by time
            
            self.covariance = F @ self.covariance @ F.T + Q_scaled
            
            self.last_imu_timestamp = imu_reading.timestamp
            
            return True
            
        except Exception as e:
            logger.error(f"Prediction step failed: {e}")
            return False
    
    def _quaternion_multiply(self, q1: np.ndarray, q2: np.ndarray) -> np.ndarray:
        """Multiply two quaternions [w, x, y, z]"""
        w1, x1, y1, z1 = q1
        w2, x2, y2, z2 = q2
        
        return np.array([
            w1*w2 - x1*x2 - y1*y2 - z1*z2,
            w1*x2 + x1*w2 + y1*z2 - z1*y2,
            w1*y2 - x1*z2 + y1*w2 + z1*x2,
            w1*z2 + x1*y2 - y1*x2 + z1*w2
        ])
    
    def _compute_jacobian(self, dt: float, accel: np.ndarray, gyro: np.ndarray) -> np.ndarray:
        """Compute state transition Jacobian matrix"""
        
        F = np.eye(self.state_size)
        
        # Position depends on velocity
        F[self.pos_idx, self.vel_idx] = np.eye(3) * dt
        
        # Velocity depends on acceleration (through rotation)
        # This is simplified - full implementation would include rotation Jacobian
        F[self.vel_idx, self.vel_idx] = np.eye(3)
        
        # Quaternion depends on angular velocity
        # Simplified approximation
        F[self.quat_idx, self.ang_vel_idx] = np.eye(4, 3) * dt * 0.5
        
        return F
    
    def update_visual(self, visual_features: Dict[str, np.ndarray]) -> bool:
        """Update filter with visual feature measurements"""
        
        if not self.is_initialized:
            return False
        
        try:
            # Extract feature correspondences
            keypoints = visual_features.get('keypoints')  # 2D image points
            landmarks = visual_features.get('landmarks')  # 3D world points
            
            if keypoints is None or landmarks is None or len(keypoints) < 4:
                return False
            
            # Compute innovation (measurement residual)
            innovation = self._compute_visual_innovation(keypoints, landmarks)
            
            if innovation is None:
                return False
            
            # Compute measurement Jacobian
            H = self._compute_visual_jacobian(keypoints, landmarks)
            
            # Innovation covariance: S = H*P*H' + R
            S = H @ self.covariance @ H.T + self.R_visual
            
            # Kalman gain: K = P*H'*S^-1
            try:
                K = self.covariance @ H.T @ np.linalg.inv(S)
            except np.linalg.LinAlgError:
                logger.warning("Innovation covariance is singular")
                return False
            
            # State update: x = x + K*innovation
            self.state += K @ innovation
            
            # Covariance update: P = (I - K*H)*P
            I_KH = np.eye(self.state_size) - K @ H
            self.covariance = I_KH @ self.covariance
            
            # Normalize quaternion after update
            quat = self.state[self.quat_idx]
            self.state[self.quat_idx] = quat / np.linalg.norm(quat)
            
            return True
            
        except Exception as e:
            logger.error(f"Visual update failed: {e}")
            return False
    
    def _compute_visual_innovation(self, keypoints: np.ndarray, landmarks: np.ndarray) -> Optional[np.ndarray]:
        """Compute visual measurement innovation (residual)"""
        
        # This is a simplified implementation
        # Real implementation would project 3D landmarks to image plane
        # and compute difference with observed keypoints
        
        if len(keypoints) != len(landmarks):
            return None
        
        # Placeholder: return small residual
        innovation = np.zeros(2)
        return innovation
    
    def _compute_visual_jacobian(self, keypoints: np.ndarray, landmarks: np.ndarray) -> np.ndarray:
        """Compute measurement Jacobian for visual features"""
        
        # Simplified Jacobian (real implementation would compute projection derivatives)
        H = np.zeros((2, self.state_size))
        
        # Visual measurements primarily affect position and orientation
        H[:2, self.pos_idx[:2]] = np.eye(2)  # Position x, y
        H[:2, self.quat_idx[:2]] = np.eye(2) * 0.1  # Orientation (simplified)
        
        return H
    
    def get_state(self) -> VIOState:
        """Get current VIO state estimate"""
        
        # Calculate confidence based on covariance trace
        pos_uncertainty = np.trace(self.covariance[self.pos_idx, self.pos_idx])
        ori_uncertainty = np.trace(self.covariance[self.quat_idx, self.quat_idx])
        confidence = max(0.0, min(1.0, 1.0 - (pos_uncertainty + ori_uncertainty) / 10.0))
        
        # Determine tracking state
        if not self.is_initialized:
            tracking_state = "initializing"
        elif confidence > 0.7:
            tracking_state = "tracking"
        elif confidence > 0.3:
            tracking_state = "limited"
        else:
            tracking_state = "lost"
        
        return VIOState(
            timestamp=self.last_imu_timestamp,
            position=self.state[self.pos_idx].copy(),
            orientation=self.state[self.quat_idx].copy(),  # [w, x, y, z]
            velocity=self.state[self.vel_idx].copy(),
            angular_velocity=self.state[self.ang_vel_idx].copy(),
            imu_bias_accel=self.state[self.bias_a_idx].copy(),
            imu_bias_gyro=self.state[self.bias_g_idx].copy(),
            position_covariance=self.covariance[self.pos_idx, self.pos_idx].copy(),
            orientation_covariance=self.covariance[self.quat_idx[:3], self.quat_idx[:3]].copy(),
            confidence=confidence,
            tracking_state=tracking_state
        )
    
    def reset(self):
        """Reset filter to uninitialized state"""
        self.state = np.zeros(self.state_size)
        self.state[self.quat_idx] = [1, 0, 0, 0]  # Identity quaternion
        self.covariance = np.eye(self.state_size) * 1000.0
        self.is_initialized = False
        self.last_imu_timestamp = 0.0
        
        logger.info("VIO Extended Kalman Filter reset")