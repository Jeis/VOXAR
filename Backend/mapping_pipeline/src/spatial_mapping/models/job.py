from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict, Any
import uuid

class JobStatus(Enum):
    """Status tracking for reconstruction jobs"""
    PENDING = "pending"
    UPLOADING = "uploading"
    PROCESSING = "processing"
    OPTIMIZING = "optimizing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class JobPriority(Enum):
    """Priority levels for job scheduling"""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    URGENT = 4

@dataclass
class GPSCoordinate:
    """GPS coordinate with accuracy information"""
    latitude: float
    longitude: float
    altitude: Optional[float] = None
    accuracy: Optional[float] = None  # meters
    timestamp: Optional[datetime] = None

@dataclass
class ImageMetadata:
    """Metadata for uploaded images"""
    filename: str
    size_bytes: int
    width: int
    height: int
    format: str  # JPEG, PNG, etc.
    timestamp: Optional[datetime] = None
    camera_model: Optional[str] = None
    focal_length: Optional[float] = None
    aperture: Optional[float] = None
    iso: Optional[int] = None
    exposure_time: Optional[float] = None
    gps: Optional[GPSCoordinate] = None
    checksum: Optional[str] = None

@dataclass
class ProcessingConfig:
    """Configuration parameters for reconstruction processing"""
    # Feature detection
    max_features: int = 8192
    feature_quality: float = 0.004
    edge_threshold: float = 10.0
    
    # Matching
    matcher_type: str = "exhaustive"  # exhaustive, sequential, vocab_tree
    max_distance: float = 0.7
    cross_check: bool = True
    
    # Bundle adjustment
    ba_local_iterations: int = 25
    ba_global_iterations: int = 50
    
    # Quality thresholds
    min_track_length: int = 3
    max_reprojection_error: float = 4.0
    min_triangulation_angle: float = 4.0
    
    # Output options
    dense_reconstruction: bool = False
    texture_generation: bool = False
    mesh_generation: bool = False
    
    # Performance
    num_threads: Optional[int] = None
    memory_limit_gb: Optional[float] = None
    gpu_acceleration: bool = True

@dataclass
class ReconstructionMetrics:
    """Metrics from the reconstruction process"""
    total_images: int
    registered_images: int
    total_points: int
    total_observations: int
    mean_reprojection_error: float
    mean_track_length: float
    processing_time_seconds: float
    memory_usage_mb: float
    
    # Quality scores
    reconstruction_quality: float  # 0-1 score
    completeness_score: float     # 0-1 score
    accuracy_score: float         # 0-1 score

@dataclass
class ReconstructionJob:
    """Complete reconstruction job with all metadata and configuration"""
    
    # Core identification
    job_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    location_id: str = ""
    user_id: str = ""
    
    # Timestamps
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    updated_at: datetime = field(default_factory=datetime.now)
    
    # Status and priority
    status: JobStatus = JobStatus.PENDING
    priority: JobPriority = JobPriority.NORMAL
    progress_percentage: float = 0.0
    
    # Input data
    images: List[ImageMetadata] = field(default_factory=list)
    storage_bucket: str = ""
    storage_prefix: str = ""
    
    # Geographic information
    center_gps: Optional[GPSCoordinate] = None
    bounding_box: Optional[Dict[str, float]] = None  # min_lat, max_lat, min_lon, max_lon
    
    # Configuration
    config: ProcessingConfig = field(default_factory=ProcessingConfig)
    
    # Results
    output_map_url: Optional[str] = None
    output_mesh_url: Optional[str] = None
    output_texture_url: Optional[str] = None
    compressed_map_size: Optional[int] = None
    
    # Metrics and quality
    metrics: Optional[ReconstructionMetrics] = None
    error_message: Optional[str] = None
    warnings: List[str] = field(default_factory=list)
    
    # Processing details
    worker_id: Optional[str] = None
    gpu_used: Optional[str] = None
    colmap_version: Optional[str] = None
    
    # Retry handling
    retry_count: int = 0
    max_retries: int = 3
    
    # Cost tracking (for billing)
    estimated_cost: Optional[float] = None
    actual_cost: Optional[float] = None
    compute_units_used: Optional[float] = None
    
    def __post_init__(self):
        """Validate job data after initialization"""
        if not self.location_id:
            raise ValueError("location_id is required")
        
        if not self.user_id:
            raise ValueError("user_id is required")
        
        if not self.images:
            raise ValueError("At least one image is required")
        
        # Validate GPS coordinates if provided
        if self.center_gps:
            if not (-90 <= self.center_gps.latitude <= 90):
                raise ValueError("Invalid latitude")
            if not (-180 <= self.center_gps.longitude <= 180):
                raise ValueError("Invalid longitude")
    
    def update_status(self, status: JobStatus, message: Optional[str] = None):
        """Update job status with timestamp"""
        self.status = status
        self.updated_at = datetime.now()
        
        if status == JobStatus.PROCESSING and not self.started_at:
            self.started_at = datetime.now()
        elif status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]:
            self.completed_at = datetime.now()
        
        if status == JobStatus.FAILED and message:
            self.error_message = message
    
    def add_warning(self, warning: str):
        """Add a warning message"""
        self.warnings.append(f"{datetime.now().isoformat()}: {warning}")
    
    def calculate_processing_time(self) -> Optional[float]:
        """Calculate total processing time in seconds"""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None
    
    def estimate_difficulty(self) -> float:
        """Estimate job difficulty (0-1 scale) based on input data"""
        difficulty = 0.0
        
        # Factor in number of images
        num_images = len(self.images)
        if num_images > 100:
            difficulty += 0.3
        elif num_images > 50:
            difficulty += 0.2
        elif num_images > 20:
            difficulty += 0.1
        
        # Factor in image resolution
        if self.images:
            total_megapixels = sum((img.width * img.height) / 1e6 for img in self.images)
            avg_megapixels = total_megapixels / num_images
            
            if avg_megapixels > 20:
                difficulty += 0.2
            elif avg_megapixels > 12:
                difficulty += 0.1
        
        # Factor in GPS availability (makes processing easier)
        has_gps = any(img.gps for img in self.images)
        if not has_gps:
            difficulty += 0.15
        
        # Factor in configuration complexity
        if self.config.dense_reconstruction:
            difficulty += 0.2
        if self.config.mesh_generation:
            difficulty += 0.15
        if self.config.texture_generation:
            difficulty += 0.1
        
        return min(difficulty, 1.0)
    
    def estimate_cost(self, cost_per_image: float = 0.10, cost_per_megapixel: float = 0.01) -> float:
        """Estimate processing cost based on job complexity"""
        base_cost = len(self.images) * cost_per_image
        
        if self.images:
            total_megapixels = sum((img.width * img.height) / 1e6 for img in self.images)
            megapixel_cost = total_megapixels * cost_per_megapixel
        else:
            megapixel_cost = 0.0
        
        # Complexity multiplier
        difficulty = self.estimate_difficulty()
        complexity_multiplier = 1.0 + difficulty
        
        # Priority multiplier
        priority_multipliers = {
            JobPriority.LOW: 0.8,
            JobPriority.NORMAL: 1.0,
            JobPriority.HIGH: 1.5,
            JobPriority.URGENT: 2.0
        }
        
        total_cost = (base_cost + megapixel_cost) * complexity_multiplier * priority_multipliers[self.priority]
        self.estimated_cost = round(total_cost, 2)
        return self.estimated_cost
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert job to dictionary for serialization"""
        return {
            "job_id": self.job_id,
            "location_id": self.location_id,
            "user_id": self.user_id,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "updated_at": self.updated_at.isoformat(),
            "status": self.status.value,
            "priority": self.priority.value,
            "progress_percentage": self.progress_percentage,
            "image_count": len(self.images),
            "storage_bucket": self.storage_bucket,
            "storage_prefix": self.storage_prefix,
            "center_gps": {
                "latitude": self.center_gps.latitude,
                "longitude": self.center_gps.longitude,
                "altitude": self.center_gps.altitude,
                "accuracy": self.center_gps.accuracy
            } if self.center_gps else None,
            "output_map_url": self.output_map_url,
            "output_mesh_url": self.output_mesh_url,
            "compressed_map_size": self.compressed_map_size,
            "metrics": {
                "total_images": self.metrics.total_images,
                "registered_images": self.metrics.registered_images,
                "total_points": self.metrics.total_points,
                "mean_reprojection_error": self.metrics.mean_reprojection_error,
                "processing_time_seconds": self.metrics.processing_time_seconds,
                "reconstruction_quality": self.metrics.reconstruction_quality,
            } if self.metrics else None,
            "error_message": self.error_message,
            "warnings": self.warnings,
            "retry_count": self.retry_count,
            "estimated_cost": self.estimated_cost,
            "actual_cost": self.actual_cost
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ReconstructionJob":
        """Create job from dictionary"""
        # This would implement the reverse conversion
        # Simplified for brevity - full implementation would handle all fields
        job = cls(
            job_id=data["job_id"],
            location_id=data["location_id"],
            user_id=data["user_id"]
        )
        
        if data.get("status"):
            job.status = JobStatus(data["status"])
        
        if data.get("priority"):
            job.priority = JobPriority(data["priority"])
        
        return job
    
    def is_retriable(self) -> bool:
        """Check if job can be retried"""
        return (
            self.status == JobStatus.FAILED and 
            self.retry_count < self.max_retries and
            self.error_message and
            "PERMANENT" not in self.error_message.upper()
        )
    
    def should_cleanup(self, retention_days: int = 30) -> bool:
        """Check if job data should be cleaned up"""
        if not self.completed_at:
            return False
        
        age_days = (datetime.now() - self.completed_at).days
        return age_days > retention_days