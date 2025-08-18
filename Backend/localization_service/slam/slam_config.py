"""
VOXAR Spatial Platform - SLAM Configuration Manager
Enterprise-grade configuration management for SLAM systems
"""

import os
import yaml
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional
import tempfile

from .slam_models import SLAMConfig

logger = logging.getLogger(__name__)

class SLAMConfigManager:
    """Enterprise configuration manager for SLAM systems"""
    
    def __init__(self, config: SLAMConfig):
        self.config = config
        self.camera_config_path: Optional[str] = None
        self.temp_files: list = []
    
    def create_camera_config(self) -> str:
        """
        Create camera configuration file for Stella VSLAM
        Returns path to generated config file
        """
        try:
            # Create temporary config file
            config_data = self._build_camera_config()
            
            # Write to temporary YAML file
            temp_fd, temp_path = tempfile.mkstemp(suffix='.yaml', prefix='stella_camera_')
            with os.fdopen(temp_fd, 'w') as f:
                yaml.dump(config_data, f, default_flow_style=False)
            
            self.camera_config_path = temp_path
            self.temp_files.append(temp_path)
            
            logger.info(f"Camera configuration created: {temp_path}")
            return temp_path
            
        except Exception as e:
            logger.error(f"Failed to create camera configuration: {e}")
            raise RuntimeError(f"Camera configuration creation failed: {e}")
    
    def _build_camera_config(self) -> Dict[str, Any]:
        """Build comprehensive camera configuration for Stella VSLAM"""
        
        # Extract camera parameters with validation
        cam_config = self.config.camera_config
        
        config_data = {
            'Camera': {
                # Core camera parameters
                'name': cam_config.get('name', 'VOXAR_Camera'),
                'setup': cam_config.get('setup', 'monocular'),
                'model': cam_config.get('model', 'perspective'),
                
                # Intrinsic parameters
                'fx': float(cam_config['Camera.fx']),
                'fy': float(cam_config['Camera.fy']),
                'cx': float(cam_config['Camera.cx']),
                'cy': float(cam_config['Camera.cy']),
                
                # Distortion parameters (if available)
                'k1': float(cam_config.get('Camera.k1', 0.0)),
                'k2': float(cam_config.get('Camera.k2', 0.0)),
                'p1': float(cam_config.get('Camera.p1', 0.0)),
                'p2': float(cam_config.get('Camera.p2', 0.0)),
                'k3': float(cam_config.get('Camera.k3', 0.0)),
                
                # Image properties
                'cols': self.config.image_width,
                'rows': self.config.image_height,
                'fps': self.config.fps,
                'color_order': cam_config.get('color_order', 'RGB'),
            },
            
            # Feature detection parameters
            'Feature': {
                'max_num_keypoints': self.config.max_features,
                'scale_factor': cam_config.get('Feature.scale_factor', 1.2),
                'num_levels': cam_config.get('Feature.num_levels', 8),
                'ini_fast_threshold': cam_config.get('Feature.ini_fast_threshold', 20),
                'min_fast_threshold': cam_config.get('Feature.min_fast_threshold', 7),
            },
            
            # Tracking parameters
            'Tracking': {
                'min_num_keypoints': 100,
                'max_num_keypoints': self.config.max_features,
                'quality_threshold': self.config.tracking_quality_threshold,
            },
            
            # Mapping parameters
            'Mapping': {
                'baseline_dist_threshold': 1.0,
                'redundancy_threshold': 0.9,
                'far_point_threshold': 40.0,
                'close_point_threshold': 0.2,
            },
            
            # Loop closure parameters
            'LoopClosing': {
                'enabled': self.config.enable_loop_closure,
                'bow_similarity_threshold': 0.75,
                'consistency_threshold': 3,
            },
            
            # Relocalization parameters  
            'Relocalizing': {
                'enabled': self.config.enable_relocalization,
                'max_num_candidates': self.config.reloc_attempts,
                'bow_similarity_threshold': 0.7,
            }
        }
        
        # Add stereo-specific parameters if stereo camera
        if cam_config.get('setup') == 'stereo':
            config_data['Camera'].update({
                'baseline': float(cam_config.get('Camera.baseline', 0.12)),
                'depth_threshold': float(cam_config.get('Camera.depth_threshold', 40.0)),
            })
        
        return config_data
    
    def validate_config_file(self, config_path: str) -> bool:
        """Validate generated configuration file"""
        try:
            if not os.path.exists(config_path):
                logger.error(f"Configuration file not found: {config_path}")
                return False
            
            with open(config_path, 'r') as f:
                config_data = yaml.safe_load(f)
            
            # Validate required sections
            required_sections = ['Camera', 'Feature', 'Tracking']
            for section in required_sections:
                if section not in config_data:
                    logger.error(f"Missing required section: {section}")
                    return False
            
            # Validate camera parameters
            camera_section = config_data['Camera']
            required_params = ['fx', 'fy', 'cx', 'cy', 'cols', 'rows']
            for param in required_params:
                if param not in camera_section:
                    logger.error(f"Missing camera parameter: {param}")
                    return False
                    
                if not isinstance(camera_section[param], (int, float)):
                    logger.error(f"Invalid camera parameter type: {param}")
                    return False
            
            logger.info("Configuration file validation successful")
            return True
            
        except Exception as e:
            logger.error(f"Configuration validation failed: {e}")
            return False
    
    def update_runtime_config(self, updates: Dict[str, Any]) -> bool:
        """Update configuration parameters at runtime"""
        try:
            if not self.camera_config_path:
                logger.error("No camera configuration loaded")
                return False
            
            with open(self.camera_config_path, 'r') as f:
                config_data = yaml.safe_load(f)
            
            # Apply updates safely
            for key, value in updates.items():
                sections = key.split('.')
                current = config_data
                
                for section in sections[:-1]:
                    if section not in current:
                        current[section] = {}
                    current = current[section]
                
                current[sections[-1]] = value
                logger.info(f"Updated config: {key} = {value}")
            
            # Write updated configuration
            with open(self.camera_config_path, 'w') as f:
                yaml.dump(config_data, f, default_flow_style=False)
            
            return self.validate_config_file(self.camera_config_path)
            
        except Exception as e:
            logger.error(f"Failed to update configuration: {e}")
            return False
    
    def get_optimized_config_for_device(self, device_info: Dict[str, Any]) -> Dict[str, Any]:
        """Get device-optimized configuration parameters"""
        
        # Default optimization based on device capabilities
        optimized = {}
        
        # CPU optimization
        cpu_cores = device_info.get('cpu_cores', 4)
        if cpu_cores >= 8:
            optimized['Feature.max_num_keypoints'] = self.config.max_features
        elif cpu_cores >= 4:
            optimized['Feature.max_num_keypoints'] = min(self.config.max_features, 1500)
        else:
            optimized['Feature.max_num_keypoints'] = min(self.config.max_features, 1000)
        
        # Memory optimization
        available_memory_gb = device_info.get('memory_gb', 4)
        if available_memory_gb < 4:
            optimized['Mapping.far_point_threshold'] = 20.0  # Reduce map size
            optimized['LoopClosing.enabled'] = False  # Disable for low memory
        
        # GPU optimization
        has_gpu = device_info.get('has_gpu', False)
        if not has_gpu:
            optimized['Feature.num_levels'] = 6  # Reduce for CPU processing
        
        logger.info(f"Device optimization applied: {optimized}")
        return optimized
    
    def cleanup(self):
        """Clean up temporary configuration files"""
        for temp_file in self.temp_files:
            try:
                if os.path.exists(temp_file):
                    os.unlink(temp_file)
                    logger.debug(f"Cleaned up temp file: {temp_file}")
            except Exception as e:
                logger.warning(f"Failed to cleanup {temp_file}: {e}")
        
        self.temp_files.clear()
        self.camera_config_path = None


def create_default_camera_config(image_width: int, image_height: int, 
                                fx: float, fy: float, cx: float, cy: float) -> SLAMConfig:
    """Create default camera configuration for common use cases"""
    
    camera_config = {
        'name': 'Default_Camera',
        'setup': 'monocular',
        'model': 'perspective',
        'Camera.fx': fx,
        'Camera.fy': fy, 
        'Camera.cx': cx,
        'Camera.cy': cy,
        'color_order': 'RGB'
    }
    
    # Use a default vocabulary file path - update for your deployment
    vocab_file = os.environ.get('STELLA_VOCAB_FILE', '/opt/stella_vslam/orb_vocab.fbow')
    
    return SLAMConfig(
        vocab_file=vocab_file,
        camera_config=camera_config,
        image_width=image_width,
        image_height=image_height,
        fps=30.0
    )