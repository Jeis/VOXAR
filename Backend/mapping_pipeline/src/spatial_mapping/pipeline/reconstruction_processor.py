import os
import sys
import logging
import tempfile
import shutil
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import numpy as np
import cv2
import pycolmap
from datetime import datetime, timedelta

from ..models.job import ReconstructionJob, JobStatus, ReconstructionMetrics, ProcessingConfig
from ..models.map_data import MapData, MapMetadata
from ..utils.validation import ImageValidator
from ..utils.gps_utils import GPSProcessor
from ..monitoring.metrics import MetricsCollector

logger = logging.getLogger(__name__)

class ReconstructionProcessor:
    """
    Enterprise-grade COLMAP-based 3D reconstruction processor
    Handles the complete pipeline from images to 3D maps with robust error handling
    """
    
    def __init__(self, 
                 temp_dir: Optional[str] = None,
                 max_workers: int = 4,
                 memory_limit_gb: float = 16.0,
                 enable_gpu: bool = True):
        """
        Initialize the reconstruction processor
        
        Args:
            temp_dir: Temporary directory for processing (auto-created if None)
            max_workers: Maximum number of worker threads
            memory_limit_gb: Memory limit for processing
            enable_gpu: Enable GPU acceleration if available
        """
        self.temp_dir = Path(temp_dir) if temp_dir else None
        self.max_workers = max_workers
        self.memory_limit_gb = memory_limit_gb
        self.enable_gpu = enable_gpu
        
        # Initialize validators and utilities
        self.image_validator = ImageValidator()
        self.gps_processor = GPSProcessor()
        self.metrics_collector = MetricsCollector()
        
        # Check COLMAP availability
        self._verify_colmap_installation()
        
        logger.info(f"ReconstructionProcessor initialized with {max_workers} workers, "
                   f"{memory_limit_gb}GB memory limit, GPU={'enabled' if enable_gpu else 'disabled'}")
    
    def _verify_colmap_installation(self):
        """Verify COLMAP is properly installed and accessible"""
        try:
            # Check pycolmap
            version = pycolmap.__version__
            logger.info(f"Using pycolmap version: {version}")
            
            # Test basic functionality
            pycolmap.logging.set_log_level(pycolmap.logging.INFO)
            logger.info("COLMAP verification successful")
            
        except Exception as e:
            logger.error(f"COLMAP verification failed: {e}")
            raise RuntimeError("COLMAP is not properly installed or accessible")
    
    def process_reconstruction(self, job: ReconstructionJob) -> Tuple[bool, Optional[MapData]]:
        """
        Main processing pipeline for 3D reconstruction
        
        Args:
            job: Reconstruction job with all necessary parameters
            
        Returns:
            Tuple of (success, map_data)
        """
        work_dir = None
        start_time = time.time()
        
        try:
            # Update job status
            job.update_status(JobStatus.PROCESSING)
            self.metrics_collector.increment('reconstruction.started')
            
            logger.info(f"Starting reconstruction for job {job.job_id}")
            
            # Create working directory
            work_dir = self._create_work_directory(job.job_id)
            
            # Validate and prepare images
            image_paths = self._prepare_images(job, work_dir)
            if not image_paths:
                raise ValueError("No valid images found for processing")
            
            # Setup COLMAP database and workspace
            database_path, images_dir, output_dir = self._setup_colmap_workspace(work_dir)
            
            # Copy validated images to workspace
            self._copy_images_to_workspace(image_paths, images_dir)
            
            # Extract features
            job.progress_percentage = 10.0
            feature_stats = self._extract_features(database_path, images_dir, job.config)
            
            # Match features
            job.progress_percentage = 30.0
            match_stats = self._match_features(database_path, job.config)
            
            # Sparse reconstruction
            job.progress_percentage = 50.0
            sparse_reconstruction = self._sparse_reconstruction(
                database_path, images_dir, output_dir, job.config
            )
            
            if not sparse_reconstruction:
                raise RuntimeError("Sparse reconstruction failed - insufficient data or poor image quality")
            
            # Apply GPS alignment if available
            if job.center_gps:
                job.progress_percentage = 70.0
                self._align_with_gps(sparse_reconstruction, job)
            
            # Validate reconstruction quality
            job.progress_percentage = 80.0
            quality_metrics = self._validate_reconstruction_quality(sparse_reconstruction, job.config)
            
            # Optimize and filter point cloud
            job.progress_percentage = 90.0
            optimized_reconstruction = self._optimize_reconstruction(sparse_reconstruction, job.config)
            
            # Generate output map
            map_data = self._generate_map_data(optimized_reconstruction, job, quality_metrics)
            
            # Calculate final metrics
            processing_time = time.time() - start_time
            final_metrics = self._calculate_final_metrics(
                optimized_reconstruction, 
                feature_stats, 
                match_stats, 
                processing_time,
                len(image_paths)
            )
            
            job.metrics = final_metrics
            job.progress_percentage = 100.0
            job.update_status(JobStatus.COMPLETED)
            
            self.metrics_collector.increment('reconstruction.completed')
            self.metrics_collector.record_histogram('reconstruction.duration', processing_time)
            
            logger.info(f"Reconstruction completed successfully for job {job.job_id} "
                       f"in {processing_time:.1f}s")
            
            return True, map_data
            
        except Exception as e:
            processing_time = time.time() - start_time
            error_msg = f"Reconstruction failed: {str(e)}"
            logger.error(f"Job {job.job_id}: {error_msg}")
            
            job.update_status(JobStatus.FAILED, error_msg)
            self.metrics_collector.increment('reconstruction.failed')
            
            return False, None
            
        finally:
            # Cleanup temporary files
            if work_dir and work_dir.exists():
                try:
                    shutil.rmtree(work_dir)
                    logger.debug(f"Cleaned up work directory: {work_dir}")
                except Exception as e:
                    logger.warning(f"Failed to cleanup work directory {work_dir}: {e}")
    
    def _create_work_directory(self, job_id: str) -> Path:
        """Create a temporary working directory for the job"""
        if self.temp_dir:
            work_dir = self.temp_dir / f"job_{job_id}_{int(time.time())}"
        else:
            work_dir = Path(tempfile.mkdtemp(prefix=f"spatial_job_{job_id}_"))
        
        work_dir.mkdir(parents=True, exist_ok=True)
        logger.debug(f"Created work directory: {work_dir}")
        return work_dir
    
    def _prepare_images(self, job: ReconstructionJob, work_dir: Path) -> List[Path]:
        """
        Validate and prepare images for processing
        
        Returns list of valid image paths
        """
        logger.info(f"Preparing {len(job.images)} images for processing")
        valid_images = []
        
        for image_meta in job.images:
            try:
                # Download image from storage (implementation depends on storage backend)
                image_path = self._download_image(image_meta, work_dir)
                
                # Validate image
                if self.image_validator.validate_image(image_path):
                    valid_images.append(image_path)
                    logger.debug(f"Image validated: {image_meta.filename}")
                else:
                    job.add_warning(f"Invalid image skipped: {image_meta.filename}")
                    logger.warning(f"Invalid image skipped: {image_meta.filename}")
                    
            except Exception as e:
                job.add_warning(f"Failed to process image {image_meta.filename}: {str(e)}")
                logger.warning(f"Failed to process image {image_meta.filename}: {e}")
        
        if len(valid_images) < 3:
            raise ValueError(f"Insufficient valid images: {len(valid_images)} (minimum 3 required)")
        
        # Check image distribution for better reconstruction
        self._analyze_image_distribution(valid_images, job)
        
        logger.info(f"Prepared {len(valid_images)} valid images")
        return valid_images
    
    def _download_image(self, image_meta, work_dir: Path) -> Path:
        """
        Download image from storage backend
        This is a placeholder - actual implementation would depend on storage system
        """
        # For now, assume images are already local or implement actual download logic
        local_path = work_dir / "downloads" / image_meta.filename
        local_path.parent.mkdir(exist_ok=True)
        
        # Placeholder implementation - in reality this would download from S3/GCS/etc
        # For demo purposes, we'll just return a path
        return local_path
    
    def _analyze_image_distribution(self, image_paths: List[Path], job: ReconstructionJob):
        """Analyze spatial and temporal distribution of images"""
        # This would analyze GPS data, timestamps, and visual overlap
        # to ensure good coverage for reconstruction
        
        if len(image_paths) < 10:
            job.add_warning("Low image count may result in incomplete reconstruction")
        
        # Add more sophisticated analysis based on GPS coverage, time distribution, etc.
        logger.debug(f"Analyzed distribution of {len(image_paths)} images")
    
    def _setup_colmap_workspace(self, work_dir: Path) -> Tuple[Path, Path, Path]:
        """Setup COLMAP workspace directories"""
        database_path = work_dir / "database.db"
        images_dir = work_dir / "images"
        output_dir = work_dir / "sparse"
        
        images_dir.mkdir(exist_ok=True)
        output_dir.mkdir(exist_ok=True)
        
        return database_path, images_dir, output_dir
    
    def _copy_images_to_workspace(self, image_paths: List[Path], images_dir: Path):
        """Copy validated images to COLMAP workspace"""
        for img_path in image_paths:
            if img_path.exists():
                dest_path = images_dir / img_path.name
                shutil.copy2(img_path, dest_path)
                logger.debug(f"Copied image: {img_path.name}")
    
    def _extract_features(self, database_path: Path, images_dir: Path, config: ProcessingConfig) -> Dict:
        """Extract SIFT features from images"""
        logger.info("Extracting features...")
        
        start_time = time.time()
        
        try:
            # Configure feature extraction options
            sift_options = pycolmap.SiftExtractionOptions()
            sift_options.max_num_features = config.max_features
            sift_options.peak_threshold = config.feature_quality
            sift_options.edge_threshold = config.edge_threshold
            sift_options.use_gpu = self.enable_gpu
            
            # Extract features
            pycolmap.extract_features(
                database_path=str(database_path),
                image_path=str(images_dir),
                sift_options=sift_options
            )
            
            extraction_time = time.time() - start_time
            
            # Gather statistics
            stats = {
                'extraction_time': extraction_time,
                'num_images_processed': len(list(images_dir.glob('*'))),
                'average_features_per_image': config.max_features  # Approximate
            }
            
            logger.info(f"Feature extraction completed in {extraction_time:.1f}s")
            return stats
            
        except Exception as e:
            logger.error(f"Feature extraction failed: {e}")
            raise RuntimeError(f"Feature extraction failed: {e}")
    
    def _match_features(self, database_path: Path, config: ProcessingConfig) -> Dict:
        """Match features between images"""
        logger.info("Matching features...")
        
        start_time = time.time()
        
        try:
            # Configure matching options
            match_options = pycolmap.SiftMatchingOptions()
            match_options.max_distance = config.max_distance
            match_options.cross_check = config.cross_check
            match_options.use_gpu = self.enable_gpu
            
            # Perform exhaustive matching
            if config.matcher_type == "exhaustive":
                pycolmap.match_exhaustive(
                    database_path=str(database_path),
                    sift_options=match_options
                )
            elif config.matcher_type == "sequential":
                pycolmap.match_sequential(
                    database_path=str(database_path),
                    sift_options=match_options
                )
            else:
                raise ValueError(f"Unsupported matcher type: {config.matcher_type}")
            
            matching_time = time.time() - start_time
            
            stats = {
                'matching_time': matching_time,
                'matcher_type': config.matcher_type
            }
            
            logger.info(f"Feature matching completed in {matching_time:.1f}s")
            return stats
            
        except Exception as e:
            logger.error(f"Feature matching failed: {e}")
            raise RuntimeError(f"Feature matching failed: {e}")
    
    def _sparse_reconstruction(self, database_path: Path, images_dir: Path, 
                              output_dir: Path, config: ProcessingConfig) -> Optional[Dict]:
        """Perform sparse 3D reconstruction"""
        logger.info("Starting sparse reconstruction...")
        
        start_time = time.time()
        
        try:
            # Configure mapper options
            mapper_options = pycolmap.IncrementalMapperOptions()
            mapper_options.ba_local_max_num_iterations = config.ba_local_iterations
            mapper_options.ba_global_max_num_iterations = config.ba_global_iterations
            mapper_options.min_num_matches = 15
            mapper_options.init_min_tri_angle = config.min_triangulation_angle
            mapper_options.ba_local_function_tolerance = 1e-6
            mapper_options.ba_global_function_tolerance = 1e-6
            
            # Perform incremental reconstruction
            reconstructions = pycolmap.incremental_mapping(
                database_path=str(database_path),
                image_path=str(images_dir),
                output_path=str(output_dir),
                options=mapper_options
            )
            
            reconstruction_time = time.time() - start_time
            
            if not reconstructions:
                logger.warning("No reconstructions created")
                return None
            
            # Select the largest reconstruction
            largest_reconstruction = max(reconstructions, key=lambda r: len(r.points3D))
            
            logger.info(f"Sparse reconstruction completed in {reconstruction_time:.1f}s")
            logger.info(f"Registered {len(largest_reconstruction.images)} images, "
                       f"reconstructed {len(largest_reconstruction.points3D)} 3D points")
            
            return {
                'reconstruction': largest_reconstruction,
                'reconstruction_time': reconstruction_time,
                'num_reconstructions': len(reconstructions),
                'registered_images': len(largest_reconstruction.images),
                'num_points': len(largest_reconstruction.points3D)
            }
            
        except Exception as e:
            logger.error(f"Sparse reconstruction failed: {e}")
            raise RuntimeError(f"Sparse reconstruction failed: {e}")
    
    def _align_with_gps(self, reconstruction_data: Dict, job: ReconstructionJob):
        """Align reconstruction with GPS coordinates"""
        logger.info("Aligning reconstruction with GPS data...")
        
        try:
            reconstruction = reconstruction_data['reconstruction']
            
            # This is a simplified GPS alignment - full implementation would be more complex
            # involving robust estimation and coordinate transformations
            
            if job.center_gps:
                logger.info(f"GPS alignment with center point: "
                           f"{job.center_gps.latitude}, {job.center_gps.longitude}")
                
                # In a full implementation, this would:
                # 1. Extract GPS data from images
                # 2. Find correspondences between 3D points and GPS positions
                # 3. Calculate similarity transformation (scale, rotation, translation)
                # 4. Apply transformation to reconstruction
                
                job.add_warning("GPS alignment is simplified in current implementation")
            
        except Exception as e:
            logger.warning(f"GPS alignment failed: {e}")
            job.add_warning(f"GPS alignment failed: {str(e)}")
    
    def _validate_reconstruction_quality(self, reconstruction_data: Dict, 
                                       config: ProcessingConfig) -> Dict:
        """Validate reconstruction quality against thresholds"""
        logger.info("Validating reconstruction quality...")
        
        reconstruction = reconstruction_data['reconstruction']
        
        # Calculate quality metrics
        total_points = len(reconstruction.points3D)
        registered_images = len(reconstruction.images)
        
        # Calculate mean reprojection error
        reprojection_errors = []
        for point_id, point in reconstruction.points3D.items():
            reprojection_errors.append(point.error)
        
        mean_error = np.mean(reprojection_errors) if reprojection_errors else float('inf')
        
        # Calculate track lengths
        track_lengths = [len(point.track.elements) for point in reconstruction.points3D.values()]
        mean_track_length = np.mean(track_lengths) if track_lengths else 0
        
        # Quality checks
        quality_issues = []
        
        if total_points < 100:
            quality_issues.append("Very few 3D points reconstructed")
        
        if registered_images < 3:
            quality_issues.append("Too few images registered")
        
        if mean_error > config.max_reprojection_error:
            quality_issues.append(f"High reprojection error: {mean_error:.2f}px")
        
        if mean_track_length < config.min_track_length:
            quality_issues.append(f"Short track lengths: {mean_track_length:.1f}")
        
        # Calculate quality score (0-1)
        quality_score = 1.0
        quality_score *= min(total_points / 1000, 1.0)  # More points = better
        quality_score *= min(registered_images / 10, 1.0)  # More images = better
        quality_score *= max(0, 1.0 - mean_error / config.max_reprojection_error)  # Lower error = better
        quality_score = max(0, quality_score)
        
        quality_metrics = {
            'total_points': total_points,
            'registered_images': registered_images,
            'mean_reprojection_error': mean_error,
            'mean_track_length': mean_track_length,
            'quality_score': quality_score,
            'quality_issues': quality_issues
        }
        
        logger.info(f"Quality validation: {quality_score:.2f} score, "
                   f"{len(quality_issues)} issues identified")
        
        if quality_score < 0.3:
            raise RuntimeError(f"Reconstruction quality too low: {quality_score:.2f}")
        
        return quality_metrics
    
    def _optimize_reconstruction(self, reconstruction_data: Dict, 
                               config: ProcessingConfig) -> Dict:
        """Optimize and filter reconstruction"""
        logger.info("Optimizing reconstruction...")
        
        reconstruction = reconstruction_data['reconstruction']
        
        # Filter points by reprojection error
        points_to_remove = []
        for point_id, point in reconstruction.points3D.items():
            if point.error > config.max_reprojection_error:
                points_to_remove.append(point_id)
        
        # Remove poor quality points (in practice, would need proper COLMAP API calls)
        logger.info(f"Would remove {len(points_to_remove)} points with high error")
        
        # In a full implementation, would also:
        # - Bundle adjust after filtering
        # - Remove redundant observations
        # - Densify point cloud if requested
        
        optimized_data = reconstruction_data.copy()
        optimized_data['points_removed'] = len(points_to_remove)
        
        return optimized_data
    
    def _generate_map_data(self, reconstruction_data: Dict, job: ReconstructionJob,
                          quality_metrics: Dict) -> MapData:
        """Generate final map data structure"""
        logger.info("Generating map data...")
        
        reconstruction = reconstruction_data['reconstruction']
        
        # Extract camera poses
        camera_poses = {}
        for image_id, image in reconstruction.images.items():
            if image.registered:
                pose_matrix = image.cam_from_world.matrix()
                camera_poses[image.name] = {
                    'position': pose_matrix[:3, 3].tolist(),
                    'rotation_matrix': pose_matrix[:3, :3].tolist(),
                    'camera_id': image.camera_id
                }
        
        # Extract 3D points
        points_3d = []
        for point_id, point in reconstruction.points3D.items():
            points_3d.append({
                'id': point_id,
                'position': point.xyz.tolist(),
                'color': point.color.tolist() if hasattr(point, 'color') else [128, 128, 128],
                'error': point.error,
                'track_length': len(point.track.elements)
            })
        
        # Extract cameras
        cameras = {}
        for camera_id, camera in reconstruction.cameras.items():
            cameras[camera_id] = {
                'model': camera.model_name,
                'width': camera.width,
                'height': camera.height,
                'params': camera.params.tolist()
            }
        
        # Create metadata
        metadata = MapMetadata(
            map_id=job.job_id,
            location_id=job.location_id,
            created_at=datetime.now(),
            center_gps=job.center_gps,
            bounding_box=job.bounding_box,
            num_cameras=len(camera_poses),
            num_points=len(points_3d),
            reconstruction_quality=quality_metrics['quality_score'],
            processing_config=job.config
        )
        
        # Create map data
        map_data = MapData(
            metadata=metadata,
            cameras=cameras,
            camera_poses=camera_poses,
            points_3d=points_3d,
            quality_metrics=quality_metrics
        )
        
        logger.info(f"Generated map data: {len(camera_poses)} cameras, "
                   f"{len(points_3d)} points")
        
        return map_data
    
    def _calculate_final_metrics(self, reconstruction_data: Dict, feature_stats: Dict,
                               match_stats: Dict, processing_time: float,
                               total_images: int) -> ReconstructionMetrics:
        """Calculate final processing metrics"""
        reconstruction = reconstruction_data['reconstruction']
        
        # Calculate statistics
        total_points = len(reconstruction.points3D)
        registered_images = len([img for img in reconstruction.images.values() if img.registered])
        
        reprojection_errors = [point.error for point in reconstruction.points3D.values()]
        mean_reprojection_error = np.mean(reprojection_errors) if reprojection_errors else 0
        
        track_lengths = [len(point.track.elements) for point in reconstruction.points3D.values()]
        mean_track_length = np.mean(track_lengths) if track_lengths else 0
        
        total_observations = sum(track_lengths)
        
        # Calculate quality scores
        registration_rate = registered_images / total_images if total_images > 0 else 0
        reconstruction_quality = min(1.0, total_points / 500)  # Normalize to 0-1
        completeness_score = registration_rate
        accuracy_score = max(0, 1.0 - mean_reprojection_error / 4.0)  # Assume 4px max error
        
        return ReconstructionMetrics(
            total_images=total_images,
            registered_images=registered_images,
            total_points=total_points,
            total_observations=total_observations,
            mean_reprojection_error=mean_reprojection_error,
            mean_track_length=mean_track_length,
            processing_time_seconds=processing_time,
            memory_usage_mb=0,  # Would need process monitoring
            reconstruction_quality=reconstruction_quality,
            completeness_score=completeness_score,
            accuracy_score=accuracy_score
        )