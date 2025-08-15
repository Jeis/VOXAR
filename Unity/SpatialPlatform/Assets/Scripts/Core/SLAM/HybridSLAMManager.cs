/**
 * Spatial Platform - Hybrid SLAM Manager
 * Manages both native plugin and REST API backend SLAM implementations
 * Automatically selects optimal implementation based on platform and availability
 */

using System;
using UnityEngine;
using SpatialPlatform.Core.Services;

namespace SpatialPlatform.Core.SLAM
{
    public class HybridSLAMManager : MonoBehaviour
    {
        [Header("Implementation Selection")]
        [SerializeField] private SLAMImplementation preferredImplementation = SLAMImplementation.Auto;
        [SerializeField] private string backendUrl = "http://localhost:8080";
        [SerializeField] private bool fallbackToAlternative = true;

        [Header("Configuration")]
        [SerializeField] private bool enableDebugLogging = true;
        [SerializeField] private bool autoInitialize = true;
        [SerializeField] private string defaultMapId = "default_map";

        public enum SLAMImplementation
        {
            Auto,           // Automatically select best available
            NativePlugin,   // Use native C++ plugin (iOS/Android)
            RESTBackend,    // Use backend REST service
            Hybrid          // Use both for comparison/redundancy
        }

        // Component references
        private SLAMManager nativeManager;
        private SpatialSLAMClient restClient;
        private SLAMBridgeManager bridgeManager;

        // State
        private SLAMImplementation activeImplementation;
        private bool isInitialized = false;
        private bool isTrackingActive = false;

        // Events (unified interface)
        public event Action<Vector3, Quaternion, float> OnPoseUpdated;
        public event Action<string> OnTrackingStateChanged;
        public event Action<string> OnError;
        public event Action OnReady;

        // Properties
        public bool IsInitialized => isInitialized;
        public bool IsTrackingActive => isTrackingActive;
        public SLAMImplementation ActiveImplementation => activeImplementation;

        private void Start()
        {
            if (autoInitialize)
            {
                InitializeOptimalImplementation();
            }
        }

        #region Initialization

        public void InitializeOptimalImplementation()
        {
            Log("Initializing optimal SLAM implementation...");

            switch (preferredImplementation)
            {
                case SLAMImplementation.Auto:
                    InitializeAutoSelection();
                    break;
                case SLAMImplementation.NativePlugin:
                    InitializeNativePlugin();
                    break;
                case SLAMImplementation.RESTBackend:
                    InitializeRESTBackend();
                    break;
                case SLAMImplementation.Hybrid:
                    InitializeHybridMode();
                    break;
            }
        }

        private void InitializeAutoSelection()
        {
            // Platform-specific selection logic
            if (Application.platform == RuntimePlatform.IPhonePlayer || 
                Application.platform == RuntimePlatform.Android)
            {
                // Mobile platforms prefer native plugin for performance
                if (InitializeNativePlugin())
                {
                    activeImplementation = SLAMImplementation.NativePlugin;
                    return;
                }
            }

            // Fallback to REST backend for all platforms
            if (InitializeRESTBackend())
            {
                activeImplementation = SLAMImplementation.RESTBackend;
                return;
            }

            LogError("Failed to initialize any SLAM implementation");
        }

        private bool InitializeNativePlugin()
        {
            try
            {
                Log("Attempting to initialize native SLAM plugin...");

                // Check if native plugin is available
                nativeManager = GetComponent<SLAMManager>();
                if (nativeManager == null)
                {
                    nativeManager = gameObject.AddComponent<SLAMManager>();
                }

                // Subscribe to native events
                SLAMManager.OnSLAMStateChanged += OnNativeSLAMStateChanged;
                SLAMManager.OnPoseUpdated += OnNativePoseUpdated;
                SLAMManager.OnSLAMError += OnNativeSLAMError;

                // Wait for initialization (native manager initializes in Start())
                StartCoroutine(WaitForNativeInitialization());

                Log("Native SLAM plugin initialized");
                return true;
            }
            catch (Exception e)
            {
                LogWarning($"Native plugin initialization failed: {e.Message}");
                return false;
            }
        }

        private bool InitializeRESTBackend()
        {
            try
            {
                Log("Attempting to initialize REST backend SLAM...");

                // Setup REST client
                restClient = GetComponent<SpatialSLAMClient>();
                if (restClient == null)
                {
                    restClient = gameObject.AddComponent<SpatialSLAMClient>();
                }

                // Configure backend URL
                var clientConfig = restClient.GetType().GetField("backendUrl", 
                    System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance);
                if (clientConfig != null)
                {
                    clientConfig.SetValue(restClient, backendUrl);
                }

                // Setup bridge manager
                bridgeManager = GetComponent<SLAMBridgeManager>();
                if (bridgeManager == null)
                {
                    bridgeManager = gameObject.AddComponent<SLAMBridgeManager>();
                }

                // Subscribe to REST backend events
                restClient.OnPoseReceived += OnRESTClientPoseReceived;
                restClient.OnTrackingStateChanged += OnRESTClientTrackingStateChanged;
                restClient.OnError += OnRESTClientError;

                bridgeManager.OnSLAMReady += OnBridgeManagerReady;
                bridgeManager.OnPoseUpdated += OnBridgeManagerPoseUpdated;

                Log("REST backend SLAM initialized");
                return true;
            }
            catch (Exception e)
            {
                LogWarning($"REST backend initialization failed: {e.Message}");
                return false;
            }
        }

        private void InitializeHybridMode()
        {
            Log("Initializing hybrid SLAM mode...");

            bool nativeSuccess = InitializeNativePlugin();
            bool restSuccess = InitializeRESTBackend();

            if (nativeSuccess && restSuccess)
            {
                activeImplementation = SLAMImplementation.Hybrid;
                Log("Hybrid mode initialized successfully");
            }
            else if (nativeSuccess)
            {
                activeImplementation = SLAMImplementation.NativePlugin;
                Log("Hybrid mode fallback to native plugin");
            }
            else if (restSuccess)
            {
                activeImplementation = SLAMImplementation.RESTBackend;
                Log("Hybrid mode fallback to REST backend");
            }
            else
            {
                LogError("Hybrid mode initialization failed - no implementations available");
            }
        }

        private System.Collections.IEnumerator WaitForNativeInitialization()
        {
            float timeout = 5.0f;
            float elapsed = 0f;

            while (elapsed < timeout && !nativeManager.IsInitialized)
            {
                yield return new WaitForSeconds(0.1f);
                elapsed += 0.1f;
            }

            if (nativeManager.IsInitialized)
            {
                isInitialized = true;
                OnReady?.Invoke();
                Log("Native SLAM initialization completed");
            }
            else
            {
                LogError("Native SLAM initialization timeout");
                if (fallbackToAlternative)
                {
                    TryFallbackImplementation();
                }
            }
        }

        #endregion

        #region Public API

        public void StartTracking(string mapId = null)
        {
            if (!isInitialized)
            {
                LogError("SLAM not initialized. Cannot start tracking.");
                return;
            }

            string targetMapId = mapId ?? defaultMapId;

            switch (activeImplementation)
            {
                case SLAMImplementation.NativePlugin:
                    StartNativeTracking(targetMapId);
                    break;
                case SLAMImplementation.RESTBackend:
                    StartRESTTracking(targetMapId);
                    break;
                case SLAMImplementation.Hybrid:
                    StartHybridTracking(targetMapId);
                    break;
            }

            isTrackingActive = true;
        }

        public void StopTracking()
        {
            if (!isTrackingActive)
            {
                LogWarning("Tracking not active");
                return;
            }

            switch (activeImplementation)
            {
                case SLAMImplementation.NativePlugin:
                    nativeManager?.StopTracking();
                    break;
                case SLAMImplementation.RESTBackend:
                    restClient?.StopTracking();
                    break;
                case SLAMImplementation.Hybrid:
                    nativeManager?.StopTracking();
                    restClient?.StopTracking();
                    break;
            }

            isTrackingActive = false;
            OnTrackingStateChanged?.Invoke("stopped");
        }

        public void SaveMap(string mapId)
        {
            if (!isInitialized)
            {
                LogError("SLAM not initialized. Cannot save map.");
                return;
            }

            switch (activeImplementation)
            {
                case SLAMImplementation.NativePlugin:
                    SaveNativeMap(mapId);
                    break;
                case SLAMImplementation.RESTBackend:
                    restClient?.SaveMap(mapId);
                    break;
                case SLAMImplementation.Hybrid:
                    SaveNativeMap(mapId);
                    restClient?.SaveMap(mapId);
                    break;
            }

            Log($"Map save initiated: {mapId}");
        }

        public void LoadMap(string mapId)
        {
            if (!isInitialized)
            {
                LogError("SLAM not initialized. Cannot load map.");
                return;
            }

            switch (activeImplementation)
            {
                case SLAMImplementation.NativePlugin:
                    LoadNativeMap(mapId);
                    break;
                case SLAMImplementation.RESTBackend:
                    restClient?.LoadMap(mapId);
                    break;
                case SLAMImplementation.Hybrid:
                    LoadNativeMap(mapId);
                    restClient?.LoadMap(mapId);
                    break;
            }

            Log($"Map load initiated: {mapId}");
        }

        public string GetSystemStatus()
        {
            if (!isInitialized) return "Not initialized";

            switch (activeImplementation)
            {
                case SLAMImplementation.NativePlugin:
                    return $"Native: {nativeManager?.CurrentState}";
                case SLAMImplementation.RESTBackend:
                    return bridgeManager?.GetTrackingStatus() ?? "REST: Unknown";
                case SLAMImplementation.Hybrid:
                    return $"Native: {nativeManager?.CurrentState}, REST: {bridgeManager?.GetTrackingStatus()}";
                default:
                    return "Unknown implementation";
            }
        }

        #endregion

        #region Implementation-Specific Methods

        private void StartNativeTracking(string mapId)
        {
            if (nativeManager != null)
            {
                // Load map if specified
                if (!string.IsNullOrEmpty(mapId))
                {
                    LoadNativeMap(mapId);
                }

                nativeManager.StartTracking();
            }
        }

        private void StartRESTTracking(string mapId)
        {
            if (bridgeManager != null)
            {
                bridgeManager.StartSLAMTracking(mapId);
            }
        }

        private void StartHybridTracking(string mapId)
        {
            StartNativeTracking(mapId);
            StartRESTTracking(mapId);
        }

        private void SaveNativeMap(string mapId)
        {
            if (nativeManager != null)
            {
                byte[] mapData;
                var result = nativeManager.SaveMap(out mapData);
                
                if (result == SLAMManager.SLAMResult.Success && mapData != null)
                {
                    // Save to persistent storage
                    string mapPath = System.IO.Path.Combine(Application.persistentDataPath, $"{mapId}.slam");
                    System.IO.File.WriteAllBytes(mapPath, mapData);
                    Log($"Native map saved to: {mapPath}");
                }
                else
                {
                    LogError($"Failed to save native map: {result}");
                }
            }
        }

        private void LoadNativeMap(string mapId)
        {
            if (nativeManager != null)
            {
                string mapPath = System.IO.Path.Combine(Application.persistentDataPath, $"{mapId}.slam");
                
                if (System.IO.File.Exists(mapPath))
                {
                    byte[] mapData = System.IO.File.ReadAllBytes(mapPath);
                    var result = nativeManager.LoadMap(mapData);
                    
                    if (result == SLAMManager.SLAMResult.Success)
                    {
                        Log($"Native map loaded from: {mapPath}");
                    }
                    else
                    {
                        LogError($"Failed to load native map: {result}");
                    }
                }
                else
                {
                    LogWarning($"Native map file not found: {mapPath}");
                }
            }
        }

        private void TryFallbackImplementation()
        {
            Log("Attempting fallback to alternative implementation...");

            if (activeImplementation == SLAMImplementation.NativePlugin)
            {
                if (InitializeRESTBackend())
                {
                    activeImplementation = SLAMImplementation.RESTBackend;
                    isInitialized = true;
                    OnReady?.Invoke();
                    Log("Fallback to REST backend successful");
                    return;
                }
            }
            else if (activeImplementation == SLAMImplementation.RESTBackend)
            {
                if (InitializeNativePlugin())
                {
                    activeImplementation = SLAMImplementation.NativePlugin;
                    // Native initialization is async, handled in coroutine
                    Log("Fallback to native plugin initiated");
                    return;
                }
            }

            LogError("All fallback implementations failed");
        }

        #endregion

        #region Event Handlers

        // Native plugin events
        private void OnNativeSLAMStateChanged(SLAMManager.SLAMState state)
        {
            Log($"Native SLAM state: {state}");
            OnTrackingStateChanged?.Invoke(state.ToString());

            if (state == SLAMManager.SLAMState.Ready && !isInitialized)
            {
                isInitialized = true;
                OnReady?.Invoke();
            }
        }

        private void OnNativePoseUpdated(SLAMManager.Pose pose)
        {
            OnPoseUpdated?.Invoke(pose.position, pose.rotation, pose.confidence);
        }

        private void OnNativeSLAMError(string error)
        {
            LogError($"Native SLAM error: {error}");
            OnError?.Invoke($"Native: {error}");
        }

        // REST client events
        private void OnRESTClientPoseReceived(PoseResponse pose)
        {
            var position = new Vector3(pose.position[0], pose.position[1], pose.position[2]);
            var rotation = new Quaternion(pose.rotation[1], pose.rotation[2], pose.rotation[3], pose.rotation[0]);
            OnPoseUpdated?.Invoke(position, rotation, pose.confidence);
        }

        private void OnRESTClientTrackingStateChanged(string state)
        {
            Log($"REST client tracking state: {state}");
            OnTrackingStateChanged?.Invoke($"REST: {state}");

            if (state == "tracking" && !isInitialized)
            {
                isInitialized = true;
                OnReady?.Invoke();
            }
        }

        private void OnRESTClientError(string error)
        {
            LogError($"REST client error: {error}");
            OnError?.Invoke($"REST: {error}");
        }

        // Bridge manager events
        private void OnBridgeManagerReady()
        {
            Log("Bridge manager ready");
            if (!isInitialized)
            {
                isInitialized = true;
                OnReady?.Invoke();
            }
        }

        private void OnBridgeManagerPoseUpdated(Vector3 position, Quaternion rotation, float confidence)
        {
            OnPoseUpdated?.Invoke(position, rotation, confidence);
        }

        #endregion

        #region Utility

        private void Log(string message)
        {
            if (enableDebugLogging)
            {
                Debug.Log($"[HybridSLAM] {message}");
            }
        }

        private void LogWarning(string message)
        {
            Debug.LogWarning($"[HybridSLAM] {message}");
        }

        private void LogError(string message)
        {
            Debug.LogError($"[HybridSLAM] {message}");
            OnError?.Invoke(message);
        }

        #endregion

        #region Unity Lifecycle

        private void OnDestroy()
        {
            // Unsubscribe from events
            if (nativeManager != null)
            {
                SLAMManager.OnSLAMStateChanged -= OnNativeSLAMStateChanged;
                SLAMManager.OnPoseUpdated -= OnNativePoseUpdated;
                SLAMManager.OnSLAMError -= OnNativeSLAMError;
            }

            if (restClient != null)
            {
                restClient.OnPoseReceived -= OnRESTClientPoseReceived;
                restClient.OnTrackingStateChanged -= OnRESTClientTrackingStateChanged;
                restClient.OnError -= OnRESTClientError;
            }

            if (bridgeManager != null)
            {
                bridgeManager.OnSLAMReady -= OnBridgeManagerReady;
                bridgeManager.OnPoseUpdated -= OnBridgeManagerPoseUpdated;
            }

            if (isTrackingActive)
            {
                StopTracking();
            }
        }

        #endregion
    }
}