"""
Pose Management and Fusion
Combines SLAM and VIO data for optimal tracking
"""

import time
import numpy as np
import logging
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class PoseManager:
    """Manages pose estimation by fusing SLAM and VIO data"""
    
    def __init__(self):
        self.current_pose = None
        self.pose_history = []
        self.slam_active = False
        self.vio_active = False
        
        # Confidence thresholds
        self.min_slam_confidence = 0.7
        self.min_vio_confidence = 0.5
        
        # Keep recent poses for smoothing
        self.max_history_size = 30
        
    def update_slam_pose(self, pose_data: Dict[str, Any]) -> bool:
        """Update pose from SLAM system"""
        try:
            if pose_data and pose_data.get('confidence', 0) >= self.min_slam_confidence:
                self.slam_active = True
                
                # SLAM poses are generally more accurate when available
                self._update_current_pose(pose_data, source='slam')
                return True
            else:
                self.slam_active = False
                return False
                
        except Exception as e:
            logger.error(f"Failed to update SLAM pose: {e}")
            return False
    
    def update_vio_pose(self, pose_data: Dict[str, Any]) -> bool:
        """Update pose from VIO system"""
        try:
            if pose_data.get('success') and pose_data.get('confidence', 0) >= self.min_vio_confidence:
                self.vio_active = True
                
                # Use VIO if SLAM is not available or has low confidence
                if not self.slam_active:
                    self._update_current_pose(pose_data['pose'], source='vio')
                    
                return True
            else:
                self.vio_active = False
                return False
                
        except Exception as e:
            logger.error(f"Failed to update VIO pose: {e}")
            return False
    
    def get_current_pose(self) -> Optional[Dict[str, Any]]:
        """Get the best available pose estimate"""
        if not self.current_pose:
            return None
            
        # Check if pose is too old (more than 1 second)
        age = time.time() - self.current_pose['timestamp']
        if age > 1.0:
            logger.warning("Current pose is stale")
            return None
            
        return self.current_pose.copy()
    
    def get_tracking_quality(self) -> float:
        """Estimate overall tracking quality (0.0 to 1.0)"""
        if not self.current_pose:
            return 0.0
        
        # Base quality on confidence and recency
        confidence = self.current_pose.get('confidence', 0.0)
        age = time.time() - self.current_pose['timestamp']
        
        # Reduce quality for older poses
        age_factor = max(0.0, 1.0 - age / 2.0)  # Linear decrease over 2 seconds
        
        # Boost quality if both SLAM and VIO are active
        source_boost = 1.2 if (self.slam_active and self.vio_active) else 1.0
        
        quality = confidence * age_factor * source_boost
        return min(1.0, quality)
    
    def predict_pose(self, future_time: float) -> Optional[Dict[str, Any]]:
        """Predict pose at future timestamp using motion model"""
        if len(self.pose_history) < 2:
            return self.get_current_pose()
        
        try:
            # Use last two poses to estimate velocity
            recent_poses = self.pose_history[-2:]
            dt = recent_poses[1]['timestamp'] - recent_poses[0]['timestamp']
            
            if dt <= 0:
                return self.get_current_pose()
            
            # Calculate position and rotation deltas
            pos1 = np.array(recent_poses[0]['position'])
            pos2 = np.array(recent_poses[1]['position'])
            velocity = (pos2 - pos1) / dt
            
            # Predict future position
            prediction_dt = future_time - recent_poses[1]['timestamp']
            predicted_pos = pos2 + velocity * prediction_dt
            
            # For now, assume rotation stays the same (could add angular velocity)
            predicted_pose = recent_poses[1].copy()
            predicted_pose.update({
                'position': predicted_pos.tolist(),
                'timestamp': future_time,
                'confidence': max(0.1, predicted_pose['confidence'] * 0.8),  # Lower confidence for predictions
                'is_prediction': True
            })
            
            return predicted_pose
            
        except Exception as e:
            logger.error(f"Pose prediction failed: {e}")
            return self.get_current_pose()
    
    def get_pose_history(self, max_age_seconds: float = 5.0) -> List[Dict[str, Any]]:
        """Get recent pose history within time window"""
        cutoff_time = time.time() - max_age_seconds
        
        return [pose for pose in self.pose_history 
                if pose['timestamp'] >= cutoff_time]
    
    def reset_tracking(self):
        """Reset all tracking state"""
        self.current_pose = None
        self.pose_history.clear()
        self.slam_active = False
        self.vio_active = False
        logger.info("Pose tracking reset")
    
    def _update_current_pose(self, pose_data: Dict[str, Any], source: str):
        """Internal method to update current pose"""
        try:
            # Create standardized pose format
            standardized_pose = {
                'position': pose_data.get('position', [0, 0, 0]),
                'rotation': pose_data.get('rotation', [0, 0, 0, 1]),
                'confidence': pose_data.get('confidence', 0.0),
                'tracking_state': pose_data.get('tracking_state', 'unknown'),
                'timestamp': time.time(),
                'source': source
            }
            
            # Add velocity if available (from VIO)
            if 'velocity' in pose_data:
                standardized_pose['velocity'] = pose_data['velocity']
                standardized_pose['angular_velocity'] = pose_data.get('angular_velocity', [0, 0, 0])
            
            # Update current pose
            self.current_pose = standardized_pose
            
            # Add to history
            self.pose_history.append(standardized_pose.copy())
            
            # Trim history to prevent memory growth
            if len(self.pose_history) > self.max_history_size:
                self.pose_history = self.pose_history[-self.max_history_size:]
                
        except Exception as e:
            logger.error(f"Failed to update pose: {e}")
    
    def get_status_summary(self) -> Dict[str, Any]:
        """Get comprehensive tracking status"""
        return {
            'slam_active': self.slam_active,
            'vio_active': self.vio_active,
            'tracking_quality': self.get_tracking_quality(),
            'has_current_pose': self.current_pose is not None,
            'pose_history_count': len(self.pose_history),
            'last_update': self.current_pose['timestamp'] if self.current_pose else None
        }