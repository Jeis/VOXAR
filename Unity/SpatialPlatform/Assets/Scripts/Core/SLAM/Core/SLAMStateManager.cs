using System;
using UnityEngine;
using SpatialPlatform.Core.SLAM.Native;
using SpatialPlatform.Core.SLAM.Models;

namespace SpatialPlatform.Core.SLAM.Core
{
    /// <summary>
    /// SLAM state management and lifecycle control
    /// Handles initialization, state transitions, and error recovery
    /// </summary>
    public class SLAMStateManager
    {
        private IntPtr nativeHandle = IntPtr.Zero;
        private SLAMState currentState = SLAMState.Uninitialized;
        private readonly SLAMConfiguration config;
        private readonly CameraCalibration calibration;
        private readonly string vocabularyPath;
        
        public IntPtr NativeHandle => nativeHandle;
        public SLAMState CurrentState => currentState;
        public bool IsInitialized => nativeHandle != IntPtr.Zero && currentState != SLAMState.Failed;
        
        public event Action<SLAMState> OnStateChanged;
        public event Action<string> OnError;
        
        public SLAMStateManager(SLAMConfiguration config, CameraCalibration calibration, string vocabPath)
        {
            this.config = config;
            this.calibration = calibration;
            this.vocabularyPath = vocabPath;
        }
        
        public bool Initialize()
        {
            try
            {
                ChangeState(SLAMState.Initializing);
                
                // Validate vocabulary path
                string fullVocabPath = GetFullVocabularyPath();
                if (!string.IsNullOrEmpty(fullVocabPath) && !System.IO.File.Exists(fullVocabPath))
                {
                    Debug.LogWarning($"ORB vocabulary not found at {fullVocabPath} - SLAM may not work optimally");
                    fullVocabPath = null;
                }
                
                // Create native SLAM system
                var nativeConfig = config.ToNative();
                var nativeCalibration = calibration.ToNative();
                
                nativeHandle = SLAMNativeInterop.SpatialSLAM_Create(
                    ref nativeConfig, 
                    ref nativeCalibration, 
                    fullVocabPath
                );
                
                if (nativeHandle == IntPtr.Zero)
                {
                    throw new InvalidOperationException("Failed to create native SLAM system");
                }
                
                ChangeState(SLAMState.Ready);
                Debug.Log("✅ SLAM system initialized successfully");
                return true;
            }
            catch (Exception e)
            {
                HandleError($"SLAM initialization failed: {e.Message}");
                ChangeState(SLAMState.Failed);
                return false;
            }
        }
        
        public void Shutdown()
        {
            try
            {
                if (nativeHandle != IntPtr.Zero)
                {
                    SLAMNativeInterop.SpatialSLAM_Destroy(nativeHandle);
                    nativeHandle = IntPtr.Zero;
                }
                
                ChangeState(SLAMState.Uninitialized);
                Debug.Log("SLAM system shutdown successfully");
            }
            catch (Exception e)
            {
                HandleError($"SLAM shutdown failed: {e.Message}");
            }
        }
        
        public bool Reset()
        {
            try
            {
                if (!IsInitialized)
                {
                    return false;
                }
                
                var result = SLAMNativeInterop.CallNativeFunction(() =>
                    SLAMNativeInterop.SpatialSLAM_Reset(nativeHandle)
                );
                
                if (result == SLAMResult.Success)
                {
                    ChangeState(SLAMState.Ready);
                    return true;
                }
                else
                {
                    HandleError($"SLAM reset failed: {result}");
                    return false;
                }
            }
            catch (Exception e)
            {
                HandleError($"SLAM reset error: {e.Message}");
                return false;
            }
        }
        
        public SLAMState GetCurrentState()
        {
            try
            {
                if (!IsInitialized)
                {
                    return currentState;
                }
                
                int nativeState = SLAMNativeInterop.SpatialSLAM_GetState(nativeHandle);
                var newState = (SLAMState)nativeState;
                
                if (newState != currentState)
                {
                    ChangeState(newState);
                }
                
                return currentState;
            }
            catch (Exception e)
            {
                HandleError($"Failed to get SLAM state: {e.Message}");
                return SLAMState.Failed;
            }
        }
        
        private void ChangeState(SLAMState newState)
        {
            if (currentState != newState)
            {
                var previousState = currentState;
                currentState = newState;
                
                Debug.Log($"SLAM state changed: {previousState} → {newState}");
                OnStateChanged?.Invoke(newState);
            }
        }
        
        private void HandleError(string error)
        {
            Debug.LogError($"[SLAMStateManager] {error}");
            OnError?.Invoke(error);
        }
        
        private string GetFullVocabularyPath()
        {
            if (string.IsNullOrEmpty(vocabularyPath))
            {
                return null;
            }
            
            if (System.IO.Path.IsPathRooted(vocabularyPath))
            {
                return vocabularyPath;
            }
            
            return System.IO.Path.Combine(Application.streamingAssetsPath, vocabularyPath);
        }
    }
}