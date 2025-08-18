"""
Map Data Models for spatial mapping
"""

from dataclasses import dataclass
from typing import Optional, Dict, Any
from datetime import datetime


@dataclass
class MapMetadata:
    """Metadata for map data"""
    map_id: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    version: str = "1.0"
    tags: Optional[Dict[str, Any]] = None


@dataclass 
class MapData:
    """Map data container"""
    metadata: MapMetadata
    data_path: str
    data_type: str = "point_cloud"
    size_bytes: int = 0
    processing_status: str = "pending"