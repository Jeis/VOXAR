"""
Map Matcher - Match features against 3D maps for localization
Efficient spatial indexing and feature matching
"""

import logging
import numpy as np
from typing import Dict, List, Tuple, Optional, Any
import asyncio
from dataclasses import dataclass
import time

logger = logging.getLogger(__name__)

@dataclass
class MapData:
    """3D map data container"""
    id: str
    name: str
    point_cloud: np.ndarray  # Nx3 points
    features: np.ndarray     # Nxdescriptor_size
    feature_points: np.ndarray  # Feature 3D locations
    quality_score: float
    location: Optional[Tuple[float, float]] = None  # lat, lng
    created_at: str = ""

class MapMatcher:
    """
    Efficient map matching for VPS localization
    Handles feature matching against 3D map databases
    """
    
    def __init__(self, db_service, cache_service):
        self.db_service = db_service
        self.cache_service = cache_service
        
        # Matching configuration
        self.config = {
            'max_candidate_maps': 5,
            'feature_match_threshold': 0.7,
            'spatial_search_radius': 1000.0,  # meters
            'min_map_quality': 0.5,
            'cache_ttl': 3600  # 1 hour
        }
        
        # Performance tracking
        self.stats = {
            'total_matches': 0,
            'cache_hits': 0,
            'successful_matches': 0,
            'average_match_time': 0.0
        }

    async def find_candidate_maps(self, features, approximate_location: Optional[Tuple[float, float]] = None,
                                 map_id: Optional[str] = None) -> List[Dict]:
        """
        Find candidate maps for feature matching
        
        Args:
            features: Extracted features from query image
            approximate_location: Optional GPS coordinates (lat, lng)
            map_id: Optional specific map ID
            
        Returns:
            List of candidate map data
        """
        try:
            start_time = time.time()
            self.stats['total_matches'] += 1
            
            # Check cache first
            cache_key = f"candidates_{hash(str(approximate_location))}_{map_id}"
            cached_candidates = await self.cache_service.get(cache_key)
            
            if cached_candidates:
                self.stats['cache_hits'] += 1
                logger.debug("Using cached map candidates")
                return cached_candidates
            
            candidates = []
            
            if map_id:
                # Get specific map
                map_data = await self.db_service.get_map_data(map_id)
                if map_data:
                    candidates.append(map_data)
            else:
                # Find maps based on location or get all available
                if approximate_location:
                    candidates = await self._find_maps_by_location(approximate_location)
                else:
                    candidates = await self.db_service.get_all_maps()
            
            # Filter by quality
            candidates = [m for m in candidates if m.get('quality_score', 0) >= self.config['min_map_quality']]
            
            # Limit candidates
            candidates = candidates[:self.config['max_candidate_maps']]
            
            # Cache results
            await self.cache_service.set(cache_key, candidates, ttl=self.config['cache_ttl'])
            
            match_time = time.time() - start_time
            self._update_match_time(match_time)
            
            logger.debug(f"Found {len(candidates)} candidate maps in {match_time:.3f}s")
            
            return candidates
            
        except Exception as e:
            logger.error(f"Failed to find candidate maps: {e}")
            return []

    async def _find_maps_by_location(self, location: Tuple[float, float]) -> List[Dict]:
        """Find maps within spatial search radius"""
        
        lat, lng = location
        radius = self.config['spatial_search_radius']
        
        # Query database for maps within radius
        maps = await self.db_service.find_maps_by_location(lat, lng, radius)
        
        # Sort by distance (if location data available)
        maps_with_distance = []
        for map_data in maps:
            if map_data.get('location'):
                map_lat, map_lng = map_data['location']
                distance = self._calculate_distance(lat, lng, map_lat, map_lng)
                maps_with_distance.append((distance, map_data))
            else:
                maps_with_distance.append((float('inf'), map_data))
        
        # Sort by distance and return map data
        maps_with_distance.sort(key=lambda x: x[0])
        return [map_data for _, map_data in maps_with_distance]

    def _calculate_distance(self, lat1: float, lng1: float, lat2: float, lng2: float) -> float:
        """Calculate distance between two GPS coordinates in meters"""
        
        # Haversine formula
        from math import radians, cos, sin, asin, sqrt
        
        # Convert to radians
        lat1, lng1, lat2, lng2 = map(radians, [lat1, lng1, lat2, lng2])
        
        # Haversine formula
        dlat = lat2 - lat1
        dlng = lng2 - lng1
        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlng/2)**2
        c = 2 * asin(sqrt(a))
        
        # Earth radius in meters
        r = 6371000
        
        return c * r

    async def match_features(self, query_features, map_data: Dict) -> List[Dict]:
        """
        Match query features against map features
        
        Args:
            query_features: Features extracted from query image
            map_data: Map data containing 3D features
            
        Returns:
            List of 2D-3D feature correspondences
        """
        try:
            start_time = time.time()
            
            # Get map features
            map_features = map_data.get('features', np.array([]))
            map_points_3d = map_data.get('feature_points', np.array([]))
            
            if len(map_features) == 0 or len(query_features.descriptors) == 0:
                return []
            
            # Perform feature matching
            matches = await self._match_descriptors(
                query_features.descriptors, 
                map_features
            )
            
            # Convert to 2D-3D correspondences
            correspondences = []
            for match in matches:
                query_idx, map_idx, distance = match
                
                # Get 2D image point
                kp = query_features.keypoints[query_idx]
                image_x, image_y = kp.pt
                
                # Get 3D world point
                if map_idx < len(map_points_3d):
                    world_point = map_points_3d[map_idx]
                    
                    correspondence = {
                        'image_x': image_x,
                        'image_y': image_y,
                        'world_x': world_point[0],
                        'world_y': world_point[1],
                        'world_z': world_point[2],
                        'distance': distance,
                        'confidence': 1.0 - distance,  # Simple confidence
                        'query_idx': query_idx,
                        'map_idx': map_idx
                    }
                    
                    correspondences.append(correspondence)
            
            match_time = time.time() - start_time
            logger.debug(f"Matched {len(correspondences)} features in {match_time:.3f}s")
            
            if correspondences:
                self.stats['successful_matches'] += 1
            
            return correspondences
            
        except Exception as e:
            logger.error(f"Feature matching failed: {e}")
            return []

    async def _match_descriptors(self, query_descriptors: np.ndarray, 
                                map_descriptors: np.ndarray) -> List[Tuple[int, int, float]]:
        """Match descriptors using brute force or FLANN"""
        
        import cv2
        
        # Use appropriate matcher based on descriptor type
        if query_descriptors.dtype == np.uint8:
            # Binary descriptors (ORB, AKAZE)
            matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)
        else:
            # Float descriptors (SIFT, SURF)
            matcher = cv2.BFMatcher(cv2.NORM_L2, crossCheck=False)
        
        # Perform matching with ratio test
        raw_matches = matcher.knnMatch(query_descriptors, map_descriptors, k=2)
        
        good_matches = []
        for match_pair in raw_matches:
            if len(match_pair) == 2:
                m, n = match_pair
                # Lowe's ratio test
                if m.distance < self.config['feature_match_threshold'] * n.distance:
                    good_matches.append((m.queryIdx, m.trainIdx, m.distance))
        
        return good_matches

    async def process_new_map(self, map_id: str, map_request) -> bool:
        """Process and index a newly uploaded map"""
        
        try:
            logger.info(f"Processing new map: {map_id}")
            
            # This would typically:
            # 1. Load point cloud data
            # 2. Extract features from reference images
            # 3. Build spatial index
            # 4. Store in database
            
            # Placeholder implementation
            map_data = {
                'id': map_id,
                'name': map_request.map_name,
                'location': (map_request.location_latitude, map_request.location_longitude)
                           if map_request.location_latitude and map_request.location_longitude else None,
                'description': map_request.description,
                'quality_score': 0.8,  # Placeholder
                'feature_count': 0,    # Will be calculated
                'point_count': 0,      # Will be calculated
                'status': 'processing',
                'created_at': time.time()
            }
            
            # Store map metadata
            await self.db_service.store_map_metadata(map_id, map_data)
            
            logger.info(f"Map {map_id} processing initiated")
            return True
            
        except Exception as e:
            logger.error(f"Failed to process map {map_id}: {e}")
            return False

    def _update_match_time(self, match_time: float):
        """Update average match time statistics"""
        
        current_avg = self.stats['average_match_time']
        total_matches = self.stats['total_matches']
        
        self.stats['average_match_time'] = \
            (current_avg * (total_matches - 1) + match_time) / total_matches

    def get_statistics(self) -> Dict[str, Any]:
        """Get map matching statistics"""
        
        cache_hit_rate = 0.0
        success_rate = 0.0
        
        if self.stats['total_matches'] > 0:
            cache_hit_rate = self.stats['cache_hits'] / self.stats['total_matches']
            success_rate = self.stats['successful_matches'] / self.stats['total_matches']
        
        return {
            **self.stats,
            'cache_hit_rate': cache_hit_rate,
            'success_rate': success_rate,
            'config': self.config
        }