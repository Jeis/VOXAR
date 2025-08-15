"""
Authentication API Routes for Spatial AR Platform
Provides user registration, login, token refresh, and session management endpoints
"""

from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel, EmailStr, Field
from typing import Dict, Any
from datetime import datetime
import logging

from .auth import auth_manager, get_current_user, get_admin_user, User

logger = logging.getLogger(__name__)

# Create router
auth_router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])

# Request/Response models
class UserRegistrationRequest(BaseModel):
    """User registration request"""
    username: str = Field(..., min_length=3, max_length=50, regex="^[a-zA-Z0-9_-]+$")
    email: EmailStr
    password: str = Field(..., min_length=6, max_length=128)
    
    class Config:
        schema_extra = {
            "example": {
                "username": "john_doe",
                "email": "john@example.com",
                "password": "secure_password_123"
            }
        }

class UserLoginRequest(BaseModel):
    """User login request"""
    username: str
    password: str
    
    class Config:
        schema_extra = {
            "example": {
                "username": "john_doe",
                "password": "secure_password_123"
            }
        }

class TokenRefreshRequest(BaseModel):
    """Token refresh request"""
    refresh_token: str

class AuthTokenResponse(BaseModel):
    """Authentication token response"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 86400  # 24 hours in seconds
    user_id: str
    username: str
    roles: list

class UserProfileResponse(BaseModel):
    """User profile response"""
    id: str
    username: str
    email: str
    roles: list
    created_at: datetime
    last_active: datetime
    is_active: bool

class AuthStatsResponse(BaseModel):
    """Authentication system statistics"""
    total_users: int
    active_users: int
    active_refresh_tokens: int
    token_expiry_hours: int

@auth_router.post("/register", 
                 response_model=AuthTokenResponse,
                 status_code=status.HTTP_201_CREATED,
                 summary="Register new user",
                 description="Create a new user account and return authentication tokens")
async def register_user(request: UserRegistrationRequest) -> AuthTokenResponse:
    """Register a new user account"""
    try:
        # Create user
        user = auth_manager.create_user(
            username=request.username,
            email=request.email,
            password=request.password
        )
        
        # Generate tokens
        access_token = auth_manager.create_access_token(user)
        refresh_token = auth_manager.create_refresh_token(user)
        
        logger.info(f"User registered successfully: {user.username}")
        
        return AuthTokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            user_id=user.id,
            username=user.username,
            roles=user.roles
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Registration failed: {e}")
        raise HTTPException(500, "Registration failed")

@auth_router.post("/login",
                 response_model=AuthTokenResponse,
                 summary="User login",
                 description="Authenticate user and return tokens")
async def login_user(request: UserLoginRequest) -> AuthTokenResponse:
    """Authenticate user and return tokens"""
    try:
        # Authenticate user
        user = auth_manager.authenticate_user(request.username, request.password)
        if not user:
            raise HTTPException(401, "Invalid username or password")
        
        # Generate tokens
        access_token = auth_manager.create_access_token(user)
        refresh_token = auth_manager.create_refresh_token(user)
        
        logger.info(f"User logged in successfully: {user.username}")
        
        return AuthTokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            user_id=user.id,
            username=user.username,
            roles=user.roles
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login failed: {e}")
        raise HTTPException(500, "Login failed")

@auth_router.post("/refresh",
                 response_model=Dict[str, str],
                 summary="Refresh access token",
                 description="Get new access token using refresh token")
async def refresh_token(request: TokenRefreshRequest) -> Dict[str, str]:
    """Refresh access token"""
    try:
        access_token = auth_manager.refresh_access_token(request.refresh_token)
        
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "expires_in": "86400"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Token refresh failed: {e}")
        raise HTTPException(500, "Token refresh failed")

@auth_router.post("/logout",
                 summary="User logout",
                 description="Revoke refresh token and logout user")
async def logout_user(
    request: TokenRefreshRequest,
    current_user: User = Depends(get_current_user)
) -> Dict[str, str]:
    """Logout user and revoke refresh token"""
    try:
        auth_manager.revoke_refresh_token(request.refresh_token)
        logger.info(f"User logged out: {current_user.username}")
        
        return {"message": "Logged out successfully"}
        
    except Exception as e:
        logger.error(f"Logout failed: {e}")
        raise HTTPException(500, "Logout failed")

@auth_router.get("/profile",
                response_model=UserProfileResponse,
                summary="Get user profile",
                description="Get current user profile information")
async def get_user_profile(current_user: User = Depends(get_current_user)) -> UserProfileResponse:
    """Get current user profile"""
    return UserProfileResponse(
        id=current_user.id,
        username=current_user.username,
        email=current_user.email,
        roles=current_user.roles,
        created_at=current_user.created_at,
        last_active=current_user.last_active,
        is_active=current_user.is_active
    )

@auth_router.get("/verify",
                summary="Verify token",
                description="Verify if current token is valid")
async def verify_token(current_user: User = Depends(get_current_user)) -> Dict[str, Any]:
    """Verify current token"""
    return {
        "valid": True,
        "user_id": current_user.id,
        "username": current_user.username,
        "roles": current_user.roles,
        "expires_at": "24h"  # Simplified - in production, calculate actual expiry
    }

@auth_router.get("/stats",
                response_model=AuthStatsResponse,
                summary="Authentication statistics",
                description="Get authentication system statistics (admin only)")
async def get_auth_stats(admin_user: User = Depends(get_admin_user)) -> AuthStatsResponse:
    """Get authentication system statistics (admin only)"""
    stats = auth_manager.get_user_stats()
    return AuthStatsResponse(**stats)

@auth_router.post("/admin/create-user",
                 response_model=UserProfileResponse,
                 summary="Create user (admin)",
                 description="Create user with specific roles (admin only)")
async def admin_create_user(
    request: UserRegistrationRequest,
    roles: list = ["user"],
    admin_user: User = Depends(get_admin_user)
) -> UserProfileResponse:
    """Create user with specific roles (admin only)"""
    try:
        user = auth_manager.create_user(
            username=request.username,
            email=request.email,
            password=request.password,
            roles=roles
        )
        
        logger.info(f"Admin {admin_user.username} created user: {user.username}")
        
        return UserProfileResponse(
            id=user.id,
            username=user.username,
            email=user.email,
            roles=user.roles,
            created_at=user.created_at,
            last_active=user.last_active,
            is_active=user.is_active
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Admin user creation failed: {e}")
        raise HTTPException(500, "User creation failed")

# Health check endpoint for authentication service
@auth_router.get("/health",
                summary="Authentication health check",
                description="Check authentication service health")
async def auth_health_check() -> Dict[str, Any]:
    """Authentication service health check"""
    stats = auth_manager.get_user_stats()
    
    return {
        "status": "healthy",
        "service": "authentication",
        "timestamp": datetime.utcnow().isoformat(),
        "stats": stats
    }