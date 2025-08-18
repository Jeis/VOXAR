"""
VOXAR Enterprise Observability - Resource Management
OpenTelemetry resource creation and configuration for VOXAR services
"""

import os
from opentelemetry.sdk.resources import Resource
from opentelemetry.semconv.resource import ResourceAttributes

from core.service_types import ServiceType, PerformanceTier

def get_default_resource_attributes() -> dict:
    """Get default VOXAR platform resource attributes"""
    return {
        ResourceAttributes.SERVICE_NAMESPACE: "voxar.platform",
        
        # VOXAR-specific attributes
        "voxar.platform.name": "spatial-ar-enterprise",
        "voxar.platform.version": "2.0.0",
        
        # Technical attributes
        "container.runtime": "docker",
        "orchestration.system": "docker-compose",
        
        # Business attributes
        "business.domain": "spatial-computing",
        "business.use_case": "enterprise-ar"
    }

def create_resource(
    service_type: ServiceType,
    service_name: str,
    service_version: str = "1.0.0",
    environment: str = None,
    performance_tier: PerformanceTier = PerformanceTier.STANDARD
) -> Resource:
    """Create comprehensive resource description for VOXAR service"""
    
    environment = environment or os.getenv("ENVIRONMENT", "development")
    
    attributes = {
        ResourceAttributes.SERVICE_NAME: service_name,
        ResourceAttributes.SERVICE_VERSION: service_version,
        ResourceAttributes.DEPLOYMENT_ENVIRONMENT: environment,
        
        # VOXAR-specific attributes
        "voxar.service.type": service_type.value,
        "voxar.performance.tier": performance_tier.value,
        
        **get_default_resource_attributes()
    }
    
    # Add service-specific attributes
    if service_type == ServiceType.API_GATEWAY:
        attributes.update({
            "component.type": "gateway",
            "component.role": "routing",
            "gateway.type": "fastapi"
        })
    elif service_type == ServiceType.LOCALIZATION:
        attributes.update({
            "component.type": "ar-engine",
            "component.role": "tracking",
            "ar.framework": "custom",
            "ar.capability": "6dof-tracking"
        })
    elif service_type == ServiceType.VPS_ENGINE:
        attributes.update({
            "component.type": "computer-vision",
            "component.role": "positioning",
            "cv.framework": "colmap",
            "cv.capability": "visual-localization"
        })
    elif service_type == ServiceType.CLOUD_ANCHORS:
        attributes.update({
            "component.type": "spatial-database",
            "component.role": "persistence",
            "spatial.capability": "anchor-management"
        })
    elif service_type == ServiceType.MAPPING_PROCESSOR:
        attributes.update({
            "component.type": "3d-reconstruction",
            "component.role": "mapping",
            "reconstruction.framework": "colmap",
            "processing.type": "batch"
        })
        
    return Resource.create(attributes)