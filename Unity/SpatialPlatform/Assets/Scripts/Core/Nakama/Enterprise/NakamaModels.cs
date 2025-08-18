using System;
using System.Collections.Generic;
using UnityEngine;
using Nakama;

namespace SpatialPlatform.Nakama.Enterprise
{
    /// <summary>
    /// Enterprise data models for Nakama AR Client
    /// Centralized data structures and enums
    /// </summary>
    
    [Serializable]
    public class RemotePlayer
    {
        public string userId;
        public string displayName;
        public Pose currentPose;
        public float lastUpdateTime;
        public bool isColocalized;
        public Dictionary<string, object> metadata;
        
        public RemotePlayer()
        {
            metadata = new Dictionary<string, object>();
            lastUpdateTime = Time.time;
        }
    }
    
    [Serializable]
    public class CloudAnchor
    {
        public string id;
        public Pose pose;
        public Dictionary<string, object> metadata;
        public string creatorId;
        public DateTime createdAt;
        public bool isPersistent;
        public CloudAnchorState cloudState;
        
        public CloudAnchor()
        {
            metadata = new Dictionary<string, object>();
            createdAt = DateTime.UtcNow;
            cloudState = CloudAnchorState.Pending;
        }
    }
    
    [Serializable]
    public class PoseUpdate
    {
        public string userId;
        public Vector3 position;
        public Quaternion rotation;
        public float timestamp;
        public bool isReliable;
        
        public PoseUpdate(string userId, Pose pose, bool reliable = false)
        {
            this.userId = userId;
            position = pose.position;
            rotation = pose.rotation;
            timestamp = Time.time;
            isReliable = reliable;
        }
    }
    
    [Serializable]
    public class PerformanceMetrics
    {
        public float averageLatency;
        public float packetLoss;
        public int totalMessages;
        public int messagesPerSecond;
        public NetworkQuality networkQuality;
        public float lastUpdateTime;
        
        public PerformanceMetrics()
        {
            networkQuality = NetworkQuality.Unknown;
            lastUpdateTime = Time.time;
        }
        
        public void UpdateLatency(float latency)
        {
            averageLatency = (averageLatency * 0.9f) + (latency * 0.1f);
            
            // Update network quality based on latency
            if (averageLatency < 50f)
                networkQuality = NetworkQuality.Excellent;
            else if (averageLatency < 100f)
                networkQuality = NetworkQuality.Good;
            else if (averageLatency < 200f)
                networkQuality = NetworkQuality.Fair;
            else
                networkQuality = NetworkQuality.Poor;
        }
    }
    
    [Serializable]
    public class FeaturePointCloud
    {
        public Vector3[] points;
        public float[] confidenceScores;
        public int frameId;
        public float timestamp;
        
        public FeaturePointCloud()
        {
            timestamp = Time.time;
        }
    }
    
    // Enums
    public enum CloudAnchorState
    {
        Pending,
        Created,
        Failed,
        Deleted
    }
    
    public enum NetworkQuality
    {
        Unknown,
        Poor,
        Fair,
        Good,
        Excellent
    }
    
    public enum VPSStatus
    {
        NotInitialized,
        Initializing,
        Ready,
        Localizing,
        Localized,
        Failed
    }
    
    public enum ColocalizationMethod
    {
        QRCode,
        VPS,
        Manual
    }
    
    public enum OpCode
    {
        PoseUpdate = 1,
        AnchorCreate = 2,
        AnchorUpdate = 3,
        AnchorDelete = 4,
        ColocalizationData = 5,
        CoordinateSystem = 6,
        ChatMessage = 7,
        Ping = 8,
        Pong = 9,
        SessionState = 10,
        VPSLocalization = 11
    }
    
    // Configuration classes
    [Serializable]
    public class ConnectionConfig
    {
        public string scheme = "https";
        public string host = "api.voxar.io";
        public int port = 443;
        public string serverKey = "defaultkey";
        public bool autoReconnect = true;
        public int maxReconnectAttempts = 5;
        public float reconnectDelay = 2f;
        public bool requireAuthentication = false;
        public bool enableEncryption = true;
        public string apiKey = "";
    }
    
    [Serializable]
    public class ARConfig
    {
        public float poseUpdateInterval = 0.016f; // 60 FPS
        public float poseDistanceThreshold = 0.01f; // 1cm
        public float poseAngleThreshold = 1f; // 1 degree
        public bool enablePosePrediction = true;
        public bool enableDeltaCompression = true;
    }
    
    [Serializable]
    public class SessionConfig
    {
        public int maxPlayers = 10;
        public string colocalizationMethod = "qr_code";
        public float sessionTimeout = 3600f; // 1 hour
    }
    
    [Serializable]
    public class VPSConfig
    {
        public bool vpsEnabled = false;
        public float vpsLocalizationTimeout = 30f;
        public int vpsFeaturePointMinimum = 500;
    }
}