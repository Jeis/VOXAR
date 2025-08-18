"""
VOXAR Spatial Mapping - Reconstruction Orchestrator
Enterprise-grade 3D reconstruction pipeline orchestrator using modular components
"""

import logging
import threading
import tempfile
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime
from contextlib import contextmanager

from .colmap_interface import (
    COLMAPInterface, ReconstructionStage, QualityLevel, 
    ReconstructionSettings, ReconstructionStats
)
from .feature_extractor import FeatureExtractor, FeatureExtractionConfig
from .image_matcher import ImageMatcher, MatchingConfig
from .bundle_adjuster import BundleAdjuster, BundleAdjustmentConfig
from .mesh_generator import MeshGenerator, MeshGenerationConfig

logger = logging.getLogger(__name__)

@dataclass
class ReconstructionJob:
    """Reconstruction job definition"""
    id: str
    input_images_dir: Path
    output_dir: Path
    settings: ReconstructionSettings
    status: str = "pending"
    created_at: datetime = None
    started_at: datetime = None
    completed_at: datetime = None

class ReconstructionOrchestrator:
    """Enterprise 3D reconstruction pipeline orchestrator"""
    
    def __init__(self, settings: ReconstructionSettings = None):
        self.settings = settings or ReconstructionSettings()
        self.current_job: Optional[ReconstructionJob] = None
        self.stats: Optional[ReconstructionStats] = None
        self.workspace_dir: Optional[Path] = None
        self._lock = threading.Lock()
        
        # Initialize modular components
        self._initialize_components()
        
        logger.info(f"Reconstruction orchestrator initialized with {self.settings.quality_level.value} quality")
    
    def _initialize_components(self):
        """Initialize all modular components"""
        # Feature extraction
        self.feature_config = FeatureExtractionConfig(
            feature_type=self.settings.feature_type,
            max_image_size=self.settings.max_image_size,
            num_features=getattr(self.settings, 'sift_num_features', 8192),
            contrast_threshold=getattr(self.settings, 'sift_contrast_threshold', 0.04),
            edge_threshold=getattr(self.settings, 'sift_edge_threshold', 10.0),
            enable_gpu=self.settings.enable_gpu,
            timeout=self.settings.timeout_feature_extraction
        )
        self.feature_extractor = FeatureExtractor(self.feature_config)
        
        # Image matching
        self.matching_config = MatchingConfig(
            matcher_type=self.settings.matcher_type,
            max_distance=getattr(self.settings, 'matching_max_distance', 0.7),
            cross_check=getattr(self.settings, 'matching_cross_check', True),
            max_ratio=getattr(self.settings, 'matching_max_ratio', 0.8),
            max_error=getattr(self.settings, 'max_reprojection_error', 4.0),
            enable_gpu=self.settings.enable_gpu,
            timeout=self.settings.timeout_matching
        )
        self.image_matcher = ImageMatcher(self.matching_config)
        
        # Bundle adjustment
        self.bundle_config = BundleAdjustmentConfig(
            min_triangulation_angle=getattr(self.settings, 'min_triangulation_angle', 1.5),
            max_reprojection_error=getattr(self.settings, 'max_reprojection_error', 4.0),
            min_track_length=getattr(self.settings, 'min_track_length', 2),
            timeout=self.settings.timeout_reconstruction
        )
        self.bundle_adjuster = BundleAdjuster(self.bundle_config)
        
        # Mesh generation
        self.mesh_config = MeshGenerationConfig(
            workspace_size=getattr(self.settings, 'dense_workspace_size', 2),
            window_radius=getattr(self.settings, 'dense_window_radius', 5),
            num_samples=getattr(self.settings, 'dense_num_samples', 15),
            max_image_size=self.settings.max_image_size
        )
        self.mesh_generator = MeshGenerator(self.mesh_config)
    
    @contextmanager
    def _workspace_context(self, job: ReconstructionJob):
        """Context manager for workspace handling"""
        workspace = None
        try:
            workspace = Path(tempfile.mkdtemp(prefix=f"reconstruction_{job.id}_"))
            self.workspace_dir = workspace
            logger.info(f"Created workspace: {workspace}")
            yield workspace
        finally:
            if workspace and workspace.exists():
                try:
                    shutil.rmtree(workspace)
                    logger.info(f"Cleaned up workspace: {workspace}")
                except Exception as e:
                    logger.warning(f"Failed to cleanup workspace: {e}")
            self.workspace_dir = None
    
    def process_reconstruction_job(self, job: ReconstructionJob) -> Dict[str, Any]:
        """Process complete reconstruction job using modular components"""
        with self._lock:
            self.current_job = job
            job.status = "running"
            job.started_at = datetime.now()
        
        try:
            with self._workspace_context(job) as workspace:
                # Initialize workspace
                self._start_stage(ReconstructionStage.INITIALIZATION)
                database_path = workspace / "database.db"
                images_dir = workspace / "images"
                
                # Copy images to workspace
                shutil.copytree(job.input_images_dir, images_dir)
                
                # Stage 1: Feature Extraction
                self._start_stage(ReconstructionStage.FEATURE_EXTRACTION)
                feature_results = self.feature_extractor.extract_features(images_dir, database_path)
                
                if not feature_results:
                    raise RuntimeError("Feature extraction produced no results")
                
                self.stats.total_features = sum(r.num_features for r in feature_results.values())
                self.stats.processed_images = len(feature_results)
                
                # Stage 2: Feature Matching
                self._start_stage(ReconstructionStage.FEATURE_MATCHING)
                matching_result = self.image_matcher.match_features(database_path)
                
                if not matching_result.success:
                    raise RuntimeError(f"Feature matching failed: {matching_result.error}")
                
                self.stats.feature_matches = matching_result.num_matches
                
                # Stage 3: Sparse Reconstruction
                self._start_stage(ReconstructionStage.SPARSE_RECONSTRUCTION)
                sparse_result = self.bundle_adjuster.run_sparse_reconstruction(database_path, workspace)
                
                if not sparse_result.success:
                    raise RuntimeError(f"Sparse reconstruction failed: {sparse_result.error}")
                
                self.stats.registered_images = sparse_result.num_registered_images
                self.stats.sparse_points = sparse_result.num_points_3d
                self.stats.mean_reprojection_error = sparse_result.mean_reprojection_error
                
                # Optional: Dense Reconstruction and Meshing
                dense_result = None
                mesh_result = None
                
                if self.settings.export_ply or self.settings.export_obj:
                    # Stage 4: Dense Reconstruction
                    self._start_stage(ReconstructionStage.DENSE_RECONSTRUCTION)
                    sparse_dir = workspace / "sparse" / "0"
                    dense_result = self.mesh_generator.generate_dense_reconstruction(sparse_dir, workspace)
                    
                    if dense_result.success:
                        self.stats.dense_points = dense_result.num_dense_points
                        
                        # Stage 5: Mesh Generation
                        if self.settings.export_obj:
                            self._start_stage(ReconstructionStage.MESH_GENERATION)
                            dense_dir = workspace / "dense"
                            mesh_result = self.mesh_generator.generate_mesh(dense_dir)
                            
                            if mesh_result.success:
                                self.stats.mesh_faces = mesh_result.num_mesh_faces
                
                # Stage 6: Export Results
                self._start_stage(ReconstructionStage.EXPORT)
                output_files = self._export_results(workspace, job.output_dir, dense_result, mesh_result)
                
                # Finalize job
                self._start_stage(ReconstructionStage.CLEANUP)
                job.status = "completed"
                job.completed_at = datetime.now()
                
                return {
                    "success": True,
                    "job_id": job.id,
                    "stats": self._get_final_stats(),
                    "output_files": output_files,
                    "processing_time": (job.completed_at - job.started_at).total_seconds()
                }
                
        except Exception as e:
            logger.error(f"Reconstruction job {job.id} failed: {e}")
            job.status = "failed"
            job.completed_at = datetime.now()
            
            return {
                "success": False,
                "job_id": job.id,
                "error": str(e),
                "stats": self._get_final_stats() if self.stats else {}
            }
        finally:
            with self._lock:
                self.current_job = None
    
    def _start_stage(self, stage: ReconstructionStage):
        """Start a new processing stage"""
        if self.stats:
            # Complete current stage
            self.stats.end_time = datetime.now()
            self.stats.duration_seconds = (self.stats.end_time - self.stats.start_time).total_seconds()
        
        # Start new stage
        self.stats = ReconstructionStats(
            stage=stage,
            start_time=datetime.now()
        )
        
        logger.info(f"Stage: {stage.value}")
    
    def _export_results(self, workspace: Path, output_dir: Path, 
                       dense_result=None, mesh_result=None) -> Dict[str, Path]:
        """Export reconstruction results to output directory"""
        output_dir.mkdir(parents=True, exist_ok=True)
        output_files = {}
        
        # Export sparse reconstruction
        sparse_dir = workspace / "sparse" / "0"
        if sparse_dir.exists():
            sparse_output = output_dir / "sparse"
            shutil.copytree(sparse_dir, sparse_output, dirs_exist_ok=True)
            output_files["sparse"] = sparse_output
        
        # Export dense point cloud
        if dense_result and dense_result.success:
            dense_ply = workspace / "dense" / "fused.ply"
            if dense_ply.exists():
                dense_output = output_dir / "dense.ply"
                shutil.copy2(dense_ply, dense_output)
                output_files["dense_cloud"] = dense_output
        
        # Export mesh
        if mesh_result and mesh_result.success and mesh_result.mesh_file:
            mesh_output = output_dir / "mesh.ply"
            shutil.copy2(mesh_result.mesh_file, mesh_output)
            output_files["mesh"] = mesh_output
        
        return output_files
    
    def _get_final_stats(self) -> Dict[str, Any]:
        """Get final reconstruction statistics"""
        if not self.stats:
            return {}
        
        return {
            "input_images": self.stats.input_images,
            "processed_images": self.stats.processed_images,
            "registered_images": self.stats.registered_images,
            "total_features": self.stats.total_features,
            "feature_matches": self.stats.feature_matches,
            "sparse_points": self.stats.sparse_points,
            "dense_points": self.stats.dense_points,
            "mesh_faces": self.stats.mesh_faces,
            "mean_reprojection_error": self.stats.mean_reprojection_error,
            "stage_duration": self.stats.duration_seconds
        }
    
    def get_progress(self) -> Dict[str, Any]:
        """Get current processing progress"""
        if not self.current_job or not self.stats:
            return {"status": "idle"}
        
        return {
            "job_id": self.current_job.id,
            "status": self.current_job.status,
            "current_stage": self.stats.stage.value,
            "stats": self._get_final_stats()
        }


def create_orchestrator(quality_level: str = "balanced", **kwargs) -> ReconstructionOrchestrator:
    """Factory function to create reconstruction orchestrator"""
    settings = ReconstructionSettings(
        quality_level=QualityLevel(quality_level),
        **kwargs
    )
    return ReconstructionOrchestrator(settings)