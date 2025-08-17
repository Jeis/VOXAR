#!/usr/bin/env python3
"""
Spatial Platform - Celery Application
Background task processing for 3D reconstruction
"""

from celery import Celery
import os

# Create Celery app
app = Celery('spatial_mapping')

# Redis configuration
redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379/0')

# Configure Celery
app.conf.update(
    broker_url=redis_url,
    result_backend=redis_url,
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    include=['spatial_mapping.tasks']
)

@app.task
def test_task():
    """Test task to verify Celery is working"""
    return "Celery is working!"

@app.task(bind=True)
def reconstruction_task(self, job_id: str, config: dict = None):
    """3D reconstruction task with full COLMAP pipeline"""
    from .tasks import reconstruction_task as detailed_reconstruction_task
    
    # Delegate to the detailed implementation in tasks.py
    return detailed_reconstruction_task.apply_async(
        args=[job_id], 
        kwargs={'config': config}
    ).get()

if __name__ == '__main__':
    app.start()