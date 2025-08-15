using System;
using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Profiling;
using SpatialPlatform.Core.Utilities;

namespace SpatialPlatform.Core.Services
{
    /// <summary>
    /// Enterprise-grade performance monitoring for AR applications
    /// Tracks frame rate, memory usage, thermal state, and battery level
    /// Provides automatic quality adjustments and performance alerts
    /// </summary>
    public class PerformanceMonitor : MonoBehaviour
    {
        [Header("Performance Thresholds")]
        [SerializeField] private float targetFrameRate = 60f;
        [SerializeField] private float minimumFrameRate = 30f;
        [SerializeField] private float memoryWarningThreshold = 400f; // MB
        [SerializeField] private float memoryCriticalThreshold = 500f; // MB
        [SerializeField] private float batteryLowThreshold = 0.2f; // 20%
        
        [Header("Monitoring Settings")]
        [SerializeField] private float updateInterval = 1f;
        [SerializeField] private bool enableAutomaticQualityAdjustment = true;
        [SerializeField] private bool logPerformanceData = true;
        
        // Performance data buffers
        private readonly PerformanceBuffer frameTimeBuffer = new PerformanceBuffer(60);
        private readonly CircularBuffer<float> memoryUsageBuffer = new CircularBuffer<float>(30);
        private readonly CircularBuffer<float> batteryLevelBuffer = new CircularBuffer<float>(60);
        
        // Current performance state
        private PerformanceLevel currentPerformanceLevel = PerformanceLevel.High;
        private ThermalState currentThermalState = ThermalState.Normal;
        private bool isInLowPowerMode = false;
        private float lastMemoryUsage;
        private float lastBatteryLevel = 1f;
        
        // Performance tracking
        private float lastUpdateTime;
        private int frameCount;
        private float accumulatedFrameTime;
        private bool performanceWarningActive = false;
        
        public enum PerformanceLevel
        {
            Critical,  // Bare minimum settings
            Low,       // Reduced quality for stability
            Medium,    // Balanced performance
            High,      // Full quality
            Ultra      // Maximum quality (high-end devices only)
        }
        
        public enum ThermalState
        {
            Normal,
            Fair,
            Serious,
            Critical
        }
        
        // Events for other systems to react to performance changes
        public static event Action<PerformanceLevel> OnPerformanceLevelChanged;
        public static event Action<float> OnFrameRateChanged;
        public static event Action<float> OnMemoryPressureChanged;
        public static event Action<ThermalState> OnThermalStateChanged;
        public static event Action<bool> OnLowPowerModeChanged;
        
        // Performance metrics
        public struct PerformanceMetrics
        {
            public float currentFPS;
            public float averageFPS;
            public float minimumFPS;
            public float maximumFPS;
            public float frameTimeStdDev;
            public float memoryUsageMB;
            public float batteryLevel;
            public ThermalState thermalState;
            public PerformanceLevel performanceLevel;
            public bool isStable;
        }
        
        // Properties
        public PerformanceLevel CurrentPerformanceLevel => currentPerformanceLevel;
        public ThermalState CurrentThermalState => currentThermalState;
        public bool IsInLowPowerMode => isInLowPowerMode;
        public float CurrentFPS => frameTimeBuffer.IsEmpty ? 0f : frameTimeBuffer.GetAverageFPS();
        public float AverageMemoryUsage => memoryUsageBuffer.IsEmpty ? 0f : (float)memoryUsageBuffer.Average();
        public bool IsPerformanceStable => frameTimeBuffer.IsPerformanceStable();
        
        void Start()
        {
            // Initialize performance monitoring
            StartCoroutine(PerformanceUpdateLoop());
            
            // Set initial target frame rate
            Application.targetFrameRate = (int)targetFrameRate;
            QualitySettings.vSyncCount = 0; // Disable VSync for AR
            
            // Check initial device capabilities
            AssessDeviceCapabilities();
            
            Debug.Log($"Performance Monitor initialized - Target FPS: {targetFrameRate}");
        }
        
        private void AssessDeviceCapabilities()
        {
            // Determine baseline performance level based on device specs
            int systemMemoryMB = SystemInfo.systemMemorySize;
            int gpuMemoryMB = SystemInfo.graphicsMemorySize;
            string deviceModel = SystemInfo.deviceModel;
            
            Debug.Log($"Device Assessment: {deviceModel}, RAM: {systemMemoryMB}MB, VRAM: {gpuMemoryMB}MB");
            
            // Set initial performance level based on hardware
            if (systemMemoryMB >= 6000 && gpuMemoryMB >= 2000) // High-end device
            {
                SetPerformanceLevel(PerformanceLevel.High);
            }
            else if (systemMemoryMB >= 4000 && gpuMemoryMB >= 1000) // Mid-range device
            {
                SetPerformanceLevel(PerformanceLevel.Medium);
            }
            else if (systemMemoryMB >= 2000) // Low-end device
            {
                SetPerformanceLevel(PerformanceLevel.Low);
            }
            else // Very limited device
            {
                SetPerformanceLevel(PerformanceLevel.Critical);
                Debug.LogWarning("Device has very limited resources - performance may be poor");
            }
            
            // Check for specific device optimizations
            ApplyDeviceSpecificOptimizations();
        }
        
        private void ApplyDeviceSpecificOptimizations()
        {
            // iOS specific optimizations
#if UNITY_IOS && !UNITY_EDITOR
            // Check for specific iOS device models that need special handling
            if (SystemInfo.deviceModel.Contains("iPhone"))
            {
                // Older iPhones might need more aggressive optimization
                var deviceName = UnityEngine.iOS.Device.generation;
                Debug.Log($"iOS Device: {deviceName}");
                
                // Enable iOS-specific power management
                StartCoroutine(MonitorIOSThermalState());
            }
#endif
            
            // Android specific optimizations
#if UNITY_ANDROID && !UNITY_EDITOR
            // Check Android device characteristics
            var androidJavaClass = new AndroidJavaClass("com.unity3d.player.UnityPlayer");
            var context = androidJavaClass.GetStatic<AndroidJavaObject>("currentActivity");
            
            // Monitor Android thermal throttling
            StartCoroutine(MonitorAndroidThermalState());
#endif
        }
        
        void Update()
        {
            // Track frame timing every frame for accuracy
            frameTimeBuffer.Add(Time.deltaTime);
            
            // Accumulate frame data for periodic updates
            frameCount++;
            accumulatedFrameTime += Time.deltaTime;
        }
        
        private IEnumerator PerformanceUpdateLoop()
        {
            while (true)
            {
                yield return new WaitForSeconds(updateInterval);
                UpdatePerformanceMetrics();
            }
        }
        
        private void UpdatePerformanceMetrics()
        {
            // Calculate current frame rate
            float currentFPS = frameCount / accumulatedFrameTime;
            frameCount = 0;
            accumulatedFrameTime = 0f;
            
            // Update memory usage
            UpdateMemoryMetrics();
            
            // Update battery level
            UpdateBatteryMetrics();
            
            // Check thermal state
            UpdateThermalState();
            
            // Analyze performance and adjust if needed
            AnalyzePerformance(currentFPS);
            
            // Log performance data if enabled
            if (logPerformanceData)
            {
                LogPerformanceData();
            }
            
            lastUpdateTime = Time.time;
        }
        
        private void UpdateMemoryMetrics()
        {
            // Get current memory usage
            long allocatedMemoryBytes = Profiler.GetTotalAllocatedMemory(false);
            float memoryUsageMB = allocatedMemoryBytes / (1024f * 1024f);
            
            memoryUsageBuffer.Add(memoryUsageMB);
            lastMemoryUsage = memoryUsageMB;
            
            // Check for memory pressure
            if (memoryUsageMB > memoryCriticalThreshold)
            {
                OnMemoryCritical();
            }
            else if (memoryUsageMB > memoryWarningThreshold)
            {
                OnMemoryWarning();
            }
        }
        
        private void UpdateBatteryMetrics()
        {
            // Get battery level (0.0 to 1.0)
            float batteryLevel = SystemInfo.batteryLevel;
            
            if (batteryLevel >= 0) // -1 means battery level unavailable
            {
                batteryLevelBuffer.Add(batteryLevel);
                
                // Check for low battery
                if (batteryLevel <= batteryLowThreshold && lastBatteryLevel > batteryLowThreshold)
                {
                    OnLowBattery();
                }
                
                lastBatteryLevel = batteryLevel;
            }
        }
        
        private void UpdateThermalState()
        {
            ThermalState newThermalState = ThermalState.Normal;
            
#if UNITY_IOS && !UNITY_EDITOR
            // iOS thermal state monitoring
            var thermalState = UnityEngine.iOS.Device.thermalState;
            switch (thermalState)
            {
                case UnityEngine.iOS.DeviceThermalState.Normal:
                    newThermalState = ThermalState.Normal;
                    break;
                case UnityEngine.iOS.DeviceThermalState.Fair:
                    newThermalState = ThermalState.Fair;
                    break;
                case UnityEngine.iOS.DeviceThermalState.Serious:
                    newThermalState = ThermalState.Serious;
                    break;
                case UnityEngine.iOS.DeviceThermalState.Critical:
                    newThermalState = ThermalState.Critical;
                    break;
            }
            
            // Also check low power mode
            bool lowPowerMode = UnityEngine.iOS.Device.lowPowerModeEnabled;
            if (isInLowPowerMode != lowPowerMode)
            {
                isInLowPowerMode = lowPowerMode;
                OnLowPowerModeChanged?.Invoke(isInLowPowerMode);
                
                if (isInLowPowerMode)
                {
                    Debug.LogWarning("Device entered low power mode - reducing performance");
                    ApplyLowPowerOptimizations();
                }
            }
#endif
            
            if (currentThermalState != newThermalState)
            {
                currentThermalState = newThermalState;
                OnThermalStateChanged?.Invoke(currentThermalState);
                
                // Apply thermal throttling
                ApplyThermalThrottling(newThermalState);
            }
        }
        
        private void AnalyzePerformance(float currentFPS)
        {
            // Check if frame rate has changed significantly
            OnFrameRateChanged?.Invoke(currentFPS);
            
            // Determine if performance adjustment is needed
            if (enableAutomaticQualityAdjustment)
            {
                if (currentFPS < minimumFrameRate && !performanceWarningActive)
                {
                    // Performance is too low, reduce quality
                    ReducePerformanceLevel();
                    performanceWarningActive = true;
                    
                    Debug.LogWarning($"Performance below threshold ({currentFPS:F1} < {minimumFrameRate}) - reducing quality");
                }
                else if (currentFPS > targetFrameRate * 0.9f && performanceWarningActive)
                {
                    // Performance recovered
                    performanceWarningActive = false;
                    Debug.Log($"Performance recovered ({currentFPS:F1} FPS)");
                }
                else if (currentFPS > targetFrameRate && currentPerformanceLevel < PerformanceLevel.High)
                {
                    // Performance is good, we might be able to increase quality
                    if (frameTimeBuffer.IsPerformanceStable())
                    {
                        IncreasePerformanceLevel();
                        Debug.Log($"Stable high performance detected - increasing quality");
                    }
                }
            }
            
            // Check for performance anomalies
            if (frameTimeBuffer.Count >= 30) // Need enough samples
            {
                float stdDev = (float)frameTimeBuffer.StandardDeviation();
                if (stdDev > 0.02f) // High frame time variation
                {
                    Debug.LogWarning($"Frame time instability detected (σ={stdDev:F4}s)");
                }
            }
        }
        
        private void SetPerformanceLevel(PerformanceLevel level)
        {
            if (currentPerformanceLevel == level)
                return;
                
            var previousLevel = currentPerformanceLevel;
            currentPerformanceLevel = level;
            
            ApplyPerformanceSettings(level);
            OnPerformanceLevelChanged?.Invoke(level);
            
            Debug.Log($"Performance level changed: {previousLevel} -> {level}");
        }
        
        private void ReducePerformanceLevel()
        {
            switch (currentPerformanceLevel)
            {
                case PerformanceLevel.Ultra:
                    SetPerformanceLevel(PerformanceLevel.High);
                    break;
                case PerformanceLevel.High:
                    SetPerformanceLevel(PerformanceLevel.Medium);
                    break;
                case PerformanceLevel.Medium:
                    SetPerformanceLevel(PerformanceLevel.Low);
                    break;
                case PerformanceLevel.Low:
                    SetPerformanceLevel(PerformanceLevel.Critical);
                    break;
                case PerformanceLevel.Critical:
                    // Already at minimum, apply emergency optimizations
                    ApplyEmergencyOptimizations();
                    break;
            }
        }
        
        private void IncreasePerformanceLevel()
        {
            switch (currentPerformanceLevel)
            {
                case PerformanceLevel.Critical:
                    SetPerformanceLevel(PerformanceLevel.Low);
                    break;
                case PerformanceLevel.Low:
                    SetPerformanceLevel(PerformanceLevel.Medium);
                    break;
                case PerformanceLevel.Medium:
                    SetPerformanceLevel(PerformanceLevel.High);
                    break;
                case PerformanceLevel.High:
                    // Only go to Ultra on very capable devices
                    if (SystemInfo.systemMemorySize >= 8000 && SystemInfo.graphicsMemorySize >= 4000)
                    {
                        SetPerformanceLevel(PerformanceLevel.Ultra);
                    }
                    break;
                case PerformanceLevel.Ultra:
                    // Already at maximum
                    break;
            }
        }
        
        private void ApplyPerformanceSettings(PerformanceLevel level)
        {
            switch (level)
            {
                case PerformanceLevel.Critical:
                    Application.targetFrameRate = 20;
                    QualitySettings.SetQualityLevel(0); // Fastest quality
                    QualitySettings.pixelLightCount = 1;
                    QualitySettings.anisotropicFiltering = AnisotropicFiltering.Disable;
                    break;
                    
                case PerformanceLevel.Low:
                    Application.targetFrameRate = 30;
                    QualitySettings.SetQualityLevel(1); // Fast quality
                    QualitySettings.pixelLightCount = 2;
                    QualitySettings.anisotropicFiltering = AnisotropicFiltering.Enable;
                    break;
                    
                case PerformanceLevel.Medium:
                    Application.targetFrameRate = 45;
                    QualitySettings.SetQualityLevel(3); // Good quality
                    QualitySettings.pixelLightCount = 4;
                    QualitySettings.shadowDistance = 50f;
                    break;
                    
                case PerformanceLevel.High:
                    Application.targetFrameRate = 60;
                    QualitySettings.SetQualityLevel(4); // Beautiful quality
                    QualitySettings.pixelLightCount = 6;
                    QualitySettings.shadowDistance = 100f;
                    break;
                    
                case PerformanceLevel.Ultra:
                    Application.targetFrameRate = 60;
                    QualitySettings.SetQualityLevel(5); // Fantastic quality
                    QualitySettings.pixelLightCount = 8;
                    QualitySettings.shadowDistance = 150f;
                    QualitySettings.antiAliasing = 4;
                    break;
            }
        }
        
        private void ApplyThermalThrottling(ThermalState thermalState)
        {
            switch (thermalState)
            {
                case ThermalState.Normal:
                    // No throttling needed
                    break;
                    
                case ThermalState.Fair:
                    // Mild throttling
                    if (Application.targetFrameRate > 45)
                    {
                        Application.targetFrameRate = 45;
                        Debug.Log("Applied mild thermal throttling (45 FPS)");
                    }
                    break;
                    
                case ThermalState.Serious:
                    // Significant throttling
                    Application.targetFrameRate = 30;
                    QualitySettings.pixelLightCount = Math.Min(QualitySettings.pixelLightCount, 2);
                    Debug.LogWarning("Applied serious thermal throttling (30 FPS)");
                    break;
                    
                case ThermalState.Critical:
                    // Emergency throttling
                    Application.targetFrameRate = 20;
                    QualitySettings.SetQualityLevel(0);
                    QualitySettings.pixelLightCount = 1;
                    Debug.LogError("Applied critical thermal throttling (20 FPS, lowest quality)");
                    break;
            }
        }
        
        private void ApplyLowPowerOptimizations()
        {
            // Reduce performance when in low power mode
            Application.targetFrameRate = Math.Min(Application.targetFrameRate, 30);
            QualitySettings.pixelLightCount = Math.Min(QualitySettings.pixelLightCount, 2);
            
            // Disable expensive effects
            QualitySettings.softParticles = false;
            QualitySettings.realtimeReflectionProbes = false;
        }
        
        private void ApplyEmergencyOptimizations()
        {
            Debug.LogError("Applying emergency performance optimizations");
            
            // Absolute minimum settings
            Application.targetFrameRate = 15;
            QualitySettings.SetQualityLevel(0);
            QualitySettings.pixelLightCount = 0;
            QualitySettings.shadowDistance = 0f;
            QualitySettings.shadows = ShadowQuality.Disable;
            QualitySettings.softParticles = false;
            
            // Force garbage collection
            System.GC.Collect();
            Resources.UnloadUnusedAssets();
        }
        
        private void OnMemoryWarning()
        {
            Debug.LogWarning($"Memory usage warning: {lastMemoryUsage:F1}MB");
            OnMemoryPressureChanged?.Invoke(lastMemoryUsage);
            
            // Trigger garbage collection
            System.GC.Collect();
        }
        
        private void OnMemoryCritical()
        {
            Debug.LogError($"Critical memory usage: {lastMemoryUsage:F1}MB");
            OnMemoryPressureChanged?.Invoke(lastMemoryUsage);
            
            // Aggressive memory cleanup
            System.GC.Collect();
            Resources.UnloadUnusedAssets();
            
            // Reduce quality to free memory
            if (currentPerformanceLevel > PerformanceLevel.Critical)
            {
                ReducePerformanceLevel();
            }
        }
        
        private void OnLowBattery()
        {
            Debug.LogWarning($"Low battery detected: {lastBatteryLevel:P0}");
            
            // Apply battery saving measures
            ApplyLowPowerOptimizations();
        }
        
        public PerformanceMetrics GetCurrentMetrics()
        {
            return new PerformanceMetrics
            {
                currentFPS = CurrentFPS,
                averageFPS = frameTimeBuffer.IsEmpty ? 0f : frameTimeBuffer.GetAverageFPS(),
                minimumFPS = frameTimeBuffer.IsEmpty ? 0f : 1f / frameTimeBuffer.Max(),
                maximumFPS = frameTimeBuffer.IsEmpty ? 0f : 1f / frameTimeBuffer.Min(),
                frameTimeStdDev = frameTimeBuffer.IsEmpty ? 0f : (float)frameTimeBuffer.StandardDeviation(),
                memoryUsageMB = lastMemoryUsage,
                batteryLevel = lastBatteryLevel,
                thermalState = currentThermalState,
                performanceLevel = currentPerformanceLevel,
                isStable = IsPerformanceStable
            };
        }
        
        private void LogPerformanceData()
        {
            var metrics = GetCurrentMetrics();
            
            Debug.Log($"Performance: {metrics.currentFPS:F1} FPS | " +
                     $"Memory: {metrics.memoryUsageMB:F1}MB | " +
                     $"Battery: {metrics.batteryLevel:P0} | " +
                     $"Thermal: {metrics.thermalState} | " +
                     $"Level: {metrics.performanceLevel} | " +
                     $"Stable: {metrics.isStable}");
        }
        
#if UNITY_IOS && !UNITY_EDITOR
        private IEnumerator MonitorIOSThermalState()
        {
            while (true)
            {
                yield return new WaitForSeconds(5f); // Check every 5 seconds
                UpdateThermalState();
            }
        }
#endif
        
#if UNITY_ANDROID && !UNITY_EDITOR
        private IEnumerator MonitorAndroidThermalState()
        {
            while (true)
            {
                yield return new WaitForSeconds(10f); // Check every 10 seconds
                
                // Android thermal monitoring would require native plugins
                // For now, estimate based on performance degradation
                if (CurrentFPS < targetFrameRate * 0.7f && frameTimeBuffer.IsPerformanceStable())
                {
                    // Sustained low FPS might indicate thermal throttling
                    if (currentThermalState < ThermalState.Serious)
                    {
                        Debug.LogWarning("Possible thermal throttling detected on Android");
                        ApplyThermalThrottling(ThermalState.Serious);
                    }
                }
            }
        }
#endif
        
        // Public methods for manual control
        public void ForcePerformanceLevel(PerformanceLevel level)
        {
            enableAutomaticQualityAdjustment = false;
            SetPerformanceLevel(level);
            Debug.Log($"Performance level manually set to {level}");
        }
        
        public void EnableAutomaticAdjustment()
        {
            enableAutomaticQualityAdjustment = true;
            Debug.Log("Automatic performance adjustment enabled");
        }
        
        public void TriggerMemoryCleanup()
        {
            Debug.Log("Manual memory cleanup triggered");
            System.GC.Collect();
            Resources.UnloadUnusedAssets();
        }
        
        void OnDestroy()
        {
            StopAllCoroutines();
        }
        
        // Debug methods
        [System.Diagnostics.Conditional("DEVELOPMENT_BUILD")]
        public void LogDetailedMetrics()
        {
            var metrics = GetCurrentMetrics();
            
            Debug.Log($"=== Detailed Performance Metrics ===\n" +
                     $"Current FPS: {metrics.currentFPS:F2}\n" +
                     $"Average FPS: {metrics.averageFPS:F2}\n" +
                     $"Min FPS: {metrics.minimumFPS:F2}\n" +
                     $"Max FPS: {metrics.maximumFPS:F2}\n" +
                     $"Frame Time StdDev: {metrics.frameTimeStdDev:F4}s\n" +
                     $"Memory Usage: {metrics.memoryUsageMB:F1}MB\n" +
                     $"Battery Level: {metrics.batteryLevel:P1}\n" +
                     $"Thermal State: {metrics.thermalState}\n" +
                     $"Performance Level: {metrics.performanceLevel}\n" +
                     $"Is Stable: {metrics.isStable}\n" +
                     $"Device: {SystemInfo.deviceModel}\n" +
                     $"GPU: {SystemInfo.graphicsDeviceName}\n" +
                     $"System Memory: {SystemInfo.systemMemorySize}MB\n" +
                     $"Graphics Memory: {SystemInfo.graphicsMemorySize}MB");
        }
    }
}