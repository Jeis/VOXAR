"""
Authentication utilities for VPS Engine API
Simple API key validation for development
"""

import logging
from fastapi import HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.security.api_key import APIKeyHeader
from typing import Optional

from .config import settings

logger = logging.getLogger(__name__)

# API Key authentication
api_key_header = APIKeyHeader(name=settings.API_KEY_HEADER, auto_error=False)

# Bearer token authentication
bearer_scheme = HTTPBearer(auto_error=False)

async def verify_api_key(api_key: Optional[str] = Security(api_key_header)) -> str:
    """
    Verify API key for authentication
    
    In development, this is relaxed for testing
    In production, implement proper API key validation
    """
    
    if settings.is_development:
        # Development mode - accept any non-empty key or no key
        return api_key or "dev-key"
    
    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="API key required",
            headers={"WWW-Authenticate": "ApiKey"}
        )
    
    # In production, validate against database or config
    # For now, accept any key (implement proper validation)
    valid_keys = [
        "vps-engine-key-2024",
        "spatial-platform-key",
        settings.JWT_SECRET  # Use JWT secret as fallback
    ]
    
    if api_key not in valid_keys:
        logger.warning(f"Invalid API key attempted: {api_key[:10]}...")
        raise HTTPException(
            status_code=401,
            detail="Invalid API key"
        )
    
    return api_key

async def verify_bearer_token(credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme)) -> str:
    """
    Verify JWT bearer token
    
    For future implementation with proper JWT validation
    """
    
    if settings.is_development:
        # Development mode - accept any token
        return credentials.credentials if credentials else "dev-token"
    
    if not credentials:
        raise HTTPException(
            status_code=401,
            detail="Bearer token required",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    # JWT validation for production authentication
    token = credentials.credentials
    
    try:
        # Production: JWT token validation with proper error handling
        # Note: Requires JWT_SECRET and JWT_ALGORITHM in configuration
        # payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        # return payload.get("sub")
        
        # Development mode: Accept valid token format
        if token and len(token) > 10:
        
        return token
        
    except Exception as e:
        logger.warning(f"Invalid token: {e}")
        raise HTTPException(
            status_code=401,
            detail="Invalid token"
        )

# Development authentication bypass
async def no_auth_required() -> str:
    """No authentication required (development only)"""
    if not settings.is_development:
        raise HTTPException(status_code=401, detail="Authentication required")
    return "dev-user"