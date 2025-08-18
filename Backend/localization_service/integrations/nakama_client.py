"""
Nakama Integration Client
Sends pose updates to multiplayer matches
"""

import asyncio
import aiohttp
import json
import logging
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class NakamaClient:
    """Client for sending tracking data to Nakama multiplayer matches"""
    
    def __init__(self, nakama_host: str = "nakama", nakama_port: int = 7350):
        self.base_url = f"http://{nakama_host}:{nakama_port}"
        self.session = None
        self.auth_token = None
        
    async def initialize(self):
        """Initialize HTTP client and authenticate"""
        self.session = aiohttp.ClientSession()
        
        # For now, we'll use the device authentication
        # In production, this would be more sophisticated
        await self._authenticate()
        
    async def shutdown(self):
        """Clean shutdown"""
        if self.session:
            await self.session.close()
    
    async def _authenticate(self):
        """Authenticate with Nakama using device ID"""
        try:
            device_id = "localization-service"
            auth_url = f"{self.base_url}/v2/account/authenticate/device"
            
            payload = {
                "id": device_id,
                "create": True
            }
            
            headers = {
                "Authorization": "Basic ZGVmYXVsdGtleTo=",  # Default key
                "Content-Type": "application/json"
            }
            
            async with self.session.post(auth_url, json=payload, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    self.auth_token = data.get("token")
                    logger.info("Authenticated with Nakama")
                else:
                    logger.error(f"Nakama authentication failed: {response.status}")
                    
        except Exception as e:
            logger.error(f"Failed to authenticate with Nakama: {e}")
    
    async def send_pose_update(self, user_id: str, pose_data: Dict[str, Any]) -> bool:
        """Send pose update to active AR match"""
        if not self.auth_token:
            logger.warning("Not authenticated with Nakama")
            return False
        
        try:
            # Find active match for user
            match_id = await self._find_user_match(user_id)
            if not match_id:
                logger.debug(f"No active match found for user {user_id}")
                return False
            
            # Send pose update to match
            return await self._send_match_data(match_id, {
                "type": "pose_update",
                "user_id": user_id,
                "pose": pose_data,
                "timestamp": datetime.now().isoformat(),
                "source": "localization_service"
            })
            
        except Exception as e:
            logger.error(f"Failed to send pose update: {e}")
            return False
    
    async def notify_localization_success(self, user_id: str, map_id: str, confidence: float) -> bool:
        """Notify Nakama that user successfully localized"""
        if not self.auth_token:
            return False
        
        try:
            match_id = await self._find_user_match(user_id)
            if not match_id:
                return False
            
            return await self._send_match_data(match_id, {
                "type": "localization_success",
                "user_id": user_id,
                "map_id": map_id,
                "confidence": confidence,
                "timestamp": datetime.now().isoformat()
            })
            
        except Exception as e:
            logger.error(f"Failed to notify localization success: {e}")
            return False
    
    async def _find_user_match(self, user_id: str) -> Optional[str]:
        """Find active match for a user"""
        try:
            # This would typically query Nakama's match system
            # For now, we'll use a simple approach
            
            # List active matches (simplified)
            matches_url = f"{self.base_url}/v2/match"
            headers = {"Authorization": f"Bearer {self.auth_token}"}
            
            async with self.session.get(matches_url, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    matches = data.get("matches", [])
                    
                    # Find match with this user
                    for match in matches:
                        if self._user_in_match(user_id, match):
                            return match.get("match_id")
                            
        except Exception as e:
            logger.error(f"Failed to find user match: {e}")
        
        return None
    
    def _user_in_match(self, user_id: str, match_data: Dict) -> bool:
        """Check if user is in this match"""
        # This is a simplified check
        # Real implementation would check match presence data
        presences = match_data.get("presences", [])
        return any(p.get("user_id") == user_id for p in presences)
    
    async def _send_match_data(self, match_id: str, data: Dict[str, Any]) -> bool:
        """Send data to a specific match"""
        try:
            match_url = f"{self.base_url}/v2/match/{match_id}/data"
            headers = {
                "Authorization": f"Bearer {self.auth_token}",
                "Content-Type": "application/json"
            }
            
            # Nakama expects data in specific format
            payload = {
                "op_code": 1,  # Custom op code for pose updates
                "data": json.dumps(data)
            }
            
            async with self.session.post(match_url, json=payload, headers=headers) as response:
                if response.status == 200:
                    logger.debug(f"Sent data to match {match_id}")
                    return True
                else:
                    logger.warning(f"Failed to send match data: {response.status}")
                    return False
                    
        except Exception as e:
            logger.error(f"Failed to send match data: {e}")
            return False
    
    async def get_connection_status(self) -> Dict[str, Any]:
        """Get current connection status"""
        return {
            "connected": self.auth_token is not None,
            "base_url": self.base_url,
            "authenticated": self.auth_token is not None
        }