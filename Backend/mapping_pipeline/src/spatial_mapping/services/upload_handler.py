"""
Upload Handler for spatial mapping data
"""

import logging
from typing import List, Dict, Any
from pathlib import Path

logger = logging.getLogger(__name__)


class UploadHandler:
    """Handle file uploads for mapping pipeline"""
    
    def __init__(self, upload_dir: str = "/tmp/uploads"):
        self.upload_dir = Path(upload_dir)
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"UploadHandler initialized with directory: {self.upload_dir}")
    
    def handle_upload(self, files: List[str]) -> Dict[str, Any]:
        """Process uploaded files"""
        logger.info(f"Processing {len(files)} uploaded files")
        return {
            "status": "success",
            "files_processed": len(files),
            "upload_id": "temp_upload"
        }