#!/usr/bin/env python3
"""
Spatial Platform - Celery Tasks
Background tasks for 3D reconstruction
"""

from .celery_app import app

@app.task(bind=True)
def process_reconstruction(self, job_id: str, images: list, config: dict = None):
    """Process 3D reconstruction job using COLMAP pipeline"""
    from .pipeline.reconstruction_processor import ReconstructionProcessor
    from .models.job import ReconstructionJob, JobStatus
    
    try:
        # Update task state
        self.update_state(state='PROGRESS', meta={'current': 0, 'total': 100, 'status': 'Starting reconstruction...'})
        
        # Create reconstruction processor
        processor = ReconstructionProcessor(
            temp_dir=config.get('temp_dir') if config else None,
            max_workers=config.get('max_workers', 4) if config else 4,
            enable_gpu=config.get('enable_gpu', True) if config else True
        )
        
        # Create job object from parameters
        job = ReconstructionJob(
            job_id=job_id,
            images=images,
            status=JobStatus.PROCESSING
        )
        
        # Process reconstruction
        success, map_data = processor.process_reconstruction(job)
        
        if success:
            return {
                "job_id": job_id,
                "status": "completed",
                "message": "3D reconstruction completed successfully",
                "map_data": map_data.to_dict() if map_data else None,
                "metrics": job.metrics.to_dict() if job.metrics else None,
                "processed_images": len(images)
            }
        else:
            return {
                "job_id": job_id,
                "status": "failed",
                "message": f"Reconstruction failed: {job.error_message}",
                "errors": job.warnings,
                "processed_images": len(images)
            }
            
    except Exception as e:
        # Update task state with error
        self.update_state(
            state='FAILURE',
            meta={
                'current': 100,
                'total': 100,
                'status': f'Task failed: {str(e)}'
            }
        )
        raise

@app.task(bind=True)
def reconstruction_task(self, job_id: str, config: dict = None):
    """Main 3D reconstruction task with progress tracking"""
    from .pipeline.reconstruction_processor import ReconstructionProcessor
    from .models.job import ReconstructionJob, JobStatus
    import time
    
    try:
        # Initialize progress
        self.update_state(state='PROGRESS', meta={'current': 0, 'total': 100, 'status': 'Initializing...'})
        
        # Load job from database
        # In practice, this would load from your job storage (Redis, PostgreSQL, etc.)
        job = ReconstructionJob.load_from_storage(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")
        
        # Create processor with configuration
        processor_config = config or {}
        processor = ReconstructionProcessor(
            temp_dir=processor_config.get('temp_dir'),
            max_workers=processor_config.get('max_workers', 4),
            memory_limit_gb=processor_config.get('memory_limit_gb', 16.0),
            enable_gpu=processor_config.get('enable_gpu', True)
        )
        
        # Update progress callback
        def progress_callback(percentage: float, message: str):
            self.update_state(
                state='PROGRESS',
                meta={
                    'current': int(percentage),
                    'total': 100,
                    'status': message,
                    'job_id': job_id
                }
            )
        
        # Set progress callback on job
        job.progress_callback = progress_callback
        
        # Process reconstruction
        start_time = time.time()
        success, map_data = processor.process_reconstruction(job)
        processing_time = time.time() - start_time
        
        if success:
            # Save results to storage
            if map_data:
                map_data.save_to_storage()
            
            job.save_to_storage()
            
            return {
                "job_id": job_id,
                "status": "completed",
                "processing_time": processing_time,
                "message": "3D reconstruction completed successfully",
                "map_data_id": map_data.metadata.map_id if map_data else None,
                "metrics": {
                    "total_points": job.metrics.total_points if job.metrics else 0,
                    "registered_images": job.metrics.registered_images if job.metrics else 0,
                    "reconstruction_quality": job.metrics.reconstruction_quality if job.metrics else 0.0
                }
            }
        else:
            return {
                "job_id": job_id,
                "status": "failed",
                "processing_time": processing_time,
                "message": f"Reconstruction failed: {job.error_message}",
                "errors": job.warnings
            }
            
    except Exception as e:
        self.update_state(
            state='FAILURE',
            meta={
                'current': 100,
                'total': 100,
                'status': f'Reconstruction failed: {str(e)}',
                'job_id': job_id
            }
        )
        raise

@app.task(bind=True)
def cleanup_reconstruction_files(self, job_id: str, max_age_hours: int = 24):
    """Cleanup temporary files from reconstruction jobs"""
    import os
    import time
    from pathlib import Path
    
    try:
        temp_dirs = [
            f"/tmp/spatial_job_{job_id}_*",
            f"/app/temp/job_{job_id}_*"
        ]
        
        cleaned_files = 0
        for pattern in temp_dirs:
            for temp_dir in Path("/").glob(pattern.lstrip("/")):
                if temp_dir.is_dir():
                    # Check if directory is older than max_age_hours
                    dir_age = time.time() - temp_dir.stat().st_mtime
                    if dir_age > (max_age_hours * 3600):
                        import shutil
                        shutil.rmtree(temp_dir)
                        cleaned_files += 1
        
        return {
            "job_id": job_id,
            "cleaned_directories": cleaned_files,
            "status": "completed"
        }
        
    except Exception as e:
        return {
            "job_id": job_id,
            "status": "failed",
            "error": str(e)
        }