"""
VOXAR Spatial Mapping - Image Matcher
Enterprise-grade feature matching for 3D reconstruction
"""

import os
import logging
import subprocess
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime

import numpy as np
import cv2

logger = logging.getLogger(__name__)

@dataclass
class MatchingConfig:
    """Image matching configuration"""
    matcher_type: str = "exhaustive"  # exhaustive, sequential, spatial
    max_distance: float = 0.7
    cross_check: bool = True
    max_ratio: float = 0.8
    max_error: float = 4.0
    confidence: float = 0.999
    max_num_matches: int = 32768
    min_num_matches: int = 15
    enable_gpu: bool = True
    timeout: int = 7200

@dataclass
class MatchingResult:
    """Image matching results"""
    num_pairs: int
    num_matches: int
    avg_matches_per_pair: float
    matching_time: float
    success: bool
    error: Optional[str] = None

class ImageMatcher:
    """Enterprise COLMAP image matcher"""
    
    def __init__(self, config: MatchingConfig, colmap_path: str = None):
        self.config = config
        self.colmap_path = colmap_path or os.environ.get('COLMAP_EXE', '/usr/bin/colmap')
        self._verify_colmap()
    
    def _verify_colmap(self):
        """Verify COLMAP installation"""
        try:
            result = subprocess.run([self.colmap_path, '--help'], 
                                  capture_output=True, text=True, timeout=10)
            if result.returncode != 0:
                raise RuntimeError("COLMAP not found or not working")
            logger.info("COLMAP installation verified for matching")
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            raise RuntimeError(f"COLMAP validation failed: {e}")
    
    def match_features(self, database_path: Path) -> MatchingResult:
        """Match features between all image pairs"""
        start_time = datetime.now()
        
        try:
            if self.config.matcher_type == "exhaustive":
                return self._exhaustive_matching(database_path, start_time)
            elif self.config.matcher_type == "sequential":
                return self._sequential_matching(database_path, start_time)
            else:
                raise ValueError(f"Unknown matcher type: {self.config.matcher_type}")
                
        except Exception as e:
            matching_time = (datetime.now() - start_time).total_seconds()
            logger.error(f"Feature matching failed: {e}")
            return MatchingResult(0, 0, 0.0, matching_time, False, str(e))
    
    def _exhaustive_matching(self, database_path: Path, start_time: datetime) -> MatchingResult:
        """Perform exhaustive matching between all image pairs"""
        
        cmd = [
            self.colmap_path, 'exhaustive_matcher',
            '--database_path', str(database_path),
            '--SiftMatching.max_distance', str(self.config.max_distance),
            '--SiftMatching.max_error', str(self.config.max_error),
            '--SiftMatching.confidence', str(self.config.confidence),
            '--SiftMatching.max_num_matches', str(self.config.max_num_matches),
            '--SiftMatching.cross_check', str(int(self.config.cross_check)),
        ]
        
        if self.config.enable_gpu:
            cmd.extend(['--SiftMatching.use_gpu', '1'])
        
        try:
            logger.info(f"Starting exhaustive matching: {' '.join(cmd)}")
            result = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=self.config.timeout
            )
            
            if result.returncode != 0:
                raise RuntimeError(f"Exhaustive matching failed: {result.stderr}")
            
            matching_time = (datetime.now() - start_time).total_seconds()
            logger.info(f"Exhaustive matching completed in {matching_time:.2f}s")
            
            # Parse results from database
            return self._parse_matching_results(database_path, matching_time)
            
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"Matching timed out after {self.config.timeout}s")
    
    def _sequential_matching(self, database_path: Path, start_time: datetime) -> MatchingResult:
        """Perform sequential matching between consecutive images"""
        
        cmd = [
            self.colmap_path, 'sequential_matcher',
            '--database_path', str(database_path),
            '--SiftMatching.max_distance', str(self.config.max_distance),
            '--SiftMatching.max_error', str(self.config.max_error),
            '--SiftMatching.confidence', str(self.config.confidence),
            '--SequentialMatching.overlap', '10',
            '--SequentialMatching.quadratic_overlap', '1',
        ]
        
        if self.config.enable_gpu:
            cmd.extend(['--SiftMatching.use_gpu', '1'])
        
        try:
            logger.info(f"Starting sequential matching: {' '.join(cmd)}")
            result = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=self.config.timeout
            )
            
            if result.returncode != 0:
                raise RuntimeError(f"Sequential matching failed: {result.stderr}")
            
            matching_time = (datetime.now() - start_time).total_seconds()
            logger.info(f"Sequential matching completed in {matching_time:.2f}s")
            
            return self._parse_matching_results(database_path, matching_time)
            
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"Matching timed out after {self.config.timeout}s")
    
    def _parse_matching_results(self, database_path: Path, matching_time: float) -> MatchingResult:
        """Parse matching results from database"""
        try:
            conn = sqlite3.connect(str(database_path))
            cursor = conn.cursor()
            
            # Count image pairs and matches
            cursor.execute("SELECT COUNT(*) FROM matches")
            num_pairs = cursor.fetchone()[0]
            
            cursor.execute("SELECT SUM(matches) FROM matches")
            total_matches = cursor.fetchone()[0] or 0
            
            conn.close()
            
            avg_matches = total_matches / max(num_pairs, 1)
            
            return MatchingResult(
                num_pairs=num_pairs,
                num_matches=total_matches,
                avg_matches_per_pair=avg_matches,
                matching_time=matching_time,
                success=True
            )
            
        except Exception as e:
            logger.warning(f"Could not parse matching results: {e}")
            return MatchingResult(0, 0, 0.0, matching_time, False, str(e))
    
    def match_image_pair(self, image1_features: Dict, image2_features: Dict) -> Tuple[np.ndarray, float]:
        """Match features between two specific images using OpenCV"""
        
        try:
            desc1 = image1_features.get('descriptors')
            desc2 = image2_features.get('descriptors')
            
            if desc1 is None or desc2 is None:
                return np.array([]), 0.0
            
            # Create matcher
            if desc1.dtype == np.uint8:
                matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=self.config.cross_check)
            else:
                matcher = cv2.BFMatcher(cv2.NORM_L2, crossCheck=self.config.cross_check)
            
            # Match features
            if self.config.cross_check:
                matches = matcher.match(desc1, desc2)
                good_matches = [m for m in matches if m.distance < self.config.max_distance * 255]
            else:
                matches = matcher.knnMatch(desc1, desc2, k=2)
                good_matches = []
                for match_pair in matches:
                    if len(match_pair) == 2:
                        m, n = match_pair
                        if m.distance < self.config.max_ratio * n.distance:
                            good_matches.append(m)
            
            # Convert to numpy array
            if good_matches:
                matches_array = np.array([[m.queryIdx, m.trainIdx] for m in good_matches])
                confidence = 1.0 - np.mean([m.distance for m in good_matches]) / 255.0
            else:
                matches_array = np.array([])
                confidence = 0.0
            
            return matches_array, confidence
            
        except Exception as e:
            logger.error(f"Feature matching failed: {e}")
            return np.array([]), 0.0
    
    def verify_matches_geometric(self, 
                                kp1: List, kp2: List, 
                                matches: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """Verify matches using geometric constraints (RANSAC)"""
        
        if len(matches) < self.config.min_num_matches:
            return matches, np.array([])
        
        try:
            # Extract matched keypoints
            pts1 = np.float32([kp1[m[0]].pt for m in matches]).reshape(-1, 1, 2)
            pts2 = np.float32([kp2[m[1]].pt for m in matches]).reshape(-1, 1, 2)
            
            # Find fundamental matrix using RANSAC
            F, mask = cv2.findFundamentalMat(
                pts1, pts2,
                cv2.FM_RANSAC,
                ransacReprojThreshold=self.config.max_error,
                confidence=self.config.confidence
            )
            
            if mask is not None:
                inlier_matches = matches[mask.ravel() == 1]
                return inlier_matches, F
            else:
                return np.array([]), np.array([])
                
        except Exception as e:
            logger.warning(f"Geometric verification failed: {e}")
            return matches, np.array([])
    
    def get_matching_statistics(self, database_path: Path) -> Dict:
        """Get detailed matching statistics from database"""
        
        try:
            conn = sqlite3.connect(str(database_path))
            cursor = conn.cursor()
            
            # Basic statistics
            cursor.execute("SELECT COUNT(*) FROM matches")
            num_pairs = cursor.fetchone()[0]
            
            cursor.execute("SELECT AVG(matches), MIN(matches), MAX(matches) FROM matches")
            avg_matches, min_matches, max_matches = cursor.fetchone()
            
            # Image statistics
            cursor.execute("SELECT COUNT(*) FROM images")
            num_images = cursor.fetchone()[0]
            
            conn.close()
            
            return {
                'num_images': num_images,
                'num_pairs': num_pairs,
                'avg_matches_per_pair': avg_matches or 0,
                'min_matches_per_pair': min_matches or 0,
                'max_matches_per_pair': max_matches or 0,
                'matching_config': self.config.__dict__
            }
            
        except Exception as e:
            logger.error(f"Failed to get matching statistics: {e}")
            return {}