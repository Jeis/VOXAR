"""
GPS utilities for spatial mapping
"""

import logging
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)


class GPSProcessor:
    """Process GPS data for mapping"""
    
    def __init__(self):
        logger.info("GPSProcessor initialized")
    
    def process_gps_data(self, gps_data: Dict[str, Any]) -> Optional[Tuple[float, float, float]]:
        """Process GPS data and return lat, lon, alt"""
        try:
            lat = float(gps_data.get('latitude', 0))
            lon = float(gps_data.get('longitude', 0))
            alt = float(gps_data.get('altitude', 0))
            return (lat, lon, alt)
        except (ValueError, TypeError) as e:
            logger.error(f"GPS processing failed: {e}")
            return None
    
    def validate_coordinates(self, lat: float, lon: float) -> bool:
        """Validate GPS coordinates"""
        return -90 <= lat <= 90 and -180 <= lon <= 180