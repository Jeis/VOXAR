using System;
using System.Runtime.InteropServices;
using UnityEngine;
using SpatialPlatform.Core.Utilities;

namespace SpatialPlatform.Core.SLAM
{
    /// <summary>
    /// Unity wrapper for native SLAM functionality with enterprise-grade error handling
    /// Manages visual-inertial odometry, relocalization, and map management
    /// </summary>
    public class SLAMManager : MonoBehaviour
    {
        [Header("SLAM Configuration")]
        [SerializeField] private string vocabularyPath = "StreamingAssets/orb_vocab.yml";
        [SerializeField] private int maxFeatures = 2000;
        [SerializeField] private float featureQuality = 0.01f;
        [SerializeField] private bool enableRelocalization = true;
        [SerializeField] private bool enableLoopClosure = true;
        [SerializeField] private float memoryLimitMB = 200f;
        
        [Header("Camera Calibration")]
        [SerializeField] private float focalLengthX = 525.0f;
        [SerializeField] private float focalLengthY = 525.0f;
        [SerializeField] private float principalPointX = 319.5f;
        [SerializeField] private float principalPointY = 239.5f;
        [SerializeField] private Vector3 distortionCoefficients = Vector3.zero;
        [SerializeField] private Vector2 distortionTangential = Vector2.zero;
        
        // Native interop structures
        [StructLayout(LayoutKind.Sequential)]
        private struct NativeCameraCalibration
        {
            public float fx, fy;
            public float cx, cy;
            public float k1, k2, k3;
            public float p1, p2;
            public int width, height;
        }
        
        [StructLayout(LayoutKind.Sequential)]
        private struct NativePose
        {
            [MarshalAs(UnmanagedType.ByValArray, SizeConst = 3)]
            public float[] position;
            [MarshalAs(UnmanagedType.ByValArray, SizeConst = 4)]
            public float[] rotation;
            public double timestamp;
            public float confidence;
        }
        
        [StructLayout(LayoutKind.Sequential)]
        private struct NativeSLAMConfig
        {
            public int max_features;
            public float feature_quality;
            public float min_feature_distance;
            public float max_reprojection_error;
            public int min_tracking_features;
            public int max_tracking_iterations;
            public int keyframe_threshold;
            public float keyframe_distance;
            public float keyframe_angle;
            public bool enable_multithreading;
            public int max_threads;
            public bool enable_loop_closure;
            public bool enable_relocalization;
            public int max_keyframes;
            public int max_landmarks;
            public float memory_limit_mb;
        }
        
        [StructLayout(LayoutKind.Sequential)]
        private struct NativeTrackingStats
        {
            public int total_keyframes;
            public int total_landmarks;
            public int tracking_keyframes;
            public float average_reprojection_error;
            public float processing_time_ms;
            public int quality;
            public int feature_count;
            public int matched_features;
        }
        
        // Native function imports
        #if UNITY_IOS && !UNITY_EDITOR
        private const string NATIVE_LIB = "__Internal";
        #else
        private const string NATIVE_LIB = "SpatialSLAM";
        #endif
        
        [DllImport(NATIVE_LIB)]
        private static extern IntPtr SpatialSLAM_Create(
            ref NativeSLAMConfig config,
            ref NativeCameraCalibration calibration,
            string vocabulary_path
        );
        
        [DllImport(NATIVE_LIB)]
        private static extern void SpatialSLAM_Destroy(IntPtr handle);
        
        [DllImport(NATIVE_LIB)]
        private static extern int SpatialSLAM_ProcessFrame(
            IntPtr handle,
            IntPtr image_data,
            int width,
            int height,
            double timestamp,
            out NativePose pose
        );
        
        [DllImport(NATIVE_LIB)]
        private static extern int SpatialSLAM_GetCurrentPose(IntPtr handle, out NativePose pose);
        
        [DllImport(NATIVE_LIB)]
        private static extern int SpatialSLAM_GetTrackingStats(IntPtr handle, out NativeTrackingStats stats);
        
        [DllImport(NATIVE_LIB)]
        private static extern int SpatialSLAM_LoadMapFromBuffer(IntPtr handle, byte[] buffer, int size);
        
        [DllImport(NATIVE_LIB)]
        private static extern int SpatialSLAM_SaveMapToBuffer(IntPtr handle, byte[] buffer, int buffer_size, out int bytes_written);
        
        [DllImport(NATIVE_LIB)]
        private static extern int SpatialSLAM_SetRelocalizationEnabled(IntPtr handle, bool enable);
        
        [DllImport(NATIVE_LIB)]
        private static extern int SpatialSLAM_RequestRelocalization(IntPtr handle);
        
        [DllImport(NATIVE_LIB)]
        private static extern int SpatialSLAM_GetState(IntPtr handle);
        
        [DllImport(NATIVE_LIB)]
        private static extern int SpatialSLAM_Reset(IntPtr handle);
        
        // Enums
        public enum SLAMResult
        {
            Success = 0,
            InvalidParameter = -1,
            InitializationFailed = -2,
            SystemNotReady = -3,
            ProcessingFailed = -4,
            MapLoadFailed = -5,
            InsufficientFeatures = -6,
            TrackingLost = -7,
            OutOfMemory = -8,
            UnsupportedFormat = -9,
            FileNotFound = -10
        }
        
        public enum SLAMState
        {
            Uninitialized = 0,
            Initializing = 1,
            Ready = 2,
            Tracking = 3,
            Lost = 4,
            Relocalization = 5,
            Failed = 6
        }
        
        public enum TrackingQuality
        {
            Poor = 0,
            Fair = 1,
            Good = 2,
            Excellent = 3
        }
        
        // Public data structures
        [Serializable]
        public struct Pose
        {
            public Vector3 position;
            public Quaternion rotation;
            public double timestamp;
            public float confidence;
            
            public Matrix4x4 ToMatrix()
            {
                return Matrix4x4.TRS(position, rotation, Vector3.one);
            }
        }
        
        [Serializable]
        public struct TrackingStats
        {
            public int totalKeyframes;
            public int totalLandmarks;
            public int trackingKeyframes;
            public float averageReprojectionError;
            public float processingTimeMs;
            public TrackingQuality quality;
            public int featureCount;
            public int matchedFeatures;
        }
        
        // Events
        public static event Action<SLAMState> OnSLAMStateChanged;
        public static event Action<Pose> OnPoseUpdated;
        public static event Action<TrackingStats> OnTrackingStatsUpdated;
        public static event Action<string> OnSLAMError;
        
        // State
        private IntPtr nativeSLAMHandle = IntPtr.Zero;
        private SLAMState currentState = SLAMState.Uninitialized;
        private Pose lastKnownPose;
        private TrackingStats lastStats;
        private bool isInitialized = false;
        private bool isTrackingEnabled = false;
        
        // Performance monitoring
        private readonly CircularBuffer<float> processingTimes = new CircularBuffer<float>(30);
        private Camera arCamera;
        private Texture2D frameTexture;
        
        // Properties
        public SLAMState CurrentState => currentState;
        public bool IsInitialized => isInitialized;
        public bool IsTrackingEnabled => isTrackingEnabled;
        public Pose LastKnownPose => lastKnownPose;
        public TrackingStats LastTrackingStats => lastStats;
        public float AverageProcessingTime => processingTimes.IsEmpty ? 0f : (float)processingTimes.Average();
        
        void Start()
        {
            InitializeSLAM();
        }
        
        private void InitializeSLAM()
        {
            try
            {
                ChangeState(SLAMState.Initializing);
                
                // Get AR camera reference
                arCamera = Camera.main;
                if (arCamera == null)
                {
                    arCamera = FindObjectOfType<Camera>();
                }
                
                if (arCamera == null)
                {
                    throw new InvalidOperationException("No camera found for SLAM initialization");
                }
                
                // Setup camera calibration from current camera
                var calibration = CreateCameraCalibration();
                
                // Configure SLAM system
                var config = CreateSLAMConfig();
                
                // Get vocabulary path
                string vocabPath = System.IO.Path.Combine(Application.streamingAssetsPath, vocabularyPath);
                if (!System.IO.File.Exists(vocabPath))
                {
                    Debug.LogWarning($"ORB vocabulary not found at {vocabPath} - SLAM may not work optimally");
                    vocabPath = null; // Let native code handle missing vocabulary
                }
                
                // Create native SLAM system
                nativeSLAMHandle = SpatialSLAM_Create(ref config, ref calibration, vocabPath);
                
                if (nativeSLAMHandle == IntPtr.Zero)
                {
                    throw new InvalidOperationException("Failed to create native SLAM system");
                }
                
                isInitialized = true;
                ChangeState(SLAMState.Ready);
                
                Debug.Log("SLAM system initialized successfully");
                
                // Enable relocalization if requested
                if (enableRelocalization)
                {
                    SetRelocalizationEnabled(true);
                }
            }
            catch (Exception e)
            {
                Debug.LogError($"Failed to initialize SLAM: {e.Message}");
                ChangeState(SLAMState.Failed);
                OnSLAMError?.Invoke($"SLAM initialization failed: {e.Message}");
            }
        }
        
        private NativeCameraCalibration CreateCameraCalibration()
        {
            // Use provided calibration or estimate from camera
            float fx = focalLengthX > 0 ? focalLengthX : Screen.width * 0.8f;
            float fy = focalLengthY > 0 ? focalLengthY : Screen.height * 0.8f;
            float cx = principalPointX > 0 ? principalPointX : Screen.width * 0.5f;
            float cy = principalPointY > 0 ? principalPointY : Screen.height * 0.5f;
            
            return new NativeCameraCalibration
            {
                fx = fx,
                fy = fy,
                cx = cx,
                cy = cy,
                k1 = distortionCoefficients.x,
                k2 = distortionCoefficients.y,
                k3 = distortionCoefficients.z,
                p1 = distortionTangential.x,
                p2 = distortionTangential.y,
                width = Screen.width,
                height = Screen.height
            };
        }
        
        private NativeSLAMConfig CreateSLAMConfig()
        {
            return new NativeSLAMConfig
            {
                max_features = maxFeatures,
                feature_quality = featureQuality,
                min_feature_distance = 10f,
                max_reprojection_error = 2.0f,
                min_tracking_features = 15,
                max_tracking_iterations = 20,
                keyframe_threshold = 20,
                keyframe_distance = 0.1f,
                keyframe_angle = 0.2f,
                enable_multithreading = true,
                max_threads = SystemInfo.processorCount,
                enable_loop_closure = enableLoopClosure,
                enable_relocalization = enableRelocalization,
                max_keyframes = 1000,
                max_landmarks = 10000,
                memory_limit_mb = memoryLimitMB
            };
        }
        
        public void StartTracking()
        {
            if (!isInitialized || nativeSLAMHandle == IntPtr.Zero)
            {
                Debug.LogError("SLAM not initialized - cannot start tracking");
                return;
            }
            
            isTrackingEnabled = true;
            ChangeState(SLAMState.Tracking);
            Debug.Log("SLAM tracking started");
        }
        
        public void StopTracking()
        {
            isTrackingEnabled = false;
            
            if (currentState == SLAMState.Tracking)
            {
                ChangeState(SLAMState.Ready);
            }
            
            Debug.Log("SLAM tracking stopped");
        }
        
        public SLAMResult ProcessCameraFrame(byte[] imageData, int width, int height)
        {
            if (!isInitialized || nativeSLAMHandle == IntPtr.Zero || !isTrackingEnabled)
            {
                return SLAMResult.SystemNotReady;
            }
            
            if (imageData == null || imageData.Length == 0)
            {
                return SLAMResult.InvalidParameter;
            }
            
            try
            {
                var startTime = Time.realtimeSinceStartup;
                
                // Pin image data for native access
                GCHandle imageHandle = GCHandle.Alloc(imageData, GCHandleType.Pinned);
                IntPtr imagePtr = imageHandle.AddrOfPinnedObject();
                
                NativePose nativePose;
                int result = SpatialSLAM_ProcessFrame(
                    nativeSLAMHandle,
                    imagePtr,
                    width,
                    height,
                    Time.realtimeSinceStartup,
                    out nativePose
                );
                
                imageHandle.Free();
                
                // Track performance
                float processingTime = (Time.realtimeSinceStartup - startTime) * 1000f;
                processingTimes.Add(processingTime);
                
                if (result == 0) // Success
                {
                    // Convert native pose to Unity format
                    var pose = ConvertNativePose(nativePose);
                    lastKnownPose = pose;
                    
                    OnPoseUpdated?.Invoke(pose);
                    
                    // Update state if we were lost
                    if (currentState == SLAMState.Lost)
                    {
                        ChangeState(SLAMState.Tracking);
                    }
                }
                else if (result == (int)SLAMResult.TrackingLost)
                {
                    if (currentState == SLAMState.Tracking)
                    {
                        ChangeState(SLAMState.Lost);
                        Debug.LogWarning("SLAM tracking lost");
                    }
                }
                
                return (SLAMResult)result;
            }
            catch (Exception e)
            {
                Debug.LogError($"Error processing SLAM frame: {e.Message}");
                OnSLAMError?.Invoke($"Frame processing error: {e.Message}");
                return SLAMResult.ProcessingFailed;
            }
        }
        
        public Pose GetCurrentPose()
        {
            if (!isInitialized || nativeSLAMHandle == IntPtr.Zero)
            {
                return new Pose();
            }
            
            NativePose nativePose;
            int result = SpatialSLAM_GetCurrentPose(nativeSLAMHandle, out nativePose);
            
            if (result == 0)
            {
                return ConvertNativePose(nativePose);
            }
            
            return lastKnownPose;
        }
        
        public TrackingStats GetTrackingStats()
        {
            if (!isInitialized || nativeSLAMHandle == IntPtr.Zero)
            {
                return new TrackingStats();
            }
            
            NativeTrackingStats nativeStats;
            int result = SpatialSLAM_GetTrackingStats(nativeSLAMHandle, out nativeStats);
            
            if (result == 0)
            {
                var stats = new TrackingStats
                {
                    totalKeyframes = nativeStats.total_keyframes,
                    totalLandmarks = nativeStats.total_landmarks,
                    trackingKeyframes = nativeStats.tracking_keyframes,
                    averageReprojectionError = nativeStats.average_reprojection_error,
                    processingTimeMs = nativeStats.processing_time_ms,
                    quality = (TrackingQuality)nativeStats.quality,
                    featureCount = nativeStats.feature_count,
                    matchedFeatures = nativeStats.matched_features
                };
                
                lastStats = stats;
                OnTrackingStatsUpdated?.Invoke(stats);
                return stats;
            }
            
            return lastStats;
        }
        
        public SLAMResult LoadMap(byte[] mapData)
        {
            if (!isInitialized || nativeSLAMHandle == IntPtr.Zero)
            {
                return SLAMResult.SystemNotReady;
            }
            
            if (mapData == null || mapData.Length == 0)
            {
                return SLAMResult.InvalidParameter;
            }
            
            try
            {
                int result = SpatialSLAM_LoadMapFromBuffer(nativeSLAMHandle, mapData, mapData.Length);
                
                if (result == 0)
                {
                    Debug.Log($"Successfully loaded map ({mapData.Length} bytes)");
                }
                else
                {
                    Debug.LogError($"Failed to load map: {(SLAMResult)result}");
                }
                
                return (SLAMResult)result;
            }
            catch (Exception e)
            {
                Debug.LogError($"Exception loading map: {e.Message}");
                OnSLAMError?.Invoke($"Map loading error: {e.Message}");
                return SLAMResult.ProcessingFailed;
            }
        }
        
        public SLAMResult SaveMap(out byte[] mapData)
        {
            mapData = null;
            
            if (!isInitialized || nativeSLAMHandle == IntPtr.Zero)
            {
                return SLAMResult.SystemNotReady;
            }
            
            try
            {
                // First, get the required buffer size by calling with null buffer
                byte[] tempBuffer = new byte[10 * 1024 * 1024]; // 10MB initial buffer
                int bytesWritten;
                
                int result = SpatialSLAM_SaveMapToBuffer(
                    nativeSLAMHandle,
                    tempBuffer,
                    tempBuffer.Length,
                    out bytesWritten
                );
                
                if (result == 0 && bytesWritten > 0)
                {
                    // Trim buffer to actual size
                    mapData = new byte[bytesWritten];
                    Array.Copy(tempBuffer, mapData, bytesWritten);
                    
                    Debug.Log($"Successfully saved map ({bytesWritten} bytes)");
                }
                else
                {
                    Debug.LogError($"Failed to save map: {(SLAMResult)result}");
                }
                
                return (SLAMResult)result;
            }
            catch (Exception e)
            {
                Debug.LogError($"Exception saving map: {e.Message}");
                OnSLAMError?.Invoke($"Map saving error: {e.Message}");
                return SLAMResult.ProcessingFailed;
            }
        }
        
        public void SetRelocalizationEnabled(bool enabled)
        {
            if (isInitialized && nativeSLAMHandle != IntPtr.Zero)
            {
                int result = SpatialSLAM_SetRelocalizationEnabled(nativeSLAMHandle, enabled);
                
                if (result == 0)
                {
                    Debug.Log($"Relocalization {(enabled ? "enabled" : "disabled")}");
                }
                else
                {
                    Debug.LogError($"Failed to set relocalization: {(SLAMResult)result}");
                }
            }
        }
        
        public void RequestRelocalization()
        {
            if (isInitialized && nativeSLAMHandle != IntPtr.Zero)
            {
                int result = SpatialSLAM_RequestRelocalization(nativeSLAMHandle);
                
                if (result == 0)
                {
                    ChangeState(SLAMState.Relocalization);
                    Debug.Log("Relocalization requested");
                }
                else
                {
                    Debug.LogError($"Failed to request relocalization: {(SLAMResult)result}");
                }
            }
        }
        
        public void ResetSLAM()
        {
            if (isInitialized && nativeSLAMHandle != IntPtr.Zero)
            {
                int result = SpatialSLAM_Reset(nativeSLAMHandle);
                
                if (result == 0)
                {
                    ChangeState(SLAMState.Ready);
                    lastKnownPose = new Pose();
                    Debug.Log("SLAM system reset");
                }
                else
                {
                    Debug.LogError($"Failed to reset SLAM: {(SLAMResult)result}");
                }
            }
        }
        
        private Pose ConvertNativePose(NativePose nativePose)
        {
            return new Pose
            {
                position = new Vector3(
                    nativePose.position[0],
                    nativePose.position[1],
                    nativePose.position[2]
                ),
                rotation = new Quaternion(
                    nativePose.rotation[0],
                    nativePose.rotation[1],
                    nativePose.rotation[2],
                    nativePose.rotation[3]
                ),
                timestamp = nativePose.timestamp,
                confidence = nativePose.confidence
            };
        }
        
        private void ChangeState(SLAMState newState)
        {
            if (currentState != newState)
            {
                var previousState = currentState;
                currentState = newState;
                
                Debug.Log($"SLAM state changed: {previousState} -> {newState}");
                OnSLAMStateChanged?.Invoke(newState);
            }
        }
        
        void Update()
        {
            if (isInitialized && nativeSLAMHandle != IntPtr.Zero)
            {
                // Periodically update tracking stats
                if (Time.frameCount % 30 == 0) // Every 30 frames (~0.5 seconds at 60fps)
                {
                    GetTrackingStats();
                }
                
                // Monitor system state
                int nativeState = SpatialSLAM_GetState(nativeSLAMHandle);
                var newState = (SLAMState)nativeState;
                
                if (newState != currentState)
                {
                    ChangeState(newState);
                }
            }
        }
        
        void OnDestroy()
        {
            if (nativeSLAMHandle != IntPtr.Zero)
            {
                SpatialSLAM_Destroy(nativeSLAMHandle);
                nativeSLAMHandle = IntPtr.Zero;
                Debug.Log("SLAM system destroyed");
            }
        }
        
        // Debug methods for development
        [System.Diagnostics.Conditional("DEVELOPMENT_BUILD")]
        public void LogDetailedStats()
        {
            if (!isInitialized) return;
            
            var stats = GetTrackingStats();
            var pose = GetCurrentPose();
            
            Debug.Log($"=== SLAM Statistics ===\n" +
                     $"State: {currentState}\n" +
                     $"Pose: {pose.position} | {pose.rotation}\n" +
                     $"Confidence: {pose.confidence:F2}\n" +
                     $"Keyframes: {stats.totalKeyframes}\n" +
                     $"Landmarks: {stats.totalLandmarks}\n" +
                     $"Features: {stats.featureCount} ({stats.matchedFeatures} matched)\n" +
                     $"Processing Time: {AverageProcessingTime:F1}ms avg\n" +
                     $"Reprojection Error: {stats.averageReprojectionError:F2}px\n" +
                     $"Quality: {stats.quality}");
        }
    }
}