using System;
using System.Runtime.InteropServices;
using UnityEngine;

namespace SpatialPlatform.Core.SLAM.Native
{
    /// <summary>
    /// Native SLAM interop layer with platform-specific DLL imports
    /// Handles all native function calls and data marshaling
    /// </summary>
    public static class SLAMNativeInterop
    {
        #if UNITY_IOS && !UNITY_EDITOR
        private const string NATIVE_LIB = "__Internal";
        #else
        private const string NATIVE_LIB = "SpatialSLAM";
        #endif
        
        // Native structures
        [StructLayout(LayoutKind.Sequential)]
        public struct NativeCameraCalibration
        {
            public float fx, fy;
            public float cx, cy;
            public float k1, k2, k3;
            public float p1, p2;
            public int width, height;
        }
        
        [StructLayout(LayoutKind.Sequential)]
        public struct NativePose
        {
            [MarshalAs(UnmanagedType.ByValArray, SizeConst = 3)]
            public float[] position;
            [MarshalAs(UnmanagedType.ByValArray, SizeConst = 4)]
            public float[] rotation;
            public double timestamp;
            public float confidence;
            
            public NativePose(Vector3 pos, Quaternion rot, double time, float conf)
            {
                position = new float[] { pos.x, pos.y, pos.z };
                rotation = new float[] { rot.x, rot.y, rot.z, rot.w };
                timestamp = time;
                confidence = conf;
            }
        }
        
        [StructLayout(LayoutKind.Sequential)]
        public struct NativeSLAMConfig
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
        public struct NativeTrackingStats
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
        
        // Core SLAM functions
        [DllImport(NATIVE_LIB)]
        public static extern IntPtr SpatialSLAM_Create(
            ref NativeSLAMConfig config,
            ref NativeCameraCalibration calibration,
            string vocabulary_path
        );
        
        [DllImport(NATIVE_LIB)]
        public static extern void SpatialSLAM_Destroy(IntPtr handle);
        
        [DllImport(NATIVE_LIB)]
        public static extern int SpatialSLAM_ProcessFrame(
            IntPtr handle,
            IntPtr image_data,
            int width,
            int height,
            double timestamp,
            out NativePose pose
        );
        
        [DllImport(NATIVE_LIB)]
        public static extern int SpatialSLAM_GetCurrentPose(IntPtr handle, out NativePose pose);
        
        [DllImport(NATIVE_LIB)]
        public static extern int SpatialSLAM_GetTrackingStats(IntPtr handle, out NativeTrackingStats stats);
        
        [DllImport(NATIVE_LIB)]
        public static extern int SpatialSLAM_GetState(IntPtr handle);
        
        [DllImport(NATIVE_LIB)]
        public static extern int SpatialSLAM_Reset(IntPtr handle);
        
        // Map persistence functions
        [DllImport(NATIVE_LIB)]
        public static extern int SpatialSLAM_LoadMapFromBuffer(IntPtr handle, byte[] buffer, int size);
        
        [DllImport(NATIVE_LIB)]
        public static extern int SpatialSLAM_SaveMapToBuffer(IntPtr handle, byte[] buffer, int buffer_size, out int bytes_written);
        
        // Relocalization functions
        [DllImport(NATIVE_LIB)]
        public static extern int SpatialSLAM_SetRelocalizationEnabled(IntPtr handle, bool enable);
        
        [DllImport(NATIVE_LIB)]
        public static extern int SpatialSLAM_RequestRelocalization(IntPtr handle);
        
        // Utility functions for safe native calls
        public static bool IsValidHandle(IntPtr handle) => handle != IntPtr.Zero;
        
        public static SLAMResult CallNativeFunction(Func<int> nativeCall)
        {
            try
            {
                return (SLAMResult)nativeCall();
            }
            catch (Exception e)
            {
                Debug.LogError($"Native SLAM call failed: {e.Message}");
                return SLAMResult.ProcessingFailed;
            }
        }
    }
    
    // Result and state enums
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
}