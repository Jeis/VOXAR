"""
VOXAR Spatial Mapping - Bundle Adjuster
Enterprise-grade sparse 3D reconstruction and bundle adjustment
"""

import os
import logging
import subprocess
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime

import numpy as np

logger = logging.getLogger(__name__)

@dataclass
class BundleAdjustmentConfig:
    """Bundle adjustment configuration"""
    min_triangulation_angle: float = 1.5
    max_reprojection_error: float = 4.0
    min_track_length: int = 2
    max_num_iterations: int = 100
    refine_focal_length: bool = True
    refine_principal_point: bool = False
    refine_extra_params: bool = True
    timeout: int = 10800  # 3 hours

@dataclass
class BundleAdjustmentResult:
    """Bundle adjustment results"""
    num_registered_images: int
    num_points_3d: int
    mean_reprojection_error: float
    reconstruction_time: float
    success: bool
    error: Optional[str] = None
    
    # Quality metrics
    median_triangulation_angle: float = 0.0
    mean_track_length: float = 0.0
    num_observations: int = 0

class BundleAdjuster:
    """Enterprise COLMAP sparse reconstructor and bundle adjuster"""
    
    def __init__(self, config: BundleAdjustmentConfig, colmap_path: str = None):
        self.config = config
        self.colmap_path = colmap_path or os.environ.get('COLMAP_EXE', '/usr/bin/colmap')
        self._verify_colmap()
    
    def _verify_colmap(self):
        """Verify COLMAP installation"""
        try:
            result = subprocess.run([self.colmap_path, '--help'], 
                                  capture_output=True, text=True, timeout=10)
            if result.returncode != 0:
                raise RuntimeError("COLMAP not found or not working")
            logger.info("COLMAP installation verified for bundle adjustment")
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            raise RuntimeError(f"COLMAP validation failed: {e}")
    
    def run_sparse_reconstruction(self, database_path: Path, output_dir: Path) -> BundleAdjustmentResult:
        """Run incremental sparse reconstruction"""
        start_time = datetime.now()
        
        # Create output directory
        sparse_dir = output_dir / "sparse" / "0"
        sparse_dir.mkdir(parents=True, exist_ok=True)
        
        cmd = [
            self.colmap_path, 'mapper',
            '--database_path', str(database_path),
            '--image_path', str(output_dir / "images"),
            '--output_path', str(output_dir / "sparse"),
            '--Mapper.min_triangulation_angle', str(self.config.min_triangulation_angle),
            '--Mapper.max_reprojection_error', str(self.config.max_reprojection_error),
            '--Mapper.min_track_len', str(self.config.min_track_length),
            '--Mapper.ba_refine_focal_length', str(int(self.config.refine_focal_length)),
            '--Mapper.ba_refine_principal_point', str(int(self.config.refine_principal_point)),
            '--Mapper.ba_refine_extra_params', str(int(self.config.refine_extra_params)),
        ]
        
        try:
            logger.info(f"Starting sparse reconstruction: {' '.join(cmd)}")
            result = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=self.config.timeout, cwd=output_dir
            )
            
            if result.returncode != 0:
                raise RuntimeError(f"Sparse reconstruction failed: {result.stderr}")
            
            reconstruction_time = (datetime.now() - start_time).total_seconds()
            logger.info(f"Sparse reconstruction completed in {reconstruction_time:.2f}s")
            
            # Parse reconstruction results
            return self._parse_reconstruction_results(sparse_dir, reconstruction_time)
            
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"Reconstruction timed out after {self.config.timeout}s")
        except Exception as e:
            reconstruction_time = (datetime.now() - start_time).total_seconds()
            logger.error(f"Sparse reconstruction failed: {e}")
            return BundleAdjustmentResult(
                0, 0, 0.0, reconstruction_time, False, str(e)
            )
    
    def _parse_reconstruction_results(self, sparse_dir: Path, reconstruction_time: float) -> BundleAdjustmentResult:
        """Parse sparse reconstruction results"""
        
        try:
            # Check if reconstruction files exist
            images_file = sparse_dir / "images.txt"
            points_file = sparse_dir / "points3D.txt"
            cameras_file = sparse_dir / "cameras.txt"
            
            if not all(f.exists() for f in [images_file, points_file, cameras_file]):
                raise FileNotFoundError("Reconstruction output files not found")
            
            # Parse images
            num_images = self._count_registered_images(images_file)
            
            # Parse 3D points
            points_data = self._parse_points3d(points_file)
            num_points = len(points_data)
            
            # Calculate quality metrics
            mean_reprojection_error = np.mean([p['error'] for p in points_data]) if points_data else 0.0
            mean_track_length = np.mean([len(p['track']) for p in points_data]) if points_data else 0.0
            num_observations = sum(len(p['track']) for p in points_data)
            
            logger.info(f"Reconstruction: {num_images} images, {num_points} points, "
                       f"error: {mean_reprojection_error:.3f}")
            
            return BundleAdjustmentResult(
                num_registered_images=num_images,
                num_points_3d=num_points,
                mean_reprojection_error=mean_reprojection_error,
                reconstruction_time=reconstruction_time,
                success=True,
                mean_track_length=mean_track_length,
                num_observations=num_observations
            )
            
        except Exception as e:
            logger.error(f"Failed to parse reconstruction results: {e}")
            return BundleAdjustmentResult(
                0, 0, 0.0, reconstruction_time, False, str(e)
            )
    
    def _count_registered_images(self, images_file: Path) -> int:
        """Count registered images from images.txt"""
        count = 0
        try:
            with open(images_file, 'r') as f:
                for line in f:
                    if not line.startswith('#') and line.strip():
                        count += 1
        except Exception as e:
            logger.warning(f"Could not count registered images: {e}")
        return count // 2  # Each image has 2 lines in COLMAP format
    
    def _parse_points3d(self, points_file: Path) -> List[Dict]:
        """Parse 3D points from points3D.txt"""
        points = []
        
        try:
            with open(points_file, 'r') as f:
                for line in f:
                    if line.startswith('#') or not line.strip():
                        continue
                    
                    parts = line.strip().split()
                    if len(parts) < 8:
                        continue
                    
                    point_id = int(parts[0])
                    xyz = [float(parts[1]), float(parts[2]), float(parts[3])]
                    rgb = [int(parts[4]), int(parts[5]), int(parts[6])]
                    error = float(parts[7])
                    
                    # Parse track (image_id, feature_id pairs)
                    track = []
                    for i in range(8, len(parts), 2):
                        if i + 1 < len(parts):
                            image_id = int(parts[i])
                            feature_id = int(parts[i + 1])
                            track.append((image_id, feature_id))
                    
                    points.append({
                        'id': point_id,
                        'xyz': xyz,
                        'rgb': rgb,
                        'error': error,
                        'track': track
                    })
            
        except Exception as e:
            logger.warning(f"Could not parse 3D points: {e}")
        
        return points
    
    def run_bundle_adjustment(self, sparse_dir: Path) -> BundleAdjustmentResult:
        """Run additional bundle adjustment on existing reconstruction"""
        start_time = datetime.now()
        
        cmd = [
            self.colmap_path, 'bundle_adjuster',
            '--input_path', str(sparse_dir),
            '--output_path', str(sparse_dir),
            '--BundleAdjustment.max_num_iterations', str(self.config.max_num_iterations),
            '--BundleAdjustment.refine_focal_length', str(int(self.config.refine_focal_length)),
            '--BundleAdjustment.refine_principal_point', str(int(self.config.refine_principal_point)),
            '--BundleAdjustment.refine_extra_params', str(int(self.config.refine_extra_params)),
        ]
        
        try:
            logger.info(f"Starting bundle adjustment: {' '.join(cmd)}")
            result = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=self.config.timeout
            )
            
            if result.returncode != 0:
                raise RuntimeError(f"Bundle adjustment failed: {result.stderr}")
            
            adjustment_time = (datetime.now() - start_time).total_seconds()
            logger.info(f"Bundle adjustment completed in {adjustment_time:.2f}s")
            
            return self._parse_reconstruction_results(sparse_dir, adjustment_time)
            
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"Bundle adjustment timed out after {self.config.timeout}s")
        except Exception as e:
            adjustment_time = (datetime.now() - start_time).total_seconds()
            logger.error(f"Bundle adjustment failed: {e}")
            return BundleAdjustmentResult(
                0, 0, 0.0, adjustment_time, False, str(e)
            )
    
    def triangulate_points(self, sparse_dir: Path) -> BundleAdjustmentResult:
        """Triangulate additional 3D points"""
        start_time = datetime.now()
        
        cmd = [
            self.colmap_path, 'point_triangulator',
            '--database_path', str(sparse_dir.parent.parent / "database.db"),
            '--image_path', str(sparse_dir.parent.parent / "images"),
            '--input_path', str(sparse_dir),
            '--output_path', str(sparse_dir),
            '--Mapper.min_triangulation_angle', str(self.config.min_triangulation_angle),
            '--Mapper.max_reprojection_error', str(self.config.max_reprojection_error),
        ]
        
        try:
            logger.info(f"Starting point triangulation: {' '.join(cmd)}")
            result = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=self.config.timeout
            )
            
            if result.returncode != 0:
                logger.warning(f"Point triangulation completed with warnings: {result.stderr}")
            
            triangulation_time = (datetime.now() - start_time).total_seconds()
            logger.info(f"Point triangulation completed in {triangulation_time:.2f}s")
            
            return self._parse_reconstruction_results(sparse_dir, triangulation_time)
            
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"Point triangulation timed out after {self.config.timeout}s")
        except Exception as e:
            triangulation_time = (datetime.now() - start_time).total_seconds()
            logger.error(f"Point triangulation failed: {e}")
            return BundleAdjustmentResult(
                0, 0, 0.0, triangulation_time, False, str(e)
            )
    
    def get_reconstruction_statistics(self, sparse_dir: Path) -> Dict:
        """Get detailed reconstruction statistics"""
        
        try:
            images_file = sparse_dir / "images.txt"
            points_file = sparse_dir / "points3D.txt"
            cameras_file = sparse_dir / "cameras.txt"
            
            if not all(f.exists() for f in [images_file, points_file, cameras_file]):
                return {}
            
            # Basic counts
            num_images = self._count_registered_images(images_file)
            points_data = self._parse_points3d(points_file)
            num_points = len(points_data)
            
            # Quality metrics
            if points_data:
                reprojection_errors = [p['error'] for p in points_data]
                track_lengths = [len(p['track']) for p in points_data]
                
                stats = {
                    'num_registered_images': num_images,
                    'num_points_3d': num_points,
                    'mean_reprojection_error': np.mean(reprojection_errors),
                    'median_reprojection_error': np.median(reprojection_errors),
                    'std_reprojection_error': np.std(reprojection_errors),
                    'mean_track_length': np.mean(track_lengths),
                    'median_track_length': np.median(track_lengths),
                    'total_observations': sum(track_lengths),
                    'bundle_adjustment_config': self.config.__dict__
                }
            else:
                stats = {
                    'num_registered_images': num_images,
                    'num_points_3d': 0,
                    'bundle_adjustment_config': self.config.__dict__
                }
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get reconstruction statistics: {e}")
            return {}