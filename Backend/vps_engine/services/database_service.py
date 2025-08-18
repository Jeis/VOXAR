"""
Database Service for VPS Engine
PostgreSQL integration with spatial extensions
"""

import logging
import asyncio
from typing import Dict, List, Optional, Any, Tuple
import asyncpg
import json
from datetime import datetime
import numpy as np

from utils.config import settings

logger = logging.getLogger(__name__)

class DatabaseService:
    """PostgreSQL database service for VPS engine"""
    
    def __init__(self):
        self.pool = None
        self.is_initialized = False
        
    async def initialize(self) -> None:
        """Initialize database connection pool"""
        try:
            logger.info("Initializing database service...")
            
            # Create connection pool
            self.pool = await asyncpg.create_pool(
                settings.DATABASE_URL,
                **settings.get_database_config()
            )
            
            # Ensure VPS tables exist
            await self._ensure_tables()
            
            self.is_initialized = True
            logger.info("✅ Database service initialized")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize database service: {e}")
            raise

    async def _ensure_tables(self):
        """Create VPS-specific tables if they don't exist"""
        
        async with self.pool.acquire() as conn:
            # Create maps table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS vps_maps (
                    id VARCHAR(255) PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    description TEXT,
                    location POINT,  -- GPS coordinates
                    quality_score FLOAT DEFAULT 0.0,
                    feature_count INTEGER DEFAULT 0,
                    point_count INTEGER DEFAULT 0,
                    status VARCHAR(50) DEFAULT 'processing',
                    metadata JSONB DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create map features table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS vps_map_features (
                    id SERIAL PRIMARY KEY,
                    map_id VARCHAR(255) REFERENCES vps_maps(id) ON DELETE CASCADE,
                    feature_id INTEGER NOT NULL,
                    position POINT,  -- 3D position (x, y, z stored as POINT for now)
                    descriptor BYTEA,  -- Feature descriptor
                    strength FLOAT DEFAULT 0.0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(map_id, feature_id)
                )
            """)
            
            # Create localization history table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS vps_localization_history (
                    id SERIAL PRIMARY KEY,
                    map_id VARCHAR(255) REFERENCES vps_maps(id),
                    confidence FLOAT NOT NULL,
                    error_estimate FLOAT NOT NULL,
                    processing_time FLOAT NOT NULL,
                    feature_matches INTEGER NOT NULL,
                    success BOOLEAN NOT NULL,
                    pose_matrix JSONB,  -- 4x4 transformation matrix
                    metadata JSONB DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create spatial index for location-based queries
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_vps_maps_location 
                ON vps_maps USING GIST(location)
            """)
            
            # Create index for map features
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_vps_map_features_map_id 
                ON vps_map_features(map_id)
            """)
            
            logger.info("✅ VPS tables ensured")

    async def store_map_metadata(self, map_id: str, map_data: Dict[str, Any]) -> bool:
        """Store map metadata in database"""
        try:
            async with self.pool.acquire() as conn:
                location_point = None
                if map_data.get('location'):
                    lat, lng = map_data['location']
                    location_point = f"({lng}, {lat})"  # PostGIS uses (lng, lat)
                
                await conn.execute("""
                    INSERT INTO vps_maps 
                    (id, name, description, location, quality_score, feature_count, point_count, status, metadata)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                    ON CONFLICT (id) DO UPDATE SET
                        name = EXCLUDED.name,
                        description = EXCLUDED.description,
                        location = EXCLUDED.location,
                        quality_score = EXCLUDED.quality_score,
                        feature_count = EXCLUDED.feature_count,
                        point_count = EXCLUDED.point_count,
                        status = EXCLUDED.status,
                        metadata = EXCLUDED.metadata,
                        updated_at = CURRENT_TIMESTAMP
                """, 
                    map_id,
                    map_data.get('name', ''),
                    map_data.get('description', ''),
                    location_point,
                    map_data.get('quality_score', 0.0),
                    map_data.get('feature_count', 0),
                    map_data.get('point_count', 0),
                    map_data.get('status', 'processing'),
                    json.dumps(map_data.get('metadata', {}))
                )
                
            logger.info(f"Stored map metadata: {map_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to store map metadata: {e}")
            return False

    async def get_map_data(self, map_id: str) -> Optional[Dict[str, Any]]:
        """Get map data by ID"""
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow("""
                    SELECT id, name, description, location, quality_score, 
                           feature_count, point_count, status, metadata, 
                           created_at, updated_at
                    FROM vps_maps 
                    WHERE id = $1
                """, map_id)
                
                if not row:
                    return None
                
                map_data = dict(row)
                
                # Convert location to tuple if present
                if map_data['location']:
                    # Parse PostGIS point format
                    location_str = map_data['location']
                    # Simple parsing - in production, use proper PostGIS functions
                    if '(' in location_str:
                        coords = location_str.strip('()').split(',')
                        if len(coords) == 2:
                            lng, lat = float(coords[0]), float(coords[1])
                            map_data['location'] = (lat, lng)
                
                # Parse metadata JSON
                if map_data['metadata']:
                    map_data['metadata'] = json.loads(map_data['metadata'])
                
                return map_data
                
        except Exception as e:
            logger.error(f"Failed to get map data: {e}")
            return None

    async def get_all_maps(self) -> List[Dict[str, Any]]:
        """Get all available maps"""
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT id, name, description, location, quality_score, 
                           feature_count, point_count, status, created_at
                    FROM vps_maps 
                    WHERE status IN ('ready', 'processing')
                    ORDER BY quality_score DESC, created_at DESC
                """)
                
                maps = []
                for row in rows:
                    map_data = dict(row)
                    
                    # Convert location
                    if map_data['location']:
                        location_str = map_data['location']
                        if '(' in location_str:
                            coords = location_str.strip('()').split(',')
                            if len(coords) == 2:
                                lng, lat = float(coords[0]), float(coords[1])
                                map_data['location'] = (lat, lng)
                    
                    maps.append(map_data)
                
                return maps
                
        except Exception as e:
            logger.error(f"Failed to get all maps: {e}")
            return []

    async def find_maps_by_location(self, lat: float, lng: float, radius_meters: float) -> List[Dict[str, Any]]:
        """Find maps within radius of given location"""
        try:
            async with self.pool.acquire() as conn:
                # Use PostGIS distance function
                rows = await conn.fetch("""
                    SELECT id, name, description, location, quality_score, 
                           feature_count, point_count, status,
                           ST_Distance(
                               ST_GeogFromText('POINT(' || $2 || ' ' || $1 || ')'),
                               ST_GeogFromText('POINT(' || ST_X(location) || ' ' || ST_Y(location) || ')')
                           ) as distance
                    FROM vps_maps 
                    WHERE location IS NOT NULL 
                      AND status IN ('ready', 'processing')
                      AND ST_DWithin(
                          ST_GeogFromText('POINT(' || $2 || ' ' || $1 || ')'),
                          ST_GeogFromText('POINT(' || ST_X(location) || ' ' || ST_Y(location) || ')'),
                          $3
                      )
                    ORDER BY distance ASC, quality_score DESC
                """, lat, lng, radius_meters)
                
                maps = []
                for row in rows:
                    map_data = dict(row)
                    
                    # Convert location
                    if map_data['location']:
                        location_str = map_data['location']
                        if '(' in location_str:
                            coords = location_str.strip('()').split(',')
                            if len(coords) == 2:
                                lng_val, lat_val = float(coords[0]), float(coords[1])
                                map_data['location'] = (lat_val, lng_val)
                    
                    maps.append(map_data)
                
                return maps
                
        except Exception as e:
            logger.error(f"Failed to find maps by location: {e}")
            # Fallback to all maps
            return await self.get_all_maps()

    async def store_map_features(self, map_id: str, features: List[Dict[str, Any]]) -> bool:
        """Store map features in database"""
        try:
            async with self.pool.acquire() as conn:
                # Delete existing features for this map
                await conn.execute("DELETE FROM vps_map_features WHERE map_id = $1", map_id)
                
                # Insert new features
                for i, feature in enumerate(features):
                    position_point = None
                    if 'position' in feature and len(feature['position']) >= 3:
                        x, y, z = feature['position'][:3]
                        position_point = f"({x}, {y})"  # Store x,y as POINT, z in metadata
                    
                    descriptor_bytes = None
                    if 'descriptor' in feature:
                        descriptor_bytes = feature['descriptor'].tobytes()
                    
                    await conn.execute("""
                        INSERT INTO vps_map_features 
                        (map_id, feature_id, position, descriptor, strength)
                        VALUES ($1, $2, $3, $4, $5)
                    """, 
                        map_id,
                        i,
                        position_point,
                        descriptor_bytes,
                        feature.get('strength', 0.0)
                    )
                
                # Update feature count in maps table
                await conn.execute("""
                    UPDATE vps_maps 
                    SET feature_count = $1, updated_at = CURRENT_TIMESTAMP 
                    WHERE id = $2
                """, len(features), map_id)
                
            logger.info(f"Stored {len(features)} features for map {map_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to store map features: {e}")
            return False

    async def get_map_features(self, map_id: str) -> List[Dict[str, Any]]:
        """Get features for a specific map"""
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT feature_id, position, descriptor, strength
                    FROM vps_map_features 
                    WHERE map_id = $1
                    ORDER BY feature_id
                """, map_id)
                
                features = []
                for row in rows:
                    feature = {
                        'feature_id': row['feature_id'],
                        'strength': row['strength']
                    }
                    
                    # Parse position
                    if row['position']:
                        position_str = row['position']
                        if '(' in position_str:
                            coords = position_str.strip('()').split(',')
                            if len(coords) == 2:
                                x, y = float(coords[0]), float(coords[1])
                                feature['position'] = [x, y, 0.0]  # Z=0 for now
                    
                    # Parse descriptor
                    if row['descriptor']:
                        descriptor = np.frombuffer(row['descriptor'], dtype=np.uint8)
                        feature['descriptor'] = descriptor
                    
                    features.append(feature)
                
                return features
                
        except Exception as e:
            logger.error(f"Failed to get map features: {e}")
            return []

    async def record_localization(self, map_id: str, result_data: Dict[str, Any]) -> bool:
        """Record localization attempt in history"""
        try:
            async with self.pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO vps_localization_history
                    (map_id, confidence, error_estimate, processing_time, 
                     feature_matches, success, pose_matrix, metadata)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """,
                    map_id,
                    result_data.get('confidence', 0.0),
                    result_data.get('error_estimate', 0.0),
                    result_data.get('processing_time', 0.0),
                    result_data.get('feature_matches', 0),
                    result_data.get('success', False),
                    json.dumps(result_data.get('pose_matrix', [])),
                    json.dumps(result_data.get('metadata', {}))
                )
                
            return True
            
        except Exception as e:
            logger.error(f"Failed to record localization: {e}")
            return False

    async def get_map_info(self, map_id: str) -> Optional[Dict[str, Any]]:
        """Get comprehensive map information"""
        map_data = await self.get_map_data(map_id)
        if not map_data:
            return None
        
        try:
            async with self.pool.acquire() as conn:
                # Get localization statistics
                stats = await conn.fetchrow("""
                    SELECT 
                        COUNT(*) as total_localizations,
                        COUNT(*) FILTER (WHERE success = true) as successful_localizations,
                        AVG(confidence) FILTER (WHERE success = true) as avg_confidence,
                        AVG(error_estimate) FILTER (WHERE success = true) as avg_error,
                        AVG(processing_time) as avg_processing_time
                    FROM vps_localization_history 
                    WHERE map_id = $1
                """, map_id)
                
                if stats:
                    map_data['statistics'] = dict(stats)
                
                return map_data
                
        except Exception as e:
            logger.error(f"Failed to get map info: {e}")
            return map_data

    async def delete_map(self, map_id: str) -> bool:
        """Delete map and all associated data"""
        try:
            async with self.pool.acquire() as conn:
                # Delete map (cascades to features and history)
                result = await conn.execute("DELETE FROM vps_maps WHERE id = $1", map_id)
                
                # Check if any rows were deleted
                deleted_count = int(result.split()[-1])
                return deleted_count > 0
                
        except Exception as e:
            logger.error(f"Failed to delete map: {e}")
            return False

    async def get_available_maps(self) -> List[Dict[str, Any]]:
        """Get list of available maps for localization"""
        return await self.get_all_maps()

    async def health_check(self) -> bool:
        """Check database connection health"""
        try:
            if not self.pool:
                return False
                
            async with self.pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
                return True
                
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return False

    async def shutdown(self):
        """Close database connections"""
        try:
            if self.pool:
                await self.pool.close()
                logger.info("Database service shutdown complete")
        except Exception as e:
            logger.error(f"Error during database shutdown: {e}")