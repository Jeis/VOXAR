"""
Input Validation Models for Spatial AR Platform
Pydantic models for validating all incoming data and messages
"""

from pydantic import BaseModel, Field, validator
from typing import Dict, Any, Optional, Literal, List
from enum import Enum
import re

class ColocalizationMethod(str, Enum):
    """Supported colocalization methods"""
    QR_CODE = "qr_code"
    VISUAL = "visual"
    GPS = "gps"
    MANUAL = "manual"

class TrackingState(str, Enum):
    """AR tracking states"""
    TRACKING = "tracking"
    LIMITED = "limited"
    NOT_AVAILABLE = "not_available"

class MessageType(str, Enum):
    """WebSocket message types"""
    POSE_UPDATE = "pose_update"
    ANCHOR_CREATE = "anchor_create"
    ANCHOR_UPDATE = "anchor_update"
    ANCHOR_DELETE = "anchor_delete"
    COLOCALIZATION_DATA = "colocalization_data"
    COORDINATE_SYSTEM = "coordinate_system"
    CHAT_MESSAGE = "chat_message"
    PING = "ping"
    PONG = "pong"

# Basic geometric data structures
class Vector3Data(BaseModel):
    """3D vector validation"""
    x: float = Field(..., ge=-1000.0, le=1000.0, description="X coordinate")
    y: float = Field(..., ge=-1000.0, le=1000.0, description="Y coordinate")
    z: float = Field(..., ge=-1000.0, le=1000.0, description="Z coordinate")
    
    @validator('x', 'y', 'z')
    def validate_finite(cls, v):
        if not (-1000.0 <= v <= 1000.0):
            raise ValueError('Coordinate must be finite and within reasonable bounds')
        return v

class QuaternionData(BaseModel):
    """Quaternion validation"""
    x: float = Field(..., ge=-1.0, le=1.0, description="X component")
    y: float = Field(..., ge=-1.0, le=1.0, description="Y component")
    z: float = Field(..., ge=-1.0, le=1.0, description="Z component")
    w: float = Field(..., ge=-1.0, le=1.0, description="W component")
    
    @validator('x', 'y', 'z', 'w')
    def validate_quaternion_component(cls, v):
        if not (-1.0 <= v <= 1.0):
            raise ValueError('Quaternion component must be between -1 and 1')
        return v
    
    def is_valid(self) -> bool:
        """Check if quaternion is normalized"""
        magnitude = (self.x**2 + self.y**2 + self.z**2 + self.w**2)**0.5
        return 0.9 <= magnitude <= 1.1  # Allow small tolerance

class PoseData(BaseModel):
    """AR pose validation"""
    position: Vector3Data
    rotation: QuaternionData
    confidence: float = Field(..., ge=0.0, le=1.0, description="Tracking confidence")
    tracking_state: TrackingState = TrackingState.TRACKING
    
    def is_valid(self) -> bool:
        """Validate pose data integrity"""
        return (self.position is not None and 
                self.rotation is not None and 
                self.rotation.is_valid() and
                0.0 <= self.confidence <= 1.0)

# Session management models
class SessionCreateRequest(BaseModel):
    """Request to create a new AR session"""
    max_players: int = Field(default=8, ge=2, le=50, description="Maximum players in session")
    colocalization_method: ColocalizationMethod = ColocalizationMethod.QR_CODE
    is_public: bool = Field(default=False, description="Whether session is publicly discoverable")
    session_name: Optional[str] = Field(None, max_length=100, description="Optional session name")
    
    @validator('session_name')
    def validate_session_name(cls, v):
        if v is not None:
            # Only allow alphanumeric, spaces, and basic punctuation
            if not re.match(r'^[a-zA-Z0-9\s\-_\.]+$', v):
                raise ValueError('Session name contains invalid characters')
        return v

# WebSocket message models
class BaseMessage(BaseModel):
    """Base message structure"""
    type: MessageType
    timestamp: int = Field(..., gt=0, description="Unix timestamp in milliseconds")
    
    @validator('timestamp')
    def validate_timestamp(cls, v):
        import time
        current_time = int(time.time() * 1000)
        # Allow messages from 1 minute ago to 1 minute in future
        if not (current_time - 60000 <= v <= current_time + 60000):
            raise ValueError('Timestamp is too far from current time')
        return v

class PoseUpdateMessage(BaseMessage):
    """Pose update message validation"""
    type: Literal[MessageType.POSE_UPDATE]
    pose: PoseData
    
    class Config:
        schema_extra = {
            "example": {
                "type": "pose_update",
                "timestamp": 1642780800000,
                "pose": {
                    "position": {"x": 1.0, "y": 0.5, "z": -2.0},
                    "rotation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0},
                    "confidence": 0.95,
                    "tracking_state": "tracking"
                }
            }
        }

class AnchorCreateMessage(BaseMessage):
    """Anchor creation message validation"""
    type: Literal[MessageType.ANCHOR_CREATE]
    anchor_id: str = Field(..., regex=r'^[a-zA-Z0-9_-]{1,50}$', description="Anchor identifier")
    position: Vector3Data
    rotation: QuaternionData
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional anchor data")
    
    @validator('metadata')
    def validate_metadata(cls, v):
        # Limit metadata size to prevent abuse
        if len(str(v)) > 5000:  # 5KB limit
            raise ValueError('Metadata too large')
        return v

class AnchorUpdateMessage(BaseMessage):
    """Anchor update message validation"""
    type: Literal[MessageType.ANCHOR_UPDATE]
    anchor_id: str = Field(..., regex=r'^[a-zA-Z0-9_-]{1,50}$')
    position: Optional[Vector3Data] = None
    rotation: Optional[QuaternionData] = None
    metadata: Optional[Dict[str, Any]] = None
    
    @validator('metadata')
    def validate_metadata(cls, v):
        if v is not None and len(str(v)) > 5000:
            raise ValueError('Metadata too large')
        return v

class AnchorDeleteMessage(BaseMessage):
    """Anchor deletion message validation"""
    type: Literal[MessageType.ANCHOR_DELETE]
    anchor_id: str = Field(..., regex=r'^[a-zA-Z0-9_-]{1,50}$')

class ChatMessage(BaseMessage):
    """Chat message validation"""
    type: Literal[MessageType.CHAT_MESSAGE]
    message: str = Field(..., min_length=1, max_length=500, description="Chat message text")
    
    @validator('message')
    def validate_message_content(cls, v):
        # Basic content filtering
        v = v.strip()
        if not v:
            raise ValueError('Message cannot be empty')
        
        # Check for common spam patterns
        if len(set(v)) < 3 and len(v) > 10:  # Too many repeated characters
            raise ValueError('Message appears to be spam')
            
        return v

class ColocalizationDataMessage(BaseMessage):
    """Colocalization data message validation"""
    type: Literal[MessageType.COLOCALIZATION_DATA]
    colocalized: bool
    method: ColocalizationMethod
    coordinate_system: Optional[Dict[str, Any]] = None
    reference_data: Optional[Dict[str, Any]] = None  # QR code data, GPS coords, etc.

class PingMessage(BaseMessage):
    """Ping message validation"""
    type: Literal[MessageType.PING]

class PongMessage(BaseMessage):
    """Pong message validation"""
    type: Literal[MessageType.PONG]
    client_timestamp: Optional[int] = None  # Original ping timestamp

# Rate limiting models
class RateLimitInfo(BaseModel):
    """Rate limiting information"""
    requests_per_minute: int = 100
    burst_size: int = 20
    window_size_seconds: int = 60

class UserRateLimit(BaseModel):
    """Per-user rate limiting state"""
    user_id: str
    requests_count: int = 0
    window_start: float = 0
    burst_count: int = 0
    last_request: float = 0

# Error response models
class ErrorResponse(BaseModel):
    """Standardized error response"""
    error: bool = True
    message: str
    code: str
    details: Optional[Dict[str, Any]] = None
    timestamp: int

class ValidationError(ErrorResponse):
    """Validation error response"""
    code: str = "VALIDATION_ERROR"
    field_errors: Optional[List[Dict[str, Any]]] = None

# Message validation factory
def validate_websocket_message(data: dict) -> BaseMessage:
    """
    Validate incoming WebSocket message and return appropriate typed model
    """
    message_type = data.get('type')
    
    if not message_type:
        raise ValueError("Message type is required")
    
    # Map message types to validation models
    validators = {
        MessageType.POSE_UPDATE: PoseUpdateMessage,
        MessageType.ANCHOR_CREATE: AnchorCreateMessage,
        MessageType.ANCHOR_UPDATE: AnchorUpdateMessage,
        MessageType.ANCHOR_DELETE: AnchorDeleteMessage,
        MessageType.CHAT_MESSAGE: ChatMessage,
        MessageType.COLOCALIZATION_DATA: ColocalizationDataMessage,
        MessageType.PING: PingMessage,
        MessageType.PONG: PongMessage,
    }
    
    validator_class = validators.get(message_type)
    if not validator_class:
        raise ValueError(f"Unknown message type: {message_type}")
    
    try:
        return validator_class(**data)
    except Exception as e:
        raise ValueError(f"Invalid {message_type} message: {str(e)}")

# Rate limiting validation
def validate_rate_limit(user_id: str, rate_limits: Dict[str, UserRateLimit], 
                       limit_info: RateLimitInfo) -> bool:
    """
    Check if user is within rate limits
    """
    import time
    current_time = time.time()
    
    if user_id not in rate_limits:
        rate_limits[user_id] = UserRateLimit(user_id=user_id)
    
    user_limit = rate_limits[user_id]
    
    # Reset window if needed
    if current_time - user_limit.window_start >= limit_info.window_size_seconds:
        user_limit.window_start = current_time
        user_limit.requests_count = 0
        user_limit.burst_count = 0
    
    # Check burst limit (requests in quick succession)
    if current_time - user_limit.last_request < 1.0:  # Less than 1 second
        user_limit.burst_count += 1
        if user_limit.burst_count > limit_info.burst_size:
            return False
    else:
        user_limit.burst_count = 0
    
    # Check rate limit
    if user_limit.requests_count >= limit_info.requests_per_minute:
        return False
    
    # Update counters
    user_limit.requests_count += 1
    user_limit.last_request = current_time
    
    return True