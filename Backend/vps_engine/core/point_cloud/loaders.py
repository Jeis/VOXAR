"""
VOXAR Spatial Platform - Point Cloud File Loaders
Enterprise-grade point cloud file format parsers (PLY, PCD, XYZ)
"""

import logging
import numpy as np
from typing import Optional

logger = logging.getLogger(__name__)

class PointCloudLoader:
    """
    Enterprise point cloud file loader supporting multiple formats
    Handles PLY, PCD, and XYZ file formats with robust error handling
    """
    
    @staticmethod
    def load_point_cloud(point_cloud_data: bytes) -> Optional[np.ndarray]:
        """
        Load point cloud from file data with automatic format detection
        
        Args:
            point_cloud_data: Raw point cloud file data
            
        Returns:
            numpy array of 3D points or None if loading fails
        """
        try:
            # Auto-detect format and load accordingly
            if point_cloud_data.startswith(b'ply'):
                return PointCloudLoader._load_ply(point_cloud_data)
            elif b'PCD' in point_cloud_data[:100]:
                return PointCloudLoader._load_pcd(point_cloud_data)
            else:
                # Try as simple XYZ format
                return PointCloudLoader._load_xyz(point_cloud_data)
                
        except Exception as e:
            logger.error(f"Point cloud loading failed: {e}")
            return None
    
    @staticmethod
    def _load_ply(data: bytes) -> Optional[np.ndarray]:
        """Load PLY format point cloud with ASCII parsing"""
        try:
            lines = data.decode('utf-8').split('\n')
            
            # Parse header to find vertex count and data start
            vertex_count = 0
            header_end = 0
            
            for i, line in enumerate(lines):
                if line.startswith('element vertex'):
                    vertex_count = int(line.split()[-1])
                elif line.strip() == 'end_header':
                    header_end = i + 1
                    break
            
            if vertex_count == 0:
                logger.warning("No vertices found in PLY header")
                return None
            
            # Parse vertex data
            points = []
            for i in range(header_end, min(header_end + vertex_count, len(lines))):
                if lines[i].strip():
                    coords = lines[i].strip().split()
                    if len(coords) >= 3:
                        try:
                            x, y, z = float(coords[0]), float(coords[1]), float(coords[2])
                            # Basic validation
                            if all(np.isfinite([x, y, z])):
                                points.append([x, y, z])
                        except ValueError:
                            continue
            
            if not points:
                logger.warning("No valid points found in PLY file")
                return None
            
            logger.info(f"Loaded {len(points)} points from PLY format")
            return np.array(points, dtype=np.float32)
            
        except Exception as e:
            logger.error(f"PLY parsing failed: {e}")
            return None
    
    @staticmethod
    def _load_pcd(data: bytes) -> Optional[np.ndarray]:
        """Load PCD format point cloud with ASCII parsing"""
        try:
            lines = data.decode('utf-8').split('\n')
            
            # Find data section start
            data_start = 0
            for i, line in enumerate(lines):
                if line.startswith('DATA ascii'):
                    data_start = i + 1
                    break
                elif line.startswith('DATA binary'):
                    logger.warning("Binary PCD format not supported")
                    return None
            
            if data_start == 0:
                logger.warning("No ASCII data section found in PCD")
                return None
            
            # Parse point data
            points = []
            for i in range(data_start, len(lines)):
                if lines[i].strip():
                    coords = lines[i].strip().split()
                    if len(coords) >= 3:
                        try:
                            x, y, z = float(coords[0]), float(coords[1]), float(coords[2])
                            # Basic validation
                            if all(np.isfinite([x, y, z])):
                                points.append([x, y, z])
                        except ValueError:
                            continue
            
            if not points:
                logger.warning("No valid points found in PCD file")
                return None
            
            logger.info(f"Loaded {len(points)} points from PCD format")
            return np.array(points, dtype=np.float32)
            
        except Exception as e:
            logger.error(f"PCD parsing failed: {e}")
            return None
    
    @staticmethod
    def _load_xyz(data: bytes) -> Optional[np.ndarray]:
        """Load simple XYZ format point cloud (space/tab separated coordinates)"""
        try:
            lines = data.decode('utf-8').split('\n')
            
            points = []
            line_count = 0
            
            for line in lines:
                line_count += 1
                if line.strip():
                    # Handle both space and tab separation
                    coords = line.strip().replace('\t', ' ').split()
                    if len(coords) >= 3:
                        try:
                            x, y, z = float(coords[0]), float(coords[1]), float(coords[2])
                            # Basic validation
                            if all(np.isfinite([x, y, z])):
                                points.append([x, y, z])
                        except ValueError:
                            # Skip malformed lines
                            continue
            
            if not points:
                logger.warning(f"No valid points found in XYZ file ({line_count} lines processed)")
                return None
            
            logger.info(f"Loaded {len(points)} points from XYZ format")
            return np.array(points, dtype=np.float32)
            
        except Exception as e:
            logger.error(f"XYZ parsing failed: {e}")
            return None
    
    @staticmethod
    def validate_point_cloud(points: np.ndarray) -> bool:
        """
        Validate loaded point cloud data
        
        Args:
            points: Point cloud array to validate
            
        Returns:
            True if valid, False otherwise
        """
        if points is None:
            return False
            
        if len(points) == 0:
            logger.warning("Point cloud is empty")
            return False
            
        if points.shape[1] != 3:
            logger.error(f"Invalid point cloud shape: {points.shape}, expected (N, 3)")
            return False
            
        # Check for NaN or infinite values
        if not np.all(np.isfinite(points)):
            logger.warning("Point cloud contains NaN or infinite values")
            return False
            
        logger.info(f"Point cloud validation passed: {len(points)} valid points")
        return True