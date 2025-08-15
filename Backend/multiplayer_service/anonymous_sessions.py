"""
Anonymous Session Support for Spatial AR Platform
Provides frictionless AR experiences like Niantic Lightship
"""

import random
import string
import time
import hashlib
from typing import Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

@dataclass
class AnonymousUser:
    """Anonymous user without authentication"""
    id: str
    display_name: str
    session_code: Optional[str] = None
    created_at: datetime = None
    is_anonymous: bool = True
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow()

class AnonymousSessionManager:
    """
    Manages anonymous AR sessions similar to Niantic Lightship
    No authentication required, just simple session codes
    """
    
    def __init__(self):
        self.active_codes: Dict[str, str] = {}  # code -> session_id
        self.session_expiry: Dict[str, float] = {}  # session_id -> expiry_time
        self.anonymous_users: Dict[str, AnonymousUser] = {}
        self.session_timeout = 3600  # 1 hour default
        self.max_anonymous_users_per_session = 10
        
    def generate_session_code(self) -> str:
        """
        Generate a 6-character session code like Niantic
        Format: ABC123 (3 letters + 3 numbers)
        """
        letters = ''.join(random.choices(string.ascii_uppercase, k=3))
        numbers = ''.join(random.choices(string.digits, k=3))
        return f"{letters}{numbers}"
    
    def generate_anonymous_user_id(self) -> str:
        """Generate a unique anonymous user ID"""
        timestamp = str(time.time())
        random_str = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
        return f"anon_{hashlib.md5(f'{timestamp}{random_str}'.encode()).hexdigest()[:12]}"
    
    def create_anonymous_session(self, creator_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Create an anonymous AR session without authentication
        Returns session info with shareable code
        """
        # Generate unique session ID
        session_id = str(hashlib.md5(str(time.time()).encode()).hexdigest())[:16]
        
        # Generate shareable code
        code = self.generate_session_code()
        while code in self.active_codes:  # Ensure uniqueness
            code = self.generate_session_code()
        
        # Create anonymous creator
        creator_id = self.generate_anonymous_user_id()
        creator = AnonymousUser(
            id=creator_id,
            display_name=creator_name or f"Player_{random.randint(1000, 9999)}",
            session_code=code
        )
        
        # Store session info
        self.active_codes[code] = session_id
        self.session_expiry[session_id] = time.time() + self.session_timeout
        self.anonymous_users[creator_id] = creator
        
        logger.info(f"Created anonymous session {session_id} with code {code}")
        
        return {
            "session_id": session_id,
            "share_code": code,
            "creator": {
                "id": creator_id,
                "display_name": creator.display_name,
                "is_anonymous": True
            },
            "expires_in": self.session_timeout,
            "max_players": self.max_anonymous_users_per_session,
            "created_at": datetime.utcnow().isoformat()
        }
    
    def join_with_code(self, code: str, display_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Join a session using a 6-character code (like Niantic)
        No authentication required
        """
        # Validate code format
        if not self._validate_code_format(code):
            logger.warning(f"Invalid code format: {code}")
            return None
        
        # Check if code exists
        code = code.upper()  # Normalize to uppercase
        if code not in self.active_codes:
            logger.warning(f"Code not found: {code}")
            return None
        
        session_id = self.active_codes[code]
        
        # Check if session expired
        if self._is_session_expired(session_id):
            logger.info(f"Session {session_id} has expired")
            self._cleanup_session(session_id)
            return None
        
        # Create anonymous user
        user_id = self.generate_anonymous_user_id()
        user = AnonymousUser(
            id=user_id,
            display_name=display_name or f"Player_{random.randint(1000, 9999)}",
            session_code=code
        )
        
        self.anonymous_users[user_id] = user
        
        # Extend session expiry on activity
        self.session_expiry[session_id] = time.time() + self.session_timeout
        
        logger.info(f"Anonymous user {user_id} joined session {session_id} with code {code}")
        
        return {
            "session_id": session_id,
            "user": {
                "id": user_id,
                "display_name": user.display_name,
                "is_anonymous": True
            },
            "share_code": code,
            "session_info": {
                "max_players": self.max_anonymous_users_per_session,
                "expires_in": int(self.session_expiry[session_id] - time.time())
            }
        }
    
    def create_anonymous_user(self, session_id: str, display_name: Optional[str] = None) -> AnonymousUser:
        """
        Create an anonymous user for direct session joining
        Used when session_id is known but no authentication is available
        """
        user_id = self.generate_anonymous_user_id()
        user = AnonymousUser(
            id=user_id,
            display_name=display_name or f"Player_{random.randint(1000, 9999)}"
        )
        
        self.anonymous_users[user_id] = user
        
        # Extend session expiry on activity
        if session_id in self.session_expiry:
            self.session_expiry[session_id] = time.time() + self.session_timeout
        
        return user
    
    def get_session_by_code(self, code: str) -> Optional[str]:
        """Get session ID from share code"""
        code = code.upper()
        if code in self.active_codes:
            session_id = self.active_codes[code]
            if not self._is_session_expired(session_id):
                return session_id
            else:
                self._cleanup_session(session_id)
        return None
    
    def extend_session(self, session_id: str):
        """Extend session expiry on activity"""
        if session_id in self.session_expiry:
            self.session_expiry[session_id] = time.time() + self.session_timeout
            logger.debug(f"Extended session {session_id} expiry")
    
    def cleanup_expired_sessions(self):
        """Remove expired sessions and their codes"""
        current_time = time.time()
        expired_sessions = [
            sid for sid, expiry in self.session_expiry.items()
            if current_time > expiry
        ]
        
        for session_id in expired_sessions:
            self._cleanup_session(session_id)
            logger.info(f"Cleaned up expired session {session_id}")
    
    def _validate_code_format(self, code: str) -> bool:
        """Validate that code matches format: 3 letters + 3 numbers"""
        if len(code) != 6:
            return False
        
        code = code.upper()
        letters = code[:3]
        numbers = code[3:]
        
        return letters.isalpha() and numbers.isdigit()
    
    def _is_session_expired(self, session_id: str) -> bool:
        """Check if a session has expired"""
        if session_id not in self.session_expiry:
            return True
        return time.time() > self.session_expiry[session_id]
    
    def _cleanup_session(self, session_id: str):
        """Remove session and associated data"""
        # Remove code mapping
        codes_to_remove = [
            code for code, sid in self.active_codes.items()
            if sid == session_id
        ]
        for code in codes_to_remove:
            del self.active_codes[code]
        
        # Remove expiry
        if session_id in self.session_expiry:
            del self.session_expiry[session_id]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get anonymous session statistics"""
        return {
            "active_sessions": len(self.session_expiry),
            "active_codes": len(self.active_codes),
            "anonymous_users": len(self.anonymous_users),
            "session_timeout": self.session_timeout,
            "max_users_per_session": self.max_anonymous_users_per_session
        }

# Global anonymous session manager instance
anonymous_manager = AnonymousSessionManager()