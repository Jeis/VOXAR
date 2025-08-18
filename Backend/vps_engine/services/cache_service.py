"""
Cache Service for VPS Engine
Redis-based caching for improved performance
"""

import logging
import asyncio
import json
import pickle
from typing import Any, Optional, Dict, List
import aioredis
from datetime import datetime, timedelta

from utils.config import settings

logger = logging.getLogger(__name__)

class CacheService:
    """Redis cache service for VPS engine"""
    
    def __init__(self):
        self.redis = None
        self.is_initialized = False
        
        # Cache key prefixes
        self.prefixes = {
            'map_data': 'vps:map:',
            'features': 'vps:features:',
            'candidates': 'vps:candidates:',
            'results': 'vps:results:',
            'stats': 'vps:stats:'
        }
        
        # Default TTL values (seconds)
        self.default_ttls = {
            'map_data': 3600,      # 1 hour
            'features': 7200,      # 2 hours
            'candidates': 1800,    # 30 minutes
            'results': 1800,       # 30 minutes
            'stats': 300           # 5 minutes
        }

    async def initialize(self) -> None:
        """Initialize Redis connection"""
        try:
            logger.info("Initializing cache service...")
            
            # Parse Redis URL and create connection
            redis_config = settings.get_redis_config()
            self.redis = aioredis.from_url(
                settings.REDIS_URL,
                **redis_config
            )
            
            # Test connection
            await self.redis.ping()
            
            self.is_initialized = True
            logger.info("✅ Cache service initialized")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize cache service: {e}")
            raise

    async def get(self, key: str, prefix: str = 'results') -> Optional[Any]:
        """Get value from cache"""
        try:
            if not self.is_initialized:
                return None
            
            full_key = self._get_full_key(key, prefix)
            data = await self.redis.get(full_key)
            
            if data is None:
                return None
            
            # Try JSON first, then pickle
            try:
                return json.loads(data)
            except (json.JSONDecodeError, TypeError):
                try:
                    return pickle.loads(data)
                except (pickle.PickleError, TypeError):
                    logger.warning(f"Failed to deserialize cached data for key: {full_key}")
                    return None
            
        except Exception as e:
            logger.error(f"Cache get error for key {key}: {e}")
            return None

    async def set(self, key: str, value: Any, ttl: Optional[int] = None, prefix: str = 'results') -> bool:
        """Set value in cache"""
        try:
            if not self.is_initialized:
                return False
            
            full_key = self._get_full_key(key, prefix)
            
            # Use default TTL if not specified
            if ttl is None:
                ttl = self.default_ttls.get(prefix, 1800)
            
            # Try JSON serialization first
            try:
                data = json.dumps(value, default=str)
            except (TypeError, ValueError):
                # Fall back to pickle for complex objects
                try:
                    data = pickle.dumps(value)
                except (pickle.PickleError, TypeError) as e:
                    logger.warning(f"Failed to serialize value for key {key}: {e}")
                    return False
            
            await self.redis.setex(full_key, ttl, data)
            return True
            
        except Exception as e:
            logger.error(f"Cache set error for key {key}: {e}")
            return False

    async def delete(self, key: str, prefix: str = 'results') -> bool:
        """Delete key from cache"""
        try:
            if not self.is_initialized:
                return False
            
            full_key = self._get_full_key(key, prefix)
            result = await self.redis.delete(full_key)
            return result > 0
            
        except Exception as e:
            logger.error(f"Cache delete error for key {key}: {e}")
            return False

    async def exists(self, key: str, prefix: str = 'results') -> bool:
        """Check if key exists in cache"""
        try:
            if not self.is_initialized:
                return False
            
            full_key = self._get_full_key(key, prefix)
            result = await self.redis.exists(full_key)
            return result > 0
            
        except Exception as e:
            logger.error(f"Cache exists error for key {key}: {e}")
            return False

    async def expire(self, key: str, ttl: int, prefix: str = 'results') -> bool:
        """Set expiration time for key"""
        try:
            if not self.is_initialized:
                return False
            
            full_key = self._get_full_key(key, prefix)
            result = await self.redis.expire(full_key, ttl)
            return result
            
        except Exception as e:
            logger.error(f"Cache expire error for key {key}: {e}")
            return False

    async def get_many(self, keys: List[str], prefix: str = 'results') -> Dict[str, Any]:
        """Get multiple keys from cache"""
        try:
            if not self.is_initialized or not keys:
                return {}
            
            full_keys = [self._get_full_key(key, prefix) for key in keys]
            data_list = await self.redis.mget(full_keys)
            
            result = {}
            for i, (key, data) in enumerate(zip(keys, data_list)):
                if data is not None:
                    try:
                        result[key] = json.loads(data)
                    except (json.JSONDecodeError, TypeError):
                        try:
                            result[key] = pickle.loads(data)
                        except (pickle.PickleError, TypeError):
                            logger.warning(f"Failed to deserialize cached data for key: {key}")
            
            return result
            
        except Exception as e:
            logger.error(f"Cache get_many error: {e}")
            return {}

    async def set_many(self, data: Dict[str, Any], ttl: Optional[int] = None, prefix: str = 'results') -> bool:
        """Set multiple key-value pairs in cache"""
        try:
            if not self.is_initialized or not data:
                return False
            
            # Use default TTL if not specified
            if ttl is None:
                ttl = self.default_ttls.get(prefix, 1800)
            
            pipe = self.redis.pipeline()
            
            for key, value in data.items():
                full_key = self._get_full_key(key, prefix)
                
                # Serialize value
                try:
                    serialized = json.dumps(value, default=str)
                except (TypeError, ValueError):
                    try:
                        serialized = pickle.dumps(value)
                    except (pickle.PickleError, TypeError):
                        logger.warning(f"Failed to serialize value for key {key}")
                        continue
                
                pipe.setex(full_key, ttl, serialized)
            
            await pipe.execute()
            return True
            
        except Exception as e:
            logger.error(f"Cache set_many error: {e}")
            return False

    async def increment(self, key: str, amount: int = 1, prefix: str = 'stats') -> Optional[int]:
        """Increment counter in cache"""
        try:
            if not self.is_initialized:
                return None
            
            full_key = self._get_full_key(key, prefix)
            result = await self.redis.incrby(full_key, amount)
            
            # Set expiration if this is a new key
            if result == amount:
                ttl = self.default_ttls.get(prefix, 3600)
                await self.redis.expire(full_key, ttl)
            
            return result
            
        except Exception as e:
            logger.error(f"Cache increment error for key {key}: {e}")
            return None

    async def decrement(self, key: str, amount: int = 1, prefix: str = 'stats') -> Optional[int]:
        """Decrement counter in cache"""
        try:
            if not self.is_initialized:
                return None
            
            full_key = self._get_full_key(key, prefix)
            result = await self.redis.decrby(full_key, amount)
            return result
            
        except Exception as e:
            logger.error(f"Cache decrement error for key {key}: {e}")
            return None

    async def flush_prefix(self, prefix: str) -> bool:
        """Delete all keys with given prefix"""
        try:
            if not self.is_initialized:
                return False
            
            pattern = self.prefixes.get(prefix, f'vps:{prefix}:') + '*'
            keys = await self.redis.keys(pattern)
            
            if keys:
                await self.redis.delete(*keys)
                logger.info(f"Flushed {len(keys)} keys with prefix {prefix}")
            
            return True
            
        except Exception as e:
            logger.error(f"Cache flush_prefix error for {prefix}: {e}")
            return False

    async def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        try:
            if not self.is_initialized:
                return {}
            
            info = await self.redis.info()
            
            stats = {
                'connected_clients': info.get('connected_clients', 0),
                'used_memory': info.get('used_memory', 0),
                'used_memory_human': info.get('used_memory_human', '0B'),
                'total_commands_processed': info.get('total_commands_processed', 0),
                'keyspace_hits': info.get('keyspace_hits', 0),
                'keyspace_misses': info.get('keyspace_misses', 0),
                'uptime_in_seconds': info.get('uptime_in_seconds', 0)
            }
            
            # Calculate hit rate
            hits = stats['keyspace_hits']
            misses = stats['keyspace_misses']
            total = hits + misses
            if total > 0:
                stats['hit_rate'] = hits / total
            else:
                stats['hit_rate'] = 0.0
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get cache stats: {e}")
            return {}

    def _get_full_key(self, key: str, prefix: str) -> str:
        """Get full cache key with prefix"""
        prefix_str = self.prefixes.get(prefix, f'vps:{prefix}:')
        return f"{prefix_str}{key}"

    async def cache_map_data(self, map_id: str, map_data: Dict[str, Any], ttl: int = 3600) -> bool:
        """Cache map data"""
        return await self.set(map_id, map_data, ttl=ttl, prefix='map_data')

    async def get_cached_map_data(self, map_id: str) -> Optional[Dict[str, Any]]:
        """Get cached map data"""
        return await self.get(map_id, prefix='map_data')

    async def cache_map_features(self, map_id: str, features: List[Dict[str, Any]], ttl: int = 7200) -> bool:
        """Cache map features"""
        return await self.set(map_id, features, ttl=ttl, prefix='features')

    async def get_cached_map_features(self, map_id: str) -> Optional[List[Dict[str, Any]]]:
        """Get cached map features"""
        return await self.get(map_id, prefix='features')

    async def cache_localization_result(self, result_key: str, result_data: Dict[str, Any], ttl: int = 1800) -> bool:
        """Cache localization result"""
        return await self.set(result_key, result_data, ttl=ttl, prefix='results')

    async def get_cached_localization_result(self, result_key: str) -> Optional[Dict[str, Any]]:
        """Get cached localization result"""
        return await self.get(result_key, prefix='results')

    async def health_check(self) -> bool:
        """Check cache service health"""
        try:
            if not self.is_initialized or not self.redis:
                return False
            
            await self.redis.ping()
            return True
            
        except Exception as e:
            logger.error(f"Cache health check failed: {e}")
            return False

    async def shutdown(self):
        """Close Redis connection"""
        try:
            if self.redis:
                await self.redis.close()
                logger.info("Cache service shutdown complete")
        except Exception as e:
            logger.error(f"Error during cache shutdown: {e}")