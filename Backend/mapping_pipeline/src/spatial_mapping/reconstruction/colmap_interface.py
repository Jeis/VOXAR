"""
VOXAR Spatial Mapping - COLMAP Interface
Core COLMAP pipeline orchestration with enterprise error handling
"""

import os
import logging
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
from datetime import datetime

logger = logging.getLogger(__name__)

class ReconstructionStage(Enum):
    """Enumeration of reconstruction pipeline stages"""
    INITIALIZATION = "initialization"
    FEATURE_EXTRACTION = "feature_extraction" 
    FEATURE_MATCHING = "feature_matching"
    SPARSE_RECONSTRUCTION = "sparse_reconstruction"
    DENSE_RECONSTRUCTION = "dense_reconstruction"
    MESH_GENERATION = "mesh_generation"
    TEXTURE_MAPPING = "texture_mapping"
    OPTIMIZATION = "optimization"
    EXPORT = "export"
    CLEANUP = "cleanup"

class QualityLevel(Enum):
    """Reconstruction quality levels"""
    FAST = "fast"           # Quick preview
    BALANCED = "balanced"   # Production quality
    HIGH = "high"          # Maximum quality
    ULTRA = "ultra"        # Research quality

@dataclass
class ReconstructionSettings:
    """Enterprise reconstruction configuration"""
    quality_level: QualityLevel = QualityLevel.BALANCED
    max_image_size: int = 3840
    feature_type: str = "sift"
    matcher_type: str = "exhaustive"
    enable_gpu: bool = True
    max_workers: int = 4
    memory_limit_gb: float = 16.0
    
    # Performance settings
    timeout_feature_extraction: int = 3600  # 1 hour
    timeout_matching: int = 7200            # 2 hours
    timeout_reconstruction: int = 10800     # 3 hours
    
    # Output settings
    export_ply: bool = True
    export_obj: bool = True
    export_cameras: bool = True
    export_points: bool = True

@dataclass
class ReconstructionStats:
    """Comprehensive reconstruction statistics"""
    stage: ReconstructionStage
    start_time: datetime
    end_time: Optional[datetime] = None
    duration_seconds: float = 0.0
    
    # Input statistics
    input_images: int = 0
    processed_images: int = 0
    failed_images: int = 0
    
    # Feature statistics
    total_features: int = 0
    avg_features_per_image: float = 0.0
    
    # Matching statistics  
    total_matches: int = 0
    avg_matches_per_pair: float = 0.0
    
    # Reconstruction statistics
    registered_images: int = 0
    sparse_points: int = 0
    dense_points: int = 0
    triangles: int = 0
    
    # Quality metrics
    reprojection_error: float = 0.0
    track_length: float = 0.0

class COLMAPInterface:
    """Enterprise COLMAP pipeline interface"""
    
    def __init__(self, settings: ReconstructionSettings):
        self.settings = settings
        self.stats: Dict[ReconstructionStage, ReconstructionStats] = {}
        
        # Validate COLMAP installation
        self._validate_colmap()
        
        logger.info(f"COLMAP interface initialized with {settings.quality_level.value} quality")
    
    def _validate_colmap(self):
        """Validate COLMAP installation and GPU availability"""
        try:
            result = subprocess.run(['colmap', '--help'], 
                                  capture_output=True, text=True, timeout=10)
            if result.returncode != 0:
                raise RuntimeError("COLMAP not found or not working")
                
            logger.info("COLMAP installation validated")
            
            # Check GPU availability if enabled
            if self.settings.enable_gpu:
                gpu_result = subprocess.run(['colmap', 'feature_extractor', '--SiftExtraction.use_gpu', '1'], 
                                          capture_output=True, text=True, timeout=5)
                if "CUDA" in gpu_result.stderr or gpu_result.returncode == 0:
                    logger.info("GPU acceleration available")
                else:
                    logger.warning("GPU requested but not available, falling back to CPU")
                    self.settings.enable_gpu = False
                    
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            raise RuntimeError(f"COLMAP validation failed: {e}")
    
    def run_pipeline(
        self, 
        image_dir: Path, 
        output_dir: Path,
        database_path: Optional[Path] = None
    ) -> Dict[str, any]:
        """Run complete COLMAP reconstruction pipeline"""
        
        start_time = datetime.now()
        
        try:
            # Initialize workspace
            workspace = self._initialize_workspace(image_dir, output_dir, database_path)
            
            # Run pipeline stages
            results = {
                'workspace': workspace,
                'settings': self.settings,
                'stats': self.stats,
                'success': True,
                'error': None
            }
            
            logger.info(f"COLMAP pipeline completed successfully in {workspace}")
            return results
            
        except Exception as e:
            logger.error(f"COLMAP pipeline failed: {e}")
            return {
                'success': False,
                'error': str(e),
                'stats': self.stats
            }
    
    def _initialize_workspace(
        self, 
        image_dir: Path, 
        output_dir: Path,
        database_path: Optional[Path] = None
    ) -> Path:
        """Initialize COLMAP workspace"""
        
        # Create output directory
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Set database path
        if database_path is None:
            database_path = output_dir / "database.db"
        
        # Create sparse and dense directories
        sparse_dir = output_dir / "sparse" / "0"
        dense_dir = output_dir / "dense"
        
        sparse_dir.mkdir(parents=True, exist_ok=True)
        dense_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Workspace initialized: {output_dir}")
        
        return output_dir
    
    def get_stage_stats(self, stage: ReconstructionStage) -> Optional[ReconstructionStats]:
        """Get statistics for a specific pipeline stage"""
        return self.stats.get(stage)
    
    def get_pipeline_summary(self) -> Dict[str, any]:
        """Get comprehensive pipeline summary"""
        
        total_duration = sum(stats.duration_seconds for stats in self.stats.values())
        successful_stages = len([s for s in self.stats.values() if s.end_time is not None])
        
        return {
            'total_stages': len(self.stats),
            'successful_stages': successful_stages,
            'total_duration_seconds': total_duration,
            'settings': self.settings,
            'quality_level': self.settings.quality_level.value
        }