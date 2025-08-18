"""
VIO (Visual-Inertial Odometry) Tracking
Handles IMU fusion and motion tracking
"""

import time
import numpy as np
import logging
from typing import List, Dict, Any, Optional

from vio_integration import (
    create_vio_processor,
    VIOProcessor,
    VIODataPacket,
    VIOState,
    IMUReading,
    CameraIntrinsics as VIOCameraIntrinsics
)

logger = logging.getLogger(__name__)


class VioTracker:
    """VIO system for motion tracking with IMU fusion"""
    
    def __init__(self):
        self.vio_processor: Optional[VIOProcessor] = None
        self.is_initialized = False
        self.processing_stats = {
            'packets_processed': 0,
            'average_processing_time': 0.0,
            'last_confidence': 0.0
        }
        
    def initialize(self) -> bool:
        """Initialize VIO processing system"""
        try:
            logger.info("Setting up VIO processor")
            self.vio_processor = create_vio_processor()
            self.is_initialized = True
            return True
            
        except Exception as e:
            logger.error(f"VIO initialization failed: {e}")
            return False
    
    def process_sensor_data(self, 
                          imu_readings: List[Dict[str, Any]], 
                          camera_frame: Optional[str] = None,
                          camera_params: Dict[str, Any] = None,
                          timestamp: float = None) -> Dict[str, Any]:
        """Process VIO data and return motion estimate"""
        
        if not self.vio_processor:
            return self._create_error_response("VIO not initialized")
        
        start_time = time.time()
        
        try:
            # Convert IMU data to internal format
            processed_imu = []
            for reading in imu_readings:
                imu_data = IMUReading(
                    timestamp=reading['timestamp'],
                    acceleration=np.array(reading['acceleration']),
                    gyroscope=np.array(reading['gyroscope']),
                    magnetometer=np.array(reading.get('magnetometer', [0, 0, 0])),
                    temperature=reading.get('temperature', 0.0),
                    is_valid=reading.get('is_valid', True)
                )
                processed_imu.append(imu_data)
            
            # Set up camera parameters if provided
            cam_intrinsics = None
            if camera_params:
                cam_intrinsics = VIOCameraIntrinsics(
                    fx=camera_params['fx'],
                    fy=camera_params['fy'],
                    cx=camera_params['cx'],
                    cy=camera_params['cy'],
                    k1=camera_params.get('k1', 0.0),
                    k2=camera_params.get('k2', 0.0),
                    p1=camera_params.get('p1', 0.0),
                    p2=camera_params.get('p2', 0.0),
                    k3=camera_params.get('k3', 0.0),
                    width=camera_params.get('width', 640),
                    height=camera_params.get('height', 480)
                )
            
            # Create VIO packet
            packet = VIODataPacket(
                timestamp=timestamp or time.time(),
                imu_readings=processed_imu,
                camera_frame_base64=camera_frame,
                camera_params=cam_intrinsics,
                sequence_number=self.processing_stats['packets_processed']
            )
            
            # Process through VIO system
            motion_state = self.vio_processor.process_packet(packet)
            
            # Update stats
            processing_time = (time.time() - start_time) * 1000
            self._update_stats(processing_time, motion_state.confidence)
            
            return {
                'success': True,
                'pose': {
                    'position': motion_state.position.tolist(),
                    'rotation': motion_state.rotation.tolist(),
                    'velocity': motion_state.velocity.tolist(),
                    'angular_velocity': motion_state.angular_velocity.tolist()
                },
                'confidence': motion_state.confidence,
                'tracking_state': motion_state.tracking_state,
                'processing_time_ms': processing_time,
                'sequence_number': packet.sequence_number
            }
            
        except Exception as e:
            logger.error(f"VIO processing failed: {e}")
            return self._create_error_response(str(e))
    
    def get_status(self) -> Dict[str, Any]:
        """Get current VIO system status"""
        if not self.vio_processor:
            return {
                'initialized': False,
                'packets_processed': 0,
                'avg_processing_time_ms': 0.0,
                'current_confidence': 0.0,
                'tracking_state': 'not_initialized'
            }
        
        try:
            processor_stats = self.vio_processor.get_statistics()
            
            return {
                'initialized': self.is_initialized,
                'packets_processed': self.processing_stats['packets_processed'],
                'avg_processing_time_ms': self.processing_stats['average_processing_time'],
                'current_confidence': self.processing_stats['last_confidence'],
                'tracking_state': processor_stats.get('tracking_state', 'unknown')
            }
            
        except Exception as e:
            logger.error(f"Failed to get VIO status: {e}")
            return {
                'initialized': False,
                'packets_processed': 0,
                'avg_processing_time_ms': 0.0,
                'current_confidence': 0.0,
                'tracking_state': 'error'
            }
    
    def reset(self) -> bool:
        """Reset VIO tracking state"""
        try:
            if self.vio_processor:
                self.vio_processor.reset()
            else:
                self.vio_processor = create_vio_processor()
            
            # Clear stats
            self.processing_stats = {
                'packets_processed': 0,
                'average_processing_time': 0.0,
                'last_confidence': 0.0
            }
            
            logger.info("VIO system reset")
            return True
            
        except Exception as e:
            logger.error(f"VIO reset failed: {e}")
            return False
    
    def _update_stats(self, processing_time: float, confidence: float):
        """Update processing statistics"""
        count = self.processing_stats['packets_processed']
        current_avg = self.processing_stats['average_processing_time']
        
        # Running average calculation
        new_avg = (current_avg * count + processing_time) / (count + 1)
        
        self.processing_stats.update({
            'packets_processed': count + 1,
            'average_processing_time': new_avg,
            'last_confidence': confidence
        })
    
    def _create_error_response(self, error_message: str) -> Dict[str, Any]:
        """Create standardized error response"""
        return {
            'success': False,
            'error': error_message,
            'pose': None,
            'confidence': 0.0,
            'tracking_state': 'error',
            'processing_time_ms': 0.0,
            'sequence_number': self.processing_stats['packets_processed']
        }