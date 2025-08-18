"""
VOXAR Spatial Platform - Point Cloud Quality Analysis
Enterprise-grade quality metrics and assessment for processed point clouds
"""

import logging
import numpy as np
from typing import Dict, Optional
from .processor_models import QualityMetrics

logger = logging.getLogger(__name__)

class QualityAnalyzer:
    """
    Enterprise point cloud quality analyzer
    Provides comprehensive quality metrics for processed point clouds
    """
    
    @staticmethod
    def calculate_quality_metrics(points: np.ndarray) -> QualityMetrics:
        """
        Calculate comprehensive quality metrics for point cloud
        
        Args:
            points: Processed point cloud array
            
        Returns:
            QualityMetrics object with calculated metrics
        """
        try:
            if points is None or len(points) == 0:
                logger.warning("Empty point cloud for quality analysis")
                return QualityMetrics()
            
            logger.info(f"Calculating quality metrics for {len(points)} points")
            
            # Calculate individual metrics
            bbox_volume = QualityAnalyzer._calculate_bbox_volume(points)
            density = QualityAnalyzer._calculate_density(points, bbox_volume)
            uniformity = QualityAnalyzer._calculate_uniformity(points)
            coverage = QualityAnalyzer._calculate_coverage(points)
            
            return QualityMetrics(
                density=density,
                uniformity=uniformity,
                coverage=coverage,
                point_count=len(points),
                bbox_volume=bbox_volume
            )
            
        except Exception as e:
            logger.error(f"Quality metrics calculation failed: {e}")
            return QualityMetrics()
    
    @staticmethod
    def _calculate_bbox_volume(points: np.ndarray) -> float:
        """Calculate bounding box volume"""
        try:
            if len(points) == 0:
                return 0.0
            
            min_coords = np.min(points, axis=0)
            max_coords = np.max(points, axis=0)
            dimensions = max_coords - min_coords
            
            # Handle degenerate cases (2D or 1D point clouds)
            dimensions = np.maximum(dimensions, 1e-6)  # Minimum 1μm dimension
            
            volume = np.prod(dimensions)
            return float(volume)
            
        except Exception as e:
            logger.warning(f"Bounding box volume calculation failed: {e}")
            return 0.0
    
    @staticmethod
    def _calculate_density(points: np.ndarray, bbox_volume: float) -> float:
        """Calculate point density (points per unit volume)"""
        try:
            if bbox_volume <= 0:
                return 0.0
            
            density = len(points) / bbox_volume
            return float(density)
            
        except Exception:
            return 0.0
    
    @staticmethod
    def _calculate_uniformity(points: np.ndarray) -> float:
        """
        Calculate point distribution uniformity based on nearest neighbor distances
        Returns value between 0 (highly non-uniform) and 1 (perfectly uniform)
        """
        try:
            if len(points) < 10:
                return 0.5  # Default for small point clouds
            
            # Use efficient sampling for large point clouds
            sample_size = min(2000, len(points))
            if len(points) > sample_size:
                indices = np.random.choice(len(points), sample_size, replace=False)
                sample_points = points[indices]
            else:
                sample_points = points
            
            # Calculate nearest neighbor distances
            nn_distances = QualityAnalyzer._calculate_nearest_neighbor_distances(sample_points)
            
            if len(nn_distances) == 0:
                return 0.5
            
            # Uniformity based on coefficient of variation
            # Lower CV indicates more uniform distribution
            mean_distance = np.mean(nn_distances)
            std_distance = np.std(nn_distances)
            
            if mean_distance > 0:
                coefficient_of_variation = std_distance / mean_distance
                # Convert CV to uniformity score (0-1)
                uniformity = max(0.0, 1.0 - min(coefficient_of_variation, 2.0) / 2.0)
            else:
                uniformity = 0.0
            
            return float(uniformity)
            
        except Exception as e:
            logger.warning(f"Uniformity calculation failed: {e}")
            return 0.5
    
    @staticmethod
    def _calculate_nearest_neighbor_distances(points: np.ndarray) -> np.ndarray:
        """Calculate nearest neighbor distances efficiently"""
        try:
            from scipy.spatial.distance import cdist
            
            # Calculate pairwise distances
            distances = cdist(points, points)
            
            # Extract nearest neighbor distances (excluding self)
            nn_distances = []
            for i in range(len(points)):
                sorted_distances = np.sort(distances[i])
                if len(sorted_distances) > 1:
                    nn_distances.append(sorted_distances[1])  # First non-zero distance
            
            return np.array(nn_distances)
            
        except Exception as e:
            logger.warning(f"Nearest neighbor distance calculation failed: {e}")
            return np.array([])
    
    @staticmethod
    def _calculate_coverage(points: np.ndarray) -> float:
        """
        Calculate spatial coverage ratio using grid-based occupancy analysis
        Returns value between 0 (poor coverage) and 1 (excellent coverage)
        """
        try:
            if len(points) == 0:
                return 0.0
            
            # Use adaptive grid resolution based on point count
            grid_resolution = min(20, max(5, int(np.ceil(len(points) ** (1/3) / 10))))
            
            min_coords = np.min(points, axis=0)
            max_coords = np.max(points, axis=0)
            ranges = max_coords - min_coords
            
            # Handle degenerate cases
            ranges[ranges == 0] = 1.0
            
            # Create occupancy grid
            grid_shape = (grid_resolution, grid_resolution, grid_resolution)
            occupancy_grid = np.zeros(grid_shape, dtype=bool)
            
            # Map points to grid cells
            normalized_points = (points - min_coords) / ranges
            grid_indices = np.floor(normalized_points * (grid_resolution - 1)).astype(int)
            
            # Ensure indices are within bounds
            grid_indices = np.clip(grid_indices, 0, grid_resolution - 1)
            
            # Mark occupied cells
            for i, j, k in grid_indices:
                occupancy_grid[i, j, k] = True
            
            # Calculate coverage ratio
            occupied_cells = np.sum(occupancy_grid)
            total_cells = grid_resolution ** 3
            coverage = occupied_cells / total_cells
            
            return float(coverage)
            
        except Exception as e:
            logger.warning(f"Coverage calculation failed: {e}")
            return 0.5
    
    @staticmethod
    def assess_processing_quality(original_count: int, processed_count: int, 
                                metrics: QualityMetrics) -> Dict[str, str]:
        """
        Assess overall processing quality and provide recommendations
        
        Args:
            original_count: Original point count
            processed_count: Processed point count  
            metrics: Calculated quality metrics
            
        Returns:
            Dictionary with quality assessment and recommendations
        """
        try:
            assessment = {
                'overall_quality': 'good',
                'density_assessment': 'adequate',
                'uniformity_assessment': 'good',
                'coverage_assessment': 'good',
                'recommendations': []
            }
            
            # Reduction ratio analysis
            reduction_ratio = 1.0 - (processed_count / original_count) if original_count > 0 else 0.0
            
            if reduction_ratio > 0.9:
                assessment['recommendations'].append("High reduction ratio - consider less aggressive filtering")
            elif reduction_ratio < 0.1:
                assessment['recommendations'].append("Low reduction ratio - consider more aggressive downsampling")
            
            # Density assessment
            if metrics.density < 100:  # points per unit volume
                assessment['density_assessment'] = 'sparse'
                assessment['recommendations'].append("Low point density - may affect reconstruction quality")
            elif metrics.density > 10000:
                assessment['density_assessment'] = 'dense'
                assessment['recommendations'].append("High point density - good for detailed reconstruction")
            
            # Uniformity assessment
            if metrics.uniformity < 0.3:
                assessment['uniformity_assessment'] = 'poor'
                assessment['recommendations'].append("Poor uniformity - consider adjusting voxel size")
            elif metrics.uniformity > 0.8:
                assessment['uniformity_assessment'] = 'excellent'
            
            # Coverage assessment
            if metrics.coverage < 0.2:
                assessment['coverage_assessment'] = 'poor'
                assessment['recommendations'].append("Poor spatial coverage - may have large gaps")
            elif metrics.coverage > 0.7:
                assessment['coverage_assessment'] = 'excellent'
            
            # Overall quality determination
            quality_scores = [
                1.0 if assessment['density_assessment'] in ['adequate', 'dense'] else 0.5,
                metrics.uniformity,
                metrics.coverage
            ]
            
            avg_quality = np.mean(quality_scores)
            if avg_quality > 0.8:
                assessment['overall_quality'] = 'excellent'
            elif avg_quality > 0.6:
                assessment['overall_quality'] = 'good'
            elif avg_quality > 0.4:
                assessment['overall_quality'] = 'fair'
            else:
                assessment['overall_quality'] = 'poor'
            
            return assessment
            
        except Exception as e:
            logger.error(f"Quality assessment failed: {e}")
            return {
                'overall_quality': 'unknown',
                'error': str(e),
                'recommendations': ['Quality assessment failed - manual review recommended']
            }