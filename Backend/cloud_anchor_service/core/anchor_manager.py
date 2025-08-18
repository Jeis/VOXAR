"""
Anchor Manager - Core anchor lifecycle management
Handles creation, tracking, and persistence of spatial anchors
"""

import logging
import asyncio
import uuid
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
import numpy as np
from dataclasses import dataclass, asdict
import json

logger = logging.getLogger(__name__)

@dataclass
class SpatialAnchor:
    """Spatial anchor data structure"""
    id: str
    session_id: str
    user_id: str
    position: List[float]  # [x, y, z]
    rotation: List[float]  # [x, y, z, w] quaternion
    confidence: float
    tracking_state: str  # tracking, paused, stopped
    anchor_type: str  # persistent, temporary, shared
    metadata: Dict[str, Any]
    created_at: datetime
    updated_at: datetime
    expires_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        data = asdict(self)
        # Convert datetime objects to ISO strings
        data['created_at'] = self.created_at.isoformat()
        data['updated_at'] = self.updated_at.isoformat()
        if self.expires_at:
            data['expires_at'] = self.expires_at.isoformat()
        return data

@dataclass
class AnchorQuery:
    """Spatial anchor query parameters"""
    position: Optional[List[float]] = None
    radius: Optional[float] = None
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    anchor_type: Optional[str] = None
    min_confidence: Optional[float] = None
    tracking_state: Optional[str] = None
    limit: Optional[int] = None

class AnchorManager:
    """
    Core anchor management system
    Handles anchor lifecycle, spatial queries, and persistence
    """
    
    def __init__(self, persistence_engine):
        self.persistence_engine = persistence_engine
        
        # In-memory anchor cache for active anchors
        self.active_anchors: Dict[str, SpatialAnchor] = {}
        self.session_anchors: Dict[str, List[str]] = {}  # session_id -> anchor_ids
        
        # Configuration
        self.config = {
            'max_anchors_per_session': 100,
            'default_anchor_lifetime': timedelta(hours=24),
            'cleanup_interval': 300,  # 5 minutes
            'spatial_index_resolution': 1.0,  # 1 meter grid
            'min_confidence_threshold': 0.5,
            'max_tracking_distance': 100.0  # 100 meters
        }
        
        # Performance tracking
        self.stats = {
            'total_anchors_created': 0,
            'total_anchors_deleted': 0,
            'active_anchors_count': 0,
            'active_sessions_count': 0,
            'successful_queries': 0,
            'failed_queries': 0,
            'average_query_time': 0.0
        }
        
        # Cleanup task
        self.cleanup_task = None
        self.is_initialized = False

    async def initialize(self) -> None:
        """Initialize anchor manager"""
        try:
            logger.info("Initializing Anchor Manager...")
            
            # Load active anchors from persistence
            await self._load_active_anchors()
            
            # Start cleanup task
            self.cleanup_task = asyncio.create_task(self._cleanup_loop())
            
            self.is_initialized = True
            logger.info("✅ Anchor Manager initialized successfully")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize Anchor Manager: {e}")
            raise

    async def create_anchor(self, session_id: str, user_id: str, 
                           position: List[float], rotation: List[float],
                           anchor_type: str = "persistent",
                           metadata: Optional[Dict[str, Any]] = None,
                           lifetime: Optional[timedelta] = None) -> SpatialAnchor:
        """
        Create a new spatial anchor
        
        Args:
            session_id: AR session identifier
            user_id: User identifier
            position: 3D position [x, y, z]
            rotation: Quaternion rotation [x, y, z, w]
            anchor_type: Type of anchor (persistent, temporary, shared)
            metadata: Additional anchor metadata
            lifetime: Optional custom lifetime
            
        Returns:
            Created SpatialAnchor
        """
        try:
            # Validate session anchor limit
            if session_id in self.session_anchors:
                if len(self.session_anchors[session_id]) >= self.config['max_anchors_per_session']:
                    raise ValueError(f"Session {session_id} has reached maximum anchor limit")
            
            # Generate unique anchor ID
            anchor_id = str(uuid.uuid4())
            
            # Calculate expiration
            expires_at = None
            if anchor_type == "temporary" or lifetime:
                expires_at = datetime.utcnow() + (lifetime or self.config['default_anchor_lifetime'])
            
            # Create anchor
            anchor = SpatialAnchor(
                id=anchor_id,
                session_id=session_id,
                user_id=user_id,
                position=position,
                rotation=rotation,
                confidence=1.0,  # Initial confidence
                tracking_state="tracking",
                anchor_type=anchor_type,
                metadata=metadata or {},
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                expires_at=expires_at
            )
            
            # Store in memory cache
            self.active_anchors[anchor_id] = anchor
            
            # Update session tracking
            if session_id not in self.session_anchors:
                self.session_anchors[session_id] = []
            self.session_anchors[session_id].append(anchor_id)
            
            # Persist to storage
            await self.persistence_engine.store_anchor(anchor)
            
            # Update statistics
            self.stats['total_anchors_created'] += 1
            self.stats['active_anchors_count'] = len(self.active_anchors)
            self.stats['active_sessions_count'] = len(self.session_anchors)
            
            logger.info(f"Created anchor {anchor_id} for session {session_id}")
            
            return anchor
            
        except Exception as e:
            logger.error(f"Failed to create anchor: {e}")
            raise

    async def update_anchor(self, anchor_id: str, 
                           position: Optional[List[float]] = None,
                           rotation: Optional[List[float]] = None,
                           confidence: Optional[float] = None,
                           tracking_state: Optional[str] = None,
                           metadata: Optional[Dict[str, Any]] = None) -> Optional[SpatialAnchor]:
        """Update an existing anchor"""
        try:
            anchor = self.active_anchors.get(anchor_id)
            if not anchor:
                # Try to load from persistence
                anchor = await self.persistence_engine.load_anchor(anchor_id)
                if not anchor:
                    return None
                self.active_anchors[anchor_id] = anchor
            
            # Update fields
            if position is not None:
                anchor.position = position
            if rotation is not None:
                anchor.rotation = rotation
            if confidence is not None:
                anchor.confidence = confidence
            if tracking_state is not None:
                anchor.tracking_state = tracking_state
            if metadata is not None:
                anchor.metadata.update(metadata)
            
            anchor.updated_at = datetime.utcnow()
            
            # Persist changes
            await self.persistence_engine.store_anchor(anchor)
            
            logger.debug(f"Updated anchor {anchor_id}")
            
            return anchor
            
        except Exception as e:
            logger.error(f"Failed to update anchor {anchor_id}: {e}")
            return None

    async def delete_anchor(self, anchor_id: str) -> bool:
        """Delete an anchor"""
        try:
            # Remove from memory
            anchor = self.active_anchors.pop(anchor_id, None)
            
            if anchor:
                # Remove from session tracking
                if anchor.session_id in self.session_anchors:
                    try:
                        self.session_anchors[anchor.session_id].remove(anchor_id)
                        if not self.session_anchors[anchor.session_id]:
                            del self.session_anchors[anchor.session_id]
                    except ValueError:
                        pass
            
            # Remove from persistence
            await self.persistence_engine.delete_anchor(anchor_id)
            
            # Update statistics
            self.stats['total_anchors_deleted'] += 1
            self.stats['active_anchors_count'] = len(self.active_anchors)
            self.stats['active_sessions_count'] = len(self.session_anchors)
            
            logger.info(f"Deleted anchor {anchor_id}")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete anchor {anchor_id}: {e}")
            return False

    async def get_anchor(self, anchor_id: str) -> Optional[SpatialAnchor]:
        """Get anchor by ID"""
        try:
            # Check memory cache first
            anchor = self.active_anchors.get(anchor_id)
            if anchor:
                return anchor
            
            # Load from persistence
            anchor = await self.persistence_engine.load_anchor(anchor_id)
            if anchor:
                self.active_anchors[anchor_id] = anchor
            
            return anchor
            
        except Exception as e:
            logger.error(f"Failed to get anchor {anchor_id}: {e}")
            return None

    async def query_anchors(self, query: AnchorQuery) -> List[SpatialAnchor]:
        """Query anchors based on spatial and attribute criteria"""
        try:
            import time
            start_time = time.time()
            
            # Get base anchor set
            if query.session_id:
                # Session-specific query
                anchor_ids = self.session_anchors.get(query.session_id, [])
                anchors = [self.active_anchors[aid] for aid in anchor_ids if aid in self.active_anchors]
            else:
                # Global query
                anchors = list(self.active_anchors.values())
            
            # Apply filters
            filtered_anchors = []
            
            for anchor in anchors:
                # Check confidence threshold
                if query.min_confidence and anchor.confidence < query.min_confidence:
                    continue
                
                # Check anchor type
                if query.anchor_type and anchor.anchor_type != query.anchor_type:
                    continue
                
                # Check tracking state
                if query.tracking_state and anchor.tracking_state != query.tracking_state:
                    continue
                
                # Check user ID
                if query.user_id and anchor.user_id != query.user_id:
                    continue
                
                # Check spatial criteria
                if query.position and query.radius:
                    distance = self._calculate_distance(anchor.position, query.position)
                    if distance > query.radius:
                        continue
                
                filtered_anchors.append(anchor)
            
            # Sort by distance if position provided
            if query.position:
                filtered_anchors.sort(
                    key=lambda a: self._calculate_distance(a.position, query.position)
                )
            
            # Apply limit
            if query.limit:
                filtered_anchors = filtered_anchors[:query.limit]
            
            # Update statistics
            query_time = time.time() - start_time
            self.stats['successful_queries'] += 1
            self._update_average_query_time(query_time)
            
            logger.debug(f"Query returned {len(filtered_anchors)} anchors in {query_time:.3f}s")
            
            return filtered_anchors
            
        except Exception as e:
            logger.error(f"Anchor query failed: {e}")
            self.stats['failed_queries'] += 1
            return []

    async def get_session_anchors(self, session_id: str) -> List[SpatialAnchor]:
        """Get all anchors for a session"""
        query = AnchorQuery(session_id=session_id)
        return await self.query_anchors(query)

    async def get_nearby_anchors(self, position: List[float], radius: float,
                                max_results: int = 50) -> List[SpatialAnchor]:
        """Get anchors within radius of position"""
        query = AnchorQuery(
            position=position,
            radius=radius,
            limit=max_results,
            tracking_state="tracking"
        )
        return await self.query_anchors(query)

    def _calculate_distance(self, pos1: List[float], pos2: List[float]) -> float:
        """Calculate Euclidean distance between two positions"""
        if len(pos1) < 3 or len(pos2) < 3:
            return float('inf')
        
        dx = pos1[0] - pos2[0]
        dy = pos1[1] - pos2[1]
        dz = pos1[2] - pos2[2]
        
        return (dx*dx + dy*dy + dz*dz) ** 0.5

    def _update_average_query_time(self, query_time: float):
        """Update rolling average query time"""
        successful_queries = self.stats['successful_queries']
        current_avg = self.stats['average_query_time']
        
        self.stats['average_query_time'] = \
            (current_avg * (successful_queries - 1) + query_time) / successful_queries

    async def _load_active_anchors(self):
        """Load active anchors from persistence on startup"""
        try:
            # Load all non-expired anchors
            anchors = await self.persistence_engine.load_active_anchors()
            
            for anchor in anchors:
                self.active_anchors[anchor.id] = anchor
                
                # Update session tracking
                if anchor.session_id not in self.session_anchors:
                    self.session_anchors[anchor.session_id] = []
                self.session_anchors[anchor.session_id].append(anchor.id)
            
            logger.info(f"Loaded {len(anchors)} active anchors from persistence")
            
        except Exception as e:
            logger.error(f"Failed to load active anchors: {e}")

    async def _cleanup_loop(self):
        """Background task to cleanup expired anchors"""
        while True:
            try:
                await asyncio.sleep(self.config['cleanup_interval'])
                await self._cleanup_expired_anchors()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Cleanup loop error: {e}")

    async def _cleanup_expired_anchors(self):
        """Remove expired anchors"""
        try:
            current_time = datetime.utcnow()
            expired_anchor_ids = []
            
            for anchor_id, anchor in self.active_anchors.items():
                if anchor.expires_at and anchor.expires_at <= current_time:
                    expired_anchor_ids.append(anchor_id)
            
            for anchor_id in expired_anchor_ids:
                await self.delete_anchor(anchor_id)
            
            if expired_anchor_ids:
                logger.info(f"Cleaned up {len(expired_anchor_ids)} expired anchors")
                
        except Exception as e:
            logger.error(f"Anchor cleanup failed: {e}")

    async def get_metrics(self) -> Dict[str, Any]:
        """Get anchor management metrics"""
        return {
            'statistics': self.stats,
            'configuration': self.config,
            'active_state': {
                'active_anchors': len(self.active_anchors),
                'active_sessions': len(self.session_anchors),
                'is_initialized': self.is_initialized
            },
            'timestamp': datetime.utcnow().isoformat()
        }

    async def health_check(self) -> bool:
        """Check anchor manager health"""
        try:
            return self.is_initialized and self.persistence_engine is not None
        except Exception:
            return False

    async def shutdown(self):
        """Shutdown anchor manager"""
        try:
            # Cancel cleanup task
            if self.cleanup_task:
                self.cleanup_task.cancel()
                try:
                    await self.cleanup_task
                except asyncio.CancelledError:
                    pass
            
            # Final persist of active anchors
            for anchor in self.active_anchors.values():
                try:
                    await self.persistence_engine.store_anchor(anchor)
                except Exception as e:
                    logger.error(f"Failed to persist anchor {anchor.id} during shutdown: {e}")
            
            logger.info("Anchor Manager shutdown complete")
            
        except Exception as e:
            logger.error(f"Error during anchor manager shutdown: {e}")