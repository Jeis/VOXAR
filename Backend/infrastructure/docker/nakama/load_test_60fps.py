#!/usr/bin/env python3
"""
Nakama AR Platform - 60 FPS Load Testing Script
Validates real-time performance with multiple concurrent users
"""

import asyncio
import time
import json
import statistics
import websockets
import aiohttp
from typing import List, Dict, Any
import numpy as np
from dataclasses import dataclass, asdict
from datetime import datetime
import argparse

@dataclass
class TestMetrics:
    """Performance metrics for load testing"""
    user_id: str
    messages_sent: int = 0
    messages_received: int = 0
    pose_updates_sent: int = 0
    pose_updates_received: int = 0
    latencies: List[float] = None
    connection_time: float = 0
    test_duration: float = 0
    errors: int = 0
    
    def __post_init__(self):
        if self.latencies is None:
            self.latencies = []
    
    def get_stats(self) -> Dict[str, Any]:
        """Calculate performance statistics"""
        if not self.latencies:
            return {
                "user_id": self.user_id,
                "error": "No latency data collected"
            }
        
        return {
            "user_id": self.user_id,
            "messages_sent": self.messages_sent,
            "messages_received": self.messages_received,
            "pose_updates_sent": self.pose_updates_sent,
            "pose_updates_received": self.pose_updates_received,
            "avg_latency_ms": statistics.mean(self.latencies),
            "min_latency_ms": min(self.latencies),
            "max_latency_ms": max(self.latencies),
            "p50_latency_ms": statistics.median(self.latencies),
            "p95_latency_ms": np.percentile(self.latencies, 95) if len(self.latencies) > 0 else 0,
            "p99_latency_ms": np.percentile(self.latencies, 99) if len(self.latencies) > 0 else 0,
            "connection_time_ms": self.connection_time * 1000,
            "test_duration_s": self.test_duration,
            "errors": self.errors,
            "fps_achieved": self.pose_updates_sent / max(self.test_duration, 1)
        }

class NakamaLoadTester:
    def __init__(self, host="localhost", port=7350, ws_port=7349):
        self.host = host
        self.port = port
        self.ws_port = ws_port
        self.base_url = f"http://{host}:{port}"
        self.ws_url = f"ws://{host}:{ws_port}/ws"
        
    async def create_anonymous_session(self) -> Dict[str, Any]:
        """Create anonymous session and get credentials"""
        async with aiohttp.ClientSession() as session:
            # Call RPC to create anonymous session
            async with session.post(
                f"{self.base_url}/v2/rpc/create_anonymous_session",
                json={"display_name": f"LoadTest_{int(time.time())}"},
                headers={"Content-Type": "application/json"}
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    raise Exception(f"Failed to create session: {resp.status}")
    
    async def create_ar_match(self) -> str:
        """Create a new AR match and return match ID"""
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/v2/rpc/create_ar_match",
                json={
                    "max_players": 10,
                    "colocalization_method": "qr_code"
                },
                headers={"Content-Type": "application/json"}
            ) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    return result.get("match_id")
                else:
                    raise Exception(f"Failed to create match: {resp.status}")
    
    async def simulate_user(self, match_id: str, user_index: int, duration_seconds: int = 30) -> TestMetrics:
        """Simulate a single AR user sending pose updates at 60 FPS"""
        metrics = TestMetrics(user_id=f"user_{user_index}")
        
        try:
            # Track connection time
            connect_start = time.time()
            
            # Connect to Nakama WebSocket
            async with websockets.connect(self.ws_url) as websocket:
                metrics.connection_time = time.time() - connect_start
                
                # Join the match
                join_msg = {
                    "match_join": {
                        "match_id": match_id
                    }
                }
                await websocket.send(json.dumps(join_msg))
                
                # Start time tracking
                start_time = time.time()
                last_pose_time = start_time
                pose_interval = 1.0 / 60.0  # 60 FPS = ~16.67ms between updates
                
                # Create tasks for sending and receiving
                send_task = asyncio.create_task(
                    self.send_pose_updates(websocket, metrics, duration_seconds, pose_interval)
                )
                receive_task = asyncio.create_task(
                    self.receive_messages(websocket, metrics, duration_seconds)
                )
                
                # Wait for both tasks
                await asyncio.gather(send_task, receive_task)
                
                metrics.test_duration = time.time() - start_time
                
        except Exception as e:
            print(f"User {user_index} error: {e}")
            metrics.errors += 1
        
        return metrics
    
    async def send_pose_updates(self, websocket, metrics: TestMetrics, duration: int, interval: float):
        """Send pose updates at specified interval (60 FPS)"""
        start_time = time.time()
        
        while (time.time() - start_time) < duration:
            try:
                # Generate realistic pose data
                pose_data = {
                    "match_data_send": {
                        "match_id": "",  # Will be filled by Nakama
                        "op_code": 1,  # POSE_UPDATE
                        "data": json.dumps({
                            "position": {
                                "x": np.random.uniform(-10, 10),
                                "y": np.random.uniform(0, 3),
                                "z": np.random.uniform(-10, 10)
                            },
                            "rotation": {
                                "x": np.random.uniform(-1, 1),
                                "y": np.random.uniform(-1, 1),
                                "z": np.random.uniform(-1, 1),
                                "w": np.random.uniform(0, 1)
                            },
                            "timestamp": time.time(),
                            "confidence": 0.95,
                            "tracking_state": "tracking"
                        })
                    }
                }
                
                send_time = time.time()
                await websocket.send(json.dumps(pose_data))
                metrics.messages_sent += 1
                metrics.pose_updates_sent += 1
                
                # Maintain 60 FPS rate
                elapsed = time.time() - send_time
                sleep_time = max(0, interval - elapsed)
                await asyncio.sleep(sleep_time)
                
            except Exception as e:
                print(f"Send error: {e}")
                metrics.errors += 1
                break
    
    async def receive_messages(self, websocket, metrics: TestMetrics, duration: int):
        """Receive and process messages from Nakama"""
        start_time = time.time()
        
        while (time.time() - start_time) < duration:
            try:
                # Set timeout to avoid blocking forever
                msg = await asyncio.wait_for(websocket.recv(), timeout=0.1)
                receive_time = time.time()
                
                metrics.messages_received += 1
                
                # Parse message and track latency
                data = json.loads(msg)
                
                # Check if it's a pose update
                if "match_data" in data:
                    match_data = data["match_data"]
                    if match_data.get("op_code") == 1:  # POSE_UPDATE
                        metrics.pose_updates_received += 1
                        
                        # Calculate latency if timestamp present
                        try:
                            payload = json.loads(match_data.get("data", "{}"))
                            if "timestamp" in payload:
                                latency = (receive_time - payload["timestamp"]) * 1000
                                metrics.latencies.append(latency)
                        except:
                            pass
                
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                if "normal" not in str(e).lower():
                    print(f"Receive error: {e}")
                    metrics.errors += 1
                break
    
    async def run_load_test(self, num_users: int = 8, duration_seconds: int = 30):
        """Run load test with specified number of concurrent users"""
        print(f"\n🚀 Starting Nakama AR Load Test")
        print(f"{'='*60}")
        print(f"Users: {num_users}")
        print(f"Duration: {duration_seconds} seconds")
        print(f"Target: 60 FPS pose updates")
        print(f"Expected updates per user: {60 * duration_seconds}")
        print(f"{'='*60}\n")
        
        # Create AR match
        print("Creating AR match...")
        match_id = await self.create_ar_match()
        print(f"Match created: {match_id}\n")
        
        # Create concurrent user tasks
        print(f"Spawning {num_users} concurrent users...")
        tasks = []
        for i in range(num_users):
            task = self.simulate_user(match_id, i, duration_seconds)
            tasks.append(task)
            await asyncio.sleep(0.1)  # Stagger connections slightly
        
        # Wait for all users to complete
        print(f"Running {duration_seconds} second test...\n")
        results = await asyncio.gather(*tasks)
        
        # Analyze results
        self.analyze_results(results, duration_seconds)
    
    def analyze_results(self, results: List[TestMetrics], duration: int):
        """Analyze and display test results"""
        print(f"\n{'='*60}")
        print(f"📊 LOAD TEST RESULTS")
        print(f"{'='*60}\n")
        
        # Aggregate metrics
        total_sent = sum(m.pose_updates_sent for m in results)
        total_received = sum(m.pose_updates_received for m in results)
        all_latencies = []
        
        for metrics in results:
            all_latencies.extend(metrics.latencies)
        
        # Calculate expected values
        expected_updates_per_user = 60 * duration
        expected_total = expected_updates_per_user * len(results)
        
        # Display per-user stats
        print("PER-USER STATISTICS:")
        print("-" * 40)
        
        for metrics in results:
            stats = metrics.get_stats()
            fps = stats["fps_achieved"]
            efficiency = (metrics.pose_updates_sent / expected_updates_per_user) * 100
            
            print(f"User: {stats['user_id']}")
            print(f"  Sent: {metrics.pose_updates_sent} updates ({fps:.1f} FPS)")
            print(f"  Received: {metrics.pose_updates_received} updates")
            print(f"  Avg Latency: {stats.get('avg_latency_ms', 0):.2f}ms")
            print(f"  P95 Latency: {stats.get('p95_latency_ms', 0):.2f}ms")
            print(f"  Efficiency: {efficiency:.1f}%")
            print(f"  Errors: {metrics.errors}")
            print()
        
        # Display aggregate stats
        print("\nAGGREGATE STATISTICS:")
        print("-" * 40)
        print(f"Total Updates Sent: {total_sent}/{expected_total} ({(total_sent/expected_total)*100:.1f}%)")
        print(f"Total Updates Received: {total_received}")
        print(f"Broadcast Multiplication: {total_received/max(total_sent, 1):.2f}x")
        
        if all_latencies:
            print(f"\nLATENCY ANALYSIS:")
            print("-" * 40)
            print(f"Average: {statistics.mean(all_latencies):.2f}ms")
            print(f"Median: {statistics.median(all_latencies):.2f}ms")
            print(f"Min: {min(all_latencies):.2f}ms")
            print(f"Max: {max(all_latencies):.2f}ms")
            print(f"P95: {np.percentile(all_latencies, 95):.2f}ms")
            print(f"P99: {np.percentile(all_latencies, 99):.2f}ms")
            
            # Check if we meet 60 FPS target (16.67ms frame time)
            under_target = sum(1 for l in all_latencies if l < 16.67)
            target_percentage = (under_target / len(all_latencies)) * 100
            
            print(f"\n60 FPS TARGET (16.67ms):")
            print("-" * 40)
            print(f"Messages under target: {target_percentage:.1f}%")
            
            if target_percentage >= 95:
                print("✅ PASSED: System achieves 60 FPS for 95%+ of messages")
            elif target_percentage >= 90:
                print("⚠️  WARNING: System achieves 60 FPS for 90-95% of messages")
            else:
                print("❌ FAILED: System does not meet 60 FPS target")
        
        # Overall assessment
        print(f"\n{'='*60}")
        avg_fps = total_sent / (len(results) * duration)
        if avg_fps >= 58:  # Allow 3% variance
            print("✅ OVERALL: Load test PASSED - System handles 60 FPS")
        else:
            print(f"❌ OVERALL: Load test FAILED - Only achieved {avg_fps:.1f} FPS")
        print(f"{'='*60}\n")

async def main():
    parser = argparse.ArgumentParser(description="Nakama AR Platform Load Tester")
    parser.add_argument("--users", type=int, default=8, help="Number of concurrent users")
    parser.add_argument("--duration", type=int, default=30, help="Test duration in seconds")
    parser.add_argument("--host", default="localhost", help="Nakama host")
    parser.add_argument("--port", type=int, default=7350, help="Nakama HTTP port")
    parser.add_argument("--ws-port", type=int, default=7349, help="Nakama WebSocket port")
    
    args = parser.parse_args()
    
    tester = NakamaLoadTester(args.host, args.port, args.ws_port)
    await tester.run_load_test(args.users, args.duration)

if __name__ == "__main__":
    asyncio.run(main())