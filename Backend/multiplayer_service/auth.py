"""
Authentication and Authorization Module for Spatial AR Platform
Provides JWT-based authentication with session management and role-based access control
"""

import os
import jwt
import bcrypt
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from dataclasses import dataclass
from fastapi import HTTPException, Header, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import logging

logger = logging.getLogger(__name__)

@dataclass
class User:
    """User data model"""
    id: str
    username: str
    email: str
    roles: list
    created_at: datetime
    last_active: datetime
    is_active: bool = True

@dataclass
class SessionPermissions:
    """Session-specific permissions"""
    can_join: bool
    can_create_anchors: bool
    can_delete_anchors: bool
    can_moderate: bool
    max_sessions: int

class AuthenticationManager:
    """Handles JWT token creation, validation, and user management"""
    
    def __init__(self):
        self.jwt_secret = self._get_jwt_secret()
        self.jwt_algorithm = "HS256"
        self.token_expiry_hours = 24
        self.refresh_expiry_days = 7
        self.security = HTTPBearer()
        
        # In-memory user store (replace with database in production)
        self.users: Dict[str, User] = {}
        self.refresh_tokens: Dict[str, str] = {}  # token -> user_id
        
        # Session permissions cache
        self.session_permissions: Dict[str, Dict[str, SessionPermissions]] = {}
        
    def _get_jwt_secret(self) -> str:
        """Get JWT secret from environment variables"""
        secret = os.environ.get('JWT_SECRET')
        if not secret:
            if os.environ.get('ENVIRONMENT') == 'production':
                raise ValueError("JWT_SECRET environment variable required in production")
            else:
                # Development fallback - generate a random secret
                secret = hashlib.sha256(os.urandom(32)).hexdigest()
                logger.warning("Using generated JWT secret for development. Set JWT_SECRET env var for production.")
        return secret
    
    def _hash_password(self, password: str) -> str:
        """Hash password using bcrypt"""
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')
    
    def _verify_password(self, password: str, hashed: str) -> bool:
        """Verify password against hash"""
        return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
    
    def create_user(self, username: str, email: str, password: str, roles: list = None) -> User:
        """Create a new user account"""
        if roles is None:
            roles = ["user"]
            
        # Check if user already exists
        user_id = hashlib.sha256(f"{username}:{email}".encode()).hexdigest()[:16]
        if user_id in self.users:
            raise HTTPException(409, "User already exists")
            
        # Validate input
        if not username or len(username) < 3:
            raise HTTPException(400, "Username must be at least 3 characters")
        if not email or "@" not in email:
            raise HTTPException(400, "Valid email required")
        if not password or len(password) < 6:
            raise HTTPException(400, "Password must be at least 6 characters")
        
        # Create user
        user = User(
            id=user_id,
            username=username,
            email=email,
            roles=roles,
            created_at=datetime.utcnow(),
            last_active=datetime.utcnow()
        )
        
        # Store hashed password separately (not in user object)
        self.users[user_id] = user
        # In production, store password hash in secure database
        setattr(user, '_password_hash', self._hash_password(password))
        
        logger.info(f"Created user: {username} ({user_id})")
        return user
    
    def authenticate_user(self, username: str, password: str) -> Optional[User]:
        """Authenticate user with username/password"""
        # Find user by username
        user = None
        for u in self.users.values():
            if u.username == username:
                user = u
                break
                
        if not user or not user.is_active:
            return None
            
        # Verify password
        password_hash = getattr(user, '_password_hash', None)
        if not password_hash or not self._verify_password(password, password_hash):
            return None
            
        # Update last active
        user.last_active = datetime.utcnow()
        logger.info(f"User authenticated: {username}")
        return user
    
    def create_access_token(self, user: User) -> str:
        """Create JWT access token"""
        payload = {
            "sub": user.id,
            "username": user.username,
            "roles": user.roles,
            "exp": datetime.utcnow() + timedelta(hours=self.token_expiry_hours),
            "iat": datetime.utcnow(),
            "type": "access"
        }
        
        token = jwt.encode(payload, self.jwt_secret, algorithm=self.jwt_algorithm)
        logger.debug(f"Created access token for user: {user.username}")
        return token
    
    def create_refresh_token(self, user: User) -> str:
        """Create JWT refresh token"""
        payload = {
            "sub": user.id,
            "exp": datetime.utcnow() + timedelta(days=self.refresh_expiry_days),
            "iat": datetime.utcnow(),
            "type": "refresh"
        }
        
        token = jwt.encode(payload, self.jwt_secret, algorithm=self.jwt_algorithm)
        self.refresh_tokens[token] = user.id
        logger.debug(f"Created refresh token for user: {user.username}")
        return token
    
    def verify_token(self, token: str) -> Optional[User]:
        """Verify JWT token and return user"""
        try:
            payload = jwt.decode(token, self.jwt_secret, algorithms=[self.jwt_algorithm])
            user_id = payload.get("sub")
            token_type = payload.get("type", "access")
            
            if token_type != "access":
                raise HTTPException(401, "Invalid token type")
                
            user = self.users.get(user_id)
            if not user or not user.is_active:
                raise HTTPException(401, "User not found or inactive")
                
            # Update last active
            user.last_active = datetime.utcnow()
            return user
            
        except jwt.ExpiredSignatureError:
            raise HTTPException(401, "Token expired")
        except jwt.InvalidTokenError:
            raise HTTPException(401, "Invalid token")
    
    def refresh_access_token(self, refresh_token: str) -> str:
        """Create new access token from refresh token"""
        try:
            payload = jwt.decode(refresh_token, self.jwt_secret, algorithms=[self.jwt_algorithm])
            user_id = payload.get("sub")
            token_type = payload.get("type")
            
            if token_type != "refresh":
                raise HTTPException(401, "Invalid token type")
                
            if refresh_token not in self.refresh_tokens:
                raise HTTPException(401, "Refresh token not found")
                
            user = self.users.get(user_id)
            if not user or not user.is_active:
                raise HTTPException(401, "User not found or inactive")
                
            return self.create_access_token(user)
            
        except jwt.ExpiredSignatureError:
            # Remove expired refresh token
            if refresh_token in self.refresh_tokens:
                del self.refresh_tokens[refresh_token]
            raise HTTPException(401, "Refresh token expired")
        except jwt.InvalidTokenError:
            raise HTTPException(401, "Invalid refresh token")
    
    def revoke_refresh_token(self, refresh_token: str):
        """Revoke a refresh token"""
        if refresh_token in self.refresh_tokens:
            del self.refresh_tokens[refresh_token]
            logger.info("Refresh token revoked")
    
    def get_session_permissions(self, user_id: str, session_id: str) -> SessionPermissions:
        """Get user permissions for a specific session"""
        user = self.users.get(user_id)
        if not user:
            return SessionPermissions(
                can_join=False,
                can_create_anchors=False,
                can_delete_anchors=False,
                can_moderate=False,
                max_sessions=0
            )
        
        # Default permissions based on roles
        is_admin = "admin" in user.roles
        is_moderator = "moderator" in user.roles
        is_premium = "premium" in user.roles
        
        return SessionPermissions(
            can_join=True,
            can_create_anchors=True,
            can_delete_anchors=is_admin or is_moderator,
            can_moderate=is_admin or is_moderator,
            max_sessions=100 if is_admin else (20 if is_premium else 5)
        )
    
    def require_auth(self, credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer())) -> User:
        """FastAPI dependency for requiring authentication"""
        if not credentials:
            raise HTTPException(401, "Authorization header required")
            
        return self.verify_token(credentials.credentials)
    
    def require_role(self, required_role: str):
        """FastAPI dependency factory for requiring specific roles"""
        def role_checker(user: User = Depends(self.require_auth)) -> User:
            if required_role not in user.roles:
                raise HTTPException(403, f"Role '{required_role}' required")
            return user
        return role_checker
    
    def get_user_stats(self) -> Dict[str, Any]:
        """Get authentication system statistics"""
        active_users = sum(1 for u in self.users.values() if u.is_active)
        total_users = len(self.users)
        active_tokens = len(self.refresh_tokens)
        
        return {
            "total_users": total_users,
            "active_users": active_users,
            "active_refresh_tokens": active_tokens,
            "token_expiry_hours": self.token_expiry_hours
        }

# Global authentication manager instance
auth_manager = AuthenticationManager()

# FastAPI dependencies
async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer())) -> User:
    """Get currently authenticated user"""
    if not credentials:
        raise HTTPException(401, "Authorization header required")
    return auth_manager.verify_token(credentials.credentials)

async def get_admin_user(user: User = Depends(get_current_user)) -> User:
    """Require admin role"""
    if "admin" not in user.roles:
        raise HTTPException(403, "Admin role required")
    return user

async def check_session_access(session_id: str, user: User = Depends(get_current_user)) -> SessionPermissions:
    """Check if user can access a specific session"""
    permissions = auth_manager.get_session_permissions(user.id, session_id)
    if not permissions.can_join:
        raise HTTPException(403, "Access denied to this session")
    return permissions