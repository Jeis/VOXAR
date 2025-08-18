"""
Intelligent request routing
Routes requests to appropriate backend services
"""

import aiohttp
import logging
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from typing import Dict, Any, Optional

from .service_discovery import ServiceRegistry

logger = logging.getLogger(__name__)


class RequestRouter:
    """Routes API requests to appropriate backend services"""
    
    def __init__(self, service_registry: ServiceRegistry):
        self.registry = service_registry
        self.session = None
        
        # Define routing rules
        self.routing_rules = {
            "/api/localization": "localization",
            "/api/slam": "localization", 
            "/api/vio": "localization",
            "/api/pose": "localization",
            "/api/maps": "mapping",
            "/api/reconstruction": "mapping",
            "/api/multiplayer": "nakama",
            "/api/auth": "nakama"
        }
    
    async def initialize(self):
        """Initialize HTTP client for proxying"""
        self.session = aiohttp.ClientSession()
    
    async def shutdown(self):
        """Clean shutdown"""
        if self.session:
            await self.session.close()
    
    def get_target_service(self, path: str) -> Optional[str]:
        """Determine which service should handle this request"""
        for route_prefix, service_name in self.routing_rules.items():
            if path.startswith(route_prefix):
                return service_name
        
        return None
    
    async def route_request(self, request: Request, path: str) -> JSONResponse:
        """Route request to appropriate backend service"""
        
        # Determine target service
        service_name = self.get_target_service(path)
        if not service_name:
            raise HTTPException(404, f"No service found for path: {path}")
        
        # Check if service is available
        if not self.registry.is_service_healthy(service_name):
            raise HTTPException(503, f"Service {service_name} is not available")
        
        service_url = self.registry.get_service_url(service_name)
        if not service_url:
            raise HTTPException(503, f"Service {service_name} URL not available")
        
        # Transform path for backend service
        backend_path = self._transform_path(path, service_name)
        target_url = f"{service_url}{backend_path}"
        
        try:
            # Proxy the request
            response_data = await self._proxy_request(request, target_url)
            return JSONResponse(content=response_data)
            
        except aiohttp.ClientError as e:
            logger.error(f"Failed to proxy request to {target_url}: {e}")
            raise HTTPException(502, f"Backend service error: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error routing to {target_url}: {e}")
            raise HTTPException(500, f"Internal routing error: {str(e)}")
    
    def _transform_path(self, original_path: str, service_name: str) -> str:
        """Transform API path to backend service path"""
        
        if service_name == "localization":
            # /api/localization/status -> /status
            # /api/slam/init -> /slam/init
            # /api/pose/current -> /pose/current
            if original_path.startswith("/api/localization"):
                return original_path.replace("/api/localization", "")
            elif original_path.startswith("/api/slam"):
                return original_path.replace("/api", "")
            elif original_path.startswith("/api/vio"):
                return original_path.replace("/api", "")
            elif original_path.startswith("/api/pose"):
                return original_path.replace("/api", "")
                
        elif service_name == "mapping":
            # /api/maps/create -> /maps/create
            # /api/reconstruction/start -> /reconstruction/start
            return original_path.replace("/api", "")
            
        elif service_name == "nakama":
            # /api/multiplayer/session -> /v2/session (Nakama API format)
            # /api/auth/login -> /v2/account/authenticate
            if original_path.startswith("/api/multiplayer"):
                return original_path.replace("/api/multiplayer", "/v2")
            elif original_path.startswith("/api/auth"):
                return original_path.replace("/api/auth", "/v2/account")
        
        # Default: just remove /api prefix
        return original_path.replace("/api", "") or "/"
    
    async def _proxy_request(self, request: Request, target_url: str) -> Dict[str, Any]:
        """Proxy HTTP request to backend service"""
        
        # Prepare headers (exclude hop-by-hop headers)
        headers = {}
        for key, value in request.headers.items():
            if key.lower() not in ['host', 'content-length', 'connection']:
                headers[key] = value
        
        # Get request body if present
        body = None
        if request.method in ['POST', 'PUT', 'PATCH']:
            body = await request.body()
        
        # Make request to backend service
        async with self.session.request(
            method=request.method,
            url=target_url,
            headers=headers,
            data=body,
            params=dict(request.query_params)
        ) as response:
            
            # Handle different response types
            content_type = response.headers.get('content-type', '')
            
            if 'application/json' in content_type:
                return await response.json()
            else:
                # For non-JSON responses, return as text
                text_content = await response.text()
                return {"content": text_content, "content_type": content_type}
    
    def get_routing_info(self) -> Dict[str, Any]:
        """Get information about current routing configuration"""
        return {
            "routing_rules": self.routing_rules,
            "available_services": self.registry.get_healthy_services(),
            "service_health": {
                name: self.registry.is_service_healthy(name) 
                for name in ["localization", "mapping", "nakama"]
            }
        }