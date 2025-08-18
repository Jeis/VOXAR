"""
Pose Estimator - 6DOF pose estimation from 2D-3D correspondences
High-precision pose calculation using PnP with RANSAC
"""

import logging
import numpy as np
import cv2
from typing import List, Tuple, Dict, Any, Optional
from dataclasses import dataclass
import asyncio
from scipy.spatial.transform import Rotation

logger = logging.getLogger(__name__)

@dataclass
class PoseMatch:
    """2D-3D correspondence for pose estimation"""
    image_point: np.ndarray  # 2D image coordinates
    world_point: np.ndarray  # 3D world coordinates
    descriptor: np.ndarray   # Feature descriptor
    confidence: float        # Match confidence
    reprojection_error: float = 0.0

class PoseEstimator:
    """
    High-precision 6DOF pose estimation using PnP with RANSAC
    Optimized for AR applications requiring centimeter accuracy
    """
    
    def __init__(self):
        self.config = {
            'ransac_iterations': 10000,
            'ransac_threshold': 2.0,  # pixels
            'min_inliers': 15,
            'refinement_iterations': 10,
            'confidence_threshold': 0.99,
            'max_reprojection_error': 3.0
        }
        
        # Pose estimation methods
        self.pnp_methods = {
            'iterative': cv2.SOLVEPNP_ITERATIVE,
            'epnp': cv2.SOLVEPNP_EPNP,
            'p3p': cv2.SOLVEPNP_P3P,
            'ap3p': cv2.SOLVEPNP_AP3P,
            'ippe': cv2.SOLVEPNP_IPPE,
            'sqpnp': cv2.SOLVEPNP_SQPNP
        }
        
        # Performance tracking
        self.stats = {
            'total_estimations': 0,
            'successful_estimations': 0,
            'average_inliers': 0.0,
            'average_error': 0.0
        }

    async def estimate_pose(self, matches: List[Dict], camera_intrinsics: np.ndarray,
                           method: str = 'iterative') -> Tuple[np.ndarray, List[Dict]]:
        """
        Estimate 6DOF camera pose from 2D-3D correspondences
        
        Args:
            matches: List of 2D-3D correspondences
            camera_intrinsics: Camera intrinsic matrix (3x3)
            method: PnP method to use
            
        Returns:
            Tuple of (4x4 transformation matrix, inlier matches)
        """
        try:
            self.stats['total_estimations'] += 1
            
            if len(matches) < self.config['min_inliers']:
                raise ValueError(f"Insufficient matches: {len(matches)} < {self.config['min_inliers']}")
            
            # Convert matches to numpy arrays
            image_points, world_points = self._prepare_correspondences(matches)
            
            # Initial pose estimation with RANSAC
            success, rvec, tvec, inliers = await self._estimate_pose_ransac(
                image_points, world_points, camera_intrinsics, method
            )
            
            if not success or inliers is None or len(inliers) < self.config['min_inliers']:
                raise ValueError("RANSAC pose estimation failed")
            
            # Refine pose using inliers only
            inlier_image_points = image_points[inliers.ravel()]
            inlier_world_points = world_points[inliers.ravel()]
            
            refined_rvec, refined_tvec = await self._refine_pose(
                inlier_image_points, inlier_world_points, camera_intrinsics, rvec, tvec
            )
            
            # Convert to 4x4 transformation matrix
            pose_matrix = self._pose_to_matrix(refined_rvec, refined_tvec)
            
            # Prepare inlier matches with reprojection errors
            inlier_matches = self._prepare_inlier_matches(
                matches, inliers, inlier_image_points, inlier_world_points,
                camera_intrinsics, refined_rvec, refined_tvec
            )
            
            # Update statistics
            self.stats['successful_estimations'] += 1
            self._update_stats(len(inlier_matches), inlier_matches)
            
            logger.debug(f"Pose estimation successful: {len(inlier_matches)} inliers")
            
            return pose_matrix, inlier_matches
            
        except Exception as e:
            logger.error(f"Pose estimation failed: {e}")
            raise

    def _prepare_correspondences(self, matches: List[Dict]) -> Tuple[np.ndarray, np.ndarray]:
        """Convert matches to numpy arrays for OpenCV"""
        image_points = []
        world_points = []
        
        for match in matches:
            image_points.append([match['image_x'], match['image_y']])
            world_points.append([match['world_x'], match['world_y'], match['world_z']])
        
        return np.array(image_points, dtype=np.float32), np.array(world_points, dtype=np.float32)

    async def _estimate_pose_ransac(self, image_points: np.ndarray, world_points: np.ndarray,
                                  camera_intrinsics: np.ndarray, method: str) -> Tuple[bool, np.ndarray, np.ndarray, np.ndarray]:
        """Perform RANSAC-based pose estimation"""
        
        # Distortion coefficients (assume no distortion for now)
        dist_coeffs = np.zeros((4, 1))
        
        # PnP method
        pnp_method = self.pnp_methods.get(method, cv2.SOLVEPNP_ITERATIVE)
        
        try:
            # Use solvePnPRansac for robust estimation
            success, rvec, tvec, inliers = cv2.solvePnPRansac(
                world_points,
                image_points,
                camera_intrinsics,
                dist_coeffs,
                iterationsCount=self.config['ransac_iterations'],
                reprojectionError=self.config['ransac_threshold'],
                confidence=self.config['confidence_threshold'],
                flags=pnp_method
            )
            
            return success, rvec, tvec, inliers
            
        except Exception as e:
            logger.error(f"RANSAC pose estimation failed: {e}")
            return False, None, None, None

    async def _refine_pose(self, image_points: np.ndarray, world_points: np.ndarray,
                          camera_intrinsics: np.ndarray, initial_rvec: np.ndarray, 
                          initial_tvec: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """Refine pose estimation using iterative method"""
        
        dist_coeffs = np.zeros((4, 1))
        
        try:
            # Iterative refinement
            success, rvec, tvec = cv2.solvePnP(
                world_points,
                image_points,
                camera_intrinsics,
                dist_coeffs,
                rvec=initial_rvec,
                tvec=initial_tvec,
                useExtrinsicGuess=True,
                flags=cv2.SOLVEPNP_ITERATIVE
            )
            
            if success:
                return rvec, tvec
            else:
                logger.warning("Pose refinement failed, using initial estimate")
                return initial_rvec, initial_tvec
                
        except Exception as e:
            logger.warning(f"Pose refinement failed: {e}, using initial estimate")
            return initial_rvec, initial_tvec

    def _pose_to_matrix(self, rvec: np.ndarray, tvec: np.ndarray) -> np.ndarray:
        """Convert rotation vector and translation to 4x4 transformation matrix"""
        
        # Convert rotation vector to rotation matrix
        rotation_matrix, _ = cv2.Rodrigues(rvec)
        
        # Create 4x4 transformation matrix
        pose_matrix = np.eye(4)
        pose_matrix[:3, :3] = rotation_matrix
        pose_matrix[:3, 3] = tvec.ravel()
        
        return pose_matrix

    def _prepare_inlier_matches(self, matches: List[Dict], inliers: np.ndarray,
                               image_points: np.ndarray, world_points: np.ndarray,
                               camera_intrinsics: np.ndarray, rvec: np.ndarray, 
                               tvec: np.ndarray) -> List[Dict]:
        """Prepare inlier matches with reprojection errors"""
        
        # Calculate reprojection errors
        projected_points, _ = cv2.projectPoints(
            world_points, rvec, tvec, camera_intrinsics, np.zeros((4, 1))
        )
        projected_points = projected_points.reshape(-1, 2)
        
        reprojection_errors = np.linalg.norm(image_points - projected_points, axis=1)
        
        # Create inlier matches
        inlier_matches = []
        for i, inlier_idx in enumerate(inliers.ravel()):
            match = matches[inlier_idx].copy()
            match['reprojection_error'] = reprojection_errors[i]
            match['is_inlier'] = True
            inlier_matches.append(match)
        
        return inlier_matches

    def _update_stats(self, num_inliers: int, inlier_matches: List[Dict]):
        """Update pose estimation statistics"""
        
        # Update average inliers
        total_estimations = self.stats['successful_estimations']
        current_avg_inliers = self.stats['average_inliers']
        self.stats['average_inliers'] = \
            (current_avg_inliers * (total_estimations - 1) + num_inliers) / total_estimations
        
        # Update average reprojection error
        avg_reprojection_error = np.mean([m['reprojection_error'] for m in inlier_matches])
        current_avg_error = self.stats['average_error']
        self.stats['average_error'] = \
            (current_avg_error * (total_estimations - 1) + avg_reprojection_error) / total_estimations

    def get_pose_quality_metrics(self, pose: np.ndarray, inlier_matches: List[Dict]) -> Dict[str, float]:
        """Calculate quality metrics for estimated pose"""
        
        if not inlier_matches:
            return {'quality_score': 0.0, 'confidence': 0.0, 'stability': 0.0}
        
        # Reprojection error statistics
        reprojection_errors = [m['reprojection_error'] for m in inlier_matches]
        mean_error = np.mean(reprojection_errors)
        std_error = np.std(reprojection_errors)
        
        # Feature distribution
        image_points = np.array([[m['image_x'], m['image_y']] for m in inlier_matches])
        distribution_score = self._calculate_point_distribution(image_points)
        
        # Pose stability (based on condition number)
        stability_score = self._calculate_pose_stability(pose)
        
        # Overall quality score
        error_score = max(0, 1 - mean_error / self.config['max_reprojection_error'])
        quality_score = 0.4 * error_score + 0.3 * distribution_score + 0.3 * stability_score
        
        return {
            'quality_score': min(quality_score, 1.0),
            'confidence': error_score,
            'stability': stability_score,
            'mean_reprojection_error': mean_error,
            'std_reprojection_error': std_error,
            'num_inliers': len(inlier_matches),
            'distribution_score': distribution_score
        }

    def _calculate_point_distribution(self, points: np.ndarray) -> float:
        """Calculate how well distributed points are across the image"""
        if len(points) < 4:
            return 0.0
        
        # Calculate convex hull area
        try:
            hull = cv2.convexHull(points.astype(np.float32))
            hull_area = cv2.contourArea(hull)
            
            # Normalize by image area (assuming 640x480)
            normalized_area = hull_area / (640 * 480)
            return min(normalized_area, 1.0)
            
        except Exception:
            return 0.0

    def _calculate_pose_stability(self, pose: np.ndarray) -> float:
        """Calculate pose stability based on rotation matrix properties"""
        try:
            rotation_matrix = pose[:3, :3]
            
            # Check if rotation matrix is proper (determinant = 1)
            det = np.linalg.det(rotation_matrix)
            det_score = 1.0 - abs(1.0 - det)
            
            # Check orthogonality (R * R.T should be identity)
            identity_check = np.dot(rotation_matrix, rotation_matrix.T)
            ortho_error = np.linalg.norm(identity_check - np.eye(3))
            ortho_score = max(0, 1.0 - ortho_error)
            
            return 0.5 * det_score + 0.5 * ortho_score
            
        except Exception:
            return 0.0

    def matrix_to_pose_components(self, pose_matrix: np.ndarray) -> Dict[str, Any]:
        """Convert 4x4 transformation matrix to pose components"""
        
        rotation_matrix = pose_matrix[:3, :3]
        translation = pose_matrix[:3, 3]
        
        # Convert to rotation vector
        rvec, _ = cv2.Rodrigues(rotation_matrix)
        
        # Convert to Euler angles (for human readability)
        rotation = Rotation.from_matrix(rotation_matrix)
        euler_angles = rotation.as_euler('xyz', degrees=True)
        
        # Convert to quaternion
        quaternion = rotation.as_quat()
        
        return {
            'translation': {
                'x': float(translation[0]),
                'y': float(translation[1]),
                'z': float(translation[2])
            },
            'rotation_vector': rvec.ravel().tolist(),
            'rotation_matrix': rotation_matrix.tolist(),
            'euler_angles': {
                'roll': float(euler_angles[0]),
                'pitch': float(euler_angles[1]),
                'yaw': float(euler_angles[2])
            },
            'quaternion': {
                'x': float(quaternion[0]),
                'y': float(quaternion[1]),
                'z': float(quaternion[2]),
                'w': float(quaternion[3])
            }
        }

    def get_statistics(self) -> Dict[str, Any]:
        """Get pose estimation statistics"""
        success_rate = 0.0
        if self.stats['total_estimations'] > 0:
            success_rate = self.stats['successful_estimations'] / self.stats['total_estimations']
        
        return {
            **self.stats,
            'success_rate': success_rate,
            'config': self.config
        }