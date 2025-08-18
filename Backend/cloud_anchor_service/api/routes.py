"""
Cloud Anchor Service API Routes
RESTful API and WebSocket endpoints for spatial anchor management
"""

import logging
import asyncio
import uuid
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import json

from fastapi import APIRouter, HTTPException, Depends, WebSocket, WebSocketDisconnect, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, validator

from core.anchor_manager import SpatialAnchor, AnchorQuery, AnchorManager
from core.persistence_engine import PersistenceEngine
from core.synchronization_manager import SynchronizationManager
from utils.auth import verify_api_key
from utils.config import settings

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(tags=["Cloud Anchors"])

# Pydantic models
class CreateAnchorRequest(BaseModel):
    """Request model for creating an anchor"""
    session_id: str = Field(..., description="AR session identifier")
    user_id: str = Field(..., description="User identifier")
    position: List[float] = Field(..., description="3D position [x, y, z]")
    rotation: List[float] = Field(..., description="Quaternion rotation [x, y, z, w]")
    anchor_type: str = Field(default="persistent", description="Anchor type (persistent, temporary, shared)")
    metadata: Optional[Dict[str, Any]] = Field(default={}, description="Additional anchor metadata")
    lifetime_hours: Optional[float] = Field(None, description="Custom lifetime in hours")

    @validator('position')
    def validate_position(cls, v):
        if len(v) != 3:
            raise ValueError('Position must have exactly 3 coordinates [x, y, z]')
        return v

    @validator('rotation') 
    def validate_rotation(cls, v):
        if len(v) != 4:
            raise ValueError('Rotation must be quaternion [x, y, z, w]')
        return v

class UpdateAnchorRequest(BaseModel):
    """Request model for updating an anchor"""
    position: Optional[List[float]] = Field(None, description="Updated 3D position")
    rotation: Optional[List[float]] = Field(None, description="Updated quaternion rotation")
    confidence: Optional[float] = Field(None, description="Updated confidence score")
    tracking_state: Optional[str] = Field(None, description="Updated tracking state")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Updated metadata")

class QueryAnchorsRequest(BaseModel):
    """Request model for querying anchors"""
    position: Optional[List[float]] = Field(None, description="Query position [x, y, z]")
    radius: Optional[float] = Field(None, description="Search radius in meters")
    session_id: Optional[str] = Field(None, description="Filter by session ID")
    user_id: Optional[str] = Field(None, description="Filter by user ID")
    anchor_type: Optional[str] = Field(None, description="Filter by anchor type")
    min_confidence: Optional[float] = Field(None, description="Minimum confidence threshold")
    tracking_state: Optional[str] = Field(None, description="Filter by tracking state")
    limit: Optional[int] = Field(50, description="Maximum results to return")

class ShareAnchorRequest(BaseModel):
    """Request model for sharing an anchor"""
    shared_with_user: str = Field(..., description="User ID to share with")
    permission_level: str = Field(default="read", description="Permission level (read, write, admin)")
    expires_hours: Optional[float] = Field(None, description="Sharing expiration in hours")

class AnchorResponse(BaseModel):
    """Response model for anchor data"""
    id: str
    session_id: str
    user_id: str
    position: List[float]
    rotation: List[float]
    confidence: float
    tracking_state: str
    anchor_type: str
    metadata: Dict[str, Any]
    created_at: str
    updated_at: str
    expires_at: Optional[str] = None

# Global service references (injected from main.py)
anchor_manager: Optional[AnchorManager] = None
persistence_engine: Optional[PersistenceEngine] = None
sync_manager: Optional[SynchronizationManager] = None

def get_anchor_manager():
    """Get anchor manager dependency"""
    if not anchor_manager:
        raise HTTPException(status_code=503, detail="Anchor manager not available")
    return anchor_manager

def get_persistence_engine():
    """Get persistence engine dependency"""
    if not persistence_engine:
        raise HTTPException(status_code=503, detail="Persistence engine not available")
    return persistence_engine

def get_sync_manager():
    """Get synchronization manager dependency"""
    if not sync_manager:
        raise HTTPException(status_code=503, detail="Synchronization manager not available")
    return sync_manager

# REST API Endpoints

@router.post("/anchors", response_model=AnchorResponse)
async def create_anchor(
    request: CreateAnchorRequest,
    manager: AnchorManager = Depends(get_anchor_manager),
    api_key: str = Depends(verify_api_key)
):
    """Create a new spatial anchor"""
    try:
        # Convert lifetime to timedelta if provided
        lifetime = None
        if request.lifetime_hours:
            lifetime = timedelta(hours=request.lifetime_hours)
        
        # Create anchor
        anchor = await manager.create_anchor(
            session_id=request.session_id,
            user_id=request.user_id,
            position=request.position,
            rotation=request.rotation,
            anchor_type=request.anchor_type,
            metadata=request.metadata,
            lifetime=lifetime
        )
        
        return AnchorResponse(**anchor.to_dict())
        
    except Exception as e:
        logger.error(f"Failed to create anchor: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create anchor: {e}")

@router.get("/anchors/{anchor_id}", response_model=AnchorResponse)
async def get_anchor(
    anchor_id: str,
    manager: AnchorManager = Depends(get_anchor_manager),
    api_key: str = Depends(verify_api_key)
):
    """Get an anchor by ID"""
    try:
        anchor = await manager.get_anchor(anchor_id)
        if not anchor:
            raise HTTPException(status_code=404, detail="Anchor not found")
        
        return AnchorResponse(**anchor.to_dict())
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get anchor: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get anchor: {e}")

@router.put("/anchors/{anchor_id}", response_model=AnchorResponse)
async def update_anchor(
    anchor_id: str,
    request: UpdateAnchorRequest,
    manager: AnchorManager = Depends(get_anchor_manager),
    api_key: str = Depends(verify_api_key)
):
    """Update an existing anchor"""
    try:
        anchor = await manager.update_anchor(
            anchor_id=anchor_id,
            position=request.position,
            rotation=request.rotation,
            confidence=request.confidence,
            tracking_state=request.tracking_state,
            metadata=request.metadata
        )
        
        if not anchor:
            raise HTTPException(status_code=404, detail="Anchor not found")
        
        return AnchorResponse(**anchor.to_dict())
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update anchor: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update anchor: {e}")

@router.delete("/anchors/{anchor_id}")
async def delete_anchor(
    anchor_id: str,
    manager: AnchorManager = Depends(get_anchor_manager),
    api_key: str = Depends(verify_api_key)
):
    """Delete an anchor"""
    try:
        success = await manager.delete_anchor(anchor_id)
        if not success:
            raise HTTPException(status_code=404, detail="Anchor not found")
        
        return {"message": "Anchor deleted successfully", "anchor_id": anchor_id}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete anchor: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete anchor: {e}")

@router.post("/anchors/query", response_model=List[AnchorResponse])
async def query_anchors(
    request: QueryAnchorsRequest,
    manager: AnchorManager = Depends(get_anchor_manager),
    api_key: str = Depends(verify_api_key)
):
    """Query anchors based on criteria"""
    try:
        query = AnchorQuery(
            position=request.position,
            radius=request.radius,
            session_id=request.session_id,
            user_id=request.user_id,
            anchor_type=request.anchor_type,
            min_confidence=request.min_confidence,
            tracking_state=request.tracking_state,
            limit=request.limit
        )
        
        anchors = await manager.query_anchors(query)
        
        return [AnchorResponse(**anchor.to_dict()) for anchor in anchors]
        
    except Exception as e:
        logger.error(f"Failed to query anchors: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to query anchors: {e}")

@router.get("/sessions/{session_id}/anchors", response_model=List[AnchorResponse])
async def get_session_anchors(
    session_id: str,
    manager: AnchorManager = Depends(get_anchor_manager),
    api_key: str = Depends(verify_api_key)
):
    """Get all anchors for a session"""
    try:
        anchors = await manager.get_session_anchors(session_id)
        return [AnchorResponse(**anchor.to_dict()) for anchor in anchors]
        
    except Exception as e:
        logger.error(f"Failed to get session anchors: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get session anchors: {e}")

@router.get("/nearby", response_model=List[AnchorResponse])
async def get_nearby_anchors(
    x: float,
    y: float,
    z: float,
    radius: float = 10.0,
    limit: int = 50,
    manager: AnchorManager = Depends(get_anchor_manager),
    api_key: str = Depends(verify_api_key)
):
    """Get anchors near a position"""
    try:
        anchors = await manager.get_nearby_anchors([x, y, z], radius, limit)
        return [AnchorResponse(**anchor.to_dict()) for anchor in anchors]
        
    except Exception as e:
        logger.error(f"Failed to get nearby anchors: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get nearby anchors: {e}")

@router.post("/anchors/{anchor_id}/share")
async def share_anchor(
    anchor_id: str,
    request: ShareAnchorRequest,
    persistence: PersistenceEngine = Depends(get_persistence_engine),
    api_key: str = Depends(verify_api_key)
):
    """Share an anchor with another user"""
    try:
        # Calculate expiration
        expires_at = None
        if request.expires_hours:
            expires_at = datetime.utcnow() + timedelta(hours=request.expires_hours)
        
        success = await persistence.share_anchor(
            anchor_id=anchor_id,
            shared_with_user=request.shared_with_user,
            shared_by_user=current_user or "system",  # Use authenticated user or system
            permission_level=request.permission_level,
            expires_at=expires_at
        )
        
        if not success:
            raise HTTPException(status_code=404, detail="Anchor not found")
        
        return {
            "message": "Anchor shared successfully",
            "anchor_id": anchor_id,
            "shared_with": request.shared_with_user,
            "permission": request.permission_level
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to share anchor: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to share anchor: {e}")

@router.get("/users/{user_id}/shared-anchors", response_model=List[AnchorResponse])
async def get_shared_anchors(
    user_id: str,
    persistence: PersistenceEngine = Depends(get_persistence_engine),
    api_key: str = Depends(verify_api_key)
):
    """Get anchors shared with a user"""
    try:
        anchors = await persistence.get_shared_anchors(user_id)
        return [AnchorResponse(**anchor.to_dict()) for anchor in anchors]
        
    except Exception as e:
        logger.error(f"Failed to get shared anchors: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get shared anchors: {e}")

@router.get("/statistics")
async def get_statistics(
    persistence: PersistenceEngine = Depends(get_persistence_engine),
    api_key: str = Depends(verify_api_key)
):
    """Get anchor statistics"""
    try:
        stats = await persistence.get_statistics()
        return stats
        
    except Exception as e:
        logger.error(f"Failed to get statistics: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get statistics: {e}")

# WebSocket endpoint for real-time synchronization

@router.websocket("/sync")
async def websocket_sync(websocket: WebSocket):
    """WebSocket endpoint for real-time anchor synchronization"""
    
    await websocket.accept()
    client_id = str(uuid.uuid4())
    
    try:
        # Get connection parameters
        query_params = websocket.query_params
        user_id = query_params.get("user_id")
        session_id = query_params.get("session_id")
        
        if not user_id or not session_id:
            await websocket.close(code=1003, reason="Missing user_id or session_id")
            return
        
        # Register client with sync manager
        if sync_manager:
            success = await sync_manager.register_client(client_id, user_id, session_id, websocket)
            if not success:
                await websocket.close(code=1003, reason="Failed to register client")
                return
        
        logger.info(f"WebSocket client {client_id} connected for user {user_id}, session {session_id}")
        
        # Handle messages
        while True:
            try:
                data = await websocket.receive_text()
                message = json.loads(data)
                
                if sync_manager:
                    await sync_manager.handle_message(client_id, message)
                
            except WebSocketDisconnect:
                break
            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON from client {client_id}")
            except Exception as e:
                logger.error(f"Error handling WebSocket message: {e}")
                break
    
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    
    finally:
        # Unregister client
        if sync_manager:
            await sync_manager.unregister_client(client_id)
        
        logger.info(f"WebSocket client {client_id} disconnected")

# Set global service references (called from main.py)
def set_services(anchor_mgr: AnchorManager, persistence_eng: PersistenceEngine, sync_mgr: SynchronizationManager):
    """Set global service references"""
    global anchor_manager, persistence_engine, sync_manager
    anchor_manager = anchor_mgr
    persistence_engine = persistence_eng
    sync_manager = sync_mgr