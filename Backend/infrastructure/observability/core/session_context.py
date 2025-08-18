"""
VOXAR Enterprise Observability - AR Session Context & Spatial Metrics
AR-specific tracking contexts and performance metrics for spatial computing
"""

import time
from typing import Optional
from dataclasses import dataclass, field

@dataclass
class ARSessionContext:
    """AR Session tracking context"""
    session_id: str
    user_id: str
    device_id: str
    platform: str  # iOS, Android, Unity
    ar_framework: str  # ARKit, ARCore, AR Foundation
    map_id: Optional[str] = None
    tracking_state: str = "initializing"
    quality_score: float = 0.0
    fps_target: int = 60
    started_at: float = field(default_factory=time.time)
    last_update: float = field(default_factory=time.time)

@dataclass
class SpatialMetrics:
    """Spatial AR performance metrics"""
    pose_accuracy: float  # meters
    tracking_confidence: float  # 0-1
    feature_points: int
    anchor_count: int
    map_quality: float  # 0-1
    localization_time: float  # seconds
    reconstruction_progress: float  # 0-1