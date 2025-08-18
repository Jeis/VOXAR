using System;
using UnityEngine;
using SpatialPlatform.Core.SLAM.Native;
using SpatialPlatform.Core.SLAM.Models;

namespace SpatialPlatform.Core.SLAM.Core
{
    /// <summary>
    /// SLAM tracking and pose estimation core
    /// Handles frame processing, pose updates, and tracking statistics
    /// </summary>
    public class SLAMTracker
    {
        private readonly SLAMStateManager stateManager;
        private SLAMPose lastKnownPose;
        private SLAMTrackingStats lastStats;
        private bool isTrackingEnabled = false;
        
        public SLAMPose LastKnownPose => lastKnownPose;
        public SLAMTrackingStats LastStats => lastStats;
        public bool IsTrackingEnabled => isTrackingEnabled;
        
        public event Action<SLAMPose> OnPoseUpdated;
        public event Action<SLAMTrackingStats> OnStatsUpdated;
        public event Action<string> OnTrackingError;
        
        public SLAMTracker(SLAMStateManager stateManager)
        {
            this.stateManager = stateManager;
        }
        
        public bool ProcessFrame(IntPtr imageData, int width, int height, double timestamp)
        {
            try
            {
                if (!stateManager.IsInitialized)
                {
                    return false;
                }
                
                var result = SLAMNativeInterop.CallNativeFunction(() =>
                {
                    SLAMNativeInterop.NativePose nativePose;
                    return SLAMNativeInterop.SpatialSLAM_ProcessFrame(
                        stateManager.NativeHandle,
                        imageData,
                        width,
                        height,
                        timestamp,
                        out nativePose
                    );
                });
                
                if (result == SLAMResult.Success)
                {
                    // Update pose and stats
                    UpdateCurrentPose();
                    UpdateTrackingStats();
                    return true;
                }
                else if (result == SLAMResult.TrackingLost)
                {
                    HandleTrackingLost();
                    return false;
                }
                else
                {
                    OnTrackingError?.Invoke($"Frame processing failed: {result}");
                    return false;
                }
            }
            catch (Exception e)
            {
                OnTrackingError?.Invoke($"Frame processing error: {e.Message}");
                return false;
            }
        }
        
        public bool GetCurrentPose(out SLAMPose pose)
        {
            pose = default;
            
            try
            {
                if (!stateManager.IsInitialized)
                {
                    return false;
                }
                
                SLAMNativeInterop.NativePose nativePose;
                var result = SLAMNativeInterop.CallNativeFunction(() =>
                    SLAMNativeInterop.SpatialSLAM_GetCurrentPose(stateManager.NativeHandle, out nativePose)
                );
                
                if (result == SLAMResult.Success)
                {
                    pose = SLAMPose.FromNative(nativePose);
                    return true;
                }
                
                return false;
            }
            catch (Exception e)
            {
                OnTrackingError?.Invoke($"Failed to get current pose: {e.Message}");
                return false;
            }
        }
        
        public bool GetTrackingStats(out SLAMTrackingStats stats)
        {
            stats = default;
            
            try
            {
                if (!stateManager.IsInitialized)
                {
                    return false;
                }
                
                SLAMNativeInterop.NativeTrackingStats nativeStats;
                var result = SLAMNativeInterop.CallNativeFunction(() =>
                    SLAMNativeInterop.SpatialSLAM_GetTrackingStats(stateManager.NativeHandle, out nativeStats)
                );
                
                if (result == SLAMResult.Success)
                {
                    stats = SLAMTrackingStats.FromNative(nativeStats);
                    return true;
                }
                
                return false;
            }
            catch (Exception e)
            {
                OnTrackingError?.Invoke($"Failed to get tracking stats: {e.Message}");
                return false;
            }
        }
        
        public void EnableTracking(bool enable)
        {
            isTrackingEnabled = enable;
            
            if (enable && stateManager.CurrentState == SLAMState.Ready)
            {
                // Ready to start tracking
                Debug.Log("SLAM tracking enabled");
            }
            else if (!enable)
            {
                Debug.Log("SLAM tracking disabled");
            }
        }
        
        private void UpdateCurrentPose()
        {
            if (GetCurrentPose(out SLAMPose pose))
            {
                lastKnownPose = pose;
                OnPoseUpdated?.Invoke(pose);
            }
        }
        
        private void UpdateTrackingStats()
        {
            if (GetTrackingStats(out SLAMTrackingStats stats))
            {
                lastStats = stats;
                OnStatsUpdated?.Invoke(stats);
            }
        }
        
        private void HandleTrackingLost()
        {
            OnTrackingError?.Invoke("SLAM tracking lost - attempting recovery");
            
            // Could implement automatic recovery strategies here
            // For now, just report the state change
            stateManager.GetCurrentState(); // This will trigger state change events
        }
        
        public void Reset()
        {
            lastKnownPose = default;
            lastStats = default;
            isTrackingEnabled = false;
        }
    }
}