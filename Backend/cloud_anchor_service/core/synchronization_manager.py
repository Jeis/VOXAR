"""
Synchronization Manager - Real-time anchor synchronization
WebSocket-based real-time updates and conflict resolution
"""

import logging
import asyncio
import json
from typing import Dict, List, Set, Optional, Any, Callable
from datetime import datetime, timedelta
import weakref
from dataclasses import asdict

from .anchor_manager import SpatialAnchor, AnchorManager

logger = logging.getLogger(__name__)

class SyncClient:
    """Represents a connected client for synchronization"""
    
    def __init__(self, client_id: str, user_id: str, session_id: str, websocket):
        self.client_id = client_id
        self.user_id = user_id
        self.session_id = session_id
        self.websocket = websocket
        self.subscribed_anchors: Set[str] = set()
        self.last_heartbeat = datetime.utcnow()
        self.is_active = True

class SynchronizationManager:
    """
    Real-time synchronization manager for spatial anchors
    Handles WebSocket connections and anchor updates
    """
    
    def __init__(self, anchor_manager: AnchorManager):
        self.anchor_manager = anchor_manager
        
        # Connected clients
        self.clients: Dict[str, SyncClient] = {}
        self.session_clients: Dict[str, Set[str]] = {}  # session_id -> client_ids
        self.user_clients: Dict[str, Set[str]] = {}     # user_id -> client_ids
        
        # Synchronization configuration
        self.config = {
            'heartbeat_interval': 30,  # seconds
            'client_timeout': 90,      # seconds
            'max_clients_per_session': 50,
            'sync_batch_size': 100,
            'conflict_resolution': 'last_writer_wins'
        }
        
        # Performance tracking
        self.stats = {
            'total_connections': 0,
            'active_connections': 0,
            'messages_sent': 0,
            'messages_received': 0,
            'sync_operations': 0,
            'conflicts_resolved': 0
        }
        
        # Background tasks
        self.heartbeat_task = None
        self.cleanup_task = None
        self.is_initialized = False

    async def initialize(self) -> None:
        """Initialize synchronization manager"""
        try:
            logger.info("Initializing Synchronization Manager...")
            
            # Start background tasks
            self.heartbeat_task = asyncio.create_task(self._heartbeat_loop())
            self.cleanup_task = asyncio.create_task(self._cleanup_loop())
            
            self.is_initialized = True
            logger.info("✅ Synchronization Manager initialized")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize Synchronization Manager: {e}")
            raise

    async def register_client(self, client_id: str, user_id: str, session_id: str, 
                            websocket) -> bool:
        """Register a new client for synchronization"""
        try:
            # Check session client limit
            if session_id in self.session_clients:
                if len(self.session_clients[session_id]) >= self.config['max_clients_per_session']:
                    logger.warning(f"Session {session_id} has reached maximum client limit")
                    return False
            
            # Create client
            client = SyncClient(client_id, user_id, session_id, websocket)
            self.clients[client_id] = client
            
            # Update session tracking
            if session_id not in self.session_clients:
                self.session_clients[session_id] = set()
            self.session_clients[session_id].add(client_id)
            
            # Update user tracking
            if user_id not in self.user_clients:
                self.user_clients[user_id] = set()
            self.user_clients[user_id].add(client_id)
            
            # Update statistics
            self.stats['total_connections'] += 1
            self.stats['active_connections'] = len(self.clients)
            
            logger.info(f"Registered client {client_id} for user {user_id} in session {session_id}")
            
            # Send initial anchor state
            await self._send_initial_anchors(client)
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to register client {client_id}: {e}")
            return False

    async def unregister_client(self, client_id: str) -> bool:
        """Unregister a client"""
        try:
            client = self.clients.pop(client_id, None)
            if not client:
                return False
            
            # Remove from session tracking
            if client.session_id in self.session_clients:
                self.session_clients[client.session_id].discard(client_id)
                if not self.session_clients[client.session_id]:
                    del self.session_clients[client.session_id]
            
            # Remove from user tracking
            if client.user_id in self.user_clients:
                self.user_clients[client.user_id].discard(client_id)
                if not self.user_clients[client.user_id]:
                    del self.user_clients[client.user_id]
            
            # Update statistics
            self.stats['active_connections'] = len(self.clients)
            
            logger.info(f"Unregistered client {client_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to unregister client {client_id}: {e}")
            return False

    async def handle_message(self, client_id: str, message: Dict[str, Any]) -> None:
        """Handle incoming message from client"""
        try:
            client = self.clients.get(client_id)
            if not client:
                logger.warning(f"Message from unknown client {client_id}")
                return
            
            client.last_heartbeat = datetime.utcnow()
            self.stats['messages_received'] += 1
            
            message_type = message.get('type')
            
            if message_type == 'heartbeat':
                await self._handle_heartbeat(client)
            
            elif message_type == 'anchor_created':
                await self._handle_anchor_created(client, message)
            
            elif message_type == 'anchor_updated':
                await self._handle_anchor_updated(client, message)
            
            elif message_type == 'anchor_deleted':
                await self._handle_anchor_deleted(client, message)
            
            elif message_type == 'subscribe_anchor':
                await self._handle_subscribe_anchor(client, message)
            
            elif message_type == 'unsubscribe_anchor':
                await self._handle_unsubscribe_anchor(client, message)
            
            else:
                logger.warning(f"Unknown message type: {message_type}")
                
        except Exception as e:
            logger.error(f"Error handling message from {client_id}: {e}")

    async def _handle_heartbeat(self, client: SyncClient):
        """Handle heartbeat message"""
        response = {
            'type': 'heartbeat_ack',
            'timestamp': datetime.utcnow().isoformat(),
            'server_time': datetime.utcnow().timestamp()
        }
        await self._send_to_client(client, response)

    async def _handle_anchor_created(self, client: SyncClient, message: Dict[str, Any]):
        """Handle anchor creation from client"""
        try:
            anchor_data = message.get('anchor')
            if not anchor_data:
                return
            
            # Create anchor through anchor manager
            anchor = await self.anchor_manager.create_anchor(
                session_id=client.session_id,
                user_id=client.user_id,
                position=anchor_data.get('position', [0, 0, 0]),
                rotation=anchor_data.get('rotation', [0, 0, 0, 1]),
                anchor_type=anchor_data.get('anchor_type', 'persistent'),
                metadata=anchor_data.get('metadata', {})
            )
            
            # Broadcast to other clients in session
            await self._broadcast_anchor_update(anchor, 'anchor_created', exclude_client=client.client_id)
            
            # Send confirmation to originating client
            response = {
                'type': 'anchor_created_ack',
                'anchor_id': anchor.id,
                'timestamp': datetime.utcnow().isoformat()
            }
            await self._send_to_client(client, response)
            
            self.stats['sync_operations'] += 1
            
        except Exception as e:
            logger.error(f"Failed to handle anchor creation: {e}")
            await self._send_error(client, "anchor_creation_failed", str(e))

    async def _handle_anchor_updated(self, client: SyncClient, message: Dict[str, Any]):
        """Handle anchor update from client"""
        try:
            anchor_id = message.get('anchor_id')
            updates = message.get('updates', {})
            
            if not anchor_id:
                return
            
            # Update anchor through anchor manager
            anchor = await self.anchor_manager.update_anchor(
                anchor_id=anchor_id,
                position=updates.get('position'),
                rotation=updates.get('rotation'),
                confidence=updates.get('confidence'),
                tracking_state=updates.get('tracking_state'),
                metadata=updates.get('metadata')
            )
            
            if anchor:
                # Broadcast to subscribed clients
                await self._broadcast_anchor_update(anchor, 'anchor_updated', exclude_client=client.client_id)
                
                # Send confirmation
                response = {
                    'type': 'anchor_updated_ack',
                    'anchor_id': anchor_id,
                    'timestamp': datetime.utcnow().isoformat()
                }
                await self._send_to_client(client, response)
                
                self.stats['sync_operations'] += 1
            
        except Exception as e:
            logger.error(f"Failed to handle anchor update: {e}")
            await self._send_error(client, "anchor_update_failed", str(e))

    async def _handle_anchor_deleted(self, client: SyncClient, message: Dict[str, Any]):
        """Handle anchor deletion from client"""
        try:
            anchor_id = message.get('anchor_id')
            if not anchor_id:
                return
            
            # Get anchor before deletion for broadcasting
            anchor = await self.anchor_manager.get_anchor(anchor_id)
            
            # Delete anchor
            success = await self.anchor_manager.delete_anchor(anchor_id)
            
            if success and anchor:
                # Broadcast to subscribed clients
                await self._broadcast_anchor_update(anchor, 'anchor_deleted', exclude_client=client.client_id)
                
                # Send confirmation
                response = {
                    'type': 'anchor_deleted_ack',
                    'anchor_id': anchor_id,
                    'timestamp': datetime.utcnow().isoformat()
                }
                await self._send_to_client(client, response)
                
                self.stats['sync_operations'] += 1
            
        except Exception as e:
            logger.error(f"Failed to handle anchor deletion: {e}")
            await self._send_error(client, "anchor_deletion_failed", str(e))

    async def _handle_subscribe_anchor(self, client: SyncClient, message: Dict[str, Any]):
        """Handle anchor subscription request"""
        try:
            anchor_id = message.get('anchor_id')
            if anchor_id:
                client.subscribed_anchors.add(anchor_id)
                
                # Send current anchor state
                anchor = await self.anchor_manager.get_anchor(anchor_id)
                if anchor:
                    response = {
                        'type': 'anchor_state',
                        'anchor': anchor.to_dict(),
                        'timestamp': datetime.utcnow().isoformat()
                    }
                    await self._send_to_client(client, response)
                
        except Exception as e:
            logger.error(f"Failed to handle anchor subscription: {e}")

    async def _handle_unsubscribe_anchor(self, client: SyncClient, message: Dict[str, Any]):
        """Handle anchor unsubscription request"""
        try:
            anchor_id = message.get('anchor_id')
            if anchor_id:
                client.subscribed_anchors.discard(anchor_id)
                
        except Exception as e:
            logger.error(f"Failed to handle anchor unsubscription: {e}")

    async def _send_initial_anchors(self, client: SyncClient):
        """Send initial anchor state to newly connected client"""
        try:
            # Get session anchors
            anchors = await self.anchor_manager.get_session_anchors(client.session_id)
            
            # Send anchors in batches
            batch_size = self.config['sync_batch_size']
            for i in range(0, len(anchors), batch_size):
                batch = anchors[i:i + batch_size]
                
                response = {
                    'type': 'initial_anchors',
                    'anchors': [anchor.to_dict() for anchor in batch],
                    'batch_info': {
                        'batch_index': i // batch_size,
                        'total_batches': (len(anchors) + batch_size - 1) // batch_size,
                        'total_anchors': len(anchors)
                    },
                    'timestamp': datetime.utcnow().isoformat()
                }
                
                await self._send_to_client(client, response)
            
        except Exception as e:
            logger.error(f"Failed to send initial anchors to {client.client_id}: {e}")

    async def _broadcast_anchor_update(self, anchor: SpatialAnchor, update_type: str, 
                                     exclude_client: Optional[str] = None):
        """Broadcast anchor update to relevant clients"""
        try:
            message = {
                'type': update_type,
                'anchor': anchor.to_dict(),
                'timestamp': datetime.utcnow().isoformat()
            }
            
            # Send to session clients
            session_clients = self.session_clients.get(anchor.session_id, set())
            
            tasks = []
            for client_id in session_clients:
                if client_id == exclude_client:
                    continue
                
                client = self.clients.get(client_id)
                if client and client.is_active:
                    # Check if client is subscribed to this anchor
                    if update_type == 'anchor_deleted' or anchor.id in client.subscribed_anchors:
                        tasks.append(self._send_to_client(client, message))
            
            # Send concurrently
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
                self.stats['messages_sent'] += len(tasks)
            
        except Exception as e:
            logger.error(f"Failed to broadcast anchor update: {e}")

    async def _send_to_client(self, client: SyncClient, message: Dict[str, Any]):
        """Send message to specific client"""
        try:
            if not client.is_active:
                return
            
            message_json = json.dumps(message, default=str)
            await client.websocket.send_text(message_json)
            
        except Exception as e:
            logger.error(f"Failed to send message to client {client.client_id}: {e}")
            client.is_active = False

    async def _send_error(self, client: SyncClient, error_type: str, error_message: str):
        """Send error message to client"""
        error_response = {
            'type': 'error',
            'error_type': error_type,
            'error_message': error_message,
            'timestamp': datetime.utcnow().isoformat()
        }
        await self._send_to_client(client, error_response)

    async def _heartbeat_loop(self):
        """Background heartbeat and client health check"""
        while True:
            try:
                await asyncio.sleep(self.config['heartbeat_interval'])
                
                current_time = datetime.utcnow()
                timeout_threshold = current_time - timedelta(seconds=self.config['client_timeout'])
                
                # Check for timed out clients
                timed_out_clients = []
                for client_id, client in self.clients.items():
                    if client.last_heartbeat < timeout_threshold:
                        timed_out_clients.append(client_id)
                        client.is_active = False
                
                # Remove timed out clients
                for client_id in timed_out_clients:
                    await self.unregister_client(client_id)
                
                if timed_out_clients:
                    logger.info(f"Removed {len(timed_out_clients)} timed out clients")
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Heartbeat loop error: {e}")

    async def _cleanup_loop(self):
        """Background cleanup task"""
        while True:
            try:
                await asyncio.sleep(300)  # 5 minutes
                
                # Remove inactive clients
                inactive_clients = [
                    client_id for client_id, client in self.clients.items()
                    if not client.is_active
                ]
                
                for client_id in inactive_clients:
                    await self.unregister_client(client_id)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Cleanup loop error: {e}")

    async def get_metrics(self) -> Dict[str, Any]:
        """Get synchronization metrics"""
        return {
            'statistics': self.stats,
            'configuration': self.config,
            'active_state': {
                'active_clients': len(self.clients),
                'active_sessions': len(self.session_clients),
                'active_users': len(self.user_clients),
                'is_initialized': self.is_initialized
            },
            'timestamp': datetime.utcnow().isoformat()
        }

    async def health_check(self) -> bool:
        """Check synchronization manager health"""
        try:
            return self.is_initialized and self.anchor_manager is not None
        except Exception:
            return False

    async def shutdown(self):
        """Shutdown synchronization manager"""
        try:
            # Cancel background tasks
            if self.heartbeat_task:
                self.heartbeat_task.cancel()
            if self.cleanup_task:
                self.cleanup_task.cancel()
            
            # Wait for tasks to complete
            tasks = [self.heartbeat_task, self.cleanup_task]
            await asyncio.gather(*[t for t in tasks if t], return_exceptions=True)
            
            # Close all client connections
            for client in self.clients.values():
                try:
                    await client.websocket.close()
                except Exception:
                    pass
            
            self.clients.clear()
            self.session_clients.clear()
            self.user_clients.clear()
            
            logger.info("Synchronization Manager shutdown complete")
            
        except Exception as e:
            logger.error(f"Error during synchronization manager shutdown: {e}")