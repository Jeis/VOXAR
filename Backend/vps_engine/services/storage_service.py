"""
Storage Service for VPS Engine
MinIO/S3 object storage for maps and assets
"""

import logging
import asyncio
from typing import Optional, Dict, Any, List
import aiofiles
from minio import Minio
from minio.error import S3Error
import io
from datetime import datetime, timedelta

from utils.config import settings

logger = logging.getLogger(__name__)

class StorageService:
    """Object storage service for VPS engine"""
    
    def __init__(self):
        self.client = None
        self.bucket_name = settings.STORAGE_BUCKET
        self.is_initialized = False
        
        # Storage paths
        self.paths = {
            'point_clouds': 'point_clouds/',
            'reference_images': 'reference_images/',
            'maps': 'maps/',
            'cache': 'cache/'
        }

    async def initialize(self) -> None:
        """Initialize MinIO client and create bucket if needed"""
        try:
            logger.info("Initializing storage service...")
            
            storage_config = settings.get_storage_config()
            
            self.client = Minio(
                storage_config['endpoint'],
                access_key=storage_config['access_key'],
                secret_key=storage_config['secret_key'],
                secure=storage_config['secure'],
                region=storage_config['region']
            )
            
            # Create bucket if it doesn't exist
            await self._ensure_bucket()
            
            self.is_initialized = True
            logger.info("✅ Storage service initialized")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize storage service: {e}")
            raise

    async def _ensure_bucket(self):
        """Create bucket if it doesn't exist"""
        try:
            # Run in thread pool since minio is sync
            loop = asyncio.get_event_loop()
            bucket_exists = await loop.run_in_executor(
                None, self.client.bucket_exists, self.bucket_name
            )
            
            if not bucket_exists:
                await loop.run_in_executor(
                    None, self.client.make_bucket, self.bucket_name
                )
                logger.info(f"Created bucket: {self.bucket_name}")
            
        except Exception as e:
            logger.error(f"Failed to ensure bucket: {e}")
            raise

    async def store_point_cloud(self, map_id: str, point_cloud_data: bytes) -> bool:
        """Store point cloud data for a map"""
        try:
            object_name = f"{self.paths['point_clouds']}{map_id}.ply"
            
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                self.client.put_object,
                self.bucket_name,
                object_name,
                io.BytesIO(point_cloud_data),
                len(point_cloud_data),
                "application/octet-stream"
            )
            
            logger.info(f"Stored point cloud for map {map_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to store point cloud: {e}")
            return False

    async def get_point_cloud(self, map_id: str) -> Optional[bytes]:
        """Get point cloud data for a map"""
        try:
            object_name = f"{self.paths['point_clouds']}{map_id}.ply"
            
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, self.client.get_object, self.bucket_name, object_name
            )
            
            data = response.read()
            response.close()
            response.release_conn()
            
            return data
            
        except S3Error as e:
            if e.code == 'NoSuchKey':
                logger.warning(f"Point cloud not found for map {map_id}")
            else:
                logger.error(f"Failed to get point cloud: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to get point cloud: {e}")
            return None

    async def store_reference_image(self, map_id: str, image_name: str, image_data: bytes) -> bool:
        """Store reference image for a map"""
        try:
            object_name = f"{self.paths['reference_images']}{map_id}/{image_name}.jpg"
            
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                self.client.put_object,
                self.bucket_name,
                object_name,
                io.BytesIO(image_data),
                len(image_data),
                "image/jpeg"
            )
            
            logger.debug(f"Stored reference image {image_name} for map {map_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to store reference image: {e}")
            return False

    async def get_reference_image(self, map_id: str, image_name: str) -> Optional[bytes]:
        """Get reference image for a map"""
        try:
            object_name = f"{self.paths['reference_images']}{map_id}/{image_name}.jpg"
            
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, self.client.get_object, self.bucket_name, object_name
            )
            
            data = response.read()
            response.close()
            response.release_conn()
            
            return data
            
        except S3Error as e:
            if e.code == 'NoSuchKey':
                logger.warning(f"Reference image not found: {map_id}/{image_name}")
            else:
                logger.error(f"Failed to get reference image: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to get reference image: {e}")
            return None

    async def list_reference_images(self, map_id: str) -> List[str]:
        """List all reference images for a map"""
        try:
            prefix = f"{self.paths['reference_images']}{map_id}/"
            
            loop = asyncio.get_event_loop()
            objects = await loop.run_in_executor(
                None, self.client.list_objects, self.bucket_name, prefix
            )
            
            image_names = []
            for obj in objects:
                # Extract image name from path
                name = obj.object_name.replace(prefix, '').replace('.jpg', '')
                image_names.append(name)
            
            return image_names
            
        except Exception as e:
            logger.error(f"Failed to list reference images: {e}")
            return []

    async def store_map_data(self, map_id: str, map_data: Dict[str, Any]) -> bool:
        """Store processed map data"""
        try:
            import json
            
            object_name = f"{self.paths['maps']}{map_id}/metadata.json"
            data = json.dumps(map_data, indent=2, default=str).encode('utf-8')
            
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                self.client.put_object,
                self.bucket_name,
                object_name,
                io.BytesIO(data),
                len(data),
                "application/json"
            )
            
            logger.info(f"Stored map data for {map_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to store map data: {e}")
            return False

    async def get_map_data(self, map_id: str) -> Optional[Dict[str, Any]]:
        """Get processed map data"""
        try:
            import json
            
            object_name = f"{self.paths['maps']}{map_id}/metadata.json"
            
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, self.client.get_object, self.bucket_name, object_name
            )
            
            data = response.read()
            response.close()
            response.release_conn()
            
            return json.loads(data.decode('utf-8'))
            
        except S3Error as e:
            if e.code == 'NoSuchKey':
                logger.warning(f"Map data not found for {map_id}")
            else:
                logger.error(f"Failed to get map data: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to get map data: {e}")
            return None

    async def store_map_features(self, map_id: str, features_data: bytes) -> bool:
        """Store map features (binary format)"""
        try:
            object_name = f"{self.paths['maps']}{map_id}/features.bin"
            
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                self.client.put_object,
                self.bucket_name,
                object_name,
                io.BytesIO(features_data),
                len(features_data),
                "application/octet-stream"
            )
            
            logger.info(f"Stored map features for {map_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to store map features: {e}")
            return False

    async def get_map_features(self, map_id: str) -> Optional[bytes]:
        """Get map features (binary format)"""
        try:
            object_name = f"{self.paths['maps']}{map_id}/features.bin"
            
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, self.client.get_object, self.bucket_name, object_name
            )
            
            data = response.read()
            response.close()
            response.release_conn()
            
            return data
            
        except S3Error as e:
            if e.code == 'NoSuchKey':
                logger.warning(f"Map features not found for {map_id}")
            else:
                logger.error(f"Failed to get map features: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to get map features: {e}")
            return None

    async def delete_map_data(self, map_id: str) -> bool:
        """Delete all data for a map"""
        try:
            # List all objects for this map
            prefixes = [
                f"{self.paths['point_clouds']}{map_id}",
                f"{self.paths['reference_images']}{map_id}/",
                f"{self.paths['maps']}{map_id}/"
            ]
            
            loop = asyncio.get_event_loop()
            
            for prefix in prefixes:
                try:
                    objects = await loop.run_in_executor(
                        None, self.client.list_objects, self.bucket_name, prefix
                    )
                    
                    for obj in objects:
                        await loop.run_in_executor(
                            None, self.client.remove_object, self.bucket_name, obj.object_name
                        )
                except Exception as e:
                    logger.warning(f"Failed to delete objects with prefix {prefix}: {e}")
            
            logger.info(f"Deleted all data for map {map_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete map data: {e}")
            return False

    async def get_storage_stats(self) -> Dict[str, Any]:
        """Get storage usage statistics"""
        try:
            loop = asyncio.get_event_loop()
            objects = await loop.run_in_executor(
                None, self.client.list_objects, self.bucket_name, recursive=True
            )
            
            stats = {
                'total_objects': 0,
                'total_size': 0,
                'by_type': {
                    'point_clouds': {'count': 0, 'size': 0},
                    'reference_images': {'count': 0, 'size': 0},
                    'maps': {'count': 0, 'size': 0},
                    'cache': {'count': 0, 'size': 0}
                }
            }
            
            for obj in objects:
                stats['total_objects'] += 1
                stats['total_size'] += obj.size
                
                # Categorize by path
                for category, path in self.paths.items():
                    if obj.object_name.startswith(path):
                        stats['by_type'][category]['count'] += 1
                        stats['by_type'][category]['size'] += obj.size
                        break
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get storage stats: {e}")
            return {}

    async def cleanup_old_cache(self, older_than_days: int = 7) -> bool:
        """Clean up old cache files"""
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=older_than_days)
            prefix = self.paths['cache']
            
            loop = asyncio.get_event_loop()
            objects = await loop.run_in_executor(
                None, self.client.list_objects, self.bucket_name, prefix
            )
            
            deleted_count = 0
            for obj in objects:
                if obj.last_modified < cutoff_date:
                    await loop.run_in_executor(
                        None, self.client.remove_object, self.bucket_name, obj.object_name
                    )
                    deleted_count += 1
            
            logger.info(f"Cleaned up {deleted_count} old cache files")
            return True
            
        except Exception as e:
            logger.error(f"Failed to cleanup old cache: {e}")
            return False

    async def health_check(self) -> bool:
        """Check storage service health"""
        try:
            if not self.is_initialized or not self.client:
                return False
            
            loop = asyncio.get_event_loop()
            bucket_exists = await loop.run_in_executor(
                None, self.client.bucket_exists, self.bucket_name
            )
            
            return bucket_exists
            
        except Exception as e:
            logger.error(f"Storage health check failed: {e}")
            return False

    async def shutdown(self):
        """Shutdown storage service"""
        try:
            # MinIO client doesn't need explicit cleanup
            self.is_initialized = False
            logger.info("Storage service shutdown complete")
        except Exception as e:
            logger.error(f"Error during storage shutdown: {e}")