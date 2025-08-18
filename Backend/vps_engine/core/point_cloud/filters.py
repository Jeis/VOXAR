"""
VOXAR Spatial Platform - Point Cloud Filtering
Enterprise-grade point cloud filtering and processing algorithms
"""

import logging
import numpy as np
from typing import Optional
from .processor_models import PointCloudConfig

logger = logging.getLogger(__name__)

class PointCloudFilter:
    """
    Enterprise point cloud filtering and processing pipeline
    Handles voxel downsampling, outlier removal, and data validation
    """
    
    def __init__(self, config: PointCloudConfig):
        self.config = config
    
    def process_points(self, points: np.ndarray) -> Optional[np.ndarray]:
        """
        Complete point cloud processing pipeline
        
        Args:
            points: Input point cloud array
            
        Returns:
            Processed point cloud or None if processing fails
        """
        try:
            # Input validation
            if points is None or len(points) == 0:
                logger.warning("Empty point cloud provided for processing")
                return None
            
            logger.info(f"Processing point cloud: {len(points)} input points")
            
            # Remove NaN and infinite values
            points = self._clean_invalid_points(points)
            if points is None or len(points) == 0:
                logger.warning("No valid points after cleaning")
                return None
            
            # Random downsampling if too many points
            if len(points) > self.config.max_points:
                points = self._random_downsample(points)
                logger.info(f"Random downsampled to {len(points)} points")
            
            # Voxel downsampling for spatial uniformity
            points = self._voxel_downsample(points)
            logger.info(f"Voxel downsampled to {len(points)} points")
            
            # Remove statistical outliers
            points = self._remove_outliers(points)
            logger.info(f"Outlier removal result: {len(points)} points")
            
            return points
            
        except Exception as e:
            logger.error(f"Point cloud processing failed: {e}")
            return None
    
    def _clean_invalid_points(self, points: np.ndarray) -> Optional[np.ndarray]:
        """Remove NaN and infinite values from point cloud"""
        try:
            # Remove points with NaN or infinite coordinates
            valid_mask = np.isfinite(points).all(axis=1)
            valid_points = points[valid_mask]
            
            removed_count = len(points) - len(valid_points)
            if removed_count > 0:
                logger.info(f"Removed {removed_count} invalid points")
            
            return valid_points if len(valid_points) > 0 else None
            
        except Exception as e:
            logger.error(f"Point cleaning failed: {e}")
            return None
    
    def _random_downsample(self, points: np.ndarray) -> np.ndarray:
        """Random downsampling for performance"""
        try:
            indices = np.random.choice(
                len(points), 
                self.config.max_points, 
                replace=False
            )
            return points[indices]
            
        except Exception as e:
            logger.warning(f"Random downsampling failed: {e}")
            return points
    
    def _voxel_downsample(self, points: np.ndarray) -> np.ndarray:
        """
        Voxel grid downsampling for spatial uniformity
        Groups points into voxels and averages coordinates
        """
        try:
            if len(points) == 0:
                return points
            
            voxel_size = self.config.voxel_size
            
            # Quantize points to voxel grid coordinates
            voxel_coords = np.floor(points / voxel_size).astype(np.int32)
            
            # Find unique voxels and their inverse mapping
            unique_voxels, inverse_indices = np.unique(
                voxel_coords, axis=0, return_inverse=True
            )
            
            # Average points within each voxel
            downsampled_points = []
            for i in range(len(unique_voxels)):
                # Get all points in this voxel
                voxel_mask = (inverse_indices == i)
                voxel_points = points[voxel_mask]
                
                # Only keep voxels with sufficient points
                if len(voxel_points) >= self.config.min_points_per_voxel:
                    centroid = np.mean(voxel_points, axis=0)
                    downsampled_points.append(centroid)
            
            result = np.array(downsampled_points, dtype=np.float32) if downsampled_points else points
            
            if len(downsampled_points) == 0:
                logger.warning("Voxel downsampling produced no points, returning original")
                return points
            
            return result
            
        except Exception as e:
            logger.warning(f"Voxel downsampling failed: {e}")
            return points
    
    def _remove_outliers(self, points: np.ndarray) -> np.ndarray:
        """
        Statistical outlier removal based on nearest neighbor analysis
        Removes points that are statistical outliers in their local neighborhood
        """
        try:
            if len(points) < self.config.outlier_nb_neighbors:
                logger.info("Too few points for outlier removal")
                return points
            
            # Use efficient subset approach for large point clouds
            max_subset_size = 10000
            if len(points) > max_subset_size:
                subset_indices = np.random.choice(len(points), max_subset_size, replace=False)
                subset_points = points[subset_indices]
            else:
                subset_indices = np.arange(len(points))
                subset_points = points
            
            # Calculate outlier threshold from subset
            threshold = self._calculate_outlier_threshold(subset_points)
            if threshold is None:
                return points
            
            # Apply threshold to filter outliers
            inlier_mask = self._filter_outliers_with_threshold(points, threshold)
            filtered_points = points[inlier_mask]
            
            removed_count = len(points) - len(filtered_points)
            if removed_count > 0:
                logger.info(f"Removed {removed_count} outlier points")
            
            return filtered_points
            
        except Exception as e:
            logger.warning(f"Outlier removal failed: {e}")
            return points
    
    def _calculate_outlier_threshold(self, points: np.ndarray) -> Optional[float]:
        """Calculate outlier threshold based on nearest neighbor distances"""
        try:
            from scipy.spatial.distance import cdist
            
            # Calculate pairwise distances
            distances = cdist(points, points)
            k = min(self.config.outlier_nb_neighbors, len(points) - 1)
            
            # Calculate mean distance to k nearest neighbors for each point
            neighbor_distances = []
            for i in range(len(points)):
                # Sort distances and take k nearest (excluding self at index 0)
                sorted_distances = np.sort(distances[i])[1:k+1]
                if len(sorted_distances) > 0:
                    neighbor_distances.append(np.mean(sorted_distances))
            
            if not neighbor_distances:
                return None
            
            neighbor_distances = np.array(neighbor_distances)
            
            # Calculate statistical threshold
            mean_distance = np.mean(neighbor_distances)
            std_distance = np.std(neighbor_distances)
            threshold = mean_distance + self.config.outlier_std_ratio * std_distance
            
            return threshold
            
        except Exception as e:
            logger.warning(f"Threshold calculation failed: {e}")
            return None
    
    def _filter_outliers_with_threshold(self, points: np.ndarray, threshold: float) -> np.ndarray:
        """Filter outliers using pre-calculated threshold"""
        try:
            from scipy.spatial.distance import cdist
            
            # For very large point clouds, use spatial approximation
            if len(points) > 50000:
                return self._approximate_outlier_filter(points, threshold)
            
            # Calculate exact distances for smaller point clouds
            distances = cdist(points, points)
            k = min(self.config.outlier_nb_neighbors, len(points) - 1)
            
            inlier_mask = np.ones(len(points), dtype=bool)
            
            for i in range(len(points)):
                sorted_distances = np.sort(distances[i])[1:k+1]
                if len(sorted_distances) > 0:
                    mean_neighbor_distance = np.mean(sorted_distances)
                    if mean_neighbor_distance > threshold:
                        inlier_mask[i] = False
            
            return inlier_mask
            
        except Exception as e:
            logger.warning(f"Outlier filtering failed: {e}")
            return np.ones(len(points), dtype=bool)
    
    def _approximate_outlier_filter(self, points: np.ndarray, threshold: float) -> np.ndarray:
        """Approximate outlier filtering for large point clouds"""
        try:
            # Use spatial subdivision for efficiency
            grid_size = int(np.ceil(len(points) ** (1/3)))
            
            # Simple density-based filtering as approximation
            min_coords = np.min(points, axis=0)
            max_coords = np.max(points, axis=0)
            ranges = max_coords - min_coords
            ranges[ranges == 0] = 1.0  # Avoid division by zero
            
            # Create spatial grid
            grid_indices = np.floor((points - min_coords) / ranges * grid_size).astype(int)
            grid_indices = np.clip(grid_indices, 0, grid_size - 1)
            
            # Count points in each grid cell
            inlier_mask = np.ones(len(points), dtype=bool)
            
            # Mark sparse regions as potential outliers
            unique_cells, cell_counts = np.unique(
                grid_indices, axis=0, return_counts=True
            )
            
            sparse_threshold = max(1, len(points) // (grid_size ** 3) // 10)
            
            for i, (cell, count) in enumerate(zip(unique_cells, cell_counts)):
                if count < sparse_threshold:
                    # Mark points in sparse cells
                    cell_mask = np.all(grid_indices == cell, axis=1)
                    inlier_mask[cell_mask] = False
            
            return inlier_mask
            
        except Exception:
            # Return all points as inliers if approximation fails
            return np.ones(len(points), dtype=bool)