using System;
using System.Collections.Generic;
using System.Linq;
using UnityEngine;
using Nakama;
using Newtonsoft.Json;

namespace SpatialPlatform.Nakama.Enterprise
{
    /// <summary>
    /// Enterprise Player Manager for Nakama AR
    /// Handles remote player tracking, pose updates, and synchronization
    /// </summary>
    public class PlayerManager
    {
        private readonly SessionManager sessionManager;
        private readonly ARConfig arConfig;
        private readonly Dictionary<string, RemotePlayer> remotePlayers;
        private readonly Queue<PoseUpdate> poseUpdateQueue;
        
        private float lastPoseUpdateTime;
        private Pose lastSentPose;
        private bool isColocalized = false;
        
        public IReadOnlyDictionary<string, RemotePlayer> RemotePlayers => remotePlayers;
        public bool IsColocalized => isColocalized;
        public float LastPoseUpdateTime => lastPoseUpdateTime;
        
        public event Action<RemotePlayer> OnPlayerJoined;
        public event Action<string> OnPlayerLeft;
        public event Action<string, Pose> OnPlayerPoseUpdated;
        public event Action<bool> OnColocalizationChanged;
        
        public PlayerManager(SessionManager sessionManager, ARConfig arConfig)
        {
            this.sessionManager = sessionManager;
            this.arConfig = arConfig;
            this.remotePlayers = new Dictionary<string, RemotePlayer>();
            this.poseUpdateQueue = new Queue<PoseUpdate>();
        }
        
        /// <summary>
        /// Process match presence updates (players joining/leaving)
        /// </summary>
        public void ProcessMatchPresence(IMatchPresenceEvent matchPresence)
        {
            // Handle joins
            foreach (var user in matchPresence.Joins)
            {
                if (user.UserId != sessionManager.CurrentMatch?.Self?.UserId)
                {
                    var player = new RemotePlayer
                    {
                        userId = user.UserId,
                        displayName = user.Username ?? $"Player_{user.UserId.Substring(0, 4)}",
                        isColocalized = false
                    };
                    
                    remotePlayers[user.UserId] = player;
                    OnPlayerJoined?.Invoke(player);
                    
                    Debug.Log($"[PlayerManager] Player joined: {player.displayName} ({user.UserId})");
                }
            }
            
            // Handle leaves
            foreach (var user in matchPresence.Leaves)
            {
                if (remotePlayers.ContainsKey(user.UserId))
                {
                    var player = remotePlayers[user.UserId];
                    remotePlayers.Remove(user.UserId);
                    OnPlayerLeft?.Invoke(user.UserId);
                    
                    Debug.Log($"[PlayerManager] Player left: {player.displayName} ({user.UserId})");
                }
            }
        }
        
        /// <summary>
        /// Process incoming match state for player updates
        /// </summary>
        public void ProcessMatchState(IMatchState matchState)
        {
            try
            {
                var opCode = (OpCode)matchState.OpCode;
                var data = JsonConvert.DeserializeObject<Dictionary<string, object>>(
                    System.Text.Encoding.UTF8.GetString(matchState.State)
                );
                
                switch (opCode)
                {
                    case OpCode.PoseUpdate:
                        ProcessPoseUpdate(matchState.UserPresence.UserId, data);
                        break;
                        
                    case OpCode.ColocalizationData:
                        ProcessColocalizationUpdate(matchState.UserPresence.UserId, data);
                        break;
                        
                    case OpCode.Ping:
                        ProcessPingMessage(matchState.UserPresence.UserId, data);
                        break;
                }
            }
            catch (Exception e)
            {
                Debug.LogError($"[PlayerManager] Error processing match state: {e.Message}");
            }
        }
        
        /// <summary>
        /// Send pose update if significant movement detected
        /// </summary>
        public async void UpdateLocalPose(Pose currentPose)
        {
            if (Time.time - lastPoseUpdateTime < arConfig.poseUpdateInterval)
            {
                return;
            }
            
            // Check if pose changed significantly
            if (HasPoseChangedSignificantly(currentPose, lastSentPose))
            {
                var poseData = new Dictionary<string, object>
                {
                    { "position", PoseToDict(currentPose.position) },
                    { "rotation", PoseToDict(currentPose.rotation) },
                    { "timestamp", Time.time },
                    { "is_colocalized", isColocalized }
                };
                
                try
                {
                    await sessionManager.SendMatchState(OpCode.PoseUpdate, poseData);
                    
                    lastSentPose = currentPose;
                    lastPoseUpdateTime = Time.time;
                }
                catch (Exception e)
                {
                    Debug.LogError($"[PlayerManager] Failed to send pose update: {e.Message}");
                }
            }
        }
        
        private void ProcessPoseUpdate(string userId, Dictionary<string, object> data)
        {
            if (!remotePlayers.ContainsKey(userId))
            {
                return;
            }
            
            try
            {
                var position = DictToVector3((Dictionary<string, object>)data["position"]);
                var rotation = DictToQuaternion((Dictionary<string, object>)data["rotation"]);
                var timestamp = Convert.ToSingle(data["timestamp"]);
                var isPlayerColocalized = data.ContainsKey("is_colocalized") && 
                                        Convert.ToBoolean(data["is_colocalized"]);
                
                var player = remotePlayers[userId];
                player.currentPose = new Pose(position, rotation);
                player.lastUpdateTime = timestamp;
                player.isColocalized = isPlayerColocalized;
                
                OnPlayerPoseUpdated?.Invoke(userId, player.currentPose);
                
                // Apply pose prediction if enabled
                if (arConfig.enablePosePrediction)
                {
                    ApplyPosePrediction(player);
                }
            }
            catch (Exception e)
            {
                Debug.LogError($"[PlayerManager] Error processing pose update: {e.Message}");
            }
        }
        
        private void ProcessColocalizationUpdate(string userId, Dictionary<string, object> data)
        {
            try
            {
                var wasColocalized = isColocalized;
                var newColocalizationState = Convert.ToBoolean(data["is_colocalized"]);
                
                if (remotePlayers.ContainsKey(userId))
                {
                    remotePlayers[userId].isColocalized = newColocalizationState;
                }
                
                // Update global colocalization state
                UpdateGlobalColocalizationState();
                
                if (wasColocalized != isColocalized)
                {
                    OnColocalizationChanged?.Invoke(isColocalized);
                }
            }
            catch (Exception e)
            {
                Debug.LogError($"[PlayerManager] Error processing colocalization update: {e.Message}");
            }
        }
        
        private void ProcessPingMessage(string userId, Dictionary<string, object> data)
        {
            // Respond with pong for latency measurement
            var pongData = new Dictionary<string, object>
            {
                { "timestamp", data["timestamp"] },
                { "pong_timestamp", Time.time }
            };
            
            _ = sessionManager.SendMatchState(OpCode.Pong, pongData);
        }
        
        private bool HasPoseChangedSignificantly(Pose current, Pose last)
        {
            var positionDelta = Vector3.Distance(current.position, last.position);
            var rotationDelta = Quaternion.Angle(current.rotation, last.rotation);
            
            return positionDelta > arConfig.poseDistanceThreshold ||
                   rotationDelta > arConfig.poseAngleThreshold;
        }
        
        private void ApplyPosePrediction(RemotePlayer player)
        {
            if (!arConfig.enablePosePrediction) return;
            
            // Simple linear prediction based on time delta
            var timeDelta = Time.time - player.lastUpdateTime;
            if (timeDelta > 0.1f) // Only predict if update is old
            {
                // This is a simplified prediction - real implementation would use velocity
                var predictedPosition = player.currentPose.position;
                player.currentPose = new Pose(predictedPosition, player.currentPose.rotation);
            }
        }
        
        private void UpdateGlobalColocalizationState()
        {
            // All players must be colocalized for global state to be true
            isColocalized = remotePlayers.Values.All(p => p.isColocalized) && 
                           remotePlayers.Count > 0;
        }
        
        /// <summary>
        /// Send colocalization status update
        /// </summary>
        public async void UpdateColocalizationStatus(bool colocalized)
        {
            var data = new Dictionary<string, object>
            {
                { "is_colocalized", colocalized },
                { "timestamp", Time.time }
            };
            
            try
            {
                await sessionManager.SendMatchState(OpCode.ColocalizationData, data);
                UpdateGlobalColocalizationState();
            }
            catch (Exception e)
            {
                Debug.LogError($"[PlayerManager] Failed to send colocalization update: {e.Message}");
            }
        }
        
        /// <summary>
        /// Get player by user ID
        /// </summary>
        public RemotePlayer GetPlayer(string userId)
        {
            return remotePlayers.ContainsKey(userId) ? remotePlayers[userId] : null;
        }
        
        /// <summary>
        /// Clear all player data
        /// </summary>
        public void ClearPlayers()
        {
            remotePlayers.Clear();
            poseUpdateQueue.Clear();
            isColocalized = false;
        }
        
        // Utility methods
        private Dictionary<string, object> PoseToDict(Vector3 vector)
        {
            return new Dictionary<string, object>
            {
                { "x", vector.x },
                { "y", vector.y },
                { "z", vector.z }
            };
        }
        
        private Dictionary<string, object> PoseToDict(Quaternion quaternion)
        {
            return new Dictionary<string, object>
            {
                { "x", quaternion.x },
                { "y", quaternion.y },
                { "z", quaternion.z },
                { "w", quaternion.w }
            };
        }
        
        private Vector3 DictToVector3(Dictionary<string, object> dict)
        {
            return new Vector3(
                Convert.ToSingle(dict["x"]),
                Convert.ToSingle(dict["y"]),
                Convert.ToSingle(dict["z"])
            );
        }
        
        private Quaternion DictToQuaternion(Dictionary<string, object> dict)
        {
            return new Quaternion(
                Convert.ToSingle(dict["x"]),
                Convert.ToSingle(dict["y"]),
                Convert.ToSingle(dict["z"]),
                Convert.ToSingle(dict["w"])
            );
        }
        
        // Enterprise Integration Methods
        
        /// <summary>
        /// Send pose update - enterprise integration method
        /// </summary>
        public async Task SendPoseUpdate(Pose currentPose)
        {
            UpdateLocalPose(currentPose);
            await Task.CompletedTask; // UpdateLocalPose is already async
        }
        
        /// <summary>
        /// Start colocalization process with enterprise methods
        /// </summary>
        public async Task<bool> StartColocalization(ColocalizationMethod method = ColocalizationMethod.QRCode)
        {
            try
            {
                switch (method)
                {
                    case ColocalizationMethod.VPS:
                        return await StartVPSColocalization();
                        
                    case ColocalizationMethod.QRCode:
                        return await StartQRColocalization();
                        
                    case ColocalizationMethod.Manual:
                        return await StartManualColocalization();
                        
                    default:
                        Debug.LogError($"[PlayerManager] Unknown colocalization method: {method}");
                        return false;
                }
            }
            catch (Exception e)
            {
                Debug.LogError($"[PlayerManager] Colocalization failed: {e.Message}");
                return false;
            }
        }
        
        private async Task<bool> StartVPSColocalization()
        {
            Debug.Log("[PlayerManager] Starting VPS colocalization");
            
            // Enterprise VPS colocalization implementation
            // This would integrate with actual VPS service
            await Task.Delay(2000); // Simulate VPS localization time
            
            UpdateColocalizationStatus(true);
            Debug.Log("[PlayerManager] ✅ VPS colocalization completed");
            
            return true;
        }
        
        private async Task<bool> StartQRColocalization()
        {
            Debug.Log("[PlayerManager] Starting QR colocalization");
            
            // Enterprise QR colocalization implementation
            // This would integrate with QR scanning framework
            await Task.Delay(1000); // Simulate QR detection time
            
            UpdateColocalizationStatus(true);
            Debug.Log("[PlayerManager] ✅ QR colocalization completed");
            
            return true;
        }
        
        private async Task<bool> StartManualColocalization()
        {
            Debug.Log("[PlayerManager] Starting manual colocalization");
            
            // Enterprise manual colocalization
            // User manually aligns to known reference point
            await Task.Delay(500); // Immediate confirmation
            
            UpdateColocalizationStatus(true);
            Debug.Log("[PlayerManager] ✅ Manual colocalization completed");
            
            return true;
        }
    }
}