"""
Persistence Engine - Database persistence for spatial anchors
PostgreSQL with PostGIS spatial extensions for anchor storage
"""

import logging
import asyncio
from typing import Dict, List, Optional, Any
import asyncpg
import json
from datetime import datetime, timedelta
import numpy as np

from .anchor_manager import SpatialAnchor
from utils.config import settings

logger = logging.getLogger(__name__)

class PersistenceEngine:
    """
    Database persistence engine for spatial anchors
    Handles anchor storage, retrieval, and spatial queries
    """
    
    def __init__(self):
        self.pool = None
        self.is_initialized = False
        
    async def initialize(self) -> None:
        """Initialize database connection and ensure tables"""
        try:
            logger.info("Initializing Persistence Engine...")
            
            # Create connection pool
            self.pool = await asyncpg.create_pool(
                settings.DATABASE_URL,
                **settings.get_database_config()
            )
            
            # Ensure anchor tables exist
            await self._ensure_tables()
            
            self.is_initialized = True
            logger.info("✅ Persistence Engine initialized")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize Persistence Engine: {e}")
            raise

    async def _ensure_tables(self):
        """Create anchor tables if they don't exist"""
        
        async with self.pool.acquire() as conn:
            # Enable PostGIS extension
            await conn.execute("CREATE EXTENSION IF NOT EXISTS postgis")
            
            # Create anchors table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS spatial_anchors (
                    id VARCHAR(255) PRIMARY KEY,
                    session_id VARCHAR(255) NOT NULL,
                    user_id VARCHAR(255) NOT NULL,
                    position GEOMETRY(POINT, 4326),  -- 3D position with spatial indexing
                    rotation_x FLOAT NOT NULL,
                    rotation_y FLOAT NOT NULL,
                    rotation_z FLOAT NOT NULL,
                    rotation_w FLOAT NOT NULL,
                    confidence FLOAT DEFAULT 1.0,
                    tracking_state VARCHAR(50) DEFAULT 'tracking',
                    anchor_type VARCHAR(50) DEFAULT 'persistent',
                    metadata JSONB DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP
                )
            """)
            
            # Create anchor sharing table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS anchor_sharing (
                    id SERIAL PRIMARY KEY,
                    anchor_id VARCHAR(255) REFERENCES spatial_anchors(id) ON DELETE CASCADE,
                    shared_with_user VARCHAR(255) NOT NULL,
                    shared_by_user VARCHAR(255) NOT NULL,
                    permission_level VARCHAR(50) DEFAULT 'read',  -- read, write, admin
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP,
                    UNIQUE(anchor_id, shared_with_user)
                )
            """)
            
            # Create anchor history table for tracking changes
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS anchor_history (
                    id SERIAL PRIMARY KEY,
                    anchor_id VARCHAR(255) NOT NULL,
                    action VARCHAR(50) NOT NULL,  -- created, updated, deleted, shared
                    user_id VARCHAR(255) NOT NULL,
                    position_before GEOMETRY(POINT, 4326),
                    position_after GEOMETRY(POINT, 4326),
                    metadata_changes JSONB DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create spatial indexes
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_spatial_anchors_position 
                ON spatial_anchors USING GIST(position)
            """)
            
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_spatial_anchors_session 
                ON spatial_anchors(session_id)
            """)
            
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_spatial_anchors_user 
                ON spatial_anchors(user_id)
            """)
            
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_spatial_anchors_type 
                ON spatial_anchors(anchor_type)
            """)
            
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_spatial_anchors_expires 
                ON spatial_anchors(expires_at) WHERE expires_at IS NOT NULL
            """)
            
            logger.info("✅ Anchor tables ensured")

    async def store_anchor(self, anchor: SpatialAnchor) -> bool:
        """Store or update an anchor in the database"""
        try:
            async with self.pool.acquire() as conn:
                # Convert position to PostGIS point (assuming position is [x, y, z])
                if len(anchor.position) >= 3:
                    # For simplicity, we'll store x,y as 2D point and z in metadata
                    point_wkt = f"POINT({anchor.position[0]} {anchor.position[1]})"
                    anchor.metadata['z_coordinate'] = anchor.position[2]
                else:
                    point_wkt = f"POINT({anchor.position[0]} {anchor.position[1]})"
                
                await conn.execute("""
                    INSERT INTO spatial_anchors 
                    (id, session_id, user_id, position, rotation_x, rotation_y, rotation_z, rotation_w,
                     confidence, tracking_state, anchor_type, metadata, created_at, updated_at, expires_at)
                    VALUES ($1, $2, $3, ST_GeomFromText($4, 4326), $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
                    ON CONFLICT (id) DO UPDATE SET
                        position = ST_GeomFromText($4, 4326),
                        rotation_x = $5, rotation_y = $6, rotation_z = $7, rotation_w = $8,
                        confidence = $9, tracking_state = $10, metadata = $12, updated_at = $14
                """, 
                    anchor.id,
                    anchor.session_id,
                    anchor.user_id,
                    point_wkt,
                    anchor.rotation[0],
                    anchor.rotation[1],
                    anchor.rotation[2],
                    anchor.rotation[3],
                    anchor.confidence,
                    anchor.tracking_state,
                    anchor.anchor_type,
                    json.dumps(anchor.metadata),
                    anchor.created_at,
                    anchor.updated_at,
                    anchor.expires_at
                )
                
            logger.debug(f"Stored anchor {anchor.id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to store anchor: {e}")
            return False

    async def load_anchor(self, anchor_id: str) -> Optional[SpatialAnchor]:
        """Load an anchor by ID"""
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow("""
                    SELECT id, session_id, user_id, 
                           ST_X(position) as x, ST_Y(position) as y,
                           rotation_x, rotation_y, rotation_z, rotation_w,
                           confidence, tracking_state, anchor_type, metadata,
                           created_at, updated_at, expires_at
                    FROM spatial_anchors 
                    WHERE id = $1
                """, anchor_id)
                
                if not row:
                    return None
                
                return self._row_to_anchor(row)
                
        except Exception as e:
            logger.error(f"Failed to load anchor {anchor_id}: {e}")
            return None

    async def load_active_anchors(self) -> List[SpatialAnchor]:
        """Load all non-expired anchors"""
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT id, session_id, user_id, 
                           ST_X(position) as x, ST_Y(position) as y,
                           rotation_x, rotation_y, rotation_z, rotation_w,
                           confidence, tracking_state, anchor_type, metadata,
                           created_at, updated_at, expires_at
                    FROM spatial_anchors 
                    WHERE expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP
                    ORDER BY created_at DESC
                """)
                
                return [self._row_to_anchor(row) for row in rows]
                
        except Exception as e:
            logger.error(f"Failed to load active anchors: {e}")
            return []

    async def load_session_anchors(self, session_id: str) -> List[SpatialAnchor]:
        """Load anchors for a specific session"""
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT id, session_id, user_id, 
                           ST_X(position) as x, ST_Y(position) as y,
                           rotation_x, rotation_y, rotation_z, rotation_w,
                           confidence, tracking_state, anchor_type, metadata,
                           created_at, updated_at, expires_at
                    FROM spatial_anchors 
                    WHERE session_id = $1 
                      AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)
                    ORDER BY created_at DESC
                """, session_id)
                
                return [self._row_to_anchor(row) for row in rows]
                
        except Exception as e:
            logger.error(f"Failed to load session anchors: {e}")
            return []

    async def find_nearby_anchors(self, position: List[float], radius_meters: float,
                                 limit: int = 50) -> List[SpatialAnchor]:
        """Find anchors within radius of position"""
        try:
            if len(position) < 2:
                return []
            
            async with self.pool.acquire() as conn:
                point_wkt = f"POINT({position[0]} {position[1]})"
                
                rows = await conn.fetch("""
                    SELECT id, session_id, user_id, 
                           ST_X(position) as x, ST_Y(position) as y,
                           rotation_x, rotation_y, rotation_z, rotation_w,
                           confidence, tracking_state, anchor_type, metadata,
                           created_at, updated_at, expires_at,
                           ST_Distance(position, ST_GeomFromText($1, 4326)) as distance
                    FROM spatial_anchors 
                    WHERE ST_DWithin(position, ST_GeomFromText($1, 4326), $2)
                      AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)
                      AND tracking_state = 'tracking'
                    ORDER BY distance ASC
                    LIMIT $3
                """, point_wkt, radius_meters, limit)
                
                return [self._row_to_anchor(row) for row in rows]
                
        except Exception as e:
            logger.error(f"Failed to find nearby anchors: {e}")
            return []

    async def delete_anchor(self, anchor_id: str) -> bool:
        """Delete an anchor"""
        try:
            async with self.pool.acquire() as conn:
                # Record deletion in history
                await conn.execute("""
                    INSERT INTO anchor_history (anchor_id, action, user_id)
                    SELECT id, 'deleted', user_id FROM spatial_anchors WHERE id = $1
                """, anchor_id)
                
                # Delete the anchor
                result = await conn.execute("DELETE FROM spatial_anchors WHERE id = $1", anchor_id)
                
                # Check if any rows were deleted
                deleted_count = int(result.split()[-1])
                return deleted_count > 0
                
        except Exception as e:
            logger.error(f"Failed to delete anchor: {e}")
            return False

    async def share_anchor(self, anchor_id: str, shared_with_user: str, 
                          shared_by_user: str, permission_level: str = "read",
                          expires_at: Optional[datetime] = None) -> bool:
        """Share an anchor with another user"""
        try:
            async with self.pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO anchor_sharing 
                    (anchor_id, shared_with_user, shared_by_user, permission_level, expires_at)
                    VALUES ($1, $2, $3, $4, $5)
                    ON CONFLICT (anchor_id, shared_with_user) DO UPDATE SET
                        permission_level = EXCLUDED.permission_level,
                        expires_at = EXCLUDED.expires_at
                """, anchor_id, shared_with_user, shared_by_user, permission_level, expires_at)
                
                # Record sharing in history
                await conn.execute("""
                    INSERT INTO anchor_history (anchor_id, action, user_id, metadata_changes)
                    VALUES ($1, 'shared', $2, $3)
                """, anchor_id, shared_by_user, json.dumps({
                    'shared_with': shared_with_user,
                    'permission': permission_level
                }))
                
            logger.info(f"Shared anchor {anchor_id} with user {shared_with_user}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to share anchor: {e}")
            return False

    async def get_shared_anchors(self, user_id: str) -> List[SpatialAnchor]:
        """Get anchors shared with a user"""
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT a.id, a.session_id, a.user_id, 
                           ST_X(a.position) as x, ST_Y(a.position) as y,
                           a.rotation_x, a.rotation_y, a.rotation_z, a.rotation_w,
                           a.confidence, a.tracking_state, a.anchor_type, a.metadata,
                           a.created_at, a.updated_at, a.expires_at,
                           s.permission_level
                    FROM spatial_anchors a
                    JOIN anchor_sharing s ON a.id = s.anchor_id
                    WHERE s.shared_with_user = $1 
                      AND (a.expires_at IS NULL OR a.expires_at > CURRENT_TIMESTAMP)
                      AND (s.expires_at IS NULL OR s.expires_at > CURRENT_TIMESTAMP)
                    ORDER BY a.created_at DESC
                """, user_id)
                
                anchors = []
                for row in rows:
                    anchor = self._row_to_anchor(row)
                    # Add sharing metadata
                    anchor.metadata['shared_permission'] = row['permission_level']
                    anchors.append(anchor)
                
                return anchors
                
        except Exception as e:
            logger.error(f"Failed to get shared anchors: {e}")
            return []

    async def cleanup_expired_anchors(self) -> int:
        """Remove expired anchors and return count"""
        try:
            async with self.pool.acquire() as conn:
                # Record expired anchors in history before deletion
                await conn.execute("""
                    INSERT INTO anchor_history (anchor_id, action, user_id)
                    SELECT id, 'expired', user_id FROM spatial_anchors 
                    WHERE expires_at IS NOT NULL AND expires_at <= CURRENT_TIMESTAMP
                """)
                
                # Delete expired anchors
                result = await conn.execute("""
                    DELETE FROM spatial_anchors 
                    WHERE expires_at IS NOT NULL AND expires_at <= CURRENT_TIMESTAMP
                """)
                
                # Also clean up expired sharing permissions
                await conn.execute("""
                    DELETE FROM anchor_sharing 
                    WHERE expires_at IS NOT NULL AND expires_at <= CURRENT_TIMESTAMP
                """)
                
                deleted_count = int(result.split()[-1])
                if deleted_count > 0:
                    logger.info(f"Cleaned up {deleted_count} expired anchors")
                
                return deleted_count
                
        except Exception as e:
            logger.error(f"Failed to cleanup expired anchors: {e}")
            return 0

    def _row_to_anchor(self, row) -> SpatialAnchor:
        """Convert database row to SpatialAnchor object"""
        
        # Reconstruct position from x, y and metadata z
        position = [float(row['x']), float(row['y'])]
        metadata = json.loads(row['metadata']) if row['metadata'] else {}
        
        if 'z_coordinate' in metadata:
            position.append(float(metadata['z_coordinate']))
        else:
            position.append(0.0)  # Default z
        
        rotation = [
            float(row['rotation_x']),
            float(row['rotation_y']), 
            float(row['rotation_z']),
            float(row['rotation_w'])
        ]
        
        return SpatialAnchor(
            id=row['id'],
            session_id=row['session_id'],
            user_id=row['user_id'],
            position=position,
            rotation=rotation,
            confidence=float(row['confidence']),
            tracking_state=row['tracking_state'],
            anchor_type=row['anchor_type'],
            metadata=metadata,
            created_at=row['created_at'],
            updated_at=row['updated_at'],
            expires_at=row['expires_at']
        )

    async def get_statistics(self) -> Dict[str, Any]:
        """Get database statistics"""
        try:
            async with self.pool.acquire() as conn:
                stats = await conn.fetchrow("""
                    SELECT 
                        COUNT(*) as total_anchors,
                        COUNT(*) FILTER (WHERE expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP) as active_anchors,
                        COUNT(*) FILTER (WHERE anchor_type = 'persistent') as persistent_anchors,
                        COUNT(*) FILTER (WHERE anchor_type = 'temporary') as temporary_anchors,
                        COUNT(*) FILTER (WHERE anchor_type = 'shared') as shared_anchors,
                        COUNT(DISTINCT session_id) as unique_sessions,
                        COUNT(DISTINCT user_id) as unique_users
                    FROM spatial_anchors
                """)
                
                sharing_stats = await conn.fetchrow("""
                    SELECT COUNT(*) as total_shares,
                           COUNT(DISTINCT shared_with_user) as users_with_shared_anchors
                    FROM anchor_sharing
                    WHERE expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP
                """)
                
                return {
                    'anchor_statistics': dict(stats),
                    'sharing_statistics': dict(sharing_stats),
                    'timestamp': datetime.utcnow().isoformat()
                }
                
        except Exception as e:
            logger.error(f"Failed to get statistics: {e}")
            return {}

    async def get_metrics(self) -> Dict[str, Any]:
        """Get persistence metrics"""
        try:
            stats = await self.get_statistics()
            return {
                'database_statistics': stats,
                'pool_status': {
                    'size': self.pool.get_size() if self.pool else 0,
                    'max_size': self.pool.get_max_size() if self.pool else 0,
                    'min_size': self.pool.get_min_size() if self.pool else 0
                },
                'is_initialized': self.is_initialized
            }
        except Exception as e:
            logger.error(f"Failed to get persistence metrics: {e}")
            return {}

    async def health_check(self) -> bool:
        """Check database health"""
        try:
            if not self.pool:
                return False
                
            async with self.pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
                return True
                
        except Exception as e:
            logger.error(f"Persistence health check failed: {e}")
            return False

    async def shutdown(self):
        """Close database connections"""
        try:
            if self.pool:
                await self.pool.close()
                logger.info("Persistence Engine shutdown complete")
        except Exception as e:
            logger.error(f"Error during persistence shutdown: {e}")