using System;
using System.Collections.Generic;
using UnityEngine;

namespace SpatialPlatform.Nakama.Enterprise
{
    /// <summary>
    /// Enterprise Metrics Manager for performance monitoring
    /// Tracks network quality, latency, and AR performance metrics
    /// </summary>
    public class MetricsManager
    {
        private readonly PerformanceMetrics metrics;
        private readonly Dictionary<string, float> customMetrics;
        private float lastMetricsUpdateTime;
        private int messagesInCurrentSecond;
        private float currentSecondStart;
        private bool isMetricsActive = false;
        private int errorCount = 0;
        
        public PerformanceMetrics Metrics => metrics;
        public PerformanceMetrics CurrentMetrics => metrics; // Enterprise alias
        public IReadOnlyDictionary<string, float> CustomMetrics => customMetrics;
        
        public event Action<NetworkQuality> OnNetworkQualityChanged;
        public event Action<string, float> OnCustomMetricRecorded;
        
        public MetricsManager()
        {
            metrics = new PerformanceMetrics();
            customMetrics = new Dictionary<string, float>();
            currentSecondStart = Time.time;
        }
        
        /// <summary>
        /// Update metrics every frame
        /// </summary>
        public void UpdateMetrics()
        {
            // Update messages per second
            if (Time.time - currentSecondStart >= 1.0f)
            {
                metrics.messagesPerSecond = messagesInCurrentSecond;
                messagesInCurrentSecond = 0;
                currentSecondStart = Time.time;
            }
            
            metrics.lastUpdateTime = Time.time;
        }
        
        /// <summary>
        /// Record a message sent/received
        /// </summary>
        public void RecordMessage()
        {
            metrics.totalMessages++;
            messagesInCurrentSecond++;
        }
        
        /// <summary>
        /// Update network latency from ping/pong
        /// </summary>
        public void UpdateLatency(float latency)
        {
            var previousQuality = metrics.networkQuality;
            metrics.UpdateLatency(latency);
            
            if (previousQuality != metrics.networkQuality)
            {
                OnNetworkQualityChanged?.Invoke(metrics.networkQuality);
            }
        }
        
        /// <summary>
        /// Record packet loss
        /// </summary>
        public void RecordPacketLoss(float lossPercentage)
        {
            metrics.packetLoss = lossPercentage;
        }
        
        /// <summary>
        /// Record custom metric
        /// </summary>
        public void RecordCustomMetric(string name, float value)
        {
            customMetrics[name] = value;
            OnCustomMetricRecorded?.Invoke(name, value);
        }
        
        /// <summary>
        /// Get custom metric value
        /// </summary>
        public float GetCustomMetric(string name, float defaultValue = 0f)
        {
            return customMetrics.ContainsKey(name) ? customMetrics[name] : defaultValue;
        }
        
        /// <summary>
        /// Generate metrics report
        /// </summary>
        public Dictionary<string, object> GenerateReport()
        {
            var report = new Dictionary<string, object>
            {
                { "average_latency_ms", metrics.averageLatency },
                { "packet_loss_percent", metrics.packetLoss },
                { "total_messages", metrics.totalMessages },
                { "messages_per_second", metrics.messagesPerSecond },
                { "network_quality", metrics.networkQuality.ToString() },
                { "timestamp", Time.time }
            };
            
            // Add custom metrics
            foreach (var kvp in customMetrics)
            {
                report[$"custom_{kvp.Key}"] = kvp.Value;
            }
            
            return report;
        }
        
        /// <summary>
        /// Log metrics to console (debug)
        /// </summary>
        public void LogMetrics()
        {
            Debug.Log($"[Metrics] Latency: {metrics.averageLatency:F1}ms | " +
                     $"Loss: {metrics.packetLoss:F1}% | " +
                     $"Msgs/s: {metrics.messagesPerSecond} | " +
                     $"Quality: {metrics.networkQuality}");
        }
        
        /// <summary>
        /// Reset all metrics
        /// </summary>
        public void Reset()
        {
            metrics.averageLatency = 0;
            metrics.packetLoss = 0;
            metrics.totalMessages = 0;
            metrics.messagesPerSecond = 0;
            metrics.networkQuality = NetworkQuality.Unknown;
            customMetrics.Clear();
            messagesInCurrentSecond = 0;
            currentSecondStart = Time.time;
        }
        
        // Enterprise Integration Methods
        
        /// <summary>
        /// Start metrics collection
        /// </summary>
        public void StartMetrics()
        {
            isMetricsActive = true;
            Reset();
            Debug.Log("[MetricsManager] ✅ Enterprise metrics started");
        }
        
        /// <summary>
        /// Pause metrics collection
        /// </summary>
        public void PauseMetrics()
        {
            isMetricsActive = false;
            Debug.Log("[MetricsManager] ⏸️ Enterprise metrics paused");
        }
        
        /// <summary>
        /// Resume metrics collection
        /// </summary>
        public void ResumeMetrics()
        {
            isMetricsActive = true;
            Debug.Log("[MetricsManager] ▶️ Enterprise metrics resumed");
        }
        
        /// <summary>
        /// Reset session-specific metrics
        /// </summary>
        public void ResetSessionMetrics()
        {
            metrics.totalMessages = 0;
            metrics.messagesPerSecond = 0;
            errorCount = 0;
            customMetrics.Clear();
            Debug.Log("[MetricsManager] 🔄 Session metrics reset");
        }
        
        /// <summary>
        /// Log an error occurrence
        /// </summary>
        public void LogError()
        {
            errorCount++;
            RecordCustomMetric("error_count", errorCount);
        }
        
        /// <summary>
        /// Enterprise metrics update with manager coordination
        /// </summary>
        public void UpdateMetrics(ConnectionManager connectionManager, SessionManager sessionManager, 
                                 PlayerManager playerManager, AnchorManager anchorManager)
        {
            if (!isMetricsActive) return;
            
            // Connection metrics
            if (connectionManager != null)
            {
                RecordCustomMetric("is_connected", connectionManager.IsConnected ? 1f : 0f);
            }
            
            // Session metrics  
            if (sessionManager != null)
            {
                RecordCustomMetric("is_host", sessionManager.IsHost ? 1f : 0f);
                RecordCustomMetric("has_session", !string.IsNullOrEmpty(sessionManager.SessionCode) ? 1f : 0f);
            }
            
            // Player metrics
            if (playerManager != null)
            {
                RecordCustomMetric("is_colocalized", playerManager.IsColocalized ? 1f : 0f);
                RecordCustomMetric("remote_player_count", playerManager.RemotePlayers.Count);
            }
            
            // Anchor metrics
            if (anchorManager != null)
            {
                RecordCustomMetric("cloud_anchor_count", anchorManager.CloudAnchors.Count);
            }
            
            // Update base metrics
            UpdateMetrics();
        }
        
        /// <summary>
        /// Get comprehensive enterprise metrics report
        /// </summary>
        public Dictionary<string, object> GetEnterpriseReport()
        {
            var report = GenerateReport();
            report["error_count"] = errorCount;
            report["metrics_active"] = isMetricsActive;
            report["uptime_seconds"] = Time.time - currentSecondStart;
            
            return report;
        }
        
        /// <summary>
        /// Dispose metrics manager
        /// </summary>
        public void Dispose()
        {
            isMetricsActive = false;
            Debug.Log("[MetricsManager] 🧹 Enterprise metrics disposed");
        }
    }
}