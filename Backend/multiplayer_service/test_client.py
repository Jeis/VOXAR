#!/usr/bin/env python3
"""
Simple WebSocket test client for the Spatial Platform multiplayer service
"""

import asyncio
import json
import time
import websockets
import requests
from typing import Optional

class TestClient:
    def __init__(self, server_host: str = "localhost", server_port: int = 8080):
        self.server_host = server_host
        self.server_port = server_port
        self.websocket: Optional[websockets.WebSocketServerProtocol] = None
        self.session_id: Optional[str] = None
        self.user_id = f"test_user_{int(time.time())}"
        
    async def create_session(self):
        """Create a new AR session"""
        url = f"http://{self.server_host}:{self.server_port}/api/session/create"
        
        payload = {
            "max_players": 4,
            "colocalization_method": "qr_code"
        }
        
        response = requests.post(url, json=payload)
        
        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                self.session_id = data["session_id"]
                print(f"✅ Session created: {self.session_id}")
                return True
            else:
                print(f"❌ Failed to create session: {data.get('error')}")
                return False
        else:
            print(f"❌ HTTP error: {response.status_code}")
            return False
    
    async def connect_to_session(self, session_id: str = None):
        """Connect to an AR session via WebSocket"""
        if session_id:
            self.session_id = session_id
            
        if not self.session_id:
            print("❌ No session ID available")
            return False
            
        try:
            uri = f"ws://{self.server_host}:{self.server_port}/ws/{self.session_id}/{self.user_id}"
            print(f"🔌 Connecting to {uri}")
            
            self.websocket = await websockets.connect(uri)
            print(f"✅ Connected to session: {self.session_id}")
            
            # Start message handler
            asyncio.create_task(self.message_handler())
            return True
            
        except Exception as e:
            print(f"❌ Connection failed: {e}")
            return False
    
    async def message_handler(self):
        """Handle incoming WebSocket messages"""
        try:
            async for message in self.websocket:
                data = json.loads(message)
                await self.handle_message(data)
                
        except websockets.exceptions.ConnectionClosed:
            print("🔌 WebSocket connection closed")
        except Exception as e:
            print(f"❌ Message handler error: {e}")
    
    async def handle_message(self, data: dict):
        """Handle a specific message"""
        message_type = data.get("type")
        
        if message_type == "session_state":
            print(f"📋 Session state received")
            print(f"   Players: {len(data.get('players', {}))}")
            print(f"   Anchors: {len(data.get('anchors', {}))}")
            print(f"   Colocalized: {data.get('is_colocalized', False)}")
            
        elif message_type == "user_joined":
            user_id = data.get("user_id")
            is_host = data.get("is_host", False)
            print(f"👤 User joined: {user_id} {'(Host)' if is_host else ''}")
            
        elif message_type == "user_left":
            user_id = data.get("user_id")
            print(f"👋 User left: {user_id}")
            
        elif message_type == "pose_update":
            user_id = data.get("user_id")
            if user_id:
                pose = data.get("pose", {})
                pos = pose.get("position", {})
                print(f"📍 Pose update from {user_id}: ({pos.get('x', 0):.2f}, {pos.get('y', 0):.2f}, {pos.get('z', 0):.2f})")
            else:
                poses = data.get("poses", {})
                print(f"📍 Batch pose update: {len(poses)} users")
            
        elif message_type == "anchor_create":
            anchor = data.get("anchor", {})
            anchor_id = anchor.get("id", "unknown")
            creator = anchor.get("creator_id", "unknown")
            print(f"⚓ Anchor created: {anchor_id} by {creator}")
            
        elif message_type == "anchor_update":
            anchor_id = data.get("anchor_id", "unknown")
            print(f"⚓ Anchor updated: {anchor_id}")
            
        elif message_type == "anchor_delete":
            anchor_id = data.get("anchor_id", "unknown")
            print(f"⚓ Anchor deleted: {anchor_id}")
            
        elif message_type == "coordinate_system":
            method = data.get("colocalization_method", "unknown")
            print(f"🎯 Coordinate system established (method: {method})")
            
        elif message_type == "chat_message":
            user_id = data.get("user_id", "unknown")
            message = data.get("message", "")
            print(f"💬 Chat from {user_id}: {message}")
            
        elif message_type == "pong":
            client_timestamp = data.get("client_timestamp", 0)
            server_timestamp = data.get("timestamp", 0)
            current_time = int(time.time() * 1000)
            
            if client_timestamp > 0:
                latency = current_time - client_timestamp
                print(f"🏓 Pong received - Latency: {latency}ms")
            
        elif message_type == "error":
            error_message = data.get("message", "Unknown error")
            print(f"❌ Server error: {error_message}")
            
        else:
            print(f"❓ Unknown message type: {message_type}")
    
    async def send_message(self, message: dict):
        """Send a message to the server"""
        if self.websocket:
            try:
                await self.websocket.send(json.dumps(message))
                return True
            except Exception as e:
                print(f"❌ Failed to send message: {e}")
                return False
        return False
    
    async def send_ping(self):
        """Send a ping message"""
        message = {
            "type": "ping",
            "timestamp": int(time.time() * 1000)
        }
        return await self.send_message(message)
    
    async def send_pose_update(self, x: float = 0, y: float = 0, z: float = 1):
        """Send a pose update"""
        message = {
            "type": "pose_update",
            "position": {"x": x, "y": y, "z": z},
            "rotation": {"x": 0, "y": 0, "z": 0, "w": 1},
            "confidence": 1.0,
            "tracking_state": "tracking",
            "timestamp": int(time.time() * 1000)
        }
        return await self.send_message(message)
    
    async def create_anchor(self, x: float = 0, y: float = 0, z: float = 1):
        """Create a spatial anchor"""
        import uuid
        anchor_id = str(uuid.uuid4())
        
        message = {
            "type": "anchor_create",
            "anchor_id": anchor_id,
            "position": {"x": x, "y": y, "z": z},
            "rotation": {"x": 0, "y": 0, "z": 0, "w": 1},
            "metadata": {
                "type": "test_anchor",
                "created_by": "test_client"
            },
            "timestamp": int(time.time() * 1000)
        }
        
        success = await self.send_message(message)
        if success:
            print(f"⚓ Created anchor: {anchor_id}")
        return success
    
    async def send_chat_message(self, text: str):
        """Send a chat message"""
        message = {
            "type": "chat_message",
            "message": text,
            "timestamp": int(time.time() * 1000)
        }
        return await self.send_message(message)
    
    async def set_colocalized(self, colocalized: bool = True):
        """Set colocalization status"""
        message = {
            "type": "colocalization_data",
            "colocalized": colocalized,
            "timestamp": int(time.time() * 1000)
        }
        
        if colocalized:
            # Include coordinate system data
            message["coordinate_system"] = {
                "origin": {"x": 0, "y": 0, "z": 0},
                "rotation": {"x": 0, "y": 0, "z": 0, "w": 1}
            }
            message["method"] = "qr_code"
        
        return await self.send_message(message)
    
    async def disconnect(self):
        """Disconnect from the session"""
        if self.websocket:
            await self.websocket.close()
            print("🔌 Disconnected")

async def interactive_demo():
    """Interactive demo of the multiplayer system"""
    client = TestClient()
    
    print("🚀 Spatial Platform Multiplayer Test Client")
    print("==========================================")
    
    # Create and connect to session
    if not await client.create_session():
        return
    
    if not await client.connect_to_session():
        return
    
    print("\nℹ️  Available commands:")
    print("  ping          - Send ping")
    print("  pose          - Send pose update")
    print("  anchor        - Create anchor")
    print("  chat <msg>    - Send chat message")
    print("  colocalize    - Set as colocalized")
    print("  session_id    - Show session ID")
    print("  quit          - Exit")
    print()
    
    try:
        while True:
            command = input(">>> ").strip().lower()
            
            if command == "quit":
                break
            elif command == "ping":
                await client.send_ping()
            elif command == "pose":
                import random
                x, y, z = random.uniform(-2, 2), random.uniform(0, 2), random.uniform(-2, 2)
                await client.send_pose_update(x, y, z)
                print(f"📍 Sent pose: ({x:.2f}, {y:.2f}, {z:.2f})")
            elif command == "anchor":
                import random
                x, y, z = random.uniform(-1, 1), random.uniform(0, 1), random.uniform(-1, 1)
                await client.create_anchor(x, y, z)
            elif command.startswith("chat "):
                message = command[5:]
                await client.send_chat_message(message)
                print(f"💬 Sent: {message}")
            elif command == "colocalize":
                await client.set_colocalized(True)
                print("🎯 Set as colocalized")
            elif command == "session_id":
                print(f"📋 Session ID: {client.session_id}")
            elif command == "":
                continue
            else:
                print("❓ Unknown command")
                
    except KeyboardInterrupt:
        print("\n👋 Exiting...")
    finally:
        await client.disconnect()

async def automated_test():
    """Automated test sequence"""
    print("🤖 Running automated test sequence...")
    
    client = TestClient()
    
    # Test session creation
    assert await client.create_session(), "Failed to create session"
    
    # Test WebSocket connection
    assert await client.connect_to_session(), "Failed to connect to session"
    
    # Wait for initial session state
    await asyncio.sleep(1)
    
    # Test ping
    await client.send_ping()
    await asyncio.sleep(0.5)
    
    # Test pose updates
    for i in range(3):
        await client.send_pose_update(i, 0, i)
        await asyncio.sleep(0.2)
    
    # Test anchor creation
    await client.create_anchor(1, 0, 1)
    await asyncio.sleep(0.5)
    
    # Test chat
    await client.send_chat_message("Hello from test client!")
    await asyncio.sleep(0.5)
    
    # Test colocalization
    await client.set_colocalized(True)
    await asyncio.sleep(0.5)
    
    print("✅ All tests completed successfully!")
    
    await client.disconnect()

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "auto":
        asyncio.run(automated_test())
    else:
        asyncio.run(interactive_demo())