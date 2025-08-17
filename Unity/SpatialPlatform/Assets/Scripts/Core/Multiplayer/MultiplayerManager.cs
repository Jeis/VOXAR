/*
 * Spatial Platform - Multiplayer Manager
 * Handles WebSocket connections, session management, and real-time synchronization
 */

using System;
using System.Collections;
using System.Collections.Generic;
using System.Text;
using UnityEngine;
using UnityEngine.Networking;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using NativeWebSocket;
using SpatialPlatform.Auth;

namespace SpatialPlatform.Multiplayer
{
    public class MultiplayerManager : MonoBehaviour
    {
        [Header("Connection Settings")]
        [SerializeField] private string serverHost = "localhost";
        [SerializeField] private int serverPort = 8080;
        [SerializeField] private bool useSSL = false;
        [SerializeField] private float reconnectDelay = 5f;
        [SerializeField] private int maxReconnectAttempts = 5;
        
        [Header("Session Settings")]
        [SerializeField] private int maxPlayersPerSession = 8;
        [SerializeField] private string colocalizationMethod = "qr_code";
        [SerializeField] private bool autoReconnect = true;
        
        [Header("Authentication")]
        [SerializeField] private AuthenticationManager authManager;
        [SerializeField] private bool requireAuthentication = false;
        [SerializeField] private bool allowAnonymousSessions = true;
        [SerializeField] private string anonymousDisplayName = "";
        
        [Header("Performance")]
        [SerializeField] private float poseUpdateRate = 60f; // Hz
        [SerializeField] private float pingInterval = 10f; // seconds
        [SerializeField] private bool enableInterpolation = true;
        
        [Header("Debug")]
        [SerializeField] private bool showDebugInfo = true;
        [SerializeField] private bool logMessages = false;
        
        // Connection state
        private WebSocket websocket;
        private bool isConnected = false;
        private bool isConnecting = false;
        private int reconnectAttempts = 0;
        
        // Anonymous session support
        private bool isAnonymousSession = false;
        private string anonymousSessionId = "";
        private string anonymousShareCode = "";
        private string anonymousUserId = "";
        private float lastPingTime = 0f;
        private float lastPoseUpdateTime = 0f;
        
        // Session state
        private string currentSessionId;
        private bool isHost = false;
        private bool isColocalized = false;
        private Dictionary<string, PlayerData> remotePlayers = new Dictionary<string, PlayerData>();
        private Dictionary<string, SpatialAnchorData> sharedAnchors = new Dictionary<string, SpatialAnchorData>();
        private CoordinateSystem coordinateSystem;
        
        // Performance metrics
        private float averageLatency = 0f;
        private int messagesSent = 0;
        private int messagesReceived = 0;
        private float connectionStartTime = 0f;
        
        // Events
        public event Action<bool> OnConnectionStateChanged;
        public event Action<string> OnSessionJoined;
        public event Action<PlayerData> OnPlayerJoined;
        public event Action<string> OnPlayerLeft;
        public event Action<string, Pose> OnPlayerPoseUpdate;
        public event Action<SpatialAnchorData> OnAnchorCreated;
        public event Action<SpatialAnchorData> OnAnchorUpdated;
        public event Action<string> OnAnchorDeleted;
        public event Action<CoordinateSystem> OnCoordinateSystemEstablished;
        public event Action<string, string> OnChatMessage;
        public event Action<string> OnError;
        
        // Anonymous session events
        public event Action<AnonymousSessionResponse> OnAnonymousSessionCreated;
        public event Action<AnonymousJoinResponse> OnAnonymousSessionJoined;
        
        // Properties
        public bool IsConnected => isConnected;
        public bool IsHost => isHost;
        public bool IsColocalized => isColocalized;
        public string CurrentSessionId => currentSessionId;
        public Dictionary<string, PlayerData> RemotePlayers => remotePlayers;
        public Dictionary<string, SpatialAnchorData> SharedAnchors => sharedAnchors;
        public NetworkStats NetworkStats => GetNetworkStats();
        
        // Anonymous session properties
        public bool IsAnonymousSession => isAnonymousSession;
        public string AnonymousShareCode => anonymousShareCode;
        public string AnonymousUserId => anonymousUserId;
        
        private void Awake()
        {
            // Find authentication manager if not assigned
            if (authManager == null)
            {
                authManager = FindObjectOfType<AuthenticationManager>();
            }
            
            if (authManager == null && requireAuthentication)
            {
                Debug.LogError("AuthenticationManager is required but not found!");
            }
        }
        
        private void Start()
        {
            StartCoroutine(UpdateLoop());
        }
        
        private void Update()
        {
            // Dispatch WebSocket messages on main thread
            websocket?.DispatchMessageQueue();
        }
        
        private IEnumerator UpdateLoop()
        {
            while (true)
            {
                try
                {
                    // Send ping periodically
                    if (isConnected && Time.time - lastPingTime > pingInterval)
                    {
                        await SendPing();
                        lastPingTime = Time.time;
                    }
                    
                    // Send pose updates at specified rate
                    if (isConnected && isColocalized && Time.time - lastPoseUpdateTime > (1f / poseUpdateRate))
                    {
                        await SendPoseUpdate();
                        lastPoseUpdateTime = Time.time;
                    }
                    
                    yield return new WaitForSeconds(0.016f); // ~60 FPS
                }
                catch (Exception e)
                {
                    Debug.LogError($"Error in multiplayer update loop: {e.Message}");
                    yield return new WaitForSeconds(1f);
                }
            }
        }
        
        // Public API Methods
        public async void CreateSession()
        {
            // Check authentication
            if (requireAuthentication && (authManager == null || !authManager.IsAuthenticated))
            {
                OnError?.Invoke("Authentication required to create session");
                return;
            }
            
            try
            {
                string url = $"http{(useSSL ? "s" : "")}://{serverHost}:{serverPort}/api/v1/session/create";
                
                var requestData = new
                {
                    max_players = maxPlayersPerSession,
                    colocalization_method = colocalizationMethod,
                    is_public = false,
                    session_name = $"{authManager?.Username ?? "Unknown"}'s Session"
                };
                
                using (UnityWebRequest request = authManager.CreateAuthenticatedRequest(url, "POST", requestData))
                {
                    await request.SendWebRequest();
                    
                    if (request.result == UnityWebRequest.Result.Success)
                    {
                        var response = JsonConvert.DeserializeObject<SessionCreateResponse>(request.downloadHandler.text);
                        if (response.success)
                        {
                            Debug.Log($"Session created: {response.session_id}");
                            await ConnectToSession(response.session_id);
                        }
                        else
                        {
                            OnError?.Invoke($"Failed to create session: {response.error}");
                        }
                    }
                    else
                    {
                        OnError?.Invoke($"Network error creating session: {request.error}");
                    }
                }
            }
            catch (Exception e)
            {
                OnError?.Invoke($"Error creating session: {e.Message}");
            }
        }
        
        public async void CreateAnonymousSession()
        {
            try
            {
                string url = $"http{(useSSL ? "s" : "")}://{serverHost}:{serverPort}/api/v1/session/anonymous/create";
                
                var requestData = new
                {
                    display_name = string.IsNullOrEmpty(anonymousDisplayName) ? $"Player_{UnityEngine.Random.Range(1000, 9999)}" : anonymousDisplayName,
                    colocalization_method = colocalizationMethod,
                    max_players = maxPlayersPerSession
                };
                
                string jsonData = JsonConvert.SerializeObject(requestData);
                byte[] bodyRaw = Encoding.UTF8.GetBytes(jsonData);
                
                using (UnityWebRequest request = new UnityWebRequest(url, "POST"))
                {
                    request.uploadHandler = new UploadHandlerRaw(bodyRaw);
                    request.downloadHandler = new DownloadHandlerBuffer();
                    request.SetRequestHeader("Content-Type", "application/json");
                    
                    await request.SendWebRequest();
                    
                    if (request.result == UnityWebRequest.Result.Success)
                    {
                        var response = JsonConvert.DeserializeObject<AnonymousSessionResponse>(request.downloadHandler.text);
                        
                        isAnonymousSession = true;
                        anonymousSessionId = response.session_id;
                        anonymousShareCode = response.share_code;
                        anonymousUserId = response.creator.id;
                        
                        Debug.Log($"Anonymous session created with code: {anonymousShareCode}");
                        OnAnonymousSessionCreated?.Invoke(response);
                        
                        await ConnectToSession(response.session_id);
                    }
                    else
                    {
                        OnError?.Invoke($"Network error creating anonymous session: {request.error}");
                    }
                }
            }
            catch (Exception e)
            {
                OnError?.Invoke($"Error creating anonymous session: {e.Message}");
            }
        }
        
        public async void JoinAnonymousSession(string shareCode)
        {
            try
            {
                string url = $"http{(useSSL ? "s" : "")}://{serverHost}:{serverPort}/api/v1/session/anonymous/join";
                
                var requestData = new
                {
                    code = shareCode.ToUpper(),
                    display_name = string.IsNullOrEmpty(anonymousDisplayName) ? $"Player_{UnityEngine.Random.Range(1000, 9999)}" : anonymousDisplayName
                };
                
                string jsonData = JsonConvert.SerializeObject(requestData);
                byte[] bodyRaw = Encoding.UTF8.GetBytes(jsonData);
                
                using (UnityWebRequest request = new UnityWebRequest(url, "POST"))
                {
                    request.uploadHandler = new UploadHandlerRaw(bodyRaw);
                    request.downloadHandler = new DownloadHandlerBuffer();
                    request.SetRequestHeader("Content-Type", "application/json");
                    
                    await request.SendWebRequest();
                    
                    if (request.result == UnityWebRequest.Result.Success)
                    {
                        var response = JsonConvert.DeserializeObject<AnonymousJoinResponse>(request.downloadHandler.text);
                        
                        isAnonymousSession = true;
                        anonymousSessionId = response.session_id;
                        anonymousShareCode = response.share_code;
                        anonymousUserId = response.user.id;
                        
                        Debug.Log($"Joined anonymous session with code: {anonymousShareCode}");
                        OnAnonymousSessionJoined?.Invoke(response);
                        
                        await ConnectToSession(response.session_id);
                    }
                    else
                    {
                        OnError?.Invoke($"Failed to join session with code {shareCode}: {request.error}");
                    }
                }
            }
            catch (Exception e)
            {
                OnError?.Invoke($"Error joining anonymous session: {e.Message}");
            }
        }

        public async void JoinSession(string sessionId)
        {
            await ConnectToSession(sessionId);
        }
        
        public async void LeaveSession()
        {
            if (websocket != null && isConnected)
            {
                await websocket.Close();
            }
            
            ResetSessionState();
        }
        
        public async void SetColocalized(bool colocalized, CoordinateSystem coordinateSystem = null)
        {
            isColocalized = colocalized;
            
            if (isConnected)
            {
                var message = new
                {
                    type = "colocalization_data",
                    colocalized = colocalized,
                    coordinate_system = coordinateSystem,
                    method = colocalizationMethod,
                    timestamp = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds()
                };
                
                await SendMessage(message);
            }
        }
        
        public async void CreateAnchor(string anchorId, Pose pose, Dictionary<string, object> metadata = null)
        {
            if (!isConnected) return;
            
            var message = new
            {
                type = "anchor_create",
                anchor_id = anchorId,
                position = new { x = pose.position.x, y = pose.position.y, z = pose.position.z },
                rotation = new { x = pose.rotation.x, y = pose.rotation.y, z = pose.rotation.z, w = pose.rotation.w },
                metadata = metadata ?? new Dictionary<string, object>(),
                timestamp = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds()
            };
            
            await SendMessage(message);
        }
        
        public async void UpdateAnchor(string anchorId, Pose? pose = null, Dictionary<string, object> metadata = null)
        {
            if (!isConnected) return;
            
            var message = new Dictionary<string, object>
            {
                ["type"] = "anchor_update",
                ["anchor_id"] = anchorId,
                ["timestamp"] = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds()
            };
            
            if (pose.HasValue)
            {
                message["position"] = new { x = pose.Value.position.x, y = pose.Value.position.y, z = pose.Value.position.z };
                message["rotation"] = new { x = pose.Value.rotation.x, y = pose.Value.rotation.y, z = pose.Value.rotation.z, w = pose.Value.rotation.w };
            }
            
            if (metadata != null)
            {
                message["metadata"] = metadata;
            }
            
            await SendMessage(message);
        }
        
        public async void DeleteAnchor(string anchorId)
        {
            if (!isConnected) return;
            
            var message = new
            {
                type = "anchor_delete",
                anchor_id = anchorId,
                timestamp = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds()
            };
            
            await SendMessage(message);
        }
        
        public async void SendChatMessage(string text)
        {
            if (!isConnected) return;
            
            var message = new
            {
                type = "chat_message",
                message = text,
                timestamp = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds()
            };
            
            await SendMessage(message);
        }
        
        // Private Methods
        private async Task ConnectToSession(string sessionId)
        {
            if (isConnecting || isConnected) return;
            
            // Check authentication for non-anonymous sessions
            if (requireAuthentication && !isAnonymousSession && (authManager == null || !authManager.IsAuthenticated))
            {
                OnError?.Invoke("Authentication required to connect to session");
                return;
            }
            
            isConnecting = true;
            currentSessionId = sessionId;
            connectionStartTime = Time.time;
            
            try
            {
                // Build WebSocket URL with optional token
                string wsUrl;
                if (isAnonymousSession)
                {
                    // Anonymous sessions don't require authentication token
                    wsUrl = $"ws{(useSSL ? "s" : "")}://{serverHost}:{serverPort}/ws/{sessionId}";
                }
                else
                {
                    // Use token-based WebSocket URL for authenticated sessions
                    string token = authManager?.AccessToken ?? "";
                    wsUrl = $"ws{(useSSL ? "s" : "")}://{serverHost}:{serverPort}/ws/{sessionId}?token={token}";
                }
                
                websocket = new WebSocket(wsUrl);
                
                websocket.OnOpen += OnWebSocketOpen;
                websocket.OnMessage += OnWebSocketMessage;
                websocket.OnError += OnWebSocketError;
                websocket.OnClose += OnWebSocketClose;
                
                await websocket.Connect();
            }
            catch (Exception e)
            {
                isConnecting = false;
                OnError?.Invoke($"Connection failed: {e.Message}");
                
                if (autoReconnect && reconnectAttempts < maxReconnectAttempts)
                {
                    StartCoroutine(ReconnectAfterDelay());
                }
            }
        }
        
        private void OnWebSocketOpen()
        {
            isConnected = true;
            isConnecting = false;
            reconnectAttempts = 0;
            
            Debug.Log($"Connected to multiplayer session: {currentSessionId}");
            OnConnectionStateChanged?.Invoke(true);
            OnSessionJoined?.Invoke(currentSessionId);
        }
        
        private void OnWebSocketMessage(byte[] data)
        {
            try
            {
                string messageText = Encoding.UTF8.GetString(data);
                messagesReceived++;
                
                if (logMessages)
                {
                    Debug.Log($"Received: {messageText}");
                }
                
                JObject message = JObject.Parse(messageText);
                string messageType = message["type"]?.ToString();
                
                switch (messageType)
                {
                    case "session_state":
                        HandleSessionState(message);
                        break;
                    case "user_joined":
                        HandleUserJoined(message);
                        break;
                    case "user_left":
                        HandleUserLeft(message);
                        break;
                    case "pose_update":
                        HandlePoseUpdate(message);
                        break;
                    case "anchor_create":
                        HandleAnchorCreate(message);
                        break;
                    case "anchor_update":
                        HandleAnchorUpdate(message);
                        break;
                    case "anchor_delete":
                        HandleAnchorDelete(message);
                        break;
                    case "coordinate_system":
                        HandleCoordinateSystem(message);
                        break;
                    case "chat_message":
                        HandleChatMessage(message);
                        break;
                    case "pong":
                        HandlePong(message);
                        break;
                    case "error":
                        OnError?.Invoke(message["message"]?.ToString());
                        break;
                }
            }
            catch (Exception e)
            {
                Debug.LogError($"Error processing message: {e.Message}");
            }
        }
        
        private void OnWebSocketError(string error)
        {
            Debug.LogError($"WebSocket error: {error}");
            OnError?.Invoke($"Connection error: {error}");
        }
        
        private void OnWebSocketClose(WebSocketCloseCode closeCode)
        {
            isConnected = false;
            isConnecting = false;
            
            Debug.Log($"WebSocket closed: {closeCode}");
            OnConnectionStateChanged?.Invoke(false);
            
            if (autoReconnect && reconnectAttempts < maxReconnectAttempts && closeCode != WebSocketCloseCode.Normal)
            {
                StartCoroutine(ReconnectAfterDelay());
            }
        }
        
        private IEnumerator ReconnectAfterDelay()
        {
            reconnectAttempts++;
            Debug.Log($"Attempting reconnect {reconnectAttempts}/{maxReconnectAttempts} in {reconnectDelay} seconds...");
            
            yield return new WaitForSeconds(reconnectDelay);
            
            if (!isConnected && !string.IsNullOrEmpty(currentSessionId))
            {
                await ConnectToSession(currentSessionId);
            }
        }
        
        private async Task SendMessage(object message)
        {
            if (!isConnected || websocket == null) return;
            
            try
            {
                string json = JsonConvert.SerializeObject(message);
                byte[] data = Encoding.UTF8.GetBytes(json);
                
                await websocket.Send(data);
                messagesSent++;
                
                if (logMessages)
                {
                    Debug.Log($"Sent: {json}");
                }
            }
            catch (Exception e)
            {
                Debug.LogError($"Error sending message: {e.Message}");
            }
        }
        
        private async Task SendPing()
        {
            var message = new
            {
                type = "ping",
                timestamp = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds()
            };
            
            await SendMessage(message);
        }
        
        private async Task SendPoseUpdate()
        {
            if (!isColocalized) return;
            
            // Get current pose from AR session or camera
            Transform cameraTransform = Camera.main?.transform;
            if (cameraTransform == null) return;
            
            var message = new
            {
                type = "pose_update",
                position = new { x = cameraTransform.position.x, y = cameraTransform.position.y, z = cameraTransform.position.z },
                rotation = new { x = cameraTransform.rotation.x, y = cameraTransform.rotation.y, z = cameraTransform.rotation.z, w = cameraTransform.rotation.w },
                confidence = 1.0f,
                tracking_state = "tracking",
                timestamp = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds()
            };
            
            await SendMessage(message);
        }
        
        // Message Handlers
        private void HandleSessionState(JObject message)
        {
            // Handle initial session state
            isHost = message["players"]?[userId]?["is_host"]?.Value<bool>() ?? false;
            
            // Load existing anchors
            var anchors = message["anchors"];
            if (anchors != null)
            {
                foreach (var anchor in anchors.Children<JProperty>())
                {
                    var anchorData = JsonConvert.DeserializeObject<SpatialAnchorData>(anchor.Value.ToString());
                    sharedAnchors[anchor.Name] = anchorData;
                }
            }
            
            // Load coordinate system
            var coordSystem = message["coordinate_system"];
            if (coordSystem != null)
            {
                coordinateSystem = JsonConvert.DeserializeObject<CoordinateSystem>(coordSystem.ToString());
                OnCoordinateSystemEstablished?.Invoke(coordinateSystem);
            }
            
            Debug.Log($"Session state loaded - Host: {isHost}, Anchors: {sharedAnchors.Count}");
        }
        
        private void HandleUserJoined(JObject message)
        {
            string userId = message["user_id"]?.ToString();
            bool isHost = message["is_host"]?.Value<bool>() ?? false;
            bool colocalized = message["colocalized"]?.Value<bool>() ?? false;
            
            if (!string.IsNullOrEmpty(userId) && userId != this.userId)
            {
                var playerData = new PlayerData
                {
                    userId = userId,
                    isHost = isHost,
                    isColocalized = colocalized,
                    lastPoseUpdate = Time.time
                };
                
                remotePlayers[userId] = playerData;
                OnPlayerJoined?.Invoke(playerData);
                
                Debug.Log($"Player joined: {userId} (Host: {isHost}, Colocalized: {colocalized})");
            }
        }
        
        private void HandleUserLeft(JObject message)
        {
            string userId = message["user_id"]?.ToString();
            
            if (!string.IsNullOrEmpty(userId) && remotePlayers.ContainsKey(userId))
            {
                remotePlayers.Remove(userId);
                OnPlayerLeft?.Invoke(userId);
                
                Debug.Log($"Player left: {userId}");
            }
        }
        
        private void HandlePoseUpdate(JObject message)
        {
            string userId = message["user_id"]?.ToString();
            var poseData = message["pose"];
            
            if (!string.IsNullOrEmpty(userId) && userId != this.userId && poseData != null)
            {
                var position = poseData["position"];
                var rotation = poseData["rotation"];
                
                var pose = new Pose(
                    new Vector3(
                        position["x"]?.Value<float>() ?? 0f,
                        position["y"]?.Value<float>() ?? 0f,
                        position["z"]?.Value<float>() ?? 0f
                    ),
                    new Quaternion(
                        rotation["x"]?.Value<float>() ?? 0f,
                        rotation["y"]?.Value<float>() ?? 0f,
                        rotation["z"]?.Value<float>() ?? 0f,
                        rotation["w"]?.Value<float>() ?? 1f
                    )
                );
                
                if (remotePlayers.ContainsKey(userId))
                {
                    remotePlayers[userId].currentPose = pose;
                    remotePlayers[userId].lastPoseUpdate = Time.time;
                }
                
                OnPlayerPoseUpdate?.Invoke(userId, pose);
            }
        }
        
        private void HandleAnchorCreate(JObject message)
        {
            var anchor = message["anchor"];
            if (anchor != null)
            {
                var anchorData = JsonConvert.DeserializeObject<SpatialAnchorData>(anchor.ToString());
                sharedAnchors[anchorData.id] = anchorData;
                OnAnchorCreated?.Invoke(anchorData);
                
                Debug.Log($"Anchor created: {anchorData.id}");
            }
        }
        
        private void HandleAnchorUpdate(JObject message)
        {
            string anchorId = message["anchor_id"]?.ToString();
            
            if (!string.IsNullOrEmpty(anchorId) && sharedAnchors.ContainsKey(anchorId))
            {
                var anchor = sharedAnchors[anchorId];
                
                // Update position if provided
                var position = message["position"];
                if (position != null)
                {
                    anchor.position = new Vector3(
                        position["x"]?.Value<float>() ?? anchor.position.x,
                        position["y"]?.Value<float>() ?? anchor.position.y,
                        position["z"]?.Value<float>() ?? anchor.position.z
                    );
                }
                
                // Update rotation if provided
                var rotation = message["rotation"];
                if (rotation != null)
                {
                    anchor.rotation = new Quaternion(
                        rotation["x"]?.Value<float>() ?? anchor.rotation.x,
                        rotation["y"]?.Value<float>() ?? anchor.rotation.y,
                        rotation["z"]?.Value<float>() ?? anchor.rotation.z,
                        rotation["w"]?.Value<float>() ?? anchor.rotation.w
                    );
                }
                
                // Update metadata if provided
                var metadata = message["metadata"];
                if (metadata != null)
                {
                    anchor.metadata = JsonConvert.DeserializeObject<Dictionary<string, object>>(metadata.ToString());
                }
                
                anchor.lastUpdate = Time.time;
                OnAnchorUpdated?.Invoke(anchor);
                
                Debug.Log($"Anchor updated: {anchorId}");
            }
        }
        
        private void HandleAnchorDelete(JObject message)
        {
            string anchorId = message["anchor_id"]?.ToString();
            
            if (!string.IsNullOrEmpty(anchorId) && sharedAnchors.ContainsKey(anchorId))
            {
                sharedAnchors.Remove(anchorId);
                OnAnchorDeleted?.Invoke(anchorId);
                
                Debug.Log($"Anchor deleted: {anchorId}");
            }
        }
        
        private void HandleCoordinateSystem(JObject message)
        {
            var coordSystemData = message["coordinate_system"];
            if (coordSystemData != null)
            {
                coordinateSystem = JsonConvert.DeserializeObject<CoordinateSystem>(coordSystemData.ToString());
                OnCoordinateSystemEstablished?.Invoke(coordinateSystem);
                
                Debug.Log("Coordinate system established");
            }
        }
        
        private void HandleChatMessage(JObject message)
        {
            string userId = message["user_id"]?.ToString();
            string text = message["message"]?.ToString();
            
            if (!string.IsNullOrEmpty(userId) && !string.IsNullOrEmpty(text))
            {
                OnChatMessage?.Invoke(userId, text);
            }
        }
        
        private void HandlePong(JObject message)
        {
            float clientTimestamp = message["client_timestamp"]?.Value<float>() ?? 0f;
            float serverTimestamp = message["timestamp"]?.Value<float>() ?? 0f;
            float currentTime = (float)DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();
            
            if (clientTimestamp > 0)
            {
                float roundTripTime = currentTime - clientTimestamp;
                averageLatency = averageLatency * 0.9f + roundTripTime * 0.1f;
            }
        }
        
        private void ResetSessionState()
        {
            currentSessionId = null;
            isHost = false;
            isColocalized = false;
            remotePlayers.Clear();
            sharedAnchors.Clear();
            coordinateSystem = null;
            reconnectAttempts = 0;
            
            // Clear anonymous session state
            isAnonymousSession = false;
            anonymousSessionId = "";
            anonymousShareCode = "";
            anonymousUserId = "";
        }
        
        private NetworkStats GetNetworkStats()
        {
            return new NetworkStats
            {
                isConnected = isConnected,
                averageLatency = averageLatency,
                messagesSent = messagesSent,
                messagesReceived = messagesReceived,
                connectionDuration = isConnected ? Time.time - connectionStartTime : 0f,
                playerCount = remotePlayers.Count + (isConnected ? 1 : 0)
            };
        }
        
        private void OnDestroy()
        {
            LeaveSession();
        }
        
        private void OnApplicationPause(bool pauseStatus)
        {
            if (pauseStatus && isConnected)
            {
                LeaveSession();
            }
        }
        
        // Debug GUI
        private void OnGUI()
        {
            if (!showDebugInfo) return;
            
            GUILayout.BeginArea(new Rect(10, 200, 300, 300));
            GUILayout.Label($"Multiplayer Status: {(isConnected ? "Connected" : "Disconnected")}");
            GUILayout.Label($"Session: {currentSessionId ?? "None"}");
            GUILayout.Label($"Host: {isHost}");
            GUILayout.Label($"Colocalized: {isColocalized}");
            GUILayout.Label($"Players: {remotePlayers.Count + (isConnected ? 1 : 0)}");
            GUILayout.Label($"Anchors: {sharedAnchors.Count}");
            GUILayout.Label($"Latency: {averageLatency:F1}ms");
            GUILayout.Label($"Messages: {messagesReceived}↓ {messagesSent}↑");
            GUILayout.EndArea();
        }
    }
    
    // Data structures
    [Serializable]
    public class PlayerData
    {
        public string userId;
        public bool isHost;
        public bool isColocalized;
        public Pose currentPose;
        public float lastPoseUpdate;
    }
    
    [Serializable]
    public class SpatialAnchorData
    {
        public string id;
        public Vector3 position;
        public Quaternion rotation;
        public Dictionary<string, object> metadata;
        public string creatorId;
        public float creationTime;
        public float lastUpdate;
    }
    
    [Serializable]
    public class CoordinateSystem
    {
        public Vector3 origin;
        public Quaternion rotation;
    }
    
    [Serializable]
    public class NetworkStats
    {
        public bool isConnected;
        public float averageLatency;
        public int messagesSent;
        public int messagesReceived;
        public float connectionDuration;
        public int playerCount;
    }
    
    [Serializable]
    public class SessionCreateResponse
    {
        public bool success;
        public string session_id;
        public string error;
        public int max_players;
        public string colocalization_method;
    }
    
    [Serializable]
    public class AnonymousSessionResponse
    {
        public string session_id;
        public string share_code;
        public AnonymousCreator creator;
        public int expires_in;
        public int max_players;
        public string created_at;
    }
    
    [Serializable]
    public class AnonymousCreator
    {
        public string id;
        public string display_name;
        public bool is_anonymous;
    }
    
    [Serializable]
    public class AnonymousJoinResponse
    {
        public string session_id;
        public AnonymousUser user;
        public string share_code;
        public AnonymousSessionInfo session_info;
    }
    
    [Serializable]
    public class AnonymousUser
    {
        public string id;
        public string display_name;
        public bool is_anonymous;
    }
    
    [Serializable]
    public class AnonymousSessionInfo
    {
        public int max_players;
        public int expires_in;
    }
}