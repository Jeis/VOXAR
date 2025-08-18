using System;
using UnityEngine;
using SpatialPlatform.Core.SLAM.Native;

namespace SpatialPlatform.Core.SLAM.Models
{
    /// <summary>
    /// SLAM data models and configuration structures
    /// Clean C# representations of SLAM data
    /// </summary>
    
    [Serializable]
    public struct SLAMPose
    {
        public Vector3 position;
        public Quaternion rotation;
        public double timestamp;
        public float confidence;
        
        public SLAMPose(Vector3 pos, Quaternion rot, double time, float conf)
        {
            position = pos;
            rotation = rot;
            timestamp = time;
            confidence = conf;
        }
        
        public Matrix4x4 ToMatrix()
        {
            return Matrix4x4.TRS(position, rotation, Vector3.one);
        }
        
        public static SLAMPose FromNative(SLAMNativeInterop.NativePose native)
        {
            return new SLAMPose(
                new Vector3(native.position[0], native.position[1], native.position[2]),
                new Quaternion(native.rotation[0], native.rotation[1], native.rotation[2], native.rotation[3]),
                native.timestamp,
                native.confidence
            );
        }
    }
    
    [Serializable]
    public struct SLAMTrackingStats
    {
        public int totalKeyframes;
        public int totalLandmarks;
        public int trackingKeyframes;
        public float averageReprojectionError;
        public float processingTimeMs;
        public TrackingQuality quality;
        public int featureCount;
        public int matchedFeatures;
        
        public static SLAMTrackingStats FromNative(SLAMNativeInterop.NativeTrackingStats native)
        {
            return new SLAMTrackingStats
            {
                totalKeyframes = native.total_keyframes,
                totalLandmarks = native.total_landmarks,
                trackingKeyframes = native.tracking_keyframes,
                averageReprojectionError = native.average_reprojection_error,
                processingTimeMs = native.processing_time_ms,
                quality = (TrackingQuality)native.quality,
                featureCount = native.feature_count,
                matchedFeatures = native.matched_features
            };
        }
    }
    
    [Serializable]
    public class SLAMConfiguration
    {
        [Header("Features")]
        public int maxFeatures = 2000;
        public float featureQuality = 0.01f;
        public float minFeatureDistance = 5.0f;
        public float maxReprojectionError = 2.0f;
        public int minTrackingFeatures = 100;
        public int maxTrackingIterations = 30;
        
        [Header("Keyframes")]
        public int keyframeThreshold = 20;
        public float keyframeDistance = 0.1f;
        public float keyframeAngle = 0.2f;
        public int maxKeyframes = 500;
        
        [Header("Performance")]
        public bool enableMultithreading = true;
        public int maxThreads = 4;
        public float memoryLimitMB = 200f;
        
        [Header("Advanced")]
        public bool enableLoopClosure = true;
        public bool enableRelocalization = true;
        public int maxLandmarks = 10000;
        
        public SLAMNativeInterop.NativeSLAMConfig ToNative()
        {
            return new SLAMNativeInterop.NativeSLAMConfig
            {
                max_features = maxFeatures,
                feature_quality = featureQuality,
                min_feature_distance = minFeatureDistance,
                max_reprojection_error = maxReprojectionError,
                min_tracking_features = minTrackingFeatures,
                max_tracking_iterations = maxTrackingIterations,
                keyframe_threshold = keyframeThreshold,
                keyframe_distance = keyframeDistance,
                keyframe_angle = keyframeAngle,
                enable_multithreading = enableMultithreading,
                max_threads = maxThreads,
                enable_loop_closure = enableLoopClosure,
                enable_relocalization = enableRelocalization,
                max_keyframes = maxKeyframes,
                max_landmarks = maxLandmarks,
                memory_limit_mb = memoryLimitMB
            };
        }
    }
    
    [Serializable]
    public class CameraCalibration
    {
        [Header("Intrinsics")]
        public float focalLengthX = 525.0f;
        public float focalLengthY = 525.0f;
        public float principalPointX = 319.5f;
        public float principalPointY = 239.5f;
        
        [Header("Distortion")]
        public Vector3 distortionCoefficients = Vector3.zero;
        public Vector2 distortionTangential = Vector2.zero;
        
        [Header("Resolution")]
        public int imageWidth = 640;
        public int imageHeight = 480;
        
        public SLAMNativeInterop.NativeCameraCalibration ToNative()
        {
            return new SLAMNativeInterop.NativeCameraCalibration
            {
                fx = focalLengthX,
                fy = focalLengthY,
                cx = principalPointX,
                cy = principalPointY,
                k1 = distortionCoefficients.x,
                k2 = distortionCoefficients.y,
                k3 = distortionCoefficients.z,
                p1 = distortionTangential.x,
                p2 = distortionTangential.y,
                width = imageWidth,
                height = imageHeight
            };
        }
        
        public static CameraCalibration CreateFromScreen()
        {
            return new CameraCalibration
            {
                focalLengthX = Screen.width * 0.8f,
                focalLengthY = Screen.height * 0.8f,
                principalPointX = Screen.width * 0.5f,
                principalPointY = Screen.height * 0.5f,
                imageWidth = Screen.width,
                imageHeight = Screen.height
            };
        }
    }
}