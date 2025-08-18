"""
Validation utilities for spatial mapping
"""

import logging
from pathlib import Path
from typing import Optional
from PIL import Image

logger = logging.getLogger(__name__)


class ImageValidator:
    """Validate images for mapping pipeline"""
    
    def __init__(self, min_resolution: int = 640):
        self.min_resolution = min_resolution
    
    def validate_image(self, image_path: str) -> bool:
        """Validate an image file"""
        try:
            path = Path(image_path)
            if not path.exists():
                return False
            
            with Image.open(path) as img:
                width, height = img.size
                if min(width, height) < self.min_resolution:
                    logger.warning(f"Image {path} below minimum resolution: {width}x{height}")
                    return False
                    
            return True
        except Exception as e:
            logger.error(f"Image validation failed for {image_path}: {e}")
            return False