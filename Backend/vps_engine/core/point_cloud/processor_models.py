"""
VOXAR Spatial Platform - Point Cloud Data Models
Enterprise-grade data structures for 3D point cloud processing
"""

import time
import numpy as np
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict

@dataclass
class PointCloudConfig:
    """Point cloud processing configuration with enterprise defaults"""
    voxel_size: float = 0.01              # 1cm voxel size
    min_points_per_voxel: int = 3         # Minimum points to keep voxel
    outlier_std_ratio: float = 2.0        # Standard deviation ratio for outlier detection
    outlier_nb_neighbors: int = 20        # Number of neighbors for outlier analysis
    max_points: int = 1000000             # 1M points maximum for performance
    downsample_factor: float = 0.1        # Downsampling factor if needed
    
    def __post_init__(self):
        """Validate configuration parameters"""
        if self.voxel_size <= 0:
            raise ValueError("Voxel size must be positive")
        if self.min_points_per_voxel < 1:
            raise ValueError("Minimum points per voxel must be at least 1")
        if self.max_points < 1000:
            raise ValueError("Maximum points must be at least 1000")

@dataclass
class QualityMetrics:
    """Point cloud quality assessment metrics"""
    density: float = 0.0          # Points per unit volume
    uniformity: float = 0.0       # Distribution uniformity (0-1)
    coverage: float = 0.0         # Spatial coverage ratio (0-1)
    point_count: int = 0          # Final point count
    bbox_volume: float = 0.0      # Bounding box volume
    
    def to_dict(self) -> Dict[str, float]:
        """Convert to dictionary for serialization"""
        return asdict(self)

@dataclass
class ProcessingStats:
    """Processing performance statistics"""
    total_processed: int = 0
    average_points_in: float = 0.0
    average_points_out: float = 0.0
    average_processing_time: float = 0.0
    
    def update_processing_metrics(self, points_in: int, points_out: int, processing_time: float):
        """Update processing statistics with new metrics"""
        self.total_processed += 1
        total = self.total_processed
        
        # Update running averages
        self.average_points_in = ((self.average_points_in * (total - 1)) + points_in) / total
        self.average_points_out = ((self.average_points_out * (total - 1)) + points_out) / total
        self.average_processing_time = ((self.average_processing_time * (total - 1)) + processing_time) / total
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for monitoring"""
        return asdict(self)

@dataclass
class ProcessingResult:
    """Complete point cloud processing result"""
    map_id: str
    original_point_count: int
    processed_point_count: int
    points: np.ndarray
    processing_time: float
    quality_metrics: QualityMetrics
    timestamp: float
    
    def __post_init__(self):
        """Set timestamp if not provided"""
        if self.timestamp == 0:
            self.timestamp = time.time()
    
    @property
    def reduction_ratio(self) -> float:
        """Calculate point reduction ratio"""
        if self.original_point_count == 0:
            return 0.0
        return 1.0 - (self.processed_point_count / self.original_point_count)
    
    @property
    def is_valid_result(self) -> bool:
        """Check if processing result is valid"""
        return (self.processed_point_count > 0 and 
                self.points is not None and 
                len(self.points) == self.processed_point_count)
    
    def to_summary_dict(self) -> Dict[str, Any]:
        """Convert to summary dictionary (without points array)"""
        return {
            'map_id': self.map_id,
            'original_point_count': self.original_point_count,
            'processed_point_count': self.processed_point_count,
            'processing_time': self.processing_time,
            'reduction_ratio': self.reduction_ratio,
            'quality_metrics': self.quality_metrics.to_dict(),
            'timestamp': self.timestamp
        }