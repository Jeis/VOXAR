"""
Service discovery and health monitoring
Tracks available backend services
"""

import asyncio
import aiohttp
import logging
from typing import Dict, List, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class ServiceInfo:
    def __init__(self, name: str, url: str, health_endpoint: str = "/health"):
        self.name = name
        self.url = url.rstrip('/')
        self.health_endpoint = health_endpoint
        self.is_healthy = False
        self.last_check = None
        self.response_time = None
        
    @property
    def health_url(self):
        return f"{self.url}{self.health_endpoint}"


class ServiceRegistry:
    """Manages backend service discovery and health monitoring"""
    
    def __init__(self, check_interval: int = 30):
        self.services: Dict[str, ServiceInfo] = {}
        self.check_interval = check_interval
        self.session = None
        self._monitoring_task = None
        
    async def initialize(self):
        """Start service registry and health monitoring"""
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5))
        
        # Register known services
        await self._register_default_services()
        
        # Start health monitoring
        self._monitoring_task = asyncio.create_task(self._monitor_services())
        logger.info("Service registry initialized")
    
    async def shutdown(self):
        """Clean shutdown"""
        if self._monitoring_task:
            self._monitoring_task.cancel()
            
        if self.session:
            await self.session.close()
    
    async def _register_default_services(self):
        """Register our known backend services"""
        services = [
            ServiceInfo("localization", "http://localization:8080"),
            ServiceInfo("nakama", "http://nakama:7350", "/"),
            ServiceInfo("mapping", "http://mapping-processor:8080"),
        ]
        
        for service in services:
            self.services[service.name] = service
            logger.info(f"Registered service: {service.name} -> {service.url}")
    
    async def _monitor_services(self):
        """Background task to monitor service health"""
        while True:
            try:
                await self._check_all_services()
                await asyncio.sleep(self.check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Service monitoring error: {e}")
                await asyncio.sleep(5)
    
    async def _check_all_services(self):
        """Check health of all registered services"""
        tasks = []
        for service in self.services.values():
            tasks.append(self._check_service_health(service))
        
        await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _check_service_health(self, service: ServiceInfo):
        """Check health of a single service"""
        try:
            start_time = asyncio.get_event_loop().time()
            
            async with self.session.get(service.health_url) as response:
                end_time = asyncio.get_event_loop().time()
                
                service.response_time = (end_time - start_time) * 1000  # ms
                service.is_healthy = response.status == 200
                service.last_check = datetime.now()
                
                if service.is_healthy:
                    logger.debug(f"Service {service.name} healthy ({service.response_time:.1f}ms)")
                else:
                    logger.warning(f"Service {service.name} unhealthy (status: {response.status})")
                    
        except Exception as e:
            service.is_healthy = False
            service.last_check = datetime.now()
            service.response_time = None
            logger.warning(f"Service {service.name} check failed: {e}")
    
    def get_service(self, name: str) -> Optional[ServiceInfo]:
        """Get service info by name"""
        return self.services.get(name)
    
    def get_healthy_services(self) -> List[ServiceInfo]:
        """Get list of healthy services"""
        return [service for service in self.services.values() if service.is_healthy]
    
    def is_service_healthy(self, name: str) -> bool:
        """Check if specific service is healthy"""
        service = self.services.get(name)
        return service.is_healthy if service else False
    
    def get_service_url(self, name: str) -> Optional[str]:
        """Get URL for a healthy service"""
        service = self.services.get(name)
        if service and service.is_healthy:
            return service.url
        return None
    
    def get_status_summary(self) -> Dict:
        """Get summary of all services"""
        services_status = {}
        
        for name, service in self.services.items():
            services_status[name] = {
                "url": service.url,
                "healthy": service.is_healthy,
                "last_check": service.last_check.isoformat() if service.last_check else None,
                "response_time_ms": service.response_time
            }
        
        healthy_count = len(self.get_healthy_services())
        total_count = len(self.services)
        
        return {
            "services": services_status,
            "summary": {
                "total_services": total_count,
                "healthy_services": healthy_count,
                "health_ratio": healthy_count / total_count if total_count > 0 else 0
            }
        }