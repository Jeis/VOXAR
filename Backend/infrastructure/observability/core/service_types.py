"""
VOXAR Enterprise Observability - Service Types & Performance Tiers
Core enumerations for service classification and performance requirements
"""

from enum import Enum

class ServiceType(Enum):
    """VOXAR Platform Service Categories"""
    API_GATEWAY = "api-gateway"
    LOCALIZATION = "localization" 
    VPS_ENGINE = "vps-engine"
    CLOUD_ANCHORS = "cloud-anchors"
    MAPPING_PROCESSOR = "mapping-processor"
    MULTIPLAYER = "nakama-multiplayer"

class PerformanceTier(Enum):
    """Performance criticality levels for AR operations"""
    CRITICAL_60FPS = "critical_60fps"      # <16ms response time
    HIGH_PERFORMANCE = "high_performance"   # <100ms response time
    STANDARD = "standard"                   # <500ms response time
    BACKGROUND = "background"               # <5s response time