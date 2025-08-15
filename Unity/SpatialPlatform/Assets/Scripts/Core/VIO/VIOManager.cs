/*
 * Spatial Platform - VIO Manager
 * Integrates IMU data collection with VIO processing for enhanced tracking
 */

using System;
using System.Collections;
using UnityEngine;
using UnityEngine.XR.ARFoundation;
using SpatialPlatform.Sensors;
using SpatialPlatform.Services;

namespace SpatialPlatform.VIO
{
    public class VIOManager : MonoBehaviour
    {
        [Header("VIO Configuration")]
        [SerializeField] private bool enableVIO = true;
        [SerializeField] private bool enableHybridMode = true; // Use both SLAM and VIO
        [SerializeField] private float vioWeight = 0.3f; // Weight for VIO vs SLAM fusion
        
        [Header("Performance Settings")]
        [SerializeField] private float imuTransmissionRate = 50f; // Hz
        [SerializeField] private float visualTransmissionRate = 10f; // Hz
        [SerializeField] private bool adaptiveQuality = true;
        
        [Header("Debug")]
        [SerializeField] private bool showDebugInfo = true;
        [SerializeField] private bool logVIOPoses = false;
        
        // Component references
        private IMUDataCollector imuCollector;
        private VIODataTransmitter vioTransmitter;
        private ARCamera arCamera;
        private ARSessionOrigin arSessionOrigin;
        
        // VIO state
        private bool isVIOInitialized = false;
        private bool isVIOTracking = false;
        private VIOResponse lastVIOResponse;
        private Pose currentVIOPose;
        private Pose currentSLAMPose;
        private Pose fusedPose;
        
        // Performance monitoring
        private float averageLatency = 0f;
        private int successfulVIOUpdates = 0;
        private int totalVIOAttempts = 0;
        
        // Events
        public event Action<VIOResponse> OnVIOPoseReceived;
        public event Action<Pose> OnFusedPoseUpdate;
        public event Action<bool> OnVIOTrackingStateChanged;
        public event Action<string> OnVIOError;
        
        // Properties
        public bool IsVIOEnabled => enableVIO && isVIOInitialized;
        public bool IsVIOTracking => isVIOTracking;
        public Pose CurrentVIOPose => currentVIOPose;
        public Pose FusedPose => fusedPose;
        public float VIOConfidence => lastVIOResponse?.pose_estimate?.confidence ?? 0f;
        public NetworkStats NetworkStats => vioTransmitter?.GetNetworkStats() ?? default;
        
        private void Awake()
        {
            InitializeComponents();
        }
        
        private void InitializeComponents()
        {
            // Get or create IMU collector
            imuCollector = GetComponent<IMUDataCollector>();
            if (imuCollector == null)
            {
                imuCollector = gameObject.AddComponent<IMUDataCollector>();
            }
            
            // Get or create VIO transmitter
            vioTransmitter = GetComponent<VIODataTransmitter>();
            if (vioTransmitter == null)
            {
                vioTransmitter = gameObject.AddComponent<VIODataTransmitter>();
            }
            
            // Find AR components
            arCamera = FindObjectOfType<ARCamera>();
            arSessionOrigin = FindObjectOfType<ARSessionOrigin>();
            
            if (arCamera == null)
            {
                Debug.LogWarning("ARCamera not found - VIO will use fallback camera");
            }
        }
        
        private void Start()
        {
            if (enableVIO)
            {
                StartCoroutine(InitializeVIOSystem());
            }
        }
        
        private IEnumerator InitializeVIOSystem()
        {
            Debug.Log("Initializing VIO system...");
            
            // Wait for IMU system to be ready
            while (!imuCollector.IsSensorAvailable("accelerometer") || 
                   !imuCollector.IsSensorAvailable("gyroscope"))
            {
                yield return new WaitForSeconds(0.1f);
            }
            
            // Subscribe to events
            if (vioTransmitter != null)
            {
                vioTransmitter.OnVIOResponseReceived += OnVIOResponseReceived;
                vioTransmitter.OnTransmissionError += OnVIOTransmissionError;
                vioTransmitter.OnNetworkQualityChanged += OnNetworkQualityChanged;
                
                // Configure transmission rates
                vioTransmitter.SetTransmissionRates(imuTransmissionRate, visualTransmissionRate);
            }
            
            if (imuCollector != null)
            {
                imuCollector.OnCalibrationComplete += OnIMUCalibrationComplete;
                imuCollector.OnError += OnIMUError;
            }
            
            // Wait for IMU calibration
            Debug.Log("Waiting for IMU calibration...");
            yield return new WaitForSeconds(2f); // Give time for calibration
            
            isVIOInitialized = true;
            Debug.Log("VIO system initialized successfully");
            
            // Start VIO processing loop
            StartCoroutine(VIOProcessingLoop());
        }
        
        private IEnumerator VIOProcessingLoop()
        {
            while (enableVIO && isVIOInitialized)
            {
                try
                {
                    // Update VIO tracking state based on recent responses
                    UpdateVIOTrackingState();
                    
                    // Perform pose fusion if we have both VIO and SLAM data
                    if (enableHybridMode)
                    {
                        PerformPoseFusion();
                    }
                    
                    yield return new WaitForSeconds(0.1f); // 10Hz update rate
                }
                catch (Exception e)
                {
                    Debug.LogError($"VIO processing loop error: {e.Message}");
                    OnVIOError?.Invoke(e.Message);
                    yield return new WaitForSeconds(1f); // Wait longer on error
                }
            }
        }
        
        private void OnVIOResponseReceived(VIOResponse response)
        {
            totalVIOAttempts++;
            
            if (response.success && response.pose_estimate != null)
            {
                successfulVIOUpdates++;
                lastVIOResponse = response;
                
                // Convert VIO pose to Unity format
                currentVIOPose = ConvertVIOPoseToUnity(response.pose_estimate);
                
                // Update performance metrics
                averageLatency = averageLatency * 0.9f + response.processing_time * 0.1f;
                
                if (logVIOPoses)
                {
                    Debug.Log($"VIO Pose: pos={currentVIOPose.position}, rot={currentVIOPose.rotation}, conf={response.pose_estimate.confidence:F2}");
                }
                
                OnVIOPoseReceived?.Invoke(response);
            }
            else
            {
                Debug.LogWarning($"VIO processing failed: {response.message}");
            }
        }
        
        private Pose ConvertVIOPoseToUnity(VIOPoseResponse vioResponse)
        {
            // Convert from backend coordinate system to Unity
            Vector3 position = new Vector3(
                (float)vioResponse.position[0],
                (float)vioResponse.position[1],
                (float)vioResponse.position[2]
            );
            
            // VIO returns [qw, qx, qy, qz], Unity uses [qx, qy, qz, qw]
            Quaternion rotation = new Quaternion(
                (float)vioResponse.rotation[1], // qx
                (float)vioResponse.rotation[2], // qy
                (float)vioResponse.rotation[3], // qz
                (float)vioResponse.rotation[0]  // qw
            );
            
            return new Pose(position, rotation);
        }
        
        private void UpdateVIOTrackingState()
        {
            bool wasTracking = isVIOTracking;
            
            // Consider VIO tracking if we have recent successful responses
            bool hasRecentResponse = lastVIOResponse != null && 
                                   (Time.time - Time.realtimeSinceStartup + lastVIOResponse.pose_estimate?.timestamp ?? 0) < 1f;
            
            bool goodConfidence = lastVIOResponse?.pose_estimate?.confidence > 0.5f;
            bool trackingState = lastVIOResponse?.pose_estimate?.tracking_state == "tracking" ||
                               lastVIOResponse?.pose_estimate?.tracking_state == "tracking_degraded";
            
            isVIOTracking = hasRecentResponse && goodConfidence && trackingState;
            
            if (wasTracking != isVIOTracking)
            {
                Debug.Log($"VIO tracking state changed: {wasTracking} -> {isVIOTracking}");
                OnVIOTrackingStateChanged?.Invoke(isVIOTracking);
            }
        }
        
        private void PerformPoseFusion()
        {
            // Simple weighted fusion of VIO and SLAM poses
            // In a production system, this would use more sophisticated fusion algorithms
            
            if (!isVIOTracking)
            {
                // Use SLAM pose only
                fusedPose = currentSLAMPose;
            }
            else
            {
                // Weighted fusion
                Vector3 fusedPosition = Vector3.Lerp(currentSLAMPose.position, currentVIOPose.position, vioWeight);
                Quaternion fusedRotation = Quaternion.Slerp(currentSLAMPose.rotation, currentVIOPose.rotation, vioWeight);
                
                fusedPose = new Pose(fusedPosition, fusedRotation);
            }
            
            OnFusedPoseUpdate?.Invoke(fusedPose);
        }
        
        private void OnVIOTransmissionError(string error)
        {
            Debug.LogWarning($"VIO transmission error: {error}");
            OnVIOError?.Invoke(error);
        }
        
        private void OnNetworkQualityChanged(float quality)
        {
            if (adaptiveQuality && quality < 0.5f)
            {
                // Reduce transmission rates for poor network conditions
                float adaptedIMURate = Mathf.Max(imuTransmissionRate * quality, 10f);
                float adaptedVisualRate = Mathf.Max(visualTransmissionRate * quality, 2f);
                vioTransmitter?.SetTransmissionRates(adaptedIMURate, adaptedVisualRate);
                
                if (showDebugInfo)
                {
                    Debug.Log($"Adapted VIO rates for network quality {quality:F2}: IMU={adaptedIMURate:F1}Hz, Visual={adaptedVisualRate:F1}Hz");
                }
            }
        }
        
        private void OnIMUCalibrationComplete(IMUCalibration calibration)
        {
            Debug.Log("IMU calibration completed - VIO accuracy should improve");
        }
        
        private void OnIMUError(string error)
        {
            Debug.LogError($"IMU error: {error}");
            OnVIOError?.Invoke($"IMU: {error}");
        }
        
        // Public methods for external control
        public void SetVIOEnabled(bool enabled)
        {
            enableVIO = enabled;
            if (!enabled && isVIOInitialized)
            {
                StopVIO();
            }
            else if (enabled && !isVIOInitialized)
            {
                StartCoroutine(InitializeVIOSystem());
            }
        }
        
        public void SetHybridMode(bool enabled)
        {
            enableHybridMode = enabled;
            Debug.Log($"VIO hybrid mode {(enabled ? "enabled" : "disabled")}");
        }
        
        public void SetVIOWeight(float weight)
        {
            vioWeight = Mathf.Clamp01(weight);
            Debug.Log($"VIO fusion weight set to {vioWeight:F2}");
        }
        
        public void UpdateSLAMPose(Pose slamPose)
        {
            currentSLAMPose = slamPose;
        }
        
        public void RecalibrateIMU()
        {
            imuCollector?.StartCalibration();
        }
        
        public VIOStatistics GetVIOStatistics()
        {
            return new VIOStatistics
            {
                isInitialized = isVIOInitialized,
                isTracking = isVIOTracking,
                confidence = VIOConfidence,
                averageLatency = averageLatency,
                successRate = totalVIOAttempts > 0 ? (float)successfulVIOUpdates / totalVIOAttempts : 0f,
                totalAttempts = totalVIOAttempts,
                networkStats = NetworkStats
            };
        }
        
        private void StopVIO()
        {
            isVIOInitialized = false;
            isVIOTracking = false;
            
            if (vioTransmitter != null)
            {
                vioTransmitter.OnVIOResponseReceived -= OnVIOResponseReceived;
                vioTransmitter.OnTransmissionError -= OnVIOTransmissionError;
                vioTransmitter.OnNetworkQualityChanged -= OnNetworkQualityChanged;
            }
            
            if (imuCollector != null)
            {
                imuCollector.OnCalibrationComplete -= OnIMUCalibrationComplete;
                imuCollector.OnError -= OnIMUError;
            }
            
            Debug.Log("VIO system stopped");
        }
        
        private void OnDestroy()
        {
            StopVIO();
        }
        
        private void OnApplicationPause(bool pauseStatus)
        {
            if (pauseStatus)
            {
                StopVIO();
            }
            else if (enableVIO && !isVIOInitialized)
            {
                StartCoroutine(InitializeVIOSystem());
            }
        }
        
        // Debug GUI
        private void OnGUI()
        {
            if (!showDebugInfo) return;
            
            GUILayout.BeginArea(new Rect(10, 10, 300, 200));
            GUILayout.Label($"VIO Status: {(isVIOInitialized ? "Initialized" : "Not Initialized")}");
            GUILayout.Label($"VIO Tracking: {(isVIOTracking ? "Active" : "Inactive")}");
            GUILayout.Label($"VIO Confidence: {VIOConfidence:F2}");
            GUILayout.Label($"Average Latency: {averageLatency:F1}ms");
            GUILayout.Label($"Success Rate: {(totalVIOAttempts > 0 ? successfulVIOUpdates * 100f / totalVIOAttempts : 0):F1}%");
            GUILayout.Label($"Network Quality: {NetworkStats.networkQuality:F2}");
            GUILayout.EndArea();
        }
    }
    
    [Serializable]
    public struct VIOStatistics
    {
        public bool isInitialized;
        public bool isTracking;
        public float confidence;
        public float averageLatency;
        public float successRate;
        public int totalAttempts;
        public NetworkStats networkStats;
    }
}