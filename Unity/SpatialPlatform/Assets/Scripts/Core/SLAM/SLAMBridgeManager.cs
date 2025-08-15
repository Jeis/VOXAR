/**
 * Spatial Platform - SLAM Bridge Manager
 * Manages the integration between AR Foundation and backend SLAM service
 */

using System;
using System.Collections;
using UnityEngine;
using UnityEngine.XR.ARFoundation;
using UnityEngine.XR.ARSubsystems;
using SpatialPlatform.Core.Services;

namespace SpatialPlatform.Core.SLAM
{
    public class SLAMBridgeManager : MonoBehaviour
    {
        [Header("AR Components")]
        [SerializeField] private ARSessionOrigin arSessionOrigin;
        [SerializeField] private ARSession arSession;
        [SerializeField] private ARCamera arCamera;

        [Header("SLAM Configuration")]
        [SerializeField] private SpatialSLAMClient slamClient;
        [SerializeField] private bool autoStartOnARReady = true;
        [SerializeField] private bool enablePoseCorrection = true;
        [SerializeField] private string defaultMapId = "default_map";

        [Header("Debugging")]
        [SerializeField] private bool visualizePoses = true;
        [SerializeField] private GameObject poseVisualizationPrefab;
        [SerializeField] private bool enableDebugLogging = true;

        // State management
        private bool isARReady = false;
        private bool isSLAMReady = false;
        private bool isTrackingActive = false;

        // Pose tracking
        private Transform arCameraTransform;
        private Vector3 lastSLAMPosition;
        private Quaternion lastSLAMRotation;
        private float lastPoseConfidence;

        // Events
        public event Action OnSLAMReady;
        public event Action OnTrackingStarted;
        public event Action OnTrackingStopped;
        public event Action<Vector3, Quaternion, float> OnPoseUpdated;

        private void Start()
        {
            InitializeBridge();
        }

        private void InitializeBridge()
        {
            // Validate AR components
            if (arSessionOrigin == null)
            {
                arSessionOrigin = FindObjectOfType<ARSessionOrigin>();
            }

            if (arSession == null)
            {
                arSession = FindObjectOfType<ARSession>();
            }

            if (arCamera == null)
            {
                arCamera = FindObjectOfType<ARCamera>();
            }

            if (slamClient == null)
            {
                slamClient = GetComponent<SpatialSLAMClient>();
                if (slamClient == null)
                {
                    LogError("SpatialSLAMClient not found. Please add SpatialSLAMClient component.");
                    return;
                }
            }

            arCameraTransform = arCamera.transform;

            // Subscribe to AR session events
            ARSession.stateChanged += OnARSessionStateChanged;

            // Subscribe to SLAM client events
            slamClient.OnPoseReceived += OnSLAMPoseReceived;
            slamClient.OnTrackingStateChanged += OnSLAMTrackingStateChanged;
            slamClient.OnError += OnSLAMError;

            Log("SLAM Bridge Manager initialized");
        }

        #region AR Session Management

        private void OnARSessionStateChanged(ARSessionStateChangedEventArgs eventArgs)
        {
            switch (eventArgs.state)
            {
                case ARSessionState.Ready:
                    OnARSessionReady();
                    break;
                case ARSessionState.SessionTracking:
                    OnARTrackingStarted();
                    break;
                case ARSessionState.NotSupported:
                case ARSessionState.NeedsInstall:
                case ARSessionState.Installing:
                case ARSessionState.CheckingAvailability:
                case ARSessionState.Unsupported:
                    OnARSessionNotReady();
                    break;
            }

            Log($"AR Session state changed: {eventArgs.state}");
        }

        private void OnARSessionReady()
        {
            isARReady = true;
            Log("AR Session ready");

            if (autoStartOnARReady)
            {
                StartSLAMTracking();
            }
        }

        private void OnARTrackingStarted()
        {
            Log("AR tracking started");
        }

        private void OnARSessionNotReady()
        {
            isARReady = false;
            if (isTrackingActive)
            {
                StopSLAMTracking();
            }
        }

        #endregion

        #region SLAM Management

        public void StartSLAMTracking(string mapId = null)
        {
            if (!isARReady)
            {
                LogWarning("AR not ready. Cannot start SLAM tracking.");
                return;
            }

            if (isTrackingActive)
            {
                LogWarning("SLAM tracking already active");
                return;
            }

            StartCoroutine(StartSLAMSequence(mapId ?? defaultMapId));
        }

        public void StopSLAMTracking()
        {
            if (!isTrackingActive)
            {
                LogWarning("SLAM tracking not active");
                return;
            }

            StartCoroutine(StopSLAMSequence());
        }

        public void SaveCurrentMap(string mapId)
        {
            if (!isSLAMReady)
            {
                LogError("SLAM not ready. Cannot save map.");
                return;
            }

            slamClient.SaveMap(mapId);
            Log($"Saving map: {mapId}");
        }

        public void LoadMap(string mapId)
        {
            if (!isSLAMReady)
            {
                LogError("SLAM not ready. Cannot load map.");
                return;
            }

            slamClient.LoadMap(mapId);
            Log($"Loading map: {mapId}");
        }

        private IEnumerator StartSLAMSequence(string mapId)
        {
            Log("Starting SLAM sequence...");

            // Step 1: Initialize SLAM system
            slamClient.InitializeSLAM(mapId);

            // Wait for initialization
            yield return new WaitUntil(() => isSLAMReady);

            // Step 2: Start tracking
            slamClient.StartTracking();

            // Wait for tracking to start
            yield return new WaitForSeconds(1.0f);

            isTrackingActive = true;
            OnTrackingStarted?.Invoke();
            Log("SLAM tracking sequence completed");
        }

        private IEnumerator StopSLAMSequence()
        {
            Log("Stopping SLAM sequence...");

            slamClient.StopTracking();
            yield return new WaitForSeconds(0.5f);

            isTrackingActive = false;
            OnTrackingStopped?.Invoke();
            Log("SLAM tracking stopped");
        }

        #endregion

        #region SLAM Event Handlers

        private void OnSLAMPoseReceived(PoseResponse pose)
        {
            // Convert SLAM pose to Unity coordinates
            var position = new Vector3(pose.position[0], pose.position[1], pose.position[2]);
            var rotation = new Quaternion(pose.rotation[1], pose.rotation[2], pose.rotation[3], pose.rotation[0]);

            lastSLAMPosition = position;
            lastSLAMRotation = rotation;
            lastPoseConfidence = pose.confidence;

            // Apply pose correction if enabled
            if (enablePoseCorrection)
            {
                ApplyPoseCorrection(position, rotation, pose.confidence);
            }

            OnPoseUpdated?.Invoke(position, rotation, pose.confidence);

            // Visualize pose if enabled
            if (visualizePoses && poseVisualizationPrefab != null)
            {
                VisualizePose(position, rotation, pose.confidence);
            }
        }

        private void OnSLAMTrackingStateChanged(string state)
        {
            Log($"SLAM tracking state: {state}");

            switch (state)
            {
                case "tracking":
                    isSLAMReady = true;
                    OnSLAMReady?.Invoke();
                    break;
                case "stopped":
                case "lost":
                    // Handle tracking loss
                    break;
            }
        }

        private void OnSLAMError(string error)
        {
            LogError($"SLAM error: {error}");
        }

        #endregion

        #region Pose Correction

        private void ApplyPoseCorrection(Vector3 slamPosition, Quaternion slamRotation, float confidence)
        {
            // Only apply correction if confidence is high enough
            if (confidence < 0.7f) return;

            // Get current AR camera pose
            var arPosition = arCameraTransform.position;
            var arRotation = arCameraTransform.rotation;

            // Calculate correction factor based on confidence
            float correctionFactor = Mathf.Lerp(0.1f, 0.9f, confidence);

            // Apply weighted correction to AR session origin
            var correctedPosition = Vector3.Lerp(arPosition, slamPosition, correctionFactor);
            var correctedRotation = Quaternion.Lerp(arRotation, slamRotation, correctionFactor);

            // Apply correction to AR session origin
            if (arSessionOrigin != null)
            {
                var offset = correctedPosition - arPosition;
                arSessionOrigin.transform.position += offset;
                
                var rotationOffset = correctedRotation * Quaternion.Inverse(arRotation);
                arSessionOrigin.transform.rotation = rotationOffset * arSessionOrigin.transform.rotation;
            }

            if (enableDebugLogging && Time.frameCount % 30 == 0)
            {
                Log($"Pose correction applied: confidence={confidence:F2}, factor={correctionFactor:F2}");
            }
        }

        #endregion

        #region Visualization

        private void VisualizePose(Vector3 position, Quaternion rotation, float confidence)
        {
            // Create pose visualization (limit to avoid memory leaks)
            if (GameObject.FindGameObjectsWithTag("PoseVisualization").Length < 10)
            {
                var visualizer = Instantiate(poseVisualizationPrefab, position, rotation);
                visualizer.tag = "PoseVisualization";

                // Color based on confidence
                var renderer = visualizer.GetComponent<Renderer>();
                if (renderer != null)
                {
                    renderer.material.color = Color.Lerp(Color.red, Color.green, confidence);
                }

                // Auto-destroy after 5 seconds
                Destroy(visualizer, 5.0f);
            }
        }

        #endregion

        #region Public API

        /// <summary>
        /// Get current SLAM pose
        /// </summary>
        public bool GetCurrentSLAMPose(out Vector3 position, out Quaternion rotation, out float confidence)
        {
            position = lastSLAMPosition;
            rotation = lastSLAMRotation;
            confidence = lastPoseConfidence;
            return isTrackingActive && confidence > 0.5f;
        }

        /// <summary>
        /// Check if SLAM tracking is active and reliable
        /// </summary>
        public bool IsTrackingReliable()
        {
            return isTrackingActive && lastPoseConfidence > 0.7f;
        }

        /// <summary>
        /// Get tracking status information
        /// </summary>
        public string GetTrackingStatus()
        {
            if (!isARReady) return "AR not ready";
            if (!isSLAMReady) return "SLAM not ready";
            if (!isTrackingActive) return "Tracking inactive";
            if (lastPoseConfidence < 0.5f) return "Low confidence";
            if (lastPoseConfidence < 0.7f) return "Medium confidence";
            return "Tracking active";
        }

        #endregion

        #region Utility

        private void Log(string message)
        {
            if (enableDebugLogging)
            {
                Debug.Log($"[SLAMBridge] {message}");
            }
        }

        private void LogWarning(string message)
        {
            Debug.LogWarning($"[SLAMBridge] {message}");
        }

        private void LogError(string message)
        {
            Debug.LogError($"[SLAMBridge] {message}");
        }

        #endregion

        #region Unity Lifecycle

        private void OnDestroy()
        {
            // Unsubscribe from events
            ARSession.stateChanged -= OnARSessionStateChanged;

            if (slamClient != null)
            {
                slamClient.OnPoseReceived -= OnSLAMPoseReceived;
                slamClient.OnTrackingStateChanged -= OnSLAMTrackingStateChanged;
                slamClient.OnError -= OnSLAMError;
            }

            if (isTrackingActive)
            {
                StopSLAMTracking();
            }
        }

        private void OnApplicationPause(bool pauseStatus)
        {
            if (pauseStatus && isTrackingActive)
            {
                StopSLAMTracking();
            }
            else if (!pauseStatus && isARReady && !isTrackingActive)
            {
                StartSLAMTracking();
            }
        }

        #endregion
    }
}