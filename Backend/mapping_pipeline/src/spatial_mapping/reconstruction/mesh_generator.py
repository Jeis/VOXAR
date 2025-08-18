"""
VOXAR Spatial Mapping - Mesh Generator
Enterprise-grade dense reconstruction and mesh generation
"""

import os
import logging
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime

import numpy as np

logger = logging.getLogger(__name__)

@dataclass
class MeshGenerationConfig:
    """Mesh generation configuration"""
    # Dense reconstruction settings
    workspace_size: int = 2
    window_radius: int = 5
    num_samples: int = 15
    num_iterations: int = 5
    
    # Photometric settings
    max_image_size: int = 2048
    patch_match_filter: bool = True
    geom_consistency: bool = True
    
    # Meshing settings
    mesh_quality: float = 1.0
    mesh_max_faces: int = 200000
    mesh_num_threads: int = -1
    
    # Timeout settings
    timeout_dense: int = 14400  # 4 hours
    timeout_meshing: int = 3600  # 1 hour

@dataclass
class MeshGenerationResult:
    """Mesh generation results"""
    num_dense_points: int
    num_mesh_vertices: int
    num_mesh_faces: int
    mesh_file: Optional[Path]
    dense_time: float
    mesh_time: float
    success: bool
    error: Optional[str] = None

class MeshGenerator:
    """Enterprise COLMAP dense reconstructor and mesh generator"""
    
    def __init__(self, config: MeshGenerationConfig, colmap_path: str = None):
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
            logger.info("COLMAP installation verified for mesh generation")
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            raise RuntimeError(f"COLMAP validation failed: {e}")
    
    def generate_dense_reconstruction(self, sparse_dir: Path, output_dir: Path) -> MeshGenerationResult:
        """Generate dense point cloud from sparse reconstruction"""
        start_time = datetime.now()
        
        # Create dense output directory
        dense_dir = output_dir / "dense"
        dense_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            # Step 1: Image undistortion
            undistort_result = self._undistort_images(sparse_dir, dense_dir)
            if not undistort_result:
                raise RuntimeError("Image undistortion failed")
            
            # Step 2: Patch match stereo
            stereo_result = self._patch_match_stereo(dense_dir)
            if not stereo_result:
                raise RuntimeError("Patch match stereo failed")
            
            # Step 3: Stereo fusion
            fusion_result = self._stereo_fusion(dense_dir)
            if not fusion_result:
                raise RuntimeError("Stereo fusion failed")
            
            dense_time = (datetime.now() - start_time).total_seconds()
            
            # Count dense points
            dense_ply = dense_dir / "fused.ply"
            num_dense_points = self._count_ply_points(dense_ply)
            
            logger.info(f"Dense reconstruction completed: {num_dense_points} points in {dense_time:.2f}s")
            
            return MeshGenerationResult(
                num_dense_points=num_dense_points,
                num_mesh_vertices=0,
                num_mesh_faces=0,
                mesh_file=None,
                dense_time=dense_time,
                mesh_time=0.0,
                success=True
            )
            
        except Exception as e:
            dense_time = (datetime.now() - start_time).total_seconds()
            logger.error(f"Dense reconstruction failed: {e}")
            return MeshGenerationResult(
                0, 0, 0, None, dense_time, 0.0, False, str(e)
            )
    
    def _undistort_images(self, sparse_dir: Path, dense_dir: Path) -> bool:
        """Undistort images for dense reconstruction"""
        
        cmd = [
            self.colmap_path, 'image_undistorter',
            '--image_path', str(sparse_dir.parent.parent / "images"),
            '--input_path', str(sparse_dir),
            '--output_path', str(dense_dir),
            '--output_type', 'COLMAP',
            '--max_image_size', str(self.config.max_image_size),
        ]
        
        try:
            logger.info("Starting image undistortion")
            result = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=self.config.timeout_dense // 3
            )
            
            if result.returncode != 0:
                logger.error(f"Image undistortion failed: {result.stderr}")
                return False
            
            logger.info("Image undistortion completed")
            return True
            
        except subprocess.TimeoutExpired:
            logger.error("Image undistortion timed out")
            return False
    
    def _patch_match_stereo(self, dense_dir: Path) -> bool:
        """Run patch match stereo"""
        
        cmd = [
            self.colmap_path, 'patch_match_stereo',
            '--workspace_path', str(dense_dir),
            '--workspace_format', 'COLMAP',
            '--PatchMatchStereo.window_radius', str(self.config.window_radius),
            '--PatchMatchStereo.num_samples', str(self.config.num_samples),
            '--PatchMatchStereo.num_iterations', str(self.config.num_iterations),
            '--PatchMatchStereo.geom_consistency', str(self.config.geom_consistency).lower(),
            '--PatchMatchStereo.filter', str(self.config.patch_match_filter).lower(),
        ]
        
        try:
            logger.info("Starting patch match stereo")
            result = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=self.config.timeout_dense // 2
            )
            
            if result.returncode != 0:
                logger.error(f"Patch match stereo failed: {result.stderr}")
                return False
            
            logger.info("Patch match stereo completed")
            return True
            
        except subprocess.TimeoutExpired:
            logger.error("Patch match stereo timed out")
            return False
    
    def _stereo_fusion(self, dense_dir: Path) -> bool:
        """Fuse stereo depth maps"""
        
        cmd = [
            self.colmap_path, 'stereo_fusion',
            '--workspace_path', str(dense_dir),
            '--workspace_format', 'COLMAP',
            '--input_type', 'geometric',
            '--output_path', str(dense_dir / "fused.ply"),
        ]
        
        try:
            logger.info("Starting stereo fusion")
            result = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=self.config.timeout_dense // 6
            )
            
            if result.returncode != 0:
                logger.error(f"Stereo fusion failed: {result.stderr}")
                return False
            
            logger.info("Stereo fusion completed")
            return True
            
        except subprocess.TimeoutExpired:
            logger.error("Stereo fusion timed out")
            return False
    
    def generate_mesh(self, dense_dir: Path) -> MeshGenerationResult:
        """Generate mesh from dense point cloud"""
        start_time = datetime.now()
        
        dense_ply = dense_dir / "fused.ply"
        mesh_ply = dense_dir / "meshed-delaunay.ply"
        
        if not dense_ply.exists():
            return MeshGenerationResult(
                0, 0, 0, None, 0.0, 0.0, False, "Dense point cloud not found"
            )
        
        cmd = [
            self.colmap_path, 'delaunay_mesher',
            '--input_path', str(dense_ply),
            '--output_path', str(mesh_ply),
            '--DelaunayMeshing.quality', str(self.config.mesh_quality),
            '--DelaunayMeshing.max_proj_dist', '20.0',
            '--DelaunayMeshing.max_depth_dist', '20.0',
            '--DelaunayMeshing.visibility_sigma', '2.0',
            '--DelaunayMeshing.distance_sigma_factor', '1.0',
        ]
        
        if self.config.mesh_num_threads > 0:
            cmd.extend(['--DelaunayMeshing.num_threads', str(self.config.mesh_num_threads)])
        
        try:
            logger.info("Starting mesh generation")
            result = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=self.config.timeout_meshing
            )
            
            if result.returncode != 0:
                logger.error(f"Mesh generation failed: {result.stderr}")
                mesh_time = (datetime.now() - start_time).total_seconds()
                return MeshGenerationResult(
                    0, 0, 0, None, 0.0, mesh_time, False, result.stderr
                )
            
            mesh_time = (datetime.now() - start_time).total_seconds()
            
            # Count mesh vertices and faces
            num_vertices, num_faces = self._count_mesh_elements(mesh_ply)
            num_dense_points = self._count_ply_points(dense_ply)
            
            logger.info(f"Mesh generation completed: {num_vertices} vertices, "
                       f"{num_faces} faces in {mesh_time:.2f}s")
            
            return MeshGenerationResult(
                num_dense_points=num_dense_points,
                num_mesh_vertices=num_vertices,
                num_mesh_faces=num_faces,
                mesh_file=mesh_ply,
                dense_time=0.0,
                mesh_time=mesh_time,
                success=True
            )
            
        except subprocess.TimeoutExpired:
            mesh_time = (datetime.now() - start_time).total_seconds()
            return MeshGenerationResult(
                0, 0, 0, None, 0.0, mesh_time, False, "Mesh generation timed out"
            )
        except Exception as e:
            mesh_time = (datetime.now() - start_time).total_seconds()
            logger.error(f"Mesh generation failed: {e}")
            return MeshGenerationResult(
                0, 0, 0, None, 0.0, mesh_time, False, str(e)
            )
    
    def _count_ply_points(self, ply_file: Path) -> int:
        """Count points in PLY file"""
        if not ply_file.exists():
            return 0
        
        try:
            with open(ply_file, 'r') as f:
                for line in f:
                    if line.startswith('element vertex'):
                        return int(line.split()[-1])
            return 0
        except Exception as e:
            logger.warning(f"Could not count PLY points: {e}")
            return 0
    
    def _count_mesh_elements(self, mesh_file: Path) -> Tuple[int, int]:
        """Count vertices and faces in mesh PLY file"""
        if not mesh_file.exists():
            return 0, 0
        
        try:
            vertices = 0
            faces = 0
            
            with open(mesh_file, 'r') as f:
                for line in f:
                    if line.startswith('element vertex'):
                        vertices = int(line.split()[-1])
                    elif line.startswith('element face'):
                        faces = int(line.split()[-1])
            
            return vertices, faces
            
        except Exception as e:
            logger.warning(f"Could not count mesh elements: {e}")
            return 0, 0
    
    def export_mesh_formats(self, mesh_ply: Path, output_dir: Path) -> Dict[str, Path]:
        """Export mesh to different formats"""
        
        if not mesh_ply.exists():
            logger.error("Source mesh PLY file not found")
            return {}
        
        exports = {}
        
        try:
            # Export to OBJ format (if requested in config)
            obj_file = output_dir / f"{mesh_ply.stem}.obj"
            if self._export_to_obj(mesh_ply, obj_file):
                exports['obj'] = obj_file
            
            # Keep original PLY
            exports['ply'] = mesh_ply
            
            logger.info(f"Exported mesh to {len(exports)} formats")
            
        except Exception as e:
            logger.error(f"Mesh export failed: {e}")
        
        return exports
    
    def _export_to_obj(self, input_ply: Path, output_obj: Path) -> bool:
        """Export PLY to OBJ format using simple conversion"""
        
        try:
            # This is a simplified implementation
            # In production, use proper PLY/OBJ conversion libraries
            logger.warning("OBJ export not fully implemented - keeping PLY format")
            return False
            
        except Exception as e:
            logger.error(f"OBJ export failed: {e}")
            return False
    
    def get_mesh_statistics(self, dense_dir: Path) -> Dict:
        """Get detailed mesh generation statistics"""
        
        try:
            dense_ply = dense_dir / "fused.ply"
            mesh_ply = dense_dir / "meshed-delaunay.ply"
            
            stats = {
                'dense_points': self._count_ply_points(dense_ply) if dense_ply.exists() else 0,
                'mesh_exists': mesh_ply.exists(),
                'config': self.config.__dict__
            }
            
            if mesh_ply.exists():
                vertices, faces = self._count_mesh_elements(mesh_ply)
                stats.update({
                    'mesh_vertices': vertices,
                    'mesh_faces': faces,
                    'mesh_file_size_mb': mesh_ply.stat().st_size / (1024 * 1024)
                })
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get mesh statistics: {e}")
            return {}