using System;
using System.Collections;
using System.Collections.Generic;
using System.Threading.Tasks;
using UnityEngine;
using UnityEngine.XR.ARFoundation;
using Nakama;
using Newtonsoft.Json;

namespace SpatialPlatform.Nakama
{
    /// <summary>
    /// Nakama AR Client - Replaces custom WebSocket implementation
    /// Handles real-time AR multiplayer with 60 FPS pose updates
    /// </summary>
    public class NakamaARClient : MonoBehaviour
    {
        [Header("Nakama Configuration")]
        [SerializeField] private string scheme = "http";
        [SerializeField] private string host = "localhost";
        [SerializeField] private int port = 7350;
        [SerializeField] private string serverKey = "defaultkey";
        
        [Header("AR Configuration")]
        [SerializeField] private ARSession arSession;
        [SerializeField] private Camera arCamera;
        [SerializeField] private float poseUpdateInterval = 0.016f; // 60 FPS
        
        [Header("Session Settings")]
        [SerializeField] private int maxPlayers = 8;
        [SerializeField] private string colocalizationMethod = "qr_code";
        
        // Nakama client instances
        private IClient client;
        private ISocket socket;
        private ISession session;
        private IMatch currentMatch;
        
        // Session management
        private string sessionCode;
        private bool isHost = false;
        private bool isColocalized = false;
        private Dictionary<string, RemotePlayer> remotePlayers = new Dictionary<string, RemotePlayer>();
        private Dictionary<string, SpatialAnchor> spatialAnchors = new Dictionary<string, SpatialAnchor>();
        
        // Pose tracking
        private float lastPoseUpdateTime;
        private Pose lastSentPose;
        private const float POSE_THRESHOLD = 0.01f; // Only send if moved 1cm
        
        // Events
        public event Action<string> OnSessionCreated;
        public event Action<string> OnPlayerJoined;
        public event Action<string> OnPlayerLeft;
        public event Action<SpatialAnchor> OnAnchorCreated;
        public event Action<string> OnAnchorDeleted;
        public event Action<bool> OnColocalizationChanged;
        
        // Message operation codes (matching Lua implementation)
        private enum OpCode
        {
            PoseUpdate = 1,
            AnchorCreate = 2,
            AnchorUpdate = 3,
            AnchorDelete = 4,
            ColocalizationData = 5,
            CoordinateSystem = 6,
            ChatMessage = 7,
            Ping = 8,
            Pong = 9,
            SessionState = 10
        }
        
        private void Awake()
        {
            // Initialize Nakama client
            client = new Client(scheme, host, port, serverKey, UnityWebRequestAdapter.Instance);
            DontDestroyOnLoad(gameObject);
        }
        
        /// <summary>
        /// Create anonymous session with 6-character code (like Niantic Lightship)
        /// </summary>
        public async Task<string> CreateAnonymousSession(string displayName = null)
        {
            try
            {
                // Authenticate anonymously
                var deviceId = SystemInfo.deviceUniqueIdentifier;
                session = await client.AuthenticateDeviceAsync(deviceId, displayName ?? $"Player_{UnityEngine.Random.Range(1000, 9999)}");
                
                // Connect to socket
                socket = client.NewSocket();
                await socket.ConnectAsync(session, true);
                
                // Call RPC to create anonymous session
                var payload = new Dictionary<string, object>
                {
                    { "display_name", displayName ?? $"Player_{UnityEngine.Random.Range(1000, 9999)}" }
                };
                
                var response = await client.RpcAsync(session, "create_anonymous_session", JsonConvert.SerializeObject(payload));
                var result = JsonConvert.DeserializeObject<Dictionary<string, object>>(response.Payload);
                
                sessionCode = result["share_code"].ToString();
                Debug.Log($"[NakamaAR] Created anonymous session with code: {sessionCode}");
                
                // Create AR match
                await CreateARMatch();
                
                OnSessionCreated?.Invoke(sessionCode);
                return sessionCode;
            }
            catch (Exception e)
            {
                Debug.LogError($"[NakamaAR] Failed to create anonymous session: {e.Message}");
                throw;
            }
        }
        
        /// <summary>
        /// Join session using 6-character code
        /// </summary>
        public async Task<bool> JoinWithCode(string code, string displayName = null)
        {
            try
            {
                // Authenticate anonymously
                var deviceId = SystemInfo.deviceUniqueIdentifier;
                session = await client.AuthenticateDeviceAsync(deviceId, displayName ?? $"Player_{UnityEngine.Random.Range(1000, 9999)}");
                
                // Connect to socket
                socket = client.NewSocket();
                await socket.ConnectAsync(session, true);
                
                // Call RPC to join with code
                var payload = new Dictionary<string, object>
                {
                    { "code", code.ToUpper() },
                    { "display_name", displayName ?? $"Player_{UnityEngine.Random.Range(1000, 9999)}" }
                };
                
                var response = await client.RpcAsync(session, "join_with_session_code", JsonConvert.SerializeObject(payload));
                var result = JsonConvert.DeserializeObject<Dictionary<string, object>>(response.Payload);
                
                sessionCode = code;
                var sessionId = result["session_id"].ToString();
                
                Debug.Log($"[NakamaAR] Joined session {sessionId} with code: {code}");
                
                // Join the AR match
                await JoinARMatch(sessionId);
                
                return true;
            }
            catch (Exception e)
            {
                Debug.LogError($"[NakamaAR] Failed to join with code: {e.Message}");
                return false;
            }
        }
        
        /// <summary>
        /// Create AR match
        /// </summary>
        private async Task CreateARMatch()
        {
            var payload = new Dictionary<string, object>
            {
                { "max_players", maxPlayers },
                { "colocalization_method", colocalizationMethod }
            };
            
            var response = await client.RpcAsync(session, "create_ar_match", JsonConvert.SerializeObject(payload));
            var result = JsonConvert.DeserializeObject<Dictionary<string, object>>(response.Payload);
            
            var matchId = result["match_id"].ToString();
            currentMatch = await socket.JoinMatchAsync(matchId);
            
            isHost = true;
            SetupMatchHandlers();
            StartCoroutine(SendPoseUpdates());
        }
        
        /// <summary>
        /// Join existing AR match
        /// </summary>
        private async Task JoinARMatch(string matchId)
        {
            currentMatch = await socket.JoinMatchAsync(matchId);
            SetupMatchHandlers();
            StartCoroutine(SendPoseUpdates());
        }
        
        /// <summary>
        /// Setup match message handlers
        /// </summary>
        private void SetupMatchHandlers()
        {
            // Handle match data (pose updates, anchors, etc.)
            socket.ReceivedMatchState += OnMatchState;
            
            // Handle player join
            socket.ReceivedMatchPresence += OnMatchPresence;
        }
        
        /// <summary>
        /// Handle incoming match state messages
        /// </summary>
        private void OnMatchState(IMatchState matchState)
        {
            try
            {
                var opCode = (OpCode)matchState.OpCode;
                var data = System.Text.Encoding.UTF8.GetString(matchState.State);
                var message = JsonConvert.DeserializeObject<Dictionary<string, object>>(data);
                
                switch (opCode)
                {
                    case OpCode.PoseUpdate:
                        HandlePoseUpdate(message);
                        break;
                    
                    case OpCode.AnchorCreate:
                        HandleAnchorCreate(message);
                        break;
                    
                    case OpCode.AnchorUpdate:
                        HandleAnchorUpdate(message);
                        break;
                    
                    case OpCode.AnchorDelete:
                        HandleAnchorDelete(message);
                        break;
                    
                    case OpCode.CoordinateSystem:
                        HandleCoordinateSystem(message);
                        break;
                    
                    case OpCode.SessionState:
                        HandleSessionState(message);
                        break;
                }
            }
            catch (Exception e)
            {
                Debug.LogError($"[NakamaAR] Error handling match state: {e.Message}");
            }
        }
        
        /// <summary>
        /// Handle player presence changes
        /// </summary>
        private void OnMatchPresence(IMatchPresenceEvent presenceEvent)
        {
            // Handle joins
            foreach (var presence in presenceEvent.Joins)
            {
                if (presence.UserId != session.UserId)
                {
                    var player = new RemotePlayer
                    {
                        UserId = presence.UserId,
                        Username = presence.Username
                    };
                    remotePlayers[presence.UserId] = player;
                    OnPlayerJoined?.Invoke(presence.Username);
                    
                    Debug.Log($"[NakamaAR] Player joined: {presence.Username}");
                }
            }
            
            // Handle leaves
            foreach (var presence in presenceEvent.Leaves)
            {
                if (remotePlayers.ContainsKey(presence.UserId))
                {
                    var player = remotePlayers[presence.UserId];
                    if (player.Avatar != null)
                    {
                        Destroy(player.Avatar);
                    }
                    remotePlayers.Remove(presence.UserId);
                    OnPlayerLeft?.Invoke(presence.Username);
                    
                    Debug.Log($"[NakamaAR] Player left: {presence.Username}");
                }
            }
        }
        
        /// <summary>
        /// Send pose updates at 60 FPS
        /// </summary>
        private IEnumerator SendPoseUpdates()
        {
            while (currentMatch != null)
            {
                if (Time.time - lastPoseUpdateTime >= poseUpdateInterval)
                {
                    if (arCamera != null && isColocalized)
                    {
                        var currentPose = new Pose(
                            arCamera.transform.position,
                            arCamera.transform.rotation
                        );
                        
                        // Only send if pose changed significantly
                        if (Vector3.Distance(currentPose.position, lastSentPose.position) > POSE_THRESHOLD ||
                            Quaternion.Angle(currentPose.rotation, lastSentPose.rotation) > 1f)
                        {
                            SendPoseUpdate(currentPose);
                            lastSentPose = currentPose;
                        }
                    }
                    
                    lastPoseUpdateTime = Time.time;
                }
                
                yield return null;
            }
        }
        
        /// <summary>
        /// Send pose update to match
        /// </summary>
        private async void SendPoseUpdate(Pose pose)
        {
            var data = new Dictionary<string, object>
            {
                { "position", new { x = pose.position.x, y = pose.position.y, z = pose.position.z } },
                { "rotation", new { x = pose.rotation.x, y = pose.rotation.y, z = pose.rotation.z, w = pose.rotation.w } },
                { "timestamp", Time.time },
                { "confidence", 0.95f },
                { "tracking_state", "tracking" }
            };
            
            var state = System.Text.Encoding.UTF8.GetBytes(JsonConvert.SerializeObject(data));
            await socket.SendMatchStateAsync(currentMatch.Id, (long)OpCode.PoseUpdate, state);
        }
        
        /// <summary>
        /// Handle incoming pose updates
        /// </summary>
        private void HandlePoseUpdate(Dictionary<string, object> message)
        {
            if (message.ContainsKey("poses"))
            {
                var poses = JsonConvert.DeserializeObject<Dictionary<string, PoseData>>(message["poses"].ToString());
                
                foreach (var kvp in poses)
                {
                    var userId = kvp.Key;
                    var poseData = kvp.Value;
                    
                    if (remotePlayers.ContainsKey(userId))
                    {
                        var player = remotePlayers[userId];
                        
                        // Create avatar if needed
                        if (player.Avatar == null)
                        {
                            player.Avatar = CreatePlayerAvatar();
                        }
                        
                        // Update position and rotation
                        player.Avatar.transform.position = new Vector3(
                            poseData.position.x,
                            poseData.position.y,
                            poseData.position.z
                        );
                        
                        player.Avatar.transform.rotation = new Quaternion(
                            poseData.rotation.x,
                            poseData.rotation.y,
                            poseData.rotation.z,
                            poseData.rotation.w
                        );
                    }
                }
            }
        }
        
        /// <summary>
        /// Create spatial anchor
        /// </summary>
        public async Task<string> CreateSpatialAnchor(Vector3 position, Quaternion rotation, Dictionary<string, object> metadata = null)
        {
            var anchorId = Guid.NewGuid().ToString();
            
            var data = new Dictionary<string, object>
            {
                { "anchor_id", anchorId },
                { "position", new { x = position.x, y = position.y, z = position.z } },
                { "rotation", new { x = rotation.x, y = rotation.y, z = rotation.z, w = rotation.w } },
                { "metadata", metadata ?? new Dictionary<string, object>() }
            };
            
            var state = System.Text.Encoding.UTF8.GetBytes(JsonConvert.SerializeObject(data));
            await socket.SendMatchStateAsync(currentMatch.Id, (long)OpCode.AnchorCreate, state);
            
            return anchorId;
        }
        
        /// <summary>
        /// Handle anchor creation
        /// </summary>
        private void HandleAnchorCreate(Dictionary<string, object> message)
        {
            var anchor = JsonConvert.DeserializeObject<SpatialAnchor>(message["anchor"].ToString());
            spatialAnchors[anchor.id] = anchor;
            
            // Create visual representation
            var anchorObject = CreateAnchorVisualization(anchor);
            anchor.gameObject = anchorObject;
            
            OnAnchorCreated?.Invoke(anchor);
        }
        
        /// <summary>
        /// Handle anchor update
        /// </summary>
        private void HandleAnchorUpdate(Dictionary<string, object> message)
        {
            var anchorId = message["anchor_id"].ToString();
            
            if (spatialAnchors.ContainsKey(anchorId))
            {
                var anchor = spatialAnchors[anchorId];
                
                // Update position if provided
                if (message.ContainsKey("position"))
                {
                    var pos = JsonConvert.DeserializeObject<Vector3Data>(message["position"].ToString());
                    anchor.position = new Vector3(pos.x, pos.y, pos.z);
                    
                    if (anchor.gameObject != null)
                    {
                        anchor.gameObject.transform.position = anchor.position;
                    }
                }
                
                // Update rotation if provided
                if (message.ContainsKey("rotation"))
                {
                    var rot = JsonConvert.DeserializeObject<QuaternionData>(message["rotation"].ToString());
                    anchor.rotation = new Quaternion(rot.x, rot.y, rot.z, rot.w);
                    
                    if (anchor.gameObject != null)
                    {
                        anchor.gameObject.transform.rotation = anchor.rotation;
                    }
                }
            }
        }
        
        /// <summary>
        /// Handle anchor deletion
        /// </summary>
        private void HandleAnchorDelete(Dictionary<string, object> message)
        {
            var anchorId = message["anchor_id"].ToString();
            
            if (spatialAnchors.ContainsKey(anchorId))
            {
                var anchor = spatialAnchors[anchorId];
                
                if (anchor.gameObject != null)
                {
                    Destroy(anchor.gameObject);
                }
                
                spatialAnchors.Remove(anchorId);
                OnAnchorDeleted?.Invoke(anchorId);
            }
        }
        
        /// <summary>
        /// Handle coordinate system updates
        /// </summary>
        private void HandleCoordinateSystem(Dictionary<string, object> message)
        {
            isColocalized = Convert.ToBoolean(message["is_colocalized"]);
            OnColocalizationChanged?.Invoke(isColocalized);
            
            Debug.Log($"[NakamaAR] Colocalization status: {isColocalized}");
        }
        
        /// <summary>
        /// Handle session state updates
        /// </summary>
        private void HandleSessionState(Dictionary<string, object> message)
        {
            // Process current session state
            if (message.ContainsKey("anchors"))
            {
                var anchors = JsonConvert.DeserializeObject<Dictionary<string, SpatialAnchor>>(message["anchors"].ToString());
                
                foreach (var kvp in anchors)
                {
                    spatialAnchors[kvp.Key] = kvp.Value;
                    var anchorObject = CreateAnchorVisualization(kvp.Value);
                    kvp.Value.gameObject = anchorObject;
                }
            }
        }
        
        /// <summary>
        /// Create player avatar GameObject
        /// </summary>
        private GameObject CreatePlayerAvatar()
        {
            var avatar = GameObject.CreatePrimitive(PrimitiveType.Capsule);
            avatar.transform.localScale = new Vector3(0.3f, 0.5f, 0.3f);
            
            // Add visual indicator
            var renderer = avatar.GetComponent<Renderer>();
            renderer.material.color = new Color(
                UnityEngine.Random.Range(0.5f, 1f),
                UnityEngine.Random.Range(0.5f, 1f),
                UnityEngine.Random.Range(0.5f, 1f)
            );
            
            return avatar;
        }
        
        /// <summary>
        /// Create anchor visualization GameObject
        /// </summary>
        private GameObject CreateAnchorVisualization(SpatialAnchor anchor)
        {
            var anchorObject = GameObject.CreatePrimitive(PrimitiveType.Cube);
            anchorObject.transform.position = anchor.position;
            anchorObject.transform.rotation = anchor.rotation;
            anchorObject.transform.localScale = Vector3.one * 0.1f;
            
            // Make it semi-transparent
            var renderer = anchorObject.GetComponent<Renderer>();
            var material = renderer.material;
            material.color = new Color(0, 1, 0, 0.5f);
            
            return anchorObject;
        }
        
        /// <summary>
        /// Disconnect from Nakama
        /// </summary>
        public async Task Disconnect()
        {
            if (currentMatch != null)
            {
                await socket.LeaveMatchAsync(currentMatch.Id);
                currentMatch = null;
            }
            
            if (socket != null)
            {
                await socket.CloseAsync();
            }
        }
        
        private void OnDestroy()
        {
            StopAllCoroutines();
            _ = Disconnect();
        }
        
        // Data structures
        [Serializable]
        private class RemotePlayer
        {
            public string UserId;
            public string Username;
            public GameObject Avatar;
        }
        
        [Serializable]
        public class SpatialAnchor
        {
            public string id;
            public Vector3 position;
            public Quaternion rotation;
            public Dictionary<string, object> metadata;
            public string creator_id;
            public float creation_time;
            public GameObject gameObject;
        }
        
        [Serializable]
        private class PoseData
        {
            public Vector3Data position;
            public QuaternionData rotation;
            public float timestamp;
            public float confidence;
            public string tracking_state;
        }
        
        [Serializable]
        private class Vector3Data
        {
            public float x, y, z;
        }
        
        [Serializable]
        private class QuaternionData
        {
            public float x, y, z, w;
        }
    }
}