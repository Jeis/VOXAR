"""
Spatial Platform - Enterprise-grade 3D mapping pipeline
Built with COLMAP for photogrammetry and real-world deployment
"""

__version__ = "1.0.0"
__author__ = "Spatial Platform Team"

# Import core components with graceful fallback for reconstruction processor
try:
    from .pipeline.reconstruction_processor import ReconstructionProcessor
    _reconstruction_available = True
except ImportError as e:
    # Graceful fallback if reconstruction processor dependencies are missing
    ReconstructionProcessor = None
    _reconstruction_available = False
    print(f"Warning: ReconstructionProcessor not available: {e}")

from .pipeline.optimization_engine import OptimizationEngine
from .services.upload_handler import UploadHandler
from .services.storage_manager import StorageManager
from .models.job import ReconstructionJob, JobStatus
from .models.map_data import MapData, MapMetadata

__all__ = [
    "OptimizationEngine", 
    "UploadHandler",
    "StorageManager",
    "ReconstructionJob",
    "JobStatus",
    "MapData",
    "MapMetadata",
]

# Add ReconstructionProcessor to exports only if available
if _reconstruction_available:
    __all__.append("ReconstructionProcessor")