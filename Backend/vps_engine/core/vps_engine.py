"""
VPS Engine Core - Main Visual Positioning System engine
Handles 3D reconstruction, feature matching, and pose estimation
"""

import asyncio
import logging
import numpy as np
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
import cv2
from datetime import datetime, timedelta
import json

from .pose_estimator import PoseEstimator
from .map_matcher import MapMatcher
from .feature_extractor import FeatureExtractor
from .point_cloud_processor import PointCloudProcessor
from services.database_service import DatabaseService
from services.cache_service import CacheService
from services.storage_service import StorageService
from utils.config import settings
from utils.metrics import VPSMetrics

logger = logging.getLogger(__name__)

@dataclass
class VPSResult:
    """VPS localization result"""
    pose: np.ndarray  # 4x4 transformation matrix
    confidence: float
    error_estimate: float  # meters
    processing_time: float  # seconds
    map_id: str
    feature_matches: int
    quality_score: float
    timestamp: datetime

class VPSEngine:
    """
    Main VPS Engine for visual positioning and localization
    Provides centimeter-level accuracy for AR applications
    """
    
    def __init__(self):
        self.pose_estimator = None
        self.map_matcher = None
        self.feature_extractor = None
        self.point_cloud_processor = None
        self.db_service = None
        self.cache_service = None
        self.storage_service = None
        self.metrics = None
        self.is_initialized = False
        
        # Engine configuration
        self.config = {
            'min_feature_matches': 50,
            'max_reprojection_error': 2.0,  # pixels
            'confidence_threshold': 0.7,
            'processing_timeout': 30.0,  # seconds
            'cache_ttl': 3600,  # 1 hour
            'quality_threshold': 0.8
        }
        
        # Performance tracking
        self.performance_stats = {
            'total_requests': 0,
            'successful_localizations': 0,
            'failed_localizations': 0,
            'average_processing_time': 0.0,
            'last_updated': datetime.utcnow()
        }

    async def initialize(self) -> None:
        """Initialize VPS engine components"""
        try:
            logger.info("Initializing VPS Engine components...")
            
            # Initialize services
            self.db_service = DatabaseService()
            await self.db_service.initialize()
            
            self.cache_service = CacheService()
            await self.cache_service.initialize()
            
            self.storage_service = StorageService()
            await self.storage_service.initialize()
            
            # Initialize core components
            self.feature_extractor = FeatureExtractor()
            self.point_cloud_processor = PointCloudProcessor()
            self.map_matcher = MapMatcher(self.db_service, self.cache_service)
            self.pose_estimator = PoseEstimator()
            
            # Initialize metrics
            self.metrics = VPSMetrics()
            
            self.is_initialized = True
            logger.info("✅ VPS Engine initialized successfully")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize VPS Engine: {e}")
            raise

    async def localize(self, image: np.ndarray, camera_intrinsics: np.ndarray, 
                      approximate_location: Optional[Tuple[float, float]] = None,
                      map_id: Optional[str] = None) -> VPSResult:
        """
        Perform visual localization using the provided image
        
        Args:
            image: Input camera image (RGB)
            camera_intrinsics: Camera intrinsic matrix (3x3)
            approximate_location: Optional GPS coordinates (lat, lng)
            map_id: Optional specific map to match against
            
        Returns:
            VPSResult with pose and metadata
        """
        start_time = datetime.utcnow()
        self.performance_stats['total_requests'] += 1
        
        try:
            if not self.is_initialized:
                raise RuntimeError("VPS Engine not initialized")
            
            logger.info(f"Starting VPS localization (map_id: {map_id})")
            
            # Extract features from input image
            features = await self.feature_extractor.extract_features(image)
            if len(features.keypoints) < self.config['min_feature_matches']:
                raise ValueError(f"Insufficient features: {len(features.keypoints)}")
            
            # Find candidate maps
            candidate_maps = await self.map_matcher.find_candidate_maps(
                features, approximate_location, map_id
            )
            
            if not candidate_maps:
                raise ValueError("No candidate maps found for localization")
            
            best_result = None
            best_confidence = 0.0
            
            # Try localization against each candidate map
            for map_data in candidate_maps:
                try:
                    result = await self._localize_against_map(
                        features, camera_intrinsics, map_data
                    )
                    
                    if result.confidence > best_confidence:
                        best_result = result
                        best_confidence = result.confidence
                        
                except Exception as e:
                    logger.warning(f"Localization failed for map {map_data['id']}: {e}")
                    continue
            
            if not best_result or best_confidence < self.config['confidence_threshold']:
                self.performance_stats['failed_localizations'] += 1
                raise ValueError(f"Localization failed: confidence {best_confidence}")
            
            # Update performance stats
            processing_time = (datetime.utcnow() - start_time).total_seconds()
            self.performance_stats['successful_localizations'] += 1
            self._update_processing_time(processing_time)
            
            # Cache result
            await self._cache_localization_result(best_result, image)
            
            # Update metrics
            self.metrics.record_localization(
                success=True,
                processing_time=processing_time,
                confidence=best_confidence,
                feature_matches=best_result.feature_matches
            )
            
            logger.info(f"✅ VPS localization successful: confidence={best_confidence:.3f}, "
                       f"error={best_result.error_estimate:.3f}m, time={processing_time:.3f}s")
            
            return best_result
            
        except Exception as e:
            processing_time = (datetime.utcnow() - start_time).total_seconds()
            self.performance_stats['failed_localizations'] += 1
            self.metrics.record_localization(
                success=False, 
                processing_time=processing_time,
                error=str(e)
            )
            logger.error(f"❌ VPS localization failed: {e}")
            raise

    async def _localize_against_map(self, features, camera_intrinsics: np.ndarray, 
                                   map_data: Dict) -> VPSResult:
        """Perform localization against a specific map"""
        
        # Match features against map
        matches = await self.map_matcher.match_features(features, map_data)
        
        if len(matches) < self.config['min_feature_matches']:
            raise ValueError(f"Insufficient matches: {len(matches)}")
        
        # Estimate pose using PnP
        pose, inlier_matches = await self.pose_estimator.estimate_pose(
            matches, camera_intrinsics
        )
        
        # Calculate confidence and error estimate
        confidence = self._calculate_confidence(inlier_matches, matches)
        error_estimate = self._calculate_error_estimate(inlier_matches, camera_intrinsics)
        quality_score = self._calculate_quality_score(inlier_matches, map_data)
        
        return VPSResult(
            pose=pose,
            confidence=confidence,
            error_estimate=error_estimate,
            processing_time=0.0,  # Will be set by caller
            map_id=map_data['id'],
            feature_matches=len(inlier_matches),
            quality_score=quality_score,
            timestamp=datetime.utcnow()
        )

    def _calculate_confidence(self, inlier_matches: List, total_matches: List) -> float:
        """Calculate localization confidence score"""
        if not total_matches:
            return 0.0
        
        inlier_ratio = len(inlier_matches) / len(total_matches)
        min_matches_ratio = min(len(inlier_matches) / self.config['min_feature_matches'], 1.0)
        
        # Weighted confidence based on inlier ratio and absolute match count
        confidence = 0.7 * inlier_ratio + 0.3 * min_matches_ratio
        return min(confidence, 1.0)

    def _calculate_error_estimate(self, inlier_matches: List, 
                                 camera_intrinsics: np.ndarray) -> float:
        """Estimate localization error in meters"""
        if not inlier_matches:
            return float('inf')
        
        # Simple heuristic based on reprojection error and feature distribution
        reprojection_errors = [match.get('reprojection_error', 0) for match in inlier_matches]
        avg_reprojection_error = np.mean(reprojection_errors)
        
        # Convert pixel error to world error (rough approximation)
        focal_length = (camera_intrinsics[0, 0] + camera_intrinsics[1, 1]) / 2
        error_meters = avg_reprojection_error / focal_length * 0.1  # Approximation
        
        return max(error_meters, 0.01)  # Minimum 1cm error

    def _calculate_quality_score(self, inlier_matches: List, map_data: Dict) -> float:
        """Calculate overall quality score for the localization"""
        if not inlier_matches:
            return 0.0
        
        # Factors: match distribution, map quality, feature strength
        match_distribution = self._calculate_match_distribution(inlier_matches)
        map_quality = map_data.get('quality_score', 0.5)
        feature_strength = np.mean([match.get('strength', 0) for match in inlier_matches])
        
        quality = 0.4 * match_distribution + 0.3 * map_quality + 0.3 * feature_strength
        return min(quality, 1.0)

    def _calculate_match_distribution(self, matches: List) -> float:
        """Calculate how well distributed the matches are across the image"""
        if len(matches) < 4:
            return 0.0
        
        # Simple distribution score based on bounding box coverage
        points = np.array([[m['image_x'], m['image_y']] for m in matches])
        bbox_area = (points[:, 0].max() - points[:, 0].min()) * \
                   (points[:, 1].max() - points[:, 1].min())
        
        # Normalize by image area (assuming 640x480 for now)
        normalized_area = bbox_area / (640 * 480)
        return min(normalized_area, 1.0)

    async def _cache_localization_result(self, result: VPSResult, image: np.ndarray):
        """Cache localization result for future use"""
        try:
            cache_key = f"vps_result_{result.map_id}_{hash(image.tobytes())}"
            cache_data = {
                'pose': result.pose.tolist(),
                'confidence': result.confidence,
                'error_estimate': result.error_estimate,
                'map_id': result.map_id,
                'timestamp': result.timestamp.isoformat()
            }
            await self.cache_service.set(cache_key, cache_data, ttl=self.config['cache_ttl'])
            
        except Exception as e:
            logger.warning(f"Failed to cache localization result: {e}")

    def _update_processing_time(self, processing_time: float):
        """Update rolling average processing time"""
        current_avg = self.performance_stats['average_processing_time']
        total_requests = self.performance_stats['total_requests']
        
        # Rolling average
        self.performance_stats['average_processing_time'] = \
            (current_avg * (total_requests - 1) + processing_time) / total_requests

    async def get_performance_stats(self) -> Dict[str, Any]:
        """Get current performance statistics"""
        success_rate = 0.0
        if self.performance_stats['total_requests'] > 0:
            success_rate = self.performance_stats['successful_localizations'] / \
                          self.performance_stats['total_requests']
        
        return {
            **self.performance_stats,
            'success_rate': success_rate,
            'uptime': (datetime.utcnow() - self.performance_stats['last_updated']).total_seconds(),
            'is_initialized': self.is_initialized
        }

    async def health_check(self) -> bool:
        """Perform health check on all components"""
        try:
            if not self.is_initialized:
                return False
            
            # Check database connection
            if not await self.db_service.health_check():
                return False
            
            # Check cache connection
            if not await self.cache_service.health_check():
                return False
            
            # Check storage service
            if not await self.storage_service.health_check():
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False

    async def get_metrics(self) -> Dict[str, Any]:
        """Get comprehensive metrics"""
        if not self.metrics:
            return {}
        
        performance_stats = await self.get_performance_stats()
        return {
            'performance': performance_stats,
            'metrics': self.metrics.get_metrics(),
            'config': self.config,
            'timestamp': datetime.utcnow().isoformat()
        }

    async def shutdown(self):
        """Shutdown VPS engine and cleanup resources"""
        logger.info("Shutting down VPS Engine...")
        
        try:
            if self.db_service:
                await self.db_service.shutdown()
            
            if self.cache_service:
                await self.cache_service.shutdown()
            
            if self.storage_service:
                await self.storage_service.shutdown()
            
            self.is_initialized = False
            logger.info("✅ VPS Engine shutdown complete")
            
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")