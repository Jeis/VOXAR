"""
Pydantic models for API requests and responses
Clear data contracts for all endpoints
"""

from pydantic import BaseModel
from typing import List, Optional, Dict, Any


class CameraConfig(BaseModel):
    fx: float
    fy: float
    cx: float
    cy: float
    width: int
    height: int
    fps: float = 30.0
    k1: float = 0.0
    k2: float = 0.0
    p1: float = 0.0
    p2: float = 0.0
    k3: float = 0.0


class SlamInitRequest(BaseModel):
    camera_config: CameraConfig
    enable_loop_closure: bool = True
    enable_relocalization: bool = True
    map_id: Optional[str] = None


class TrackingFrame(BaseModel):
    timestamp: float
    image_data: str  # Base64 encoded
    camera_id: int = 0


class PoseResponse(BaseModel):
    timestamp: float
    position: List[float]  # [x, y, z]
    rotation: List[float]  # [qw, qx, qy, qz]
    confidence: float
    tracking_state: str


class IMUReading(BaseModel):
    timestamp: float
    acceleration: List[float]  # [x, y, z] m/s²
    gyroscope: List[float]     # [x, y, z] rad/s
    magnetometer: List[float]  # [x, y, z] μT
    temperature: float = 0.0
    is_valid: bool = True


class VIOCameraParams(BaseModel):
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


class VioDataRequest(BaseModel):
    timestamp: float
    imu_readings: List[IMUReading]
    camera_frame_base64: Optional[str] = None
    camera_params: VIOCameraParams
    sequence_number: int


class VioPose(BaseModel):
    position: List[float]        # [x, y, z]
    rotation: List[float]        # [qw, qx, qy, qz]
    velocity: List[float]        # [x, y, z]
    angular_velocity: List[float] # [x, y, z]


class VioResponse(BaseModel):
    success: bool
    message: str
    pose: Optional[VioPose]
    confidence: float
    tracking_state: str
    processing_time_ms: float
    sequence_number: int


class StatusResponse(BaseModel):
    is_initialized: bool
    is_tracking: bool
    frame_count: int
    fps: float
    last_pose_time: float
    current_pose: Optional[PoseResponse]