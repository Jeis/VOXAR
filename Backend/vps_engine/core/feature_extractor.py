"""
Feature Extractor - Extract and describe visual features from images
Optimized for AR applications with robust feature detection
"""

import logging
import numpy as np
import cv2
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass
import asyncio
from concurrent.futures import ThreadPoolExecutor
import time

logger = logging.getLogger(__name__)

@dataclass
class FeatureSet:
    """Container for extracted features"""
    keypoints: List[cv2.KeyPoint]
    descriptors: np.ndarray
    image_shape: Tuple[int, int]
    detector_type: str
    extraction_time: float
    feature_count: int

class FeatureExtractor:
    """
    High-performance feature extraction for VPS localization
    Supports multiple detectors optimized for different scenarios
    """
    
    def __init__(self, detector_type: str = "ORB", max_features: int = 5000):
        self.detector_type = detector_type.upper()
        self.max_features = max_features
        self.detector = None
        self.executor = ThreadPoolExecutor(max_workers=2)
        
        # Initialize detector
        self._initialize_detector()
        
        # Performance tracking
        self.stats = {
            'total_extractions': 0,
            'average_features': 0.0,
            'average_time': 0.0,
            'failed_extractions': 0
        }

    def _initialize_detector(self):
        """Initialize the feature detector based on type"""
        try:
            if self.detector_type == "ORB":
                self.detector = cv2.ORB_create(
                    nfeatures=self.max_features,
                    scaleFactor=1.2,
                    nlevels=8,
                    edgeThreshold=31,
                    firstLevel=0,
                    WTA_K=2,
                    scoreType=cv2.ORB_HARRIS_SCORE,
                    patchSize=31,
                    fastThreshold=20
                )
            elif self.detector_type == "SIFT":
                self.detector = cv2.SIFT_create(
                    nfeatures=self.max_features,
                    nOctaveLayers=3,
                    contrastThreshold=0.04,
                    edgeThreshold=10,
                    sigma=1.6
                )
            elif self.detector_type == "SURF":
                # Note: SURF requires opencv-contrib-python
                self.detector = cv2.xfeatures2d.SURF_create(
                    hessianThreshold=400,
                    nOctaves=4,
                    nOctaveLayers=3,
                    extended=False,
                    upright=False
                )
            elif self.detector_type == "AKAZE":
                self.detector = cv2.AKAZE_create(
                    descriptor_type=cv2.AKAZE_DESCRIPTOR_MLDB,
                    descriptor_size=0,
                    descriptor_channels=3,
                    threshold=0.001,
                    nOctaves=4,
                    nOctaveLayers=4,
                    diffusivity=cv2.KAZE_DIFF_PM_G2
                )
            else:
                logger.warning(f"Unknown detector type {self.detector_type}, using ORB")
                self.detector_type = "ORB"
                self._initialize_detector()
                return
                
            logger.info(f"✅ Initialized {self.detector_type} feature detector")
            
        except Exception as e:
            logger.error(f"Failed to initialize {self.detector_type} detector: {e}")
            # Fallback to ORB
            if self.detector_type != "ORB":
                logger.info("Falling back to ORB detector")
                self.detector_type = "ORB"
                self._initialize_detector()
            else:
                raise

    async def extract_features(self, image: np.ndarray, 
                             preprocess: bool = True) -> FeatureSet:
        """
        Extract features from input image
        
        Args:
            image: Input image (RGB or grayscale)
            preprocess: Apply preprocessing for better feature detection
            
        Returns:
            FeatureSet containing keypoints and descriptors
        """
        start_time = time.time()
        self.stats['total_extractions'] += 1
        
        try:
            # Preprocess image
            processed_image = await self._preprocess_image(image, preprocess)
            
            # Extract features in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            keypoints, descriptors = await loop.run_in_executor(
                self.executor, self._extract_features_sync, processed_image
            )
            
            extraction_time = time.time() - start_time
            
            # Create feature set
            feature_set = FeatureSet(
                keypoints=keypoints,
                descriptors=descriptors,
                image_shape=processed_image.shape[:2],
                detector_type=self.detector_type,
                extraction_time=extraction_time,
                feature_count=len(keypoints)
            )
            
            # Update statistics
            self._update_stats(len(keypoints), extraction_time)
            
            logger.debug(f"Extracted {len(keypoints)} features in {extraction_time:.3f}s")
            
            return feature_set
            
        except Exception as e:
            self.stats['failed_extractions'] += 1
            logger.error(f"Feature extraction failed: {e}")
            raise

    def _extract_features_sync(self, image: np.ndarray) -> Tuple[List[cv2.KeyPoint], np.ndarray]:
        """Synchronous feature extraction (runs in thread pool)"""
        
        # Detect keypoints and compute descriptors
        keypoints, descriptors = self.detector.detectAndCompute(image, None)
        
        if descriptors is None:
            descriptors = np.array([])
            keypoints = []
        
        return keypoints, descriptors

    async def _preprocess_image(self, image: np.ndarray, apply_preprocessing: bool) -> np.ndarray:
        """Preprocess image for optimal feature detection"""
        
        # Convert to grayscale if needed
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        else:
            gray = image.copy()
        
        if not apply_preprocessing:
            return gray
        
        # Apply preprocessing pipeline
        processed = gray
        
        # Histogram equalization for better contrast
        processed = cv2.equalizeHist(processed)
        
        # Gaussian blur to reduce noise
        processed = cv2.GaussianBlur(processed, (3, 3), 0)
        
        return processed

    def _update_stats(self, feature_count: int, extraction_time: float):
        """Update extraction statistics"""
        total_extractions = self.stats['total_extractions']
        
        # Update average feature count
        current_avg_features = self.stats['average_features']
        self.stats['average_features'] = \
            (current_avg_features * (total_extractions - 1) + feature_count) / total_extractions
        
        # Update average extraction time
        current_avg_time = self.stats['average_time']
        self.stats['average_time'] = \
            (current_avg_time * (total_extractions - 1) + extraction_time) / total_extractions

    async def extract_features_batch(self, images: List[np.ndarray]) -> List[FeatureSet]:
        """Extract features from multiple images concurrently"""
        
        tasks = []
        for image in images:
            task = asyncio.create_task(self.extract_features(image))
            tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Filter out exceptions
        feature_sets = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Feature extraction failed for image {i}: {result}")
            else:
                feature_sets.append(result)
        
        return feature_sets

    def get_detector_info(self) -> Dict[str, Any]:
        """Get information about the current detector"""
        return {
            'detector_type': self.detector_type,
            'max_features': self.max_features,
            'parameters': self._get_detector_parameters()
        }

    def _get_detector_parameters(self) -> Dict[str, Any]:
        """Get detector-specific parameters"""
        if self.detector_type == "ORB":
            return {
                'nfeatures': self.max_features,
                'scaleFactor': 1.2,
                'nlevels': 8,
                'edgeThreshold': 31,
                'scoreType': 'HARRIS'
            }
        elif self.detector_type == "SIFT":
            return {
                'nfeatures': self.max_features,
                'nOctaveLayers': 3,
                'contrastThreshold': 0.04,
                'edgeThreshold': 10,
                'sigma': 1.6
            }
        elif self.detector_type == "AKAZE":
            return {
                'descriptor_type': 'MLDB',
                'threshold': 0.001,
                'nOctaves': 4,
                'nOctaveLayers': 4
            }
        else:
            return {}

    def visualize_features(self, image: np.ndarray, feature_set: FeatureSet) -> np.ndarray:
        """Visualize detected features on image"""
        
        # Convert to BGR for visualization
        if len(image.shape) == 3:
            vis_image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
        else:
            vis_image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        
        # Draw keypoints
        vis_image = cv2.drawKeypoints(
            vis_image, 
            feature_set.keypoints,
            None,
            color=(0, 255, 0),
            flags=cv2.DRAW_MATCHES_FLAGS_DRAW_RICH_KEYPOINTS
        )
        
        # Add text information
        text = f"{feature_set.detector_type}: {feature_set.feature_count} features"
        cv2.putText(vis_image, text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        
        return vis_image

    def get_statistics(self) -> Dict[str, Any]:
        """Get feature extraction statistics"""
        success_rate = 0.0
        if self.stats['total_extractions'] > 0:
            success_rate = (self.stats['total_extractions'] - self.stats['failed_extractions']) / \
                          self.stats['total_extractions']
        
        return {
            **self.stats,
            'success_rate': success_rate,
            'detector_info': self.get_detector_info()
        }

    def __del__(self):
        """Cleanup thread pool on destruction"""
        if hasattr(self, 'executor'):
            self.executor.shutdown(wait=False)