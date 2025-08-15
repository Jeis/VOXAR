"""
Spatial Platform - WebSocket Multiplayer Service with Authentication
Real-time multiplayer server for spatial AR sessions with colocalization support
Now includes JWT-based authentication and secure session management
"""

import asyncio
import json
import uuid
import time
import logging
from typing import Dict, Set, Optional, Any
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
import websockets
from websockets.server import WebSocketServerProtocol
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# Import authentication and validation modules
from .auth import auth_manager, get_current_user, check_session_access, User, SessionPermissions
from .auth_routes import auth_router
from .validation import validate_websocket_message, validate_rate_limit, RateLimitInfo, UserRateLimit, ValidationError
from .anonymous_sessions import anonymous_manager, AnonymousUser

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class Pose:
    position: Dict[str, float]  # {x, y, z}
    rotation: Dict[str, float]  # {x, y, z, w} quaternion
    timestamp: float
    confidence: float = 1.0
    tracking_state: str = "tracking"

@dataclass
class SpatialAnchor:
    id: str
    position: Dict[str, float]
    rotation: Dict[str, float]
    metadata: Dict[str, Any]
    creator_id: str
    creation_time: float
    last_update: float

@dataclass
class Player:
    user_id: str
    websocket: WebSocket
    user: Optional[User]  # Authenticated user object (optional for anonymous)
    anonymous_user: Optional[AnonymousUser]  # Anonymous user object
    permissions: SessionPermissions
    pose: Optional[Pose]
    join_time: float
    is_host: bool = False
    colocalized: bool = False
    last_ping: float = 0
    is_anonymous: bool = False

@dataclass
class ARSession:
    session_id: str
    creation_time: float
    players: Dict[str, Player]
    anchors: Dict[str, SpatialAnchor]
    host_user_id: Optional[str]
    colocalization_method: str = "qr_code"
    coordinate_system: Dict[str, Any] = None
    is_colocalized: bool = False
    max_players: int = 8

class SpatialMultiplayerServer:
    def __init__(self):
        self.sessions: Dict[str, ARSession] = {}
        self.user_to_session: Dict[str, str] = {}
        self.app = FastAPI(title="Spatial Multiplayer Service")
        self.cleanup_task = None
        
        # Rate limiting
        self.rate_limits: Dict[str, UserRateLimit] = {}
        self.rate_limit_info = RateLimitInfo(
            requests_per_minute=100,
            burst_size=20,
            window_size_seconds=60
        )
        
        # Add CORS middleware
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        
        # Setup routes
        self.setup_routes()
        
        # Include authentication routes
        self.app.include_router(auth_router)
        
        # Message types
        self.MESSAGE_TYPES = {
            'POSE_UPDATE': 'pose_update',
            'ANCHOR_CREATE': 'anchor_create',
            'ANCHOR_UPDATE': 'anchor_update',
            'ANCHOR_DELETE': 'anchor_delete',
            'COLOCALIZATION_DATA': 'colocalization_data',
            'COORDINATE_SYSTEM': 'coordinate_system',
            'USER_JOINED': 'user_joined',
            'USER_LEFT': 'user_left',
            'CHAT_MESSAGE': 'chat_message',
            'SESSION_STATE': 'session_state',
            'PING': 'ping',
            'PONG': 'pong'
        }
        
        # Add startup event
        @self.app.on_event("startup")
        async def startup_event():
            self.cleanup_task = asyncio.create_task(self.cleanup_inactive_sessions())
        
        # Add shutdown event
        @self.app.on_event("shutdown")
        async def shutdown_event():
            if self.cleanup_task:
                self.cleanup_task.cancel()
                try:
                    await self.cleanup_task
                except asyncio.CancelledError:
                    pass
    
    def setup_routes(self):
        @self.app.get("/")
        async def health_check():
            return {"status": "healthy", "service": "spatial_multiplayer", "anonymous_sessions_enabled": True}
        
        @self.app.post("/api/v1/session/create")
        async def create_session(request: dict, current_user: User = Depends(get_current_user)):
            # Check user permissions
            permissions = auth_manager.get_session_permissions(current_user.id, "")
            if permissions.max_sessions <= 0:
                raise HTTPException(403, "User not allowed to create sessions")
                
            session_id = str(uuid.uuid4())
            session = ARSession(
                session_id=session_id,
                creation_time=time.time(),
                players={},
                anchors={},
                host_user_id=current_user.id,  # Creator becomes host
                colocalization_method=request.get('colocalization_method', 'qr_code'),
                max_players=min(request.get('max_players', 8), 50)  # Cap at 50 players
            )
            
            # Initialize coordinate system
            session.coordinate_system = {
                'origin': {'x': 0, 'y': 0, 'z': 0},
                'rotation': {'x': 0, 'y': 0, 'z': 0, 'w': 1}
            }
            
            self.sessions[session_id] = session
            logger.info(f"User {current_user.username} created AR session: {session_id}")
            
            return {
                "success": True,
                "session_id": session_id,
                "max_players": session.max_players,
                "colocalization_method": session.colocalization_method,
                "creator": current_user.username
            }
        
        @self.app.post("/api/v1/session/anonymous/create")
        async def create_anonymous_session(request: dict = {}):
            """Create an anonymous session without authentication (like Niantic Lightship)"""
            # Use anonymous session manager
            result = anonymous_manager.create_anonymous_session(
                creator_name=request.get('display_name')
            )
            
            # Create actual AR session
            session = ARSession(
                session_id=result['session_id'],
                creation_time=time.time(),
                players={},
                anchors={},
                host_user_id=result['creator']['id'],
                colocalization_method=request.get('colocalization_method', 'qr_code'),
                max_players=10  # Limit anonymous sessions to 10 players like Niantic
            )
            
            session.coordinate_system = {
                'origin': {'x': 0, 'y': 0, 'z': 0},
                'rotation': {'x': 0, 'y': 0, 'z': 0, 'w': 1}
            }
            
            self.sessions[result['session_id']] = session
            logger.info(f"Created anonymous session with code: {result['share_code']}")
            
            return result
        
        @self.app.post("/api/v1/session/anonymous/join")
        async def join_anonymous_session(request: dict):
            """Join a session using a 6-character code (like Niantic Lightship)"""
            code = request.get('code')
            display_name = request.get('display_name')
            
            if not code:
                raise HTTPException(400, "Session code required")
            
            result = anonymous_manager.join_with_code(code, display_name)
            if not result:
                raise HTTPException(404, "Invalid or expired session code")
            
            return result
        
        @self.app.get("/api/session/{session_id}")
        async def get_session_info(session_id: str):
            if session_id not in self.sessions:
                # Check if it's a valid code instead
                session_id_from_code = anonymous_manager.get_session_by_code(session_id)
                if session_id_from_code:
                    session_id = session_id_from_code
                else:
                    raise HTTPException(status_code=404, detail="Session not found")
            
            session = self.sessions[session_id]
            return {
                "session_id": session_id,
                "player_count": len(session.players),
                "max_players": session.max_players,
                "is_colocalized": session.is_colocalized,
                "colocalization_method": session.colocalization_method,
                "creation_time": session.creation_time
            }
        
        @self.app.websocket("/ws/{session_id}")
        async def websocket_endpoint(websocket: WebSocket, session_id: str, token: str = Query(None)):
            await self.handle_websocket_connection(websocket, session_id, token)
    
    async def handle_websocket_connection(self, websocket: WebSocket, session_id: str, token: str):
        """Handle WebSocket connection with optional authentication"""
        try:
            user = None
            anonymous_user = None
            permissions = None
            
            if token:
                # Authenticated flow
                user = auth_manager.verify_token(token)
                if not user:
                    await websocket.close(code=4001, reason="Authentication failed")
                    return
                    
                permissions = auth_manager.get_session_permissions(user.id, session_id)
                if not permissions.can_join:
                    await websocket.close(code=4003, reason="Access denied")
                    return
                    
                await websocket.accept()
                logger.info(f"Authenticated user {user.username} ({user.id}) connecting to session {session_id}")
            else:
                # Anonymous flow (like Niantic Lightship)
                await websocket.accept()
                
                # Create anonymous user
                anonymous_user = anonymous_manager.create_anonymous_user(session_id)
                
                # Default permissions for anonymous users
                permissions = SessionPermissions(
                    can_join=True,
                    can_create_anchors=True,
                    can_delete_anchors=False,
                    can_moderate=False,
                    max_sessions=1
                )
                
                logger.info(f"Anonymous user {anonymous_user.id} connecting to session {session_id}")
            
            # Get or create session
            if session_id not in self.sessions:
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "message": "Session not found"
                }))
                await websocket.close()
                return
            
            session = self.sessions[session_id]
            
            # Check if session is full
            if len(session.players) >= session.max_players:
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "message": "Session is full"
                }))
                await websocket.close()
                return
            
            # Create player (authenticated or anonymous)
            is_host = len(session.players) == 0  # First player is host
            user_id = user.id if user else anonymous_user.id
            
            player = Player(
                user_id=user_id,
                websocket=websocket,
                user=user,
                anonymous_user=anonymous_user,
                permissions=permissions,
                pose=None,
                join_time=time.time(),
                is_host=is_host,
                last_ping=time.time(),
                is_anonymous=(user is None)
            )
            
            # Add player to session
            session.players[user_id] = player
            self.user_to_session[user_id] = session_id
            
            if is_host:
                session.host_user_id = user_id
                logger.info(f"User {user_id} is now host of session {session_id}")
            
            # Extend anonymous session expiry on activity
            if not user:
                anonymous_manager.extend_session(session_id)
            
            # Notify all players about new user
            display_name = user.username if user else anonymous_user.display_name
            await self.broadcast_to_session(session_id, {
                "type": self.MESSAGE_TYPES['USER_JOINED'],
                "user_id": user_id,
                "display_name": display_name,
                "is_host": is_host,
                "is_anonymous": player.is_anonymous,
                "timestamp": time.time()
            }, exclude_user=user_id)
            
            # Send current session state to new player
            await self.send_session_state(websocket, session)
            
            # Handle messages
            async for message in websocket.iter_text():
                await self.handle_message(session_id, user_id, message, player)
                
        except WebSocketDisconnect:
            username = user.username if user else anonymous_user.display_name
            logger.info(f"User {username} ({user_id}) disconnected from session {session_id}")
        except Exception as e:
            username = user.username if user else (anonymous_user.display_name if anonymous_user else "Unknown")
            logger.error(f"Error handling WebSocket for user {username}: {e}")
        finally:
            await self.handle_user_disconnect(session_id, user_id)
    
    async def handle_message(self, session_id: str, user_id: str, message: str, player: Player):
        """Handle incoming WebSocket messages with validation and rate limiting"""
        try:
            # Check rate limiting
            if not validate_rate_limit(user_id, self.rate_limits, self.rate_limit_info):
                logger.warning(f"Rate limit exceeded for user {user_id}")
                await player.websocket.send_text(json.dumps({
                    "type": "error",
                    "message": "Rate limit exceeded. Please slow down.",
                    "code": "RATE_LIMIT_EXCEEDED"
                }))
                return
            
            # Parse and validate message
            try:
                data = json.loads(message)
                validated_message = validate_websocket_message(data)
            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON from user {user_id}")
                await player.websocket.send_text(json.dumps({
                    "type": "error",
                    "message": "Invalid JSON format",
                    "code": "INVALID_JSON"
                }))
                return
            except ValueError as e:
                logger.warning(f"Validation error from user {user_id}: {e}")
                await player.websocket.send_text(json.dumps({
                    "type": "error",
                    "message": f"Validation error: {str(e)}",
                    "code": "VALIDATION_ERROR"
                }))
                return
            
            if session_id not in self.sessions:
                return
            
            session = self.sessions[session_id]
            
            # Update last ping time
            player.last_ping = time.time()
            
            message_type = validated_message.type
            
            if message_type == self.MESSAGE_TYPES['POSE_UPDATE']:
                await self.handle_pose_update(session, player, validated_message)
            
            elif message_type == self.MESSAGE_TYPES['ANCHOR_CREATE']:
                if not player.permissions.can_create_anchors:
                    await player.websocket.send_text(json.dumps({
                        "type": "error",
                        "message": "Permission denied: cannot create anchors",
                        "code": "PERMISSION_DENIED"
                    }))
                    return
                await self.handle_anchor_create(session, player, validated_message)
            
            elif message_type == self.MESSAGE_TYPES['ANCHOR_UPDATE']:
                await self.handle_anchor_update(session, player, validated_message)
            
            elif message_type == self.MESSAGE_TYPES['ANCHOR_DELETE']:
                if not player.permissions.can_delete_anchors:
                    await player.websocket.send_text(json.dumps({
                        "type": "error",
                        "message": "Permission denied: cannot delete anchors",
                        "code": "PERMISSION_DENIED"
                    }))
                    return
                await self.handle_anchor_delete(session, player, validated_message)
            
            elif message_type == self.MESSAGE_TYPES['COLOCALIZATION_DATA']:
                await self.handle_colocalization_data(session, player, validated_message)
            
            elif message_type == self.MESSAGE_TYPES['CHAT_MESSAGE']:
                await self.handle_chat_message(session, player, validated_message)
            
            elif message_type == self.MESSAGE_TYPES['PING']:
                await self.handle_ping(session, player, validated_message)
            
            else:
                logger.warning(f"Unknown message type: {message_type}")
                
        except Exception as e:
            logger.error(f"Error handling message from user {user_id}: {e}")
    
    async def handle_pose_update(self, session: ARSession, user_id: str, data: dict):
        """Handle pose update from a user"""
        player = session.players.get(user_id)
        if not player:
            return
        
        # Update player pose
        player.pose = Pose(
            position=data.get('position', {'x': 0, 'y': 0, 'z': 0}),
            rotation=data.get('rotation', {'x': 0, 'y': 0, 'z': 0, 'w': 1}),
            timestamp=time.time(),
            confidence=data.get('confidence', 1.0),
            tracking_state=data.get('tracking_state', 'tracking')
        )
        
        # Broadcast pose updates to other colocalized players
        if player.colocalized:
            pose_message = {
                "type": self.MESSAGE_TYPES['POSE_UPDATE'],
                "user_id": user_id,
                "pose": asdict(player.pose),
                "timestamp": time.time()
            }
            
            # Only send to other colocalized players
            for other_user_id, other_player in session.players.items():
                if other_user_id != user_id and other_player.colocalized:
                    try:
                        await other_player.websocket.send_text(json.dumps(pose_message))
                    except:
                        pass  # Handle disconnected players in cleanup
    
    async def handle_anchor_create(self, session: ARSession, user_id: str, data: dict):
        """Handle spatial anchor creation"""
        anchor_id = data.get('anchor_id', str(uuid.uuid4()))
        
        anchor = SpatialAnchor(
            id=anchor_id,
            position=data.get('position', {'x': 0, 'y': 0, 'z': 0}),
            rotation=data.get('rotation', {'x': 0, 'y': 0, 'z': 0, 'w': 1}),
            metadata=data.get('metadata', {}),
            creator_id=user_id,
            creation_time=time.time(),
            last_update=time.time()
        )
        
        session.anchors[anchor_id] = anchor
        
        # Broadcast to all players
        anchor_message = {
            "type": self.MESSAGE_TYPES['ANCHOR_CREATE'],
            "anchor": asdict(anchor)
        }
        
        await self.broadcast_to_session(session.session_id, anchor_message)
        logger.info(f"Anchor created: {anchor_id} by {user_id}")
    
    async def handle_anchor_update(self, session: ARSession, user_id: str, data: dict):
        """Handle spatial anchor update"""
        anchor_id = data.get('anchor_id')
        
        if anchor_id not in session.anchors:
            return
        
        anchor = session.anchors[anchor_id]
        
        # Update anchor properties
        if 'position' in data:
            anchor.position = data['position']
        if 'rotation' in data:
            anchor.rotation = data['rotation']
        if 'metadata' in data:
            anchor.metadata = data['metadata']
        
        anchor.last_update = time.time()
        
        # Broadcast update
        update_message = {
            "type": self.MESSAGE_TYPES['ANCHOR_UPDATE'],
            "anchor_id": anchor_id,
            "position": anchor.position,
            "rotation": anchor.rotation,
            "metadata": anchor.metadata,
            "timestamp": anchor.last_update
        }
        
        await self.broadcast_to_session(session.session_id, update_message)
    
    async def handle_anchor_delete(self, session: ARSession, user_id: str, data: dict):
        """Handle spatial anchor deletion"""
        anchor_id = data.get('anchor_id')
        
        if anchor_id not in session.anchors:
            return
        
        anchor = session.anchors[anchor_id]
        
        # Check permissions (creator or host can delete)
        if anchor.creator_id == user_id or session.host_user_id == user_id:
            del session.anchors[anchor_id]
            
            delete_message = {
                "type": self.MESSAGE_TYPES['ANCHOR_DELETE'],
                "anchor_id": anchor_id,
                "timestamp": time.time()
            }
            
            await self.broadcast_to_session(session.session_id, delete_message)
            logger.info(f"Anchor deleted: {anchor_id} by {user_id}")
    
    async def handle_colocalization_data(self, session: ARSession, user_id: str, data: dict):
        """Handle colocalization setup data"""
        player = session.players.get(user_id)
        if not player:
            return
        
        # If host is setting coordinate system
        if user_id == session.host_user_id and 'coordinate_system' in data:
            session.coordinate_system = data['coordinate_system']
            session.colocalization_method = data.get('method', 'qr_code')
            session.is_colocalized = True
            
            # Broadcast coordinate system to all players
            coord_message = {
                "type": self.MESSAGE_TYPES['COORDINATE_SYSTEM'],
                "coordinate_system": session.coordinate_system,
                "colocalization_method": session.colocalization_method,
                "is_colocalized": session.is_colocalized,
                "timestamp": time.time()
            }
            
            await self.broadcast_to_session(session.session_id, coord_message)
            logger.info(f"Coordinate system established by host: {user_id}")
        
        # Mark user as colocalized
        if 'colocalized' in data:
            player.colocalized = data['colocalized']
            
            # Notify other players about colocalization status change
            status_message = {
                "type": self.MESSAGE_TYPES['USER_JOINED'],  # Reuse for status update
                "user_id": user_id,
                "is_host": player.is_host,
                "colocalized": player.colocalized,
                "timestamp": time.time()
            }
            
            await self.broadcast_to_session(session.session_id, status_message, exclude_user=user_id)
    
    async def handle_chat_message(self, session: ARSession, user_id: str, data: dict):
        """Handle chat message"""
        chat_message = {
            "type": self.MESSAGE_TYPES['CHAT_MESSAGE'],
            "user_id": user_id,
            "message": data.get('message', ''),
            "timestamp": time.time()
        }
        
        await self.broadcast_to_session(session.session_id, chat_message)
    
    async def handle_ping(self, session: ARSession, user_id: str, data: dict):
        """Handle ping message"""
        player = session.players.get(user_id)
        if player:
            pong_message = {
                "type": self.MESSAGE_TYPES['PONG'],
                "timestamp": time.time(),
                "client_timestamp": data.get('timestamp', 0)
            }
            
            try:
                await player.websocket.send_text(json.dumps(pong_message))
            except:
                pass  # Handle disconnected players in cleanup
    
    async def send_session_state(self, websocket: WebSocket, session: ARSession):
        """Send current session state to a player"""
        players_info = {}
        for uid, player in session.players.items():
            players_info[uid] = {
                "user_id": uid,
                "is_host": player.is_host,
                "colocalized": player.colocalized,
                "join_time": player.join_time
            }
        
        session_state = {
            "type": self.MESSAGE_TYPES['SESSION_STATE'],
            "session_id": session.session_id,
            "coordinate_system": session.coordinate_system,
            "colocalization_method": session.colocalization_method,
            "is_colocalized": session.is_colocalized,
            "anchors": {aid: asdict(anchor) for aid, anchor in session.anchors.items()},
            "players": players_info,
            "timestamp": time.time()
        }
        
        try:
            await websocket.send_text(json.dumps(session_state))
        except:
            pass  # Handle disconnected players
    
    async def broadcast_to_session(self, session_id: str, message: dict, exclude_user: str = None):
        """Broadcast message to all players in a session"""
        if session_id not in self.sessions:
            return
        
        session = self.sessions[session_id]
        message_text = json.dumps(message)
        
        disconnected_players = []
        for user_id, player in session.players.items():
            if exclude_user and user_id == exclude_user:
                continue
            
            try:
                await player.websocket.send_text(message_text)
            except:
                disconnected_players.append(user_id)
        
        # Clean up disconnected players
        for user_id in disconnected_players:
            await self.handle_user_disconnect(session_id, user_id)
    
    async def handle_user_disconnect(self, session_id: str, user_id: str):
        """Handle user disconnection"""
        if session_id not in self.sessions:
            return
        
        session = self.sessions[session_id]
        
        if user_id in session.players:
            del session.players[user_id]
            
            if user_id in self.user_to_session:
                del self.user_to_session[user_id]
            
            # Notify remaining players
            leave_message = {
                "type": self.MESSAGE_TYPES['USER_LEFT'],
                "user_id": user_id,
                "timestamp": time.time()
            }
            
            await self.broadcast_to_session(session_id, leave_message)
            
            # Handle host transfer
            if session.host_user_id == user_id:
                new_host = self.get_next_host(session)
                if new_host:
                    session.host_user_id = new_host
                    session.players[new_host].is_host = True
                    
                    host_transfer = {
                        "type": self.MESSAGE_TYPES['USER_JOINED'],
                        "user_id": new_host,
                        "is_host": True,
                        "timestamp": time.time()
                    }
                    
                    await self.broadcast_to_session(session_id, host_transfer)
                    logger.info(f"Host transferred to: {new_host}")
            
            # Clean up empty sessions
            if len(session.players) == 0:
                del self.sessions[session_id]
                logger.info(f"Session {session_id} deleted (no players)")
    
    def get_next_host(self, session: ARSession) -> Optional[str]:
        """Get the next host (earliest joined player)"""
        if not session.players:
            return None
        
        earliest_join = None
        next_host = None
        
        for user_id, player in session.players.items():
            if earliest_join is None or player.join_time < earliest_join:
                earliest_join = player.join_time
                next_host = user_id
        
        return next_host
    
    async def cleanup_inactive_sessions(self):
        """Periodically clean up inactive sessions and disconnected players"""
        while True:
            try:
                current_time = time.time()
                sessions_to_delete = []
                
                for session_id, session in self.sessions.items():
                    players_to_remove = []
                    
                    # Check for inactive players (no ping for 60 seconds)
                    for user_id, player in session.players.items():
                        if current_time - player.last_ping > 60:
                            players_to_remove.append(user_id)
                    
                    # Remove inactive players
                    for user_id in players_to_remove:
                        await self.handle_user_disconnect(session_id, user_id)
                    
                    # Mark empty sessions for deletion
                    if len(session.players) == 0:
                        sessions_to_delete.append(session_id)
                
                # Delete empty sessions
                for session_id in sessions_to_delete:
                    if session_id in self.sessions:
                        del self.sessions[session_id]
                        logger.info(f"Cleaned up empty session: {session_id}")
                
                await asyncio.sleep(30)  # Check every 30 seconds
                
            except Exception as e:
                logger.error(f"Error in cleanup task: {e}")
                await asyncio.sleep(30)

# Global server instance
multiplayer_server = SpatialMultiplayerServer()

# FastAPI app instance
app = multiplayer_server.app

if __name__ == "__main__":
    uvicorn.run(
        "websocket_server:app",
        host="0.0.0.0",
        port=8080,
        reload=True,
        log_level="info"
    )