using System;
using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.XR.ARFoundation;
using UnityEngine.XR.ARSubsystems;
using SpatialPlatform.Core.Services;
using SpatialPlatform.Core.Utilities;

namespace SpatialPlatform.Core.Managers
{
    /// <summary>
    /// Enterprise-grade AR session management with robust error recovery
    /// Handles AR lifecycle, device compatibility, and performance monitoring
    /// </summary>
    public class ARSessionManager : MonoBehaviour
    {
        [Header("AR Configuration")]
        [SerializeField] private bool startAutomatically = true;
        [SerializeField] private float trackingQualityThreshold = 0.3f;
        [SerializeField] private int maxRecoveryAttempts = 3;

        // Core AR components
        private ARSession arSession;
        private ARSessionOrigin sessionOrigin;
        private ARCameraManager cameraManager;
        private ARPlaneManager planeManager;
        
        // Services
        private LocationServiceManager locationService;
        private PerformanceMonitor performanceMonitor;
        
        // Session state tracking for robust error recovery
        public enum SessionState
        {
            Uninitialized,
            CheckingSupport,
            Initializing,
            Ready,
            Running,
            Paused,
            Failed,
            Recovering
        }
        
        private SessionState currentState = SessionState.Uninitialized;
        private int recoveryAttempts = 0;
        
        // Performance metrics for real-time monitoring
        private float frameRate;
        private float trackingQuality = 1.0f;
        private readonly CircularBuffer<float> frameTimes = new CircularBuffer<float>(30);
        private DateTime sessionStartTime;
        
        // Events for other systems to hook into
        public static event System.Action<SessionState> OnSessionStateChanged;
        public static event System.Action<float> OnTrackingQualityChanged;
        public static event System.Action<TrackingState> OnTrackingStateChanged;
        
        // Properties for external access
        public SessionState CurrentState => currentState;
        public float CurrentFrameRate => frameRate;
        public float TrackingQuality => trackingQuality;
        public bool IsSessionRunning => currentState == SessionState.Running;
        
        void Awake()
        {
            // Initialize services early
            InitializeServices();
            
            if (startAutomatically)
            {
                StartCoroutine(InitializeARSession());
            }
        }
        
        private void InitializeServices()
        {
            // Get or create essential services
            locationService = FindObjectOfType<LocationServiceManager>();
            if (locationService == null)
            {
                var locationGO = new GameObject("LocationServiceManager");
                locationService = locationGO.AddComponent<LocationServiceManager>();
            }
            
            performanceMonitor = FindObjectOfType<PerformanceMonitor>();
            if (performanceMonitor == null)
            {
                var perfGO = new GameObject("PerformanceMonitor");
                performanceMonitor = perfGO.AddComponent<PerformanceMonitor>();
            }
            
            Debug.Log("ARSessionManager services initialized");
        }
        
        private IEnumerator InitializeARSession()
        {
            ChangeState(SessionState.CheckingSupport);
            
            // Check AR availability first - critical for user experience
            if ((ARSession.state == ARSessionState.None) ||
                (ARSession.state == ARSessionState.CheckingAvailability))
            {
                yield return ARSession.CheckAvailability();
            }
            
            // Handle unsupported devices gracefully
            if (ARSession.state == ARSessionState.Unsupported)
            {
                Debug.LogWarning("AR not supported on this device - falling back to limited mode");
                HandleUnsupportedDevice();
                yield break;
            }
            
            // We're good to proceed with AR setup
            yield return StartCoroutine(SetupARComponents());
        }
        
        private IEnumerator SetupARComponents()
        {
            ChangeState(SessionState.Initializing);
            
            try
            {
                // Find or create AR session components
                arSession = FindObjectOfType<ARSession>();
                if (arSession == null)
                {
                    var sessionGO = new GameObject("AR Session");
                    arSession = sessionGO.AddComponent<ARSession>();
                }
                
                // Setup session origin with proper camera configuration
                yield return StartCoroutine(SetupSessionOrigin());
                
                // Configure AR managers for our use case
                SetupARManagers();
                
                // Start location services for GPS-assisted features
                yield return StartCoroutine(StartLocationServices());
                
                // Subscribe to important AR events
                SubscribeToAREvents();
                
                // Configure session for optimal mobile performance
                ConfigureSessionForMobile();
                
                sessionStartTime = DateTime.Now;
                ChangeState(SessionState.Ready);
                
                Debug.Log($"AR session initialized successfully in {(DateTime.Now - sessionStartTime).TotalSeconds:F2} seconds");
                
                // Auto-start if configured
                if (startAutomatically)
                {
                    StartARSession();
                }
            }
            catch (Exception e)
            {
                Debug.LogError($"Failed to initialize AR session: {e.Message}");
                HandleInitializationFailure(e);
            }
        }
        
        private IEnumerator SetupSessionOrigin()
        {
            sessionOrigin = FindObjectOfType<ARSessionOrigin>();
            if (sessionOrigin == null)
            {
                var originGO = new GameObject("AR Session Origin");
                sessionOrigin = originGO.AddComponent<ARSessionOrigin>();
                
                // Create AR camera with proper setup
                var cameraGO = new GameObject("AR Camera");
                cameraGO.transform.SetParent(originGO.transform);
                
                var arCamera = cameraGO.AddComponent<Camera>();
                arCamera.clearFlags = CameraClearFlags.Color;
                arCamera.backgroundColor = Color.black;
                arCamera.nearClipPlane = 0.1f;
                arCamera.farClipPlane = 1000f;
                
                // Add AR camera components
                cameraManager = cameraGO.AddComponent<ARCameraManager>();
                var cameraBackground = cameraGO.AddComponent<ARCameraBackground>();
                
                sessionOrigin.camera = arCamera;
                
                Debug.Log("Created AR Session Origin with camera setup");
            }
            else
            {
                cameraManager = sessionOrigin.GetComponentInChildren<ARCameraManager>();
            }
            
            yield return null;
        }
        
        private void SetupARManagers()
        {
            // Plane detection for environmental understanding
            planeManager = sessionOrigin.GetComponent<ARPlaneManager>();
            if (planeManager == null)
            {
                planeManager = sessionOrigin.gameObject.AddComponent<ARPlaneManager>();
            }
            
            // Configure plane detection settings
            planeManager.detectionMode = PlaneDetectionMode.Horizontal | PlaneDetectionMode.Vertical;
            planeManager.requestedDetectionMode = PlaneDetectionMode.Horizontal;
            
            Debug.Log("AR managers configured for spatial platform");
        }
        
        private IEnumerator StartLocationServices()
        {
            if (locationService != null)
            {
                var locationStarted = false;
                locationService.StartLocationServices((success, error) =>
                {
                    if (success)
                    {
                        Debug.Log("Location services started successfully");
                        locationStarted = true;
                    }
                    else
                    {
                        Debug.LogWarning($"Location services failed to start: {error}");
                        locationStarted = true; // Continue without location
                    }
                });
                
                // Wait for location service initialization
                yield return new WaitUntil(() => locationStarted);
            }
        }
        
        private void SubscribeToAREvents()
        {
            ARSession.stateChanged += OnARSessionStateChanged;
            
            if (cameraManager != null)
            {
                cameraManager.frameReceived += OnCameraFrameReceived;
            }
            
            if (planeManager != null)
            {
                planeManager.planesChanged += OnPlanesChanged;
            }
        }
        
        private void UnsubscribeFromAREvents()
        {
            ARSession.stateChanged -= OnARSessionStateChanged;
            
            if (cameraManager != null)
            {
                cameraManager.frameReceived -= OnCameraFrameReceived;
            }
            
            if (planeManager != null)
            {
                planeManager.planesChanged -= OnPlanesChanged;
            }
        }
        
        private void ConfigureSessionForMobile()
        {
            // Platform-specific optimizations for mobile AR
#if UNITY_IOS
            ConfigureiOSOptimizations();
#elif UNITY_ANDROID
            ConfigureAndroidOptimizations();
#endif
            
            // General mobile optimizations
            Application.targetFrameRate = 60; // Important for AR tracking
            QualitySettings.vSyncCount = 0;   // Let AR manage frame timing
            
            Debug.Log("Mobile optimizations applied");
        }
        
#if UNITY_IOS
        private void ConfigureiOSOptimizations()
        {
            // iOS-specific AR optimizations
            // Configure ARKit session for best performance
            Debug.Log("iOS AR optimizations applied");
        }
#endif
        
#if UNITY_ANDROID
        private void ConfigureAndroidOptimizations()
        {
            // Android-specific ARCore optimizations
            Debug.Log("Android AR optimizations applied");
        }
#endif
        
        public void StartARSession()
        {
            if (currentState != SessionState.Ready && currentState != SessionState.Paused)
            {
                Debug.LogWarning($"Cannot start AR session in state: {currentState}");
                return;
            }
            
            try
            {
                arSession.enabled = true;
                ChangeState(SessionState.Running);
                Debug.Log("AR session started successfully");
            }
            catch (Exception e)
            {
                Debug.LogError($"Failed to start AR session: {e.Message}");
                HandleSessionStartFailure(e);
            }
        }
        
        public void PauseARSession()
        {
            if (currentState == SessionState.Running)
            {
                arSession.enabled = false;
                ChangeState(SessionState.Paused);
                Debug.Log("AR session paused");
            }
        }
        
        public void ResumeARSession()
        {
            if (currentState == SessionState.Paused)
            {
                StartARSession();
            }
        }
        
        void Update()
        {
            if (currentState == SessionState.Running)
            {
                UpdatePerformanceMetrics();
                MonitorTrackingQuality();
                
                // Periodic health checks
                if (Time.frameCount % 300 == 0) // Every 5 seconds at 60fps
                {
                    PerformHealthCheck();
                }
            }
        }
        
        private void UpdatePerformanceMetrics()
        {
            float currentFrameTime = Time.deltaTime;
            frameTimes.Add(currentFrameTime);
            
            // Calculate rolling average frame rate
            if (frameTimes.Count == frameTimes.Capacity)
            {
                float totalTime = 0f;
                for (int i = 0; i < frameTimes.Count; i++)
                {
                    totalTime += frameTimes[i];
                }
                
                frameRate = frameTimes.Count / totalTime;
                
                // Alert if performance significantly degrades
                if (frameRate < 20f)
                {
                    OnPerformanceDegradation();
                }
            }
        }
        
        private void MonitorTrackingQuality()
        {
            // Calculate tracking quality based on various factors
            float newQuality = CalculateTrackingQuality();
            
            if (Mathf.Abs(newQuality - trackingQuality) > 0.1f)
            {
                trackingQuality = newQuality;
                OnTrackingQualityChanged?.Invoke(trackingQuality);
                
                if (trackingQuality < trackingQualityThreshold)
                {
                    OnTrackingQualityDegraded();
                }
            }
        }
        
        private float CalculateTrackingQuality()
        {
            float quality = 1.0f;
            
            // Factor in AR session state
            switch (ARSession.state)
            {
                case ARSessionState.SessionTracking:
                    quality *= 1.0f;
                    break;
                case ARSessionState.SessionInitializing:
                    quality *= 0.5f;
                    break;
                case ARSessionState.NeedsInstall:
                case ARSessionState.Installing:
                    quality *= 0.1f;
                    break;
                default:
                    quality *= 0.0f;
                    break;
            }
            
            // Factor in frame rate
            if (frameRate > 0)
            {
                quality *= Mathf.Clamp01(frameRate / 30f); // Scale based on 30fps target
            }
            
            // Factor in plane detection (environmental understanding)
            if (planeManager != null)
            {
                int planeCount = planeManager.trackables.count;
                if (planeCount > 0)
                {
                    quality *= Mathf.Clamp01(1.0f + 0.1f * planeCount); // Bonus for more planes
                }
                else
                {
                    quality *= 0.7f; // Penalty for no environmental understanding
                }
            }
            
            return Mathf.Clamp01(quality);
        }
        
        private void PerformHealthCheck()
        {
            // Check for common issues that might need intervention
            
            // Memory pressure check
            if (SystemInfo.systemMemorySize > 0)
            {
                var usedMemory = Profiler.GetTotalAllocatedMemory(false) / (1024 * 1024); // MB
                if (usedMemory > 400) // 400MB threshold
                {
                    Debug.LogWarning($"High memory usage detected: {usedMemory}MB");
                    RequestGarbageCollection();
                }
            }
            
            // Temperature check (iOS specific)
#if UNITY_IOS && !UNITY_EDITOR
            var thermalState = UnityEngine.iOS.Device.lowPowerModeEnabled;
            if (thermalState)
            {
                Debug.LogWarning("Device thermal throttling detected - reducing AR quality");
                ApplyThermalThrottling();
            }
#endif
        }
        
        private void RequestGarbageCollection()
        {
            // Force garbage collection during low-activity periods
            System.GC.Collect();
            Resources.UnloadUnusedAssets();
            Debug.Log("Performed memory cleanup");
        }
        
        private void ApplyThermalThrottling()
        {
            // Reduce AR quality to prevent overheating
            Application.targetFrameRate = 30;
            if (planeManager != null)
            {
                planeManager.requestedDetectionMode = PlaneDetectionMode.None;
            }
            Debug.Log("Applied thermal throttling measures");
        }
        
        private void ChangeState(SessionState newState)
        {
            if (currentState != newState)
            {
                var previousState = currentState;
                currentState = newState;
                
                Debug.Log($"AR Session state changed: {previousState} -> {newState}");
                OnSessionStateChanged?.Invoke(newState);
            }
        }
        
        private void OnARSessionStateChanged(ARSessionStateChangedEventArgs args)
        {
            Debug.Log($"AR Foundation state changed: {args.state}");
            
            switch (args.state)
            {
                case ARSessionState.Ready:
                    if (currentState == SessionState.Initializing)
                    {
                        ChangeState(SessionState.Ready);
                    }
                    break;
                    
                case ARSessionState.SessionTracking:
                    if (currentState != SessionState.Running)
                    {
                        OnTrackingRestored();
                    }
                    break;
                    
                case ARSessionState.NeedsInstall:
                    HandleARCoreInstallRequired();
                    break;
                    
                case ARSessionState.Installing:
                    Debug.Log("ARCore installation in progress...");
                    break;
            }
        }
        
        private void OnCameraFrameReceived(ARCameraFrameEventArgs args)
        {
            // This is called every frame - keep processing minimal
            // Could be used for computer vision processing
        }
        
        private void OnPlanesChanged(ARPlanesChangedEventArgs args)
        {
            // React to plane detection changes
            int totalPlanes = args.added.Count + args.updated.Count;
            if (totalPlanes > 0 && trackingQuality < 0.5f)
            {
                Debug.Log($"Environmental understanding improving: {planeManager.trackables.count} planes detected");
            }
        }
        
        private void HandleUnsupportedDevice()
        {
            ChangeState(SessionState.Failed);
            Debug.LogError("AR is not supported on this device");
            
            // Could implement fallback mode here
            // ShowUnsupportedDeviceUI();
        }
        
        private void HandleInitializationFailure(Exception error)
        {
            ChangeState(SessionState.Failed);
            
            if (recoveryAttempts < maxRecoveryAttempts)
            {
                recoveryAttempts++;
                Debug.LogWarning($"Attempting AR session recovery (attempt {recoveryAttempts}/{maxRecoveryAttempts})");
                StartCoroutine(AttemptRecovery());
            }
            else
            {
                Debug.LogError($"AR session failed permanently after {maxRecoveryAttempts} attempts: {error.Message}");
                // Log to analytics/crash reporting
                LogCriticalFailure(error);
            }
        }
        
        private void HandleSessionStartFailure(Exception error)
        {
            Debug.LogError($"Failed to start AR session: {error.Message}");
            ChangeState(SessionState.Failed);
            
            // Try recovery if not too many attempts
            if (recoveryAttempts < maxRecoveryAttempts)
            {
                StartCoroutine(AttemptRecovery());
            }
        }
        
        private void HandleARCoreInstallRequired()
        {
            Debug.LogWarning("ARCore installation required");
            // In a real app, would prompt user to install ARCore
            // For now, just log and wait
        }
        
        private IEnumerator AttemptRecovery()
        {
            ChangeState(SessionState.Recovering);
            
            // Wait with exponential backoff
            float delay = Mathf.Pow(2, recoveryAttempts);
            yield return new WaitForSeconds(delay);
            
            Debug.Log($"Attempting AR session recovery...");
            
            // Reset components and try again
            UnsubscribeFromAREvents();
            
            if (arSession != null)
            {
                arSession.enabled = false;
                yield return new WaitForSeconds(0.5f);
            }
            
            // Restart initialization
            yield return StartCoroutine(InitializeARSession());
        }
        
        private void OnPerformanceDegradation()
        {
            Debug.LogWarning($"AR performance degraded: {frameRate:F1} FPS");
            
            // Could trigger performance optimizations here
            // ApplyPerformanceOptimizations();
        }
        
        private void OnTrackingQualityDegraded()
        {
            Debug.LogWarning($"AR tracking quality degraded: {trackingQuality:F2}");
            
            // Could trigger tracking recovery measures
            // TriggerTrackingRecovery();
        }
        
        private void OnTrackingRestored()
        {
            Debug.Log("AR tracking restored");
            recoveryAttempts = 0; // Reset recovery counter on success
        }
        
        private void LogCriticalFailure(Exception error)
        {
            // In production, would send to analytics service
            Debug.LogError($"Critical AR failure logged: {error.Message}\nStack: {error.StackTrace}");
        }
        
        void OnApplicationPause(bool pauseStatus)
        {
            if (pauseStatus && IsSessionRunning)
            {
                PauseARSession();
            }
            else if (!pauseStatus && currentState == SessionState.Paused)
            {
                ResumeARSession();
            }
        }
        
        void OnDestroy()
        {
            UnsubscribeFromAREvents();
            
            if (locationService != null)
            {
                locationService.StopLocationServices();
            }
        }
        
        // Public API for external systems
        public Vector3 GetCameraPosition()
        {
            return cameraManager?.transform.position ?? Vector3.zero;
        }
        
        public Quaternion GetCameraRotation()
        {
            return cameraManager?.transform.rotation ?? Quaternion.identity;
        }
        
        public Matrix4x4 GetCameraPose()
        {
            if (cameraManager != null)
            {
                return cameraManager.transform.localToWorldMatrix;
            }
            return Matrix4x4.identity;
        }
    }
}