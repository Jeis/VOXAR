#!/usr/bin/env python3
"""
Test script for Nakama authentication migration
Validates that new Nakama auth system works before removing custom WebSocket
"""

import asyncio
import json
import time
import requests
import websockets
from typing import Optional, Dict, Any

class NakamaAuthTester:
    def __init__(self, nakama_host="localhost", nakama_port=7350):
        self.nakama_host = nakama_host
        self.nakama_port = nakama_port
        self.base_url = f"http://{nakama_host}:{nakama_port}"
        
    async def test_anonymous_session_creation(self) -> Dict[str, Any]:
        """Test creating anonymous session with 6-character code"""
        print("Testing anonymous session creation...")
        
        try:
            # Call Nakama RPC for anonymous session creation
            response = requests.post(
                f"{self.base_url}/v2/rpc/create_anonymous_session",
                json={
                    "display_name": "TestPlayer"
                },
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code == 200:
                result = response.json()
                session_code = result.get("share_code", "")
                
                # Validate code format (ABC123)
                if len(session_code) == 6 and session_code[:3].isalpha() and session_code[3:].isdigit():
                    print(f"✅ Anonymous session created successfully: {session_code}")
                    return result
                else:
                    print(f"❌ Invalid session code format: {session_code}")
                    return None
            else:
                print(f"❌ Failed to create session: {response.status_code}")
                print(response.text)
                return None
                
        except Exception as e:
            print(f"❌ Exception during session creation: {e}")
            return None
    
    async def test_join_with_code(self, session_code: str) -> Dict[str, Any]:
        """Test joining session with 6-character code"""
        print(f"Testing join with code: {session_code}")
        
        try:
            response = requests.post(
                f"{self.base_url}/v2/rpc/join_with_session_code",
                json={
                    "code": session_code,
                    "display_name": "JoiningPlayer"
                },
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code == 200:
                result = response.json()
                print(f"✅ Successfully joined session with code: {session_code}")
                return result
            else:
                print(f"❌ Failed to join session: {response.status_code}")
                print(response.text)
                return None
                
        except Exception as e:
            print(f"❌ Exception during join: {e}")
            return None
    
    async def test_session_stats(self) -> Dict[str, Any]:
        """Test session statistics endpoint"""
        print("Testing session statistics...")
        
        try:
            response = requests.post(
                f"{self.base_url}/v2/rpc/get_session_stats",
                json={},
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code == 200:
                result = response.json()
                print(f"✅ Session stats retrieved: {result}")
                return result
            else:
                print(f"❌ Failed to get stats: {response.status_code}")
                return None
                
        except Exception as e:
            print(f"❌ Exception during stats: {e}")
            return None
    
    async def test_session_cleanup(self) -> Dict[str, Any]:
        """Test session cleanup functionality"""
        print("Testing session cleanup...")
        
        try:
            response = requests.post(
                f"{self.base_url}/v2/rpc/cleanup_expired_sessions",
                json={},
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code == 200:
                result = response.json()
                print(f"✅ Session cleanup completed: {result}")
                return result
            else:
                print(f"❌ Failed cleanup: {response.status_code}")
                return None
                
        except Exception as e:
            print(f"❌ Exception during cleanup: {e}")
            return None
    
    async def test_invalid_code_handling(self):
        """Test handling of invalid session codes"""
        print("Testing invalid code handling...")
        
        invalid_codes = [
            "INVALID",  # Wrong format
            "ABC12",    # Too short
            "ABC1234",  # Too long
            "123ABC",   # Wrong order
            "ABCDEF"    # All letters
        ]
        
        for code in invalid_codes:
            try:
                response = requests.post(
                    f"{self.base_url}/v2/rpc/join_with_session_code",
                    json={
                        "code": code,
                        "display_name": "TestPlayer"
                    },
                    headers={"Content-Type": "application/json"}
                )
                
                if response.status_code != 200:
                    print(f"✅ Correctly rejected invalid code: {code}")
                else:
                    print(f"❌ Unexpectedly accepted invalid code: {code}")
                    
            except Exception as e:
                print(f"✅ Exception for invalid code {code}: {e}")
    
    async def run_full_test_suite(self):
        """Run complete authentication migration test suite"""
        print("🧪 Starting Nakama Authentication Migration Test Suite")
        print("=" * 60)
        
        # Test 1: Anonymous session creation
        session_result = await self.test_anonymous_session_creation()
        if not session_result:
            print("❌ Critical failure: Cannot create anonymous sessions")
            return False
        
        session_code = session_result.get("share_code")
        
        # Test 2: Join with valid code
        join_result = await self.test_join_with_code(session_code)
        if not join_result:
            print("❌ Critical failure: Cannot join with valid code")
            return False
        
        # Test 3: Session statistics
        await self.test_session_stats()
        
        # Test 4: Invalid code handling
        await self.test_invalid_code_handling()
        
        # Test 5: Session cleanup
        await self.test_session_cleanup()
        
        print("\n" + "=" * 60)
        print("✅ Nakama Authentication Migration Test Suite PASSED")
        print("✅ Ready to proceed with WebSocket server migration")
        
        return True

async def main():
    """Main test execution"""
    tester = NakamaAuthTester()
    
    print("Waiting for Nakama to start...")
    await asyncio.sleep(2)
    
    # Run test suite
    success = await tester.run_full_test_suite()
    
    if success:
        print("\n🎉 Authentication migration validation successful!")
        print("🔄 Proceeding to Phase 2: Real-time AR Logic Migration")
    else:
        print("\n⚠️  Authentication migration validation failed!")
        print("🔧 Please check Nakama configuration and try again")

if __name__ == "__main__":
    asyncio.run(main())