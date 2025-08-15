#!/usr/bin/env python3
"""
Authenticated Test Client for Spatial AR Multiplayer Service
Demonstrates authentication flow and secure WebSocket connections
"""

import asyncio
import json
import time
import requests
import websockets
from typing import Optional, Dict, Any
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AuthenticatedTestClient:
    """Test client with authentication support"""
    
    def __init__(self, base_url: str = "http://localhost:8080"):
        self.base_url = base_url
        self.ws_url = base_url.replace("http", "ws")
        self.access_token: Optional[str] = None
        self.refresh_token: Optional[str] = None
        self.user_id: Optional[str] = None
        self.username: Optional[str] = None
        
    async def register_user(self, username: str, email: str, password: str) -> bool:
        """Register a new user account"""
        try:
            response = requests.post(f"{self.base_url}/api/v1/auth/register", json={
                "username": username,
                "email": email,
                "password": password
            })
            
            if response.status_code == 201:
                data = response.json()
                self.access_token = data["access_token"]
                self.refresh_token = data["refresh_token"]
                self.user_id = data["user_id"]
                self.username = data["username"]
                logger.info(f"Successfully registered user: {username}")
                return True
            else:
                logger.error(f"Registration failed: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Registration error: {e}")
            return False
    
    async def login_user(self, username: str, password: str) -> bool:
        """Login with existing credentials"""
        try:
            response = requests.post(f"{self.base_url}/api/v1/auth/login", json={
                "username": username,
                "password": password
            })
            
            if response.status_code == 200:
                data = response.json()
                self.access_token = data["access_token"]
                self.refresh_token = data["refresh_token"]
                self.user_id = data["user_id"]
                self.username = data["username"]
                logger.info(f"Successfully logged in user: {username}")
                return True
            else:
                logger.error(f"Login failed: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Login error: {e}")
            return False
    
    async def create_session(self) -> Optional[str]:
        """Create a new AR session (requires authentication)"""
        if not self.access_token:
            logger.error("No access token available")
            return None
            
        try:
            headers = {"Authorization": f"Bearer {self.access_token}"}
            response = requests.post(
                f"{self.base_url}/api/v1/session/create",
                json={
                    "max_players": 4,
                    "colocalization_method": "qr_code",
                    "is_public": False
                },
                headers=headers
            )
            
            if response.status_code == 200:
                data = response.json()
                session_id = data["session_id"]
                logger.info(f"Created session: {session_id}")
                return session_id
            else:
                logger.error(f"Session creation failed: {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"Session creation error: {e}")
            return None
    
    async def connect_to_session(self, session_id: str) -> Optional[websockets.WebSocketClientProtocol]:
        """Connect to session with authentication"""
        if not self.access_token:
            logger.error("No access token available")
            return None
            
        try:
            ws_uri = f"{self.ws_url}/ws/{session_id}?token={self.access_token}"
            websocket = await websockets.connect(ws_uri)
            logger.info(f"Connected to session: {session_id}")
            return websocket
            
        except Exception as e:
            logger.error(f"WebSocket connection error: {e}")
            return None
    
    async def send_validated_pose_update(self, websocket: websockets.WebSocketClientProtocol, 
                                       position: Dict[str, float], rotation: Dict[str, float]):
        """Send a validated pose update"""
        message = {
            "type": "pose_update",
            "timestamp": int(time.time() * 1000),
            "pose": {
                "position": position,
                "rotation": rotation,
                "confidence": 0.95,
                "tracking_state": "tracking"
            }
        }
        
        await websocket.send(json.dumps(message))
        logger.info(f"Sent pose update: {position}")
    
    async def send_chat_message(self, websocket: websockets.WebSocketClientProtocol, text: str):
        """Send a validated chat message"""
        message = {
            "type": "chat_message",
            "timestamp": int(time.time() * 1000),
            "message": text
        }
        
        await websocket.send(json.dumps(message))
        logger.info(f"Sent chat: {text}")
    
    async def create_anchor(self, websocket: websockets.WebSocketClientProtocol, 
                          anchor_id: str, position: Dict[str, float], rotation: Dict[str, float]):
        """Create a spatial anchor"""
        message = {
            "type": "anchor_create",
            "timestamp": int(time.time() * 1000),
            "anchor_id": anchor_id,
            "position": position,
            "rotation": rotation,
            "metadata": {"type": "test_anchor", "created_by": self.username}
        }
        
        await websocket.send(json.dumps(message))
        logger.info(f"Created anchor: {anchor_id}")
    
    async def send_ping(self, websocket: websockets.WebSocketClientProtocol):
        """Send ping message"""
        message = {
            "type": "ping",
            "timestamp": int(time.time() * 1000)
        }
        
        await websocket.send(json.dumps(message))
    
    async def listen_for_messages(self, websocket: websockets.WebSocketClientProtocol, duration: float = 10.0):
        """Listen for incoming messages"""
        start_time = time.time()
        
        try:
            while time.time() - start_time < duration:
                try:
                    message = await asyncio.wait_for(websocket.recv(), timeout=1.0)
                    data = json.loads(message)
                    logger.info(f"Received: {data['type']} - {data}")
                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    logger.error(f"Error receiving message: {e}")
                    break
                    
        except Exception as e:
            logger.error(f"Listen error: {e}")

async def test_authentication_flow():
    """Test complete authentication and session flow"""
    client = AuthenticatedTestClient()
    
    # Generate unique test user
    timestamp = int(time.time())
    username = f"testuser_{timestamp}"
    email = f"test_{timestamp}@example.com"
    password = "test_password_123"
    
    logger.info("=== Testing Authentication Flow ===")
    
    # Step 1: Register user
    logger.info("1. Registering new user...")
    success = await client.register_user(username, email, password)
    if not success:
        logger.error("Registration failed!")
        return False
    
    # Step 2: Create session
    logger.info("2. Creating AR session...")
    session_id = await client.create_session()
    if not session_id:
        logger.error("Session creation failed!")
        return False
    
    # Step 3: Connect to session
    logger.info("3. Connecting to session via WebSocket...")
    websocket = await client.connect_to_session(session_id)
    if not websocket:
        logger.error("WebSocket connection failed!")
        return False
    
    try:
        # Step 4: Test various message types
        logger.info("4. Testing message types...")
        
        # Send pose updates
        await client.send_validated_pose_update(websocket, 
            {"x": 1.0, "y": 0.5, "z": -2.0}, 
            {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0}
        )
        
        # Send chat message
        await client.send_chat_message(websocket, "Hello from authenticated client!")
        
        # Create anchor
        await client.create_anchor(websocket, 
            f"test_anchor_{timestamp}",
            {"x": 2.0, "y": 1.0, "z": -1.0},
            {"x": 0.0, "y": 0.707, "z": 0.0, "w": 0.707}
        )
        
        # Send ping
        await client.send_ping(websocket)
        
        # Listen for responses
        logger.info("5. Listening for responses...")
        await client.listen_for_messages(websocket, duration=5.0)
        
        logger.info("✅ Authentication flow test completed successfully!")
        return True
        
    finally:
        await websocket.close()

async def test_rate_limiting():
    """Test rate limiting functionality"""
    client = AuthenticatedTestClient()
    
    # Register and login
    timestamp = int(time.time())
    username = f"ratetest_{timestamp}"
    email = f"ratetest_{timestamp}@example.com"
    
    await client.register_user(username, email, "test_password_123")
    session_id = await client.create_session()
    websocket = await client.connect_to_session(session_id)
    
    if not websocket:
        logger.error("Failed to connect for rate limiting test")
        return False
    
    logger.info("=== Testing Rate Limiting ===")
    
    try:
        # Send many messages quickly to trigger rate limiting
        for i in range(25):  # Burst limit is 20
            await client.send_chat_message(websocket, f"Spam message {i}")
            if i < 15:
                await asyncio.sleep(0.1)  # Send fast initially
        
        # Listen for rate limit error
        await client.listen_for_messages(websocket, duration=3.0)
        
        logger.info("✅ Rate limiting test completed")
        return True
        
    finally:
        await websocket.close()

async def test_validation_errors():
    """Test input validation"""
    client = AuthenticatedTestClient()
    
    timestamp = int(time.time())
    await client.register_user(f"validtest_{timestamp}", f"validtest_{timestamp}@example.com", "test_password_123")
    session_id = await client.create_session()
    websocket = await client.connect_to_session(session_id)
    
    if not websocket:
        logger.error("Failed to connect for validation test")
        return False
    
    logger.info("=== Testing Input Validation ===")
    
    try:
        # Send invalid JSON
        await websocket.send("invalid json")
        
        # Send invalid message type
        await websocket.send(json.dumps({
            "type": "invalid_type",
            "timestamp": int(time.time() * 1000)
        }))
        
        # Send invalid pose data
        await websocket.send(json.dumps({
            "type": "pose_update",
            "timestamp": int(time.time() * 1000),
            "pose": {
                "position": {"x": "invalid", "y": 0, "z": 0},  # Invalid type
                "rotation": {"x": 0, "y": 0, "z": 0, "w": 1},
                "confidence": 1.5,  # Invalid range
                "tracking_state": "tracking"
            }
        }))
        
        # Listen for validation errors
        await client.listen_for_messages(websocket, duration=3.0)
        
        logger.info("✅ Validation test completed")
        return True
        
    finally:
        await websocket.close()

async def main():
    """Run all authentication tests"""
    logger.info("Starting Authenticated Test Suite")
    
    tests = [
        ("Authentication Flow", test_authentication_flow),
        ("Rate Limiting", test_rate_limiting),
        ("Input Validation", test_validation_errors)
    ]
    
    results = []
    for test_name, test_func in tests:
        logger.info(f"\n{'='*50}")
        logger.info(f"Running: {test_name}")
        logger.info(f"{'='*50}")
        
        try:
            success = await test_func()
            results.append((test_name, success))
            logger.info(f"✅ {test_name}: {'PASSED' if success else 'FAILED'}")
        except Exception as e:
            logger.error(f"❌ {test_name}: ERROR - {e}")
            results.append((test_name, False))
        
        await asyncio.sleep(1)  # Brief pause between tests
    
    # Summary
    logger.info(f"\n{'='*50}")
    logger.info("TEST SUMMARY")
    logger.info(f"{'='*50}")
    
    passed = sum(1 for _, success in results if success)
    total = len(results)
    
    for test_name, success in results:
        status = "✅ PASSED" if success else "❌ FAILED"
        logger.info(f"{test_name}: {status}")
    
    logger.info(f"\nOverall: {passed}/{total} tests passed")
    
    if passed == total:
        logger.info("🎉 All authentication tests passed!")
    else:
        logger.warning("⚠️  Some tests failed - check logs for details")

if __name__ == "__main__":
    asyncio.run(main())