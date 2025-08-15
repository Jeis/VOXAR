/*
 * Spatial Platform - Multiplayer AR Demo
 * Demonstrates multiplayer AR capabilities with colocalization and shared anchors
 */

using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UI;
using SpatialPlatform.Multiplayer;
using SpatialPlatform.Colocalization;

namespace SpatialPlatform.Demo
{
    public class MultiplayerARDemo : MonoBehaviour
    {
        [Header("UI References")]
        [SerializeField] private Button createSessionButton;
        [SerializeField] private Button joinSessionButton;
        [SerializeField] private Button leaveSessionButton;
        [SerializeField] private Button placeAnchorButton;
        [SerializeField] private Button startQRScanButton;
        [SerializeField] private InputField sessionIdInput;
        [SerializeField] private Text statusText;
        [SerializeField] private Text playersText;
        [SerializeField] private Text anchorsText;
        [SerializeField] private Text networkStatsText;
        
        [Header("3D Objects")]
        [SerializeField] private GameObject playerIndicatorPrefab;
        [SerializeField] private GameObject anchorVisualizerPrefab;
        [SerializeField] private Transform contentParent;
        
        [Header("Demo Settings")]
        [SerializeField] private bool enableDebugUI = true;
        [SerializeField] private float uiUpdateRate = 2f; // Hz
        
        // Component references
        private MultiplayerManager multiplayerManager;
        private QRCodeColocalization qrColocalization;
        
        // Demo state
        private Dictionary<string, GameObject> playerIndicators = new Dictionary<string, GameObject>();
        private Dictionary<string, GameObject> anchorVisualizers = new Dictionary<string, GameObject>();
        private string currentSessionId;
        private bool isConnected = false;
        
        private void Awake()
        {
            InitializeComponents();
            SetupUI();
        }
        
        private void InitializeComponents()
        {
            // Find or create multiplayer manager
            multiplayerManager = FindObjectOfType<MultiplayerManager>();
            if (multiplayerManager == null)
            {
                GameObject mpGO = new GameObject("MultiplayerManager");
                multiplayerManager = mpGO.AddComponent<MultiplayerManager>();
            }
            
            // Find or create QR colocalization
            qrColocalization = FindObjectOfType<QRCodeColocalization>();
            if (qrColocalization == null)
            {
                GameObject qrGO = new GameObject("QRCodeColocalization");
                qrColocalization = qrGO.AddComponent<QRCodeColocalization>();
            }
            
            // Create content parent if not assigned
            if (contentParent == null)
            {
                GameObject contentGO = new GameObject("MultiplayerContent");
                contentParent = contentGO.transform;
            }
        }
        
        private void SetupUI()
        {
            // Setup button listeners
            if (createSessionButton != null)
                createSessionButton.onClick.AddListener(CreateSession);
            
            if (joinSessionButton != null)
                joinSessionButton.onClick.AddListener(JoinSession);
            
            if (leaveSessionButton != null)
                leaveSessionButton.onClick.AddListener(LeaveSession);
            
            if (placeAnchorButton != null)
                placeAnchorButton.onClick.AddListener(PlaceAnchor);
            
            if (startQRScanButton != null)
                startQRScanButton.onClick.AddListener(StartQRScan);
            
            // Initial UI state
            UpdateUI();
        }
        
        private void Start()
        {
            // Subscribe to multiplayer events
            if (multiplayerManager != null)
            {
                multiplayerManager.OnConnectionStateChanged += OnConnectionStateChanged;
                multiplayerManager.OnSessionJoined += OnSessionJoined;
                multiplayerManager.OnPlayerJoined += OnPlayerJoined;
                multiplayerManager.OnPlayerLeft += OnPlayerLeft;
                multiplayerManager.OnPlayerPoseUpdate += OnPlayerPoseUpdate;
                multiplayerManager.OnAnchorCreated += OnAnchorCreated;
                multiplayerManager.OnAnchorUpdated += OnAnchorUpdated;
                multiplayerManager.OnAnchorDeleted += OnAnchorDeleted;
                multiplayerManager.OnCoordinateSystemEstablished += OnCoordinateSystemEstablished;
                multiplayerManager.OnChatMessage += OnChatMessage;
                multiplayerManager.OnError += OnMultiplayerError;
            }
            
            // Subscribe to colocalization events
            if (qrColocalization != null)
            {
                qrColocalization.OnQRCodeDetected += OnQRCodeDetected;
                qrColocalization.OnCoordinateSystemEstablished += OnColocalizationEstablished;
                qrColocalization.OnColocalizationStateChanged += OnColocalizationStateChanged;
                qrColocalization.OnError += OnColocalizationError;
            }
            
            // Start UI update coroutine
            StartCoroutine(UpdateUILoop());
        }
        
        private IEnumerator UpdateUILoop()
        {
            while (true)
            {
                UpdateUI();
                yield return new WaitForSeconds(1f / uiUpdateRate);
            }
        }
        
        // UI Event Handlers
        private void CreateSession()
        {
            if (multiplayerManager != null)
            {
                UpdateStatus("Creating session...");
                multiplayerManager.CreateSession();
            }
        }
        
        private void JoinSession()
        {
            if (multiplayerManager != null && sessionIdInput != null)
            {
                string sessionId = sessionIdInput.text.Trim();
                if (!string.IsNullOrEmpty(sessionId))
                {
                    UpdateStatus($"Joining session {sessionId}...");
                    multiplayerManager.JoinSession(sessionId);
                }
                else
                {
                    UpdateStatus("Please enter a session ID");
                }
            }
        }
        
        private void LeaveSession()
        {
            if (multiplayerManager != null)
            {
                multiplayerManager.LeaveSession();
                CleanupVisualizers();
                UpdateStatus("Left session");
            }
        }
        
        private void PlaceAnchor()
        {
            if (qrColocalization != null && qrColocalization.IsColocalized)
            {
                qrColocalization.PlaceHostAnchor();
                UpdateStatus("Host anchor placed");
            }
            else if (multiplayerManager != null && multiplayerManager.IsConnected)
            {
                // Place a regular spatial anchor at camera position
                Camera cam = Camera.main;
                if (cam != null)
                {
                    string anchorId = System.Guid.NewGuid().ToString();
                    Pose anchorPose = new Pose(cam.transform.position + cam.transform.forward * 2f, cam.transform.rotation);
                    
                    var metadata = new Dictionary<string, object>
                    {
                        ["type"] = "demo_anchor",
                        ["color"] = Random.ColorHSV().ToString()
                    };
                    
                    multiplayerManager.CreateAnchor(anchorId, anchorPose, metadata);
                    UpdateStatus($"Anchor placed: {anchorId}");
                }
            }
            else
            {
                UpdateStatus("Not connected or colocalized");
            }
        }
        
        private void StartQRScan()
        {
            if (qrColocalization != null)
            {
                if (qrColocalization.IsScanning)
                {
                    qrColocalization.StopScanning();
                    UpdateStatus("QR scanning stopped");
                }
                else
                {
                    qrColocalization.StartScanning();
                    UpdateStatus("QR scanning started");
                }
            }
        }
        
        // Multiplayer Event Handlers
        private void OnConnectionStateChanged(bool connected)
        {
            isConnected = connected;
            UpdateStatus(connected ? "Connected" : "Disconnected");
        }
        
        private void OnSessionJoined(string sessionId)
        {
            currentSessionId = sessionId;
            UpdateStatus($"Joined session: {sessionId}");
            
            // Set session ID in input field for sharing
            if (sessionIdInput != null)
            {
                sessionIdInput.text = sessionId;
            }
            
            // If we're the host, enable anchor placement
            if (multiplayerManager.IsHost && qrColocalization != null)
            {
                qrColocalization.SetAsHost(true);
                UpdateStatus("You are the host - place an anchor to start colocalization");
            }
        }
        
        private void OnPlayerJoined(PlayerData player)
        {
            UpdateStatus($"Player joined: {player.userId}");
            CreatePlayerIndicator(player.userId);
        }
        
        private void OnPlayerLeft(string userId)
        {
            UpdateStatus($"Player left: {userId}");
            RemovePlayerIndicator(userId);
        }
        
        private void OnPlayerPoseUpdate(string userId, Pose pose)
        {
            UpdatePlayerIndicator(userId, pose);
        }
        
        private void OnAnchorCreated(SpatialAnchorData anchor)
        {
            UpdateStatus($"Anchor created: {anchor.id}");
            CreateAnchorVisualizer(anchor);
        }
        
        private void OnAnchorUpdated(SpatialAnchorData anchor)
        {
            UpdateStatus($"Anchor updated: {anchor.id}");
            UpdateAnchorVisualizer(anchor);
        }
        
        private void OnAnchorDeleted(string anchorId)
        {
            UpdateStatus($"Anchor deleted: {anchorId}");
            RemoveAnchorVisualizer(anchorId);
        }
        
        private void OnCoordinateSystemEstablished(CoordinateSystem coordinateSystem)
        {
            UpdateStatus("Coordinate system established");
        }
        
        private void OnChatMessage(string userId, string message)
        {
            Debug.Log($"Chat from {userId}: {message}");
        }
        
        private void OnMultiplayerError(string error)
        {
            UpdateStatus($"Multiplayer error: {error}");
        }
        
        // Colocalization Event Handlers
        private void OnQRCodeDetected(string anchorId)
        {
            UpdateStatus($"QR Code detected: {anchorId}");
        }
        
        private void OnColocalizationEstablished(Pose anchorPose)
        {
            UpdateStatus("Colocalization established");
        }
        
        private void OnColocalizationStateChanged(bool colocalized)
        {
            UpdateStatus(colocalized ? "Colocalized" : "Not colocalized");
        }
        
        private void OnColocalizationError(string error)
        {
            UpdateStatus($"Colocalization error: {error}");
        }
        
        // Visualizer Management
        private void CreatePlayerIndicator(string userId)
        {
            if (playerIndicators.ContainsKey(userId)) return;
            
            GameObject indicator = null;
            if (playerIndicatorPrefab != null)
            {
                indicator = Instantiate(playerIndicatorPrefab, contentParent);
            }
            else
            {
                // Create simple indicator
                indicator = GameObject.CreatePrimitive(PrimitiveType.Capsule);
                indicator.transform.SetParent(contentParent);
                indicator.transform.localScale = new Vector3(0.3f, 0.3f, 0.3f);
                
                // Add color
                Renderer renderer = indicator.GetComponent<Renderer>();
                if (renderer != null)
                {
                    renderer.material.color = Random.ColorHSV();
                }
                
                // Add label
                GameObject label = new GameObject("PlayerLabel");
                label.transform.SetParent(indicator.transform);
                label.transform.localPosition = Vector3.up * 0.5f;
                
                TextMesh textMesh = label.AddComponent<TextMesh>();
                textMesh.text = userId.Substring(0, Mathf.Min(8, userId.Length));
                textMesh.fontSize = 20;
                textMesh.anchor = TextAnchor.MiddleCenter;
            }
            
            indicator.name = $"Player_{userId}";
            playerIndicators[userId] = indicator;
        }
        
        private void UpdatePlayerIndicator(string userId, Pose pose)
        {
            if (playerIndicators.ContainsKey(userId))
            {
                GameObject indicator = playerIndicators[userId];
                
                // Transform pose to local coordinate system if colocalized
                if (qrColocalization != null && qrColocalization.IsColocalized)
                {
                    pose = qrColocalization.TransformToSharedSpace(pose);
                }
                
                indicator.transform.position = pose.position;
                indicator.transform.rotation = pose.rotation;
            }
        }
        
        private void RemovePlayerIndicator(string userId)
        {
            if (playerIndicators.ContainsKey(userId))
            {
                Destroy(playerIndicators[userId]);
                playerIndicators.Remove(userId);
            }
        }
        
        private void CreateAnchorVisualizer(SpatialAnchorData anchor)
        {
            if (anchorVisualizers.ContainsKey(anchor.id)) return;
            
            GameObject visualizer = null;
            if (anchorVisualizerPrefab != null)
            {
                visualizer = Instantiate(anchorVisualizerPrefab, contentParent);
            }
            else
            {
                // Create simple visualizer
                visualizer = GameObject.CreatePrimitive(PrimitiveType.Cube);
                visualizer.transform.SetParent(contentParent);
                visualizer.transform.localScale = Vector3.one * 0.2f;
                
                // Add color based on metadata
                Renderer renderer = visualizer.GetComponent<Renderer>();
                if (renderer != null)
                {
                    if (anchor.metadata.ContainsKey("color"))
                    {
                        ColorUtility.TryParseHtmlString(anchor.metadata["color"].ToString(), out Color color);
                        renderer.material.color = color;
                    }
                    else
                    {
                        renderer.material.color = Color.red;
                    }
                }
            }
            
            visualizer.name = $"Anchor_{anchor.id}";
            visualizer.transform.position = anchor.position;
            visualizer.transform.rotation = anchor.rotation;
            
            anchorVisualizers[anchor.id] = visualizer;
        }
        
        private void UpdateAnchorVisualizer(SpatialAnchorData anchor)
        {
            if (anchorVisualizers.ContainsKey(anchor.id))
            {
                GameObject visualizer = anchorVisualizers[anchor.id];
                visualizer.transform.position = anchor.position;
                visualizer.transform.rotation = anchor.rotation;
            }
        }
        
        private void RemoveAnchorVisualizer(string anchorId)
        {
            if (anchorVisualizers.ContainsKey(anchorId))
            {
                Destroy(anchorVisualizers[anchorId]);
                anchorVisualizers.Remove(anchorId);
            }
        }
        
        private void CleanupVisualizers()
        {
            // Remove all player indicators
            foreach (var indicator in playerIndicators.Values)
            {
                if (indicator != null) Destroy(indicator);
            }
            playerIndicators.Clear();
            
            // Remove all anchor visualizers
            foreach (var visualizer in anchorVisualizers.Values)
            {
                if (visualizer != null) Destroy(visualizer);
            }
            anchorVisualizers.Clear();
        }
        
        // UI Updates
        private void UpdateUI()
        {
            if (!enableDebugUI) return;
            
            // Update button states
            if (createSessionButton != null)
                createSessionButton.interactable = !isConnected;
            
            if (joinSessionButton != null)
                joinSessionButton.interactable = !isConnected;
            
            if (leaveSessionButton != null)
                leaveSessionButton.interactable = isConnected;
            
            if (placeAnchorButton != null)
                placeAnchorButton.interactable = isConnected;
            
            if (startQRScanButton != null && qrColocalization != null)
            {
                Text buttonText = startQRScanButton.GetComponentInChildren<Text>();
                if (buttonText != null)
                {
                    buttonText.text = qrColocalization.IsScanning ? "Stop QR Scan" : "Start QR Scan";
                }
            }
            
            // Update players text
            if (playersText != null && multiplayerManager != null)
            {
                int playerCount = multiplayerManager.RemotePlayers.Count + (isConnected ? 1 : 0);
                playersText.text = $"Players: {playerCount}";
                
                if (multiplayerManager.IsHost)
                {
                    playersText.text += " (Host)";
                }
            }
            
            // Update anchors text
            if (anchorsText != null && multiplayerManager != null)
            {
                anchorsText.text = $"Anchors: {multiplayerManager.SharedAnchors.Count}";
            }
            
            // Update network stats
            if (networkStatsText != null && multiplayerManager != null)
            {
                var stats = multiplayerManager.NetworkStats;
                networkStatsText.text = $"Latency: {stats.averageLatency:F1}ms\n" +
                                      $"Messages: {stats.messagesReceived}↓ {stats.messagesSent}↑";
            }
        }
        
        private void UpdateStatus(string message)
        {
            Debug.Log($"MultiplayerARDemo: {message}");
            
            if (statusText != null)
            {
                statusText.text = message;
            }
        }
        
        private void OnDestroy()
        {
            CleanupVisualizers();
            
            // Unsubscribe from events
            if (multiplayerManager != null)
            {
                multiplayerManager.OnConnectionStateChanged -= OnConnectionStateChanged;
                multiplayerManager.OnSessionJoined -= OnSessionJoined;
                multiplayerManager.OnPlayerJoined -= OnPlayerJoined;
                multiplayerManager.OnPlayerLeft -= OnPlayerLeft;
                multiplayerManager.OnPlayerPoseUpdate -= OnPlayerPoseUpdate;
                multiplayerManager.OnAnchorCreated -= OnAnchorCreated;
                multiplayerManager.OnAnchorUpdated -= OnAnchorUpdated;
                multiplayerManager.OnAnchorDeleted -= OnAnchorDeleted;
                multiplayerManager.OnCoordinateSystemEstablished -= OnCoordinateSystemEstablished;
                multiplayerManager.OnChatMessage -= OnChatMessage;
                multiplayerManager.OnError -= OnMultiplayerError;
            }
            
            if (qrColocalization != null)
            {
                qrColocalization.OnQRCodeDetected -= OnQRCodeDetected;
                qrColocalization.OnCoordinateSystemEstablished -= OnColocalizationEstablished;
                qrColocalization.OnColocalizationStateChanged -= OnColocalizationStateChanged;
                qrColocalization.OnError -= OnColocalizationError;
            }
        }
    }
}