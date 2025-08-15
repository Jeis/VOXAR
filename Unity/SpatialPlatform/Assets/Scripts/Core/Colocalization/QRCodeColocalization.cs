/*
 * Spatial Platform - QR Code Colocalization
 * Handles QR code-based spatial alignment for multiplayer AR sessions
 */

using System;
using System.Collections;
using UnityEngine;
using UnityEngine.XR.ARFoundation;
using UnityEngine.XR.ARSubsystems;
using ZXing;
using ZXing.QrCode;
using SpatialPlatform.Multiplayer;

namespace SpatialPlatform.Colocalization
{
    public class QRCodeColocalization : MonoBehaviour
    {
        [Header("QR Code Settings")]
        [SerializeField] private float qrCodeSize = 0.1f; // 10cm QR code
        [SerializeField] private string qrCodePrefix = "spatial_anchor:";
        [SerializeField] private bool autoScanOnStart = true;
        [SerializeField] private float scanInterval = 0.5f; // Scan every 500ms
        
        [Header("Coordinate System")]
        [SerializeField] private Transform coordinateSystemOrigin;
        [SerializeField] private bool isHost = false;
        [SerializeField] private Vector3 hostAnchorOffset = Vector3.zero;
        
        [Header("Debug")]
        [SerializeField] private bool showDebugInfo = true;
        [SerializeField] private bool logQRDetection = true;
        
        // Component references
        private ARCamera arCamera;
        private ARSessionOrigin arSessionOrigin;
        private MultiplayerManager multiplayerManager;
        private Camera cameraComponent;
        
        // QR Code processing
        private IBarcodeReader barcodeReader;
        private Texture2D cameraTexture;
        private bool isScanning = false;
        private string lastDetectedQRCode;
        private float lastScanTime = 0f;
        
        // Colocalization state
        private bool isColocalized = false;
        private string anchorId;
        private Pose hostAnchorPose;
        private Matrix4x4 coordinateTransform = Matrix4x4.identity;
        
        // Events
        public event Action<string> OnQRCodeDetected;
        public event Action<Pose> OnCoordinateSystemEstablished;
        public event Action<bool> OnColocalizationStateChanged;
        public event Action<string> OnError;
        
        // Properties
        public bool IsScanning => isScanning;
        public bool IsColocalized => isColocalized;
        public string AnchorId => anchorId;
        public Pose HostAnchorPose => hostAnchorPose;
        
        private void Awake()
        {
            InitializeComponents();
            InitializeQRReader();
        }
        
        private void InitializeComponents()
        {
            // Find AR components
            arCamera = FindObjectOfType<ARCamera>();
            arSessionOrigin = FindObjectOfType<ARSessionOrigin>();
            multiplayerManager = FindObjectOfType<MultiplayerManager>();
            
            if (arCamera != null)
            {
                cameraComponent = arCamera.GetComponent<Camera>();
            }
            
            if (cameraComponent == null)
            {
                cameraComponent = Camera.main;
                Debug.LogWarning("AR Camera not found, using main camera");
            }
            
            // Create coordinate system origin if not assigned
            if (coordinateSystemOrigin == null)
            {
                GameObject originGO = new GameObject("CoordinateSystemOrigin");
                coordinateSystemOrigin = originGO.transform;
            }
        }
        
        private void InitializeQRReader()
        {
            barcodeReader = new BarcodeReader
            {
                AutoRotate = true,
                Options = new ZXing.Common.DecodingOptions
                {
                    TryHarder = true,
                    PossibleFormats = new[] { BarcodeFormat.QR_CODE }
                }
            };
        }
        
        private void Start()
        {
            if (autoScanOnStart)
            {
                StartScanning();
            }
            
            // Subscribe to multiplayer events
            if (multiplayerManager != null)
            {
                multiplayerManager.OnSessionJoined += OnSessionJoined;
                multiplayerManager.OnPlayerJoined += OnPlayerJoined;
                multiplayerManager.OnCoordinateSystemEstablished += OnCoordinateSystemReceived;
            }
        }
        
        private void Update()
        {
            if (isScanning && Time.time - lastScanTime > scanInterval)
            {
                ProcessCameraFrame();
                lastScanTime = Time.time;
            }
        }
        
        // Public API Methods
        public void StartScanning()
        {
            if (!isScanning)
            {
                isScanning = true;
                Debug.Log("Started QR code scanning");
            }
        }
        
        public void StopScanning()
        {
            if (isScanning)
            {
                isScanning = false;
                Debug.Log("Stopped QR code scanning");
            }
        }
        
        public void SetAsHost(bool host)
        {
            isHost = host;
            if (isHost)
            {
                Debug.Log("Set as colocalization host");
            }
        }
        
        public void PlaceHostAnchor()
        {
            if (!isHost || multiplayerManager == null || !multiplayerManager.IsConnected)
            {
                OnError?.Invoke("Cannot place anchor: Not host or not connected");
                return;
            }
            
            // Generate anchor ID and QR code
            anchorId = System.Guid.NewGuid().ToString();
            string qrData = qrCodePrefix + anchorId;
            
            // Set host anchor pose (current camera position + offset)
            hostAnchorPose = new Pose(
                cameraComponent.transform.position + hostAnchorOffset,
                cameraComponent.transform.rotation
            );
            
            // Establish coordinate system origin at anchor position
            coordinateSystemOrigin.position = hostAnchorPose.position;
            coordinateSystemOrigin.rotation = hostAnchorPose.rotation;
            
            // Create coordinate system data
            var coordinateSystem = new CoordinateSystem
            {
                origin = Vector3.zero, // Relative to anchor
                rotation = Quaternion.identity
            };
            
            // Send coordinate system to other players
            multiplayerManager.SetColocalized(true, coordinateSystem);
            
            // Create spatial anchor in multiplayer system
            var anchorMetadata = new System.Collections.Generic.Dictionary<string, object>
            {
                ["type"] = "qr_anchor",
                ["qr_data"] = qrData,
                ["size"] = qrCodeSize
            };
            
            multiplayerManager.CreateAnchor(anchorId, hostAnchorPose, anchorMetadata);
            
            isColocalized = true;
            OnColocalizationStateChanged?.Invoke(true);
            OnCoordinateSystemEstablished?.Invoke(hostAnchorPose);
            
            Debug.Log($"Host anchor placed: {anchorId} at {hostAnchorPose.position}");
            
            if (logQRDetection)
            {
                Debug.Log($"QR Code data for anchor: {qrData}");
            }
        }
        
        public void ProcessQRCode(string qrData)
        {
            if (string.IsNullOrEmpty(qrData) || !qrData.StartsWith(qrCodePrefix))
            {
                return;
            }
            
            // Extract anchor ID
            string detectedAnchorId = qrData.Substring(qrCodePrefix.Length);
            
            if (detectedAnchorId == lastDetectedQRCode)
            {
                return; // Already processed this QR code
            }
            
            lastDetectedQRCode = detectedAnchorId;
            OnQRCodeDetected?.Invoke(detectedAnchorId);
            
            if (logQRDetection)
            {
                Debug.Log($"QR Code detected: {detectedAnchorId}");
            }
            
            // If we're not the host, try to align with this anchor
            if (!isHost && multiplayerManager != null && multiplayerManager.IsConnected)
            {
                StartCoroutine(AlignWithAnchor(detectedAnchorId));
            }
        }
        
        private IEnumerator AlignWithAnchor(string detectedAnchorId)
        {
            // Wait a bit for spatial anchor data to be received
            float timeout = 5f;
            float elapsed = 0f;
            
            while (elapsed < timeout)
            {
                if (multiplayerManager.SharedAnchors.ContainsKey(detectedAnchorId))
                {
                    var anchorData = multiplayerManager.SharedAnchors[detectedAnchorId];
                    
                    // Calculate transformation from current camera pose to anchor
                    Pose currentCameraPose = new Pose(
                        cameraComponent.transform.position,
                        cameraComponent.transform.rotation
                    );
                    
                    Pose anchorWorldPose = new Pose(anchorData.position, anchorData.rotation);
                    
                    // Calculate coordinate system transformation
                    CalculateCoordinateTransform(currentCameraPose, anchorWorldPose);
                    
                    // Set coordinate system origin
                    coordinateSystemOrigin.position = anchorWorldPose.position;
                    coordinateSystemOrigin.rotation = anchorWorldPose.rotation;
                    
                    // Notify multiplayer system that we're colocalized
                    multiplayerManager.SetColocalized(true);
                    
                    isColocalized = true;
                    anchorId = detectedAnchorId;
                    
                    OnColocalizationStateChanged?.Invoke(true);
                    OnCoordinateSystemEstablished?.Invoke(anchorWorldPose);
                    
                    Debug.Log($"Successfully aligned with anchor: {detectedAnchorId}");
                    yield break;
                }
                
                elapsed += 0.1f;
                yield return new WaitForSeconds(0.1f);
            }
            
            OnError?.Invoke($"Timeout waiting for anchor data: {detectedAnchorId}");
        }
        
        private void ProcessCameraFrame()
        {
            if (cameraComponent == null) return;
            
            try
            {
                // Capture camera frame
                RenderTexture renderTexture = RenderTexture.GetTemporary(
                    Screen.width / 4, Screen.height / 4, 0, RenderTextureFormat.RGB565);
                
                RenderTexture currentRT = RenderTexture.active;
                cameraComponent.targetTexture = renderTexture;
                cameraComponent.Render();
                
                RenderTexture.active = renderTexture;
                
                if (cameraTexture == null || cameraTexture.width != renderTexture.width || cameraTexture.height != renderTexture.height)
                {
                    if (cameraTexture != null) Destroy(cameraTexture);
                    cameraTexture = new Texture2D(renderTexture.width, renderTexture.height, TextureFormat.RGB24, false);
                }
                
                cameraTexture.ReadPixels(new Rect(0, 0, renderTexture.width, renderTexture.height), 0, 0);
                cameraTexture.Apply();
                
                // Restore render target
                cameraComponent.targetTexture = null;
                RenderTexture.active = currentRT;
                RenderTexture.ReleaseTemporary(renderTexture);
                
                // Decode QR codes
                var result = barcodeReader.Decode(cameraTexture.GetPixels32(), cameraTexture.width, cameraTexture.height);
                if (result != null)
                {
                    ProcessQRCode(result.Text);
                }
            }
            catch (System.Exception e)
            {
                Debug.LogError($"Error processing camera frame: {e.Message}");
            }
        }
        
        private void CalculateCoordinateTransform(Pose cameraPose, Pose anchorPose)
        {
            // Calculate transformation matrix from camera space to anchor space
            Matrix4x4 cameraMatrix = Matrix4x4.TRS(cameraPose.position, cameraPose.rotation, Vector3.one);
            Matrix4x4 anchorMatrix = Matrix4x4.TRS(anchorPose.position, anchorPose.rotation, Vector3.one);
            
            // Transform = anchor * inverse(camera)
            coordinateTransform = anchorMatrix * cameraMatrix.inverse;
        }
        
        public Vector3 TransformToSharedSpace(Vector3 localPosition)
        {
            if (!isColocalized) return localPosition;
            
            Vector4 worldPos = new Vector4(localPosition.x, localPosition.y, localPosition.z, 1f);
            Vector4 sharedPos = coordinateTransform * worldPos;
            return new Vector3(sharedPos.x, sharedPos.y, sharedPos.z);
        }
        
        public Quaternion TransformToSharedSpace(Quaternion localRotation)
        {
            if (!isColocalized) return localRotation;
            
            return coordinateTransform.rotation * localRotation;
        }
        
        public Pose TransformToSharedSpace(Pose localPose)
        {
            return new Pose(
                TransformToSharedSpace(localPose.position),
                TransformToSharedSpace(localPose.rotation)
            );
        }
        
        // Event handlers
        private void OnSessionJoined(string sessionId)
        {
            Debug.Log($"Joined multiplayer session: {sessionId}");
            
            // If we're the first player (host), we can place an anchor
            if (multiplayerManager.IsHost)
            {
                SetAsHost(true);
            }
        }
        
        private void OnPlayerJoined(PlayerData player)
        {
            Debug.Log($"Player joined: {player.userId} (Host: {player.isHost})");
        }
        
        private void OnCoordinateSystemReceived(CoordinateSystem coordinateSystem)
        {
            Debug.Log("Coordinate system received from host");
            
            // Update our coordinate system origin
            coordinateSystemOrigin.position = coordinateSystem.origin;
            coordinateSystemOrigin.rotation = coordinateSystem.rotation;
        }
        
        private void OnDestroy()
        {
            StopScanning();
            
            if (cameraTexture != null)
            {
                Destroy(cameraTexture);
            }
            
            if (multiplayerManager != null)
            {
                multiplayerManager.OnSessionJoined -= OnSessionJoined;
                multiplayerManager.OnPlayerJoined -= OnPlayerJoined;
                multiplayerManager.OnCoordinateSystemEstablished -= OnCoordinateSystemReceived;
            }
        }
        
        // Debug GUI
        private void OnGUI()
        {
            if (!showDebugInfo) return;
            
            GUILayout.BeginArea(new Rect(10, 500, 300, 200));
            GUILayout.Label($"QR Scanning: {(isScanning ? "Active" : "Inactive")}");
            GUILayout.Label($"Colocalized: {isColocalized}");
            GUILayout.Label($"Is Host: {isHost}");
            GUILayout.Label($"Anchor ID: {anchorId ?? "None"}");
            GUILayout.Label($"Last QR: {lastDetectedQRCode ?? "None"}");
            
            if (isHost && !isColocalized)
            {
                if (GUILayout.Button("Place Host Anchor"))
                {
                    PlaceHostAnchor();
                }
            }
            
            if (GUILayout.Button(isScanning ? "Stop Scanning" : "Start Scanning"))
            {
                if (isScanning)
                    StopScanning();
                else
                    StartScanning();
            }
            
            GUILayout.EndArea();
        }
    }
}