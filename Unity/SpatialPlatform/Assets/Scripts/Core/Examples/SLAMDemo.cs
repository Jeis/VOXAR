/**
 * Spatial Platform - SLAM Demo Script
 * Demonstrates the Unity-to-backend SLAM integration
 */

using System.Collections;
using UnityEngine;
using SpatialPlatform.Core.SLAM;
using SpatialPlatform.Core.Services;

namespace SpatialPlatform.Core.Examples
{
    public class SLAMDemo : MonoBehaviour
    {
        [Header("Demo Configuration")]
        [SerializeField] private string backendUrl = "http://localhost:8092";
        [SerializeField] private bool autoStart = true;
        [SerializeField] private float testInterval = 1.0f;

        [Header("Visualization")]
        [SerializeField] private Transform poseIndicator;
        [SerializeField] private TextMesh statusText;
        [SerializeField] private bool showDebugGUI = true;

        // Component references
        private HybridSLAMManager hybridManager;
        private SpatialSLAMClient slamClient;

        // Demo state
        private bool isDemoRunning = false;
        private Vector3 lastPosition = Vector3.zero;
        private Quaternion lastRotation = Quaternion.identity;
        private float lastConfidence = 0f;
        private string currentStatus = "Initializing...";

        // Performance tracking
        private int framesReceived = 0;
        private float startTime;

        private void Start()
        {
            startTime = Time.time;
            InitializeDemo();
        }

        private void InitializeDemo()
        {
            Debug.Log("[SLAMDemo] Initializing SLAM demo...");

            // Get or create hybrid manager
            hybridManager = GetComponent<HybridSLAMManager>();
            if (hybridManager == null)
            {
                hybridManager = gameObject.AddComponent<HybridSLAMManager>();
            }

            // Configure for REST backend
            var clientField = hybridManager.GetType().GetField("preferredImplementation", 
                System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance);
            if (clientField != null)
            {
                clientField.SetValue(hybridManager, HybridSLAMManager.SLAMImplementation.RESTBackend);
            }

            // Subscribe to events
            hybridManager.OnReady += OnSLAMReady;
            hybridManager.OnPoseUpdated += OnPoseUpdated;
            hybridManager.OnTrackingStateChanged += OnTrackingStateChanged;
            hybridManager.OnError += OnSLAMError;

            // Create pose indicator if not assigned
            if (poseIndicator == null)
            {
                CreatePoseIndicator();
            }

            // Create status text if not assigned
            if (statusText == null)
            {
                CreateStatusText();
            }

            currentStatus = "Connecting to backend...";
            UpdateStatusDisplay();

            if (autoStart)
            {
                StartCoroutine(AutoStartDemo());
            }
        }

        private IEnumerator AutoStartDemo()
        {
            // Wait a moment for initialization
            yield return new WaitForSeconds(1.0f);

            // Initialize SLAM system
            hybridManager.InitializeOptimalImplementation();

            // Wait for initialization
            yield return new WaitUntil(() => hybridManager.IsInitialized || Time.time - startTime > 10f);

            if (hybridManager.IsInitialized)
            {
                // Start tracking
                hybridManager.StartTracking("demo_map");
                isDemoRunning = true;

                // Start sending test frames
                StartCoroutine(SendTestFrames());
            }
            else
            {
                currentStatus = "Failed to initialize SLAM";
                Debug.LogError("[SLAMDemo] SLAM initialization failed");
            }
        }

        private IEnumerator SendTestFrames()
        {
            // Get the SLAM client for direct frame sending
            slamClient = GetComponent<SpatialSLAMClient>();
            if (slamClient == null)
            {
                yield break;
            }

            while (isDemoRunning)
            {
                // Send a test frame (mock camera data)
                if (hybridManager.IsTrackingActive)
                {
                    // In a real implementation, this would capture actual camera frames
                    // For demo purposes, we rely on the mock SLAM in the backend
                    yield return new WaitForSeconds(testInterval);
                }
                else
                {
                    yield return new WaitForSeconds(0.1f);
                }
            }
        }

        #region Event Handlers

        private void OnSLAMReady()
        {
            currentStatus = "SLAM Ready";
            UpdateStatusDisplay();
            Debug.Log("[SLAMDemo] SLAM system ready");
        }

        private void OnPoseUpdated(Vector3 position, Quaternion rotation, float confidence)
        {
            lastPosition = position;
            lastRotation = rotation;
            lastConfidence = confidence;
            framesReceived++;

            // Update pose indicator
            if (poseIndicator != null)
            {
                poseIndicator.position = position;
                poseIndicator.rotation = rotation;

                // Color based on confidence
                var renderer = poseIndicator.GetComponent<Renderer>();
                if (renderer != null)
                {
                    renderer.material.color = Color.Lerp(Color.red, Color.green, confidence);
                }
            }

            UpdateStatusDisplay();

            // Log every 30 frames
            if (framesReceived % 30 == 0)
            {
                float elapsed = Time.time - startTime;
                float fps = framesReceived / elapsed;
                Debug.Log($"[SLAMDemo] Received {framesReceived} poses, {fps:F1} FPS avg, confidence: {confidence:F2}");
            }
        }

        private void OnTrackingStateChanged(string state)
        {
            currentStatus = $"Tracking: {state}";
            UpdateStatusDisplay();
            Debug.Log($"[SLAMDemo] Tracking state: {state}");
        }

        private void OnSLAMError(string error)
        {
            currentStatus = $"Error: {error}";
            UpdateStatusDisplay();
            Debug.LogError($"[SLAMDemo] SLAM error: {error}");
        }

        #endregion

        #region UI and Visualization

        private void CreatePoseIndicator()
        {
            // Create a simple cube to represent the pose
            var cube = GameObject.CreatePrimitive(PrimitiveType.Cube);
            cube.name = "SLAM Pose Indicator";
            cube.transform.localScale = Vector3.one * 0.1f;
            poseIndicator = cube.transform;

            // Add a material
            var renderer = cube.GetComponent<Renderer>();
            if (renderer != null)
            {
                renderer.material = new Material(Shader.Find("Standard"));
                renderer.material.color = Color.blue;
            }
        }

        private void CreateStatusText()
        {
            // Create status display
            var textObj = new GameObject("SLAM Status Text");
            textObj.transform.SetParent(transform);
            textObj.transform.localPosition = Vector3.forward * 2f;

            statusText = textObj.AddComponent<TextMesh>();
            statusText.characterSize = 0.1f;
            statusText.fontSize = 20;
            statusText.color = Color.white;
            statusText.anchor = TextAnchor.MiddleCenter;
        }

        private void UpdateStatusDisplay()
        {
            if (statusText != null)
            {
                float elapsed = Time.time - startTime;
                float fps = framesReceived / elapsed;
                
                statusText.text = $"SLAM Demo\n" +
                                 $"Status: {currentStatus}\n" +
                                 $"Implementation: {hybridManager?.ActiveImplementation}\n" +
                                 $"Poses Received: {framesReceived}\n" +
                                 $"FPS: {fps:F1}\n" +
                                 $"Position: {lastPosition}\n" +
                                 $"Confidence: {lastConfidence:F2}";
            }
        }

        private void OnGUI()
        {
            if (!showDebugGUI) return;

            GUILayout.BeginArea(new Rect(10, 10, 300, 200));
            GUILayout.Box("SLAM Demo Controls");

            if (GUILayout.Button("Initialize SLAM"))
            {
                hybridManager?.InitializeOptimalImplementation();
            }

            if (GUILayout.Button("Start Tracking"))
            {
                hybridManager?.StartTracking("demo_map");
                isDemoRunning = true;
                StartCoroutine(SendTestFrames());
            }

            if (GUILayout.Button("Stop Tracking"))
            {
                hybridManager?.StopTracking();
                isDemoRunning = false;
            }

            if (GUILayout.Button("Save Map"))
            {
                hybridManager?.SaveMap("demo_saved_map");
            }

            if (GUILayout.Button("Load Map"))
            {
                hybridManager?.LoadMap("demo_saved_map");
            }

            GUILayout.Label($"System Status: {hybridManager?.GetSystemStatus()}");

            GUILayout.EndArea();
        }

        #endregion

        #region Public API

        public void StartDemo()
        {
            if (!isDemoRunning)
            {
                StartCoroutine(AutoStartDemo());
            }
        }

        public void StopDemo()
        {
            isDemoRunning = false;
            hybridManager?.StopTracking();
        }

        public void RestartDemo()
        {
            StopDemo();
            framesReceived = 0;
            startTime = Time.time;
            StartDemo();
        }

        #endregion

        private void OnDestroy()
        {
            // Cleanup
            if (hybridManager != null)
            {
                hybridManager.OnReady -= OnSLAMReady;
                hybridManager.OnPoseUpdated -= OnPoseUpdated;
                hybridManager.OnTrackingStateChanged -= OnTrackingStateChanged;
                hybridManager.OnError -= OnSLAMError;
            }

            StopDemo();
        }
    }
}