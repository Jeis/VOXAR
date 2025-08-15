"""
Spatial Platform - Enterprise-grade 3D mapping pipeline
Built with COLMAP for photogrammetry and real-world deployment
"""

__version__ = "1.0.0"
__author__ = "Spatial Platform Team"

from .pipeline.reconstruction_processor import ReconstructionProcessor
from .pipeline.optimization_engine import OptimizationEngine
from .services.upload_handler import UploadHandler
from .services.storage_manager import StorageManager
from .models.job import ReconstructionJob, JobStatus
from .models.map_data import MapData, MapMetadata

__all__ = [
    "ReconstructionProcessor",
    "OptimizationEngine", 
    "UploadHandler",
    "StorageManager",
    "ReconstructionJob",
    "JobStatus",
    "MapData",
    "MapMetadata",
]