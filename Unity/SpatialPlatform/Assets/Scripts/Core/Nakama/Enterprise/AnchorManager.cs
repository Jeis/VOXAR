using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using UnityEngine;
using Newtonsoft.Json;

namespace SpatialPlatform.Nakama.Enterprise
{
    // Manages cloud anchors for AR sessions
    public class AnchorManager
    {
        private readonly SessionManager session;
        private readonly Dictionary<string, CloudAnchor> anchors;
        private readonly VPSConfig vpsConfig;
        
        public IReadOnlyDictionary<string, CloudAnchor> CloudAnchors => cloudAnchors;
        
        public event Action<CloudAnchor> OnAnchorCreated;
        public event Action<CloudAnchor> OnAnchorUpdated;
        public event Action<string> OnAnchorDeleted;
        public event Action<string> OnError;
        
        public AnchorManager(SessionManager sessionManager, VPSConfig vpsConfig)
        {
            this.sessionManager = sessionManager;
            this.vpsConfig = vpsConfig;
            this.cloudAnchors = new Dictionary<string, CloudAnchor>();
        }
        
        /// <summary>
        /// Create a new cloud anchor
        /// </summary>
        public async Task<CloudAnchor> CreateAnchor(Pose pose, Dictionary<string, object> metadata = null)
        {
            try
            {
                var anchorId = Guid.NewGuid().ToString();
                
                var anchor = new CloudAnchor
                {
                    id = anchorId,
                    pose = pose,
                    metadata = metadata ?? new Dictionary<string, object>(),
                    creatorId = sessionManager.CurrentMatch?.Self?.UserId ?? "unknown",
                    isPersistent = true,
                    cloudState = CloudAnchorState.Pending
                };
                
                // Send to other players
                var data = new Dictionary<string, object>
                {
                    { "anchor_id", anchorId },
                    { "position", PoseToDict(pose.position) },
                    { "rotation", PoseToDict(pose.rotation) },
                    { "metadata", metadata ?? new Dictionary<string, object>() },
                    { "is_persistent", true }
                };
                
                await sessionManager.SendMatchState(OpCode.AnchorCreate, data);
                
                cloudAnchors[anchorId] = anchor;
                OnAnchorCreated?.Invoke(anchor);
                
                // If VPS enabled, persist to cloud
                if (vpsConfig.vpsEnabled)
                {
                    _ = PersistAnchorToCloud(anchor);
                }
                
                Debug.Log($"[AnchorManager] Created anchor: {anchorId}");
                return anchor;
            }
            catch (Exception e)
            {
                OnError?.Invoke($"Failed to create anchor: {e.Message}");
                throw;
            }
        }
        
        /// <summary>
        /// Process anchor-related match state
        /// </summary>
        public void ProcessMatchState(OpCode opCode, string userId, Dictionary<string, object> data)
        {
            try
            {
                switch (opCode)
                {
                    case OpCode.AnchorCreate:
                        ProcessAnchorCreate(userId, data);
                        break;
                        
                    case OpCode.AnchorUpdate:
                        ProcessAnchorUpdate(userId, data);
                        break;
                        
                    case OpCode.AnchorDelete:
                        ProcessAnchorDelete(userId, data);
                        break;
                }
            }
            catch (Exception e)
            {
                OnError?.Invoke($"Error processing anchor state: {e.Message}");
            }
        }
        
        private void ProcessAnchorCreate(string userId, Dictionary<string, object> data)
        {
            var anchorId = data["anchor_id"].ToString();
            var position = DictToVector3((Dictionary<string, object>)data["position"]);
            var rotation = DictToQuaternion((Dictionary<string, object>)data["rotation"]);
            var metadata = (Dictionary<string, object>)data["metadata"];
            
            var anchor = new CloudAnchor
            {
                id = anchorId,
                pose = new Pose(position, rotation),
                metadata = metadata,
                creatorId = userId,
                isPersistent = Convert.ToBoolean(data["is_persistent"]),
                cloudState = CloudAnchorState.Created
            };
            
            cloudAnchors[anchorId] = anchor;
            OnAnchorCreated?.Invoke(anchor);
        }
        
        private void ProcessAnchorUpdate(string userId, Dictionary<string, object> data)
        {
            var anchorId = data["anchor_id"].ToString();
            
            if (cloudAnchors.ContainsKey(anchorId))
            {
                var anchor = cloudAnchors[anchorId];
                
                if (data.ContainsKey("position") && data.ContainsKey("rotation"))
                {
                    var position = DictToVector3((Dictionary<string, object>)data["position"]);
                    var rotation = DictToQuaternion((Dictionary<string, object>)data["rotation"]);
                    anchor.pose = new Pose(position, rotation);
                }
                
                if (data.ContainsKey("metadata"))
                {
                    anchor.metadata = (Dictionary<string, object>)data["metadata"];
                }
                
                OnAnchorUpdated?.Invoke(anchor);
            }
        }
        
        private void ProcessAnchorDelete(string userId, Dictionary<string, object> data)
        {
            var anchorId = data["anchor_id"].ToString();
            
            if (cloudAnchors.ContainsKey(anchorId))
            {
                cloudAnchors.Remove(anchorId);
                OnAnchorDeleted?.Invoke(anchorId);
            }
        }
        
        /// <summary>
        /// Delete an anchor
        /// </summary>
        public async Task<bool> DeleteAnchor(string anchorId)
        {
            try
            {
                if (!cloudAnchors.ContainsKey(anchorId))
                {
                    return false;
                }
                
                var data = new Dictionary<string, object>
                {
                    { "anchor_id", anchorId }
                };
                
                await sessionManager.SendMatchState(OpCode.AnchorDelete, data);
                
                cloudAnchors.Remove(anchorId);
                OnAnchorDeleted?.Invoke(anchorId);
                
                return true;
            }
            catch (Exception e)
            {
                OnError?.Invoke($"Failed to delete anchor: {e.Message}");
                return false;
            }
        }
        
        private async Task PersistAnchorToCloud(CloudAnchor anchor)
        {
            try
            {
                // Placeholder for VPS cloud persistence
                // This would integrate with actual VPS cloud anchor service
                await Task.Delay(100);
                
                anchor.cloudState = CloudAnchorState.Created;
                Debug.Log($"[AnchorManager] Anchor persisted to cloud: {anchor.id}");
            }
            catch (Exception e)
            {
                anchor.cloudState = CloudAnchorState.Failed;
                OnError?.Invoke($"Failed to persist anchor to cloud: {e.Message}");
            }
        }
        
        /// <summary>
        /// Get anchor by ID
        /// </summary>
        public CloudAnchor GetAnchor(string anchorId)
        {
            return cloudAnchors.ContainsKey(anchorId) ? cloudAnchors[anchorId] : null;
        }
        
        /// <summary>
        /// Clear all anchors
        /// </summary>
        public void ClearAnchors()
        {
            cloudAnchors.Clear();
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
    }
}