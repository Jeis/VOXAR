"""
Authentication utilities for Cloud Anchor Service API
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
        "cloud-anchor-key-2024",
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