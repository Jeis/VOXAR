"""
VOXAR Spatial Mapping - Feature Extractor
Enterprise-grade SIFT/ORB feature extraction for 3D reconstruction
"""

import os
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime

import numpy as np
import cv2

logger = logging.getLogger(__name__)

@dataclass
class FeatureExtractionConfig:
    """Feature extraction configuration"""
    feature_type: str = "sift"
    max_image_size: int = 3840
    num_features: int = 8192
    contrast_threshold: float = 0.04
    edge_threshold: float = 10.0
    enable_gpu: bool = True
    timeout: int = 3600

@dataclass
class FeatureExtractionResult:
    """Feature extraction results"""
    image_path: Path
    keypoints_file: Path
    descriptors_file: Path
    num_features: int
    extraction_time: float
    success: bool
    error: Optional[str] = None

class FeatureExtractor:
    """Enterprise COLMAP feature extractor"""
    
    def __init__(self, config: FeatureExtractionConfig, colmap_path: str = None):
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
            logger.info("COLMAP installation verified")
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            raise RuntimeError(f"COLMAP validation failed: {e}")
    
    def extract_features(self, image_dir: Path, database_path: Path) -> Dict[str, FeatureExtractionResult]:
        """Extract features from all images in directory"""
        start_time = datetime.now()
        
        # Build COLMAP command
        cmd = [
            self.colmap_path, 'feature_extractor',
            '--database_path', str(database_path),
            '--image_path', str(image_dir),
            '--ImageReader.camera_model', 'PINHOLE',
            '--ImageReader.single_camera', '1',
            f'--SiftExtraction.max_image_size', str(self.config.max_image_size),
            f'--SiftExtraction.max_num_features', str(self.config.num_features),
            f'--SiftExtraction.peak_threshold', str(self.config.contrast_threshold),
            f'--SiftExtraction.edge_threshold', str(self.config.edge_threshold),
        ]
        
        if self.config.enable_gpu:
            cmd.extend(['--SiftExtraction.use_gpu', '1'])
        
        try:
            logger.info(f"Starting feature extraction: {' '.join(cmd)}")
            result = subprocess.run(
                cmd, capture_output=True, text=True, 
                timeout=self.config.timeout, cwd=image_dir.parent
            )
            
            if result.returncode != 0:
                raise RuntimeError(f"Feature extraction failed: {result.stderr}")
            
            extraction_time = (datetime.now() - start_time).total_seconds()
            logger.info(f"Feature extraction completed in {extraction_time:.2f}s")
            
            # Parse results from database
            return self._parse_extraction_results(database_path, extraction_time)
            
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"Feature extraction timed out after {self.config.timeout}s")
        except Exception as e:
            logger.error(f"Feature extraction failed: {e}")
            raise
    
    def _parse_extraction_results(self, database_path: Path, extraction_time: float) -> Dict[str, FeatureExtractionResult]:
        """Parse feature extraction results from database"""
        results = {}
        
        try:
            import sqlite3
            conn = sqlite3.connect(str(database_path))
            cursor = conn.cursor()
            
            # Query image features
            cursor.execute("""
                SELECT name, keypoints, descriptors 
                FROM images 
                JOIN keypoints ON images.image_id = keypoints.image_id
                JOIN descriptors ON images.image_id = descriptors.image_id
            """)
            
            for row in cursor.fetchall():
                image_name, keypoints_blob, descriptors_blob = row
                
                # Count features
                num_features = len(keypoints_blob) // 24  # 6 floats per keypoint
                
                results[image_name] = FeatureExtractionResult(
                    image_path=Path(image_name),
                    keypoints_file=database_path,
                    descriptors_file=database_path,
                    num_features=num_features,
                    extraction_time=extraction_time,
                    success=True
                )
            
            conn.close()
            return results
            
        except Exception as e:
            logger.warning(f"Could not parse extraction results: {e}")
            return {}
    
    def extract_single_image(self, image_path: Path, output_dir: Path) -> FeatureExtractionResult:
        """Extract features from single image using OpenCV"""
        start_time = datetime.now()
        
        try:
            # Load image
            image = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
            if image is None:
                raise ValueError(f"Could not load image: {image_path}")
            
            # Resize if needed
            if max(image.shape) > self.config.max_image_size:
                scale = self.config.max_image_size / max(image.shape)
                new_width = int(image.shape[1] * scale)
                new_height = int(image.shape[0] * scale)
                image = cv2.resize(image, (new_width, new_height))
            
            # Extract features
            if self.config.feature_type.lower() == 'sift':
                detector = cv2.SIFT_create(
                    nfeatures=self.config.num_features,
                    contrastThreshold=self.config.contrast_threshold / 255.0,
                    edgeThreshold=self.config.edge_threshold
                )
            else:
                detector = cv2.ORB_create(nfeatures=self.config.num_features)
            
            keypoints, descriptors = detector.detectAndCompute(image, None)
            
            # Save results
            output_dir.mkdir(parents=True, exist_ok=True)
            keypoints_file = output_dir / f"{image_path.stem}_keypoints.pkl"
            descriptors_file = output_dir / f"{image_path.stem}_descriptors.npy"
            
            # Save keypoints as pickle
            import pickle
            kp_data = [(kp.pt, kp.angle, kp.response, kp.octave, kp.class_id) for kp in keypoints]
            with open(keypoints_file, 'wb') as f:
                pickle.dump(kp_data, f)
            
            # Save descriptors as numpy array
            if descriptors is not None:
                np.save(descriptors_file, descriptors)
            
            extraction_time = (datetime.now() - start_time).total_seconds()
            
            return FeatureExtractionResult(
                image_path=image_path,
                keypoints_file=keypoints_file,
                descriptors_file=descriptors_file,
                num_features=len(keypoints) if keypoints else 0,
                extraction_time=extraction_time,
                success=True
            )
            
        except Exception as e:
            extraction_time = (datetime.now() - start_time).total_seconds()
            logger.error(f"Feature extraction failed for {image_path}: {e}")
            
            return FeatureExtractionResult(
                image_path=image_path,
                keypoints_file=Path(),
                descriptors_file=Path(),
                num_features=0,
                extraction_time=extraction_time,
                success=False,
                error=str(e)
            )