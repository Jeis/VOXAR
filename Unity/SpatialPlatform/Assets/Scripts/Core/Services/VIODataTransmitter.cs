/*
 * Spatial Platform - VIO Data Transmitter
 * Handles transmission of IMU and visual data to backend VIO service
 */

using System;
using System.Collections;
using System.Collections.Generic;
using System.Text;
using UnityEngine;
using UnityEngine.Networking;
using Newtonsoft.Json;
using SpatialPlatform.Sensors;

namespace SpatialPlatform.Services
{
    [Serializable]
    public struct VIODataPacket
    {
        public double timestamp;
        public IMUReading[] imuReadings;
        public string cameraFrameBase64; // Optional - can be null for IMU-only packets
        public CameraIntrinsics cameraParams;
        public int sequenceNumber;
        
        public VIODataPacket(double time, IMUReading[] imu, string frame, CameraIntrinsics camera, int seq)
        {
            timestamp = time;
            imuReadings = imu;
            cameraFrameBase64 = frame;
            cameraParams = camera;
            sequenceNumber = seq;
        }
    }
    
    [Serializable]
    public struct CameraIntrinsics
    {
        public float fx, fy, cx, cy;
        public float k1, k2, p1, p2, k3;
        public int width, height;
        
        public static CameraIntrinsics Default => new CameraIntrinsics
        {
            fx = 800f, fy = 800f, cx = 320f, cy = 240f,
            k1 = 0f, k2 = 0f, p1 = 0f, p2 = 0f, k3 = 0f,
            width = 640, height = 480
        };
    }
    
    [Serializable]
    public struct VIOResponse
    {
        public bool success;
        public string message;
        public VIOPoseEstimate poseEstimate;
        public float processingTime;
        public int sequenceNumber;
    }
    
    [Serializable]
    public struct VIOPoseEstimate
    {
        public double timestamp;
        public Vector3 position;
        public Quaternion rotation;
        public Vector3 velocity;
        public Vector3 angularVelocity;
        public float confidence;
        public string trackingState; // "initializing", "tracking", "lost"
        public Matrix4x4 covariance; // Pose uncertainty
    }
    
    public class VIODataTransmitter : MonoBehaviour
    {
        [Header("Network Configuration")]
        [SerializeField] private string baseUrl = "http://localhost:8092";
        [SerializeField] private float imuTransmissionRate = 50f; // Hz
        [SerializeField] private float visualTransmissionRate = 10f; // Hz
        [SerializeField] private int maxRetries = 3;
        [SerializeField] private float timeoutSeconds = 1f;
        
        [Header("Data Buffering")]
        [SerializeField] private int imuBufferSize = 100;
        [SerializeField] private bool enableDataCompression = true;
        [SerializeField] private bool sendIMUOnly = false; // For testing/debugging
        
        [Header("Quality Control")]
        [SerializeField] private float maxLatency = 100f; // ms
        [SerializeField] private bool enableAdaptiveQuality = true;
        [SerializeField] private float networkQualityThreshold = 0.8f;
        
        // Component references
        private IMUDataCollector imuCollector;
        private Camera arCamera;
        
        // Data management
        private Queue<IMUReading> pendingIMUData;
        private int sequenceNumber;
        private double lastIMUTransmission;
        private double lastVisualTransmission;
        
        // Network monitoring
        private float averageLatency;
        private float networkQuality = 1f;
        private int successfulRequests;
        private int totalRequests;
        
        // Events
        public event Action<VIOResponse> OnVIOResponseReceived;
        public event Action<string> OnTransmissionError;
        public event Action<float> OnNetworkQualityChanged;
        
        private void Awake()
        {
            InitializeComponents();
            InitializeDataStructures();
        }
        
        private void InitializeComponents()
        {
            imuCollector = FindObjectOfType<IMUDataCollector>();
            if (imuCollector == null)
            {
                Debug.LogError("IMUDataCollector not found - VIO data transmission will not work");
                return;
            }
            
            arCamera = Camera.main ?? FindObjectOfType<Camera>();
            if (arCamera == null)
            {
                Debug.LogWarning("No camera found - visual data will not be transmitted");
            }
        }
        
        private void InitializeDataStructures()
        {
            pendingIMUData = new Queue<IMUReading>();
            sequenceNumber = 0;
            lastIMUTransmission = 0;
            lastVisualTransmission = 0;
        }
        
        private void Start()
        {
            if (imuCollector != null)
            {
                imuCollector.OnIMUDataReceived += OnIMUDataReceived;
            }
            
            // Start transmission loops
            StartCoroutine(IMUTransmissionLoop());
            if (!sendIMUOnly && arCamera != null)
            {
                StartCoroutine(VisualTransmissionLoop());
            }
        }
        
        private void OnIMUDataReceived(IMUReading reading)
        {
            // Buffer IMU data for transmission
            pendingIMUData.Enqueue(reading);
            
            // Maintain buffer size
            while (pendingIMUData.Count > imuBufferSize)
            {
                pendingIMUData.Dequeue();
            }
        }
        
        private IEnumerator IMUTransmissionLoop()
        {
            while (true)
            {
                double currentTime = Time.realtimeSinceStartupAsDouble;
                float transmissionInterval = 1f / imuTransmissionRate;
                
                if (currentTime - lastIMUTransmission >= transmissionInterval)
                {
                    yield return StartCoroutine(TransmitIMUData());
                    lastIMUTransmission = currentTime;
                }
                
                yield return null;
            }
        }
        
        private IEnumerator VisualTransmissionLoop()
        {
            while (true)
            {
                double currentTime = Time.realtimeSinceStartupAsDouble;
                float transmissionInterval = 1f / visualTransmissionRate;
                
                if (currentTime - lastVisualTransmission >= transmissionInterval)
                {
                    yield return StartCoroutine(TransmitVIOData(true));
                    lastVisualTransmission = currentTime;
                }
                
                yield return null;
            }
        }
        
        private IEnumerator TransmitIMUData()
        {
            yield return StartCoroutine(TransmitVIOData(false));
        }
        
        private IEnumerator TransmitVIOData(bool includeVisual)
        {
            if (pendingIMUData.Count == 0) yield break;
            
            try
            {
                // Collect IMU readings
                IMUReading[] imuReadings = new IMUReading[pendingIMUData.Count];
                int index = 0;
                while (pendingIMUData.Count > 0)
                {
                    imuReadings[index++] = pendingIMUData.Dequeue();
                }
                
                // Capture camera frame if needed
                string cameraFrameBase64 = null;
                if (includeVisual && arCamera != null)
                {
                    cameraFrameBase64 = await CaptureCurrentFrame();
                }
                
                // Create VIO data packet
                VIODataPacket packet = new VIODataPacket(
                    Time.realtimeSinceStartupAsDouble,
                    imuReadings,
                    cameraFrameBase64,
                    GetCameraIntrinsics(),
                    ++sequenceNumber
                );
                
                // Transmit data
                yield return StartCoroutine(SendVIOPacket(packet));
            }
            catch (Exception e)
            {
                OnTransmissionError?.Invoke($"VIO transmission error: {e.Message}");
            }
        }
        
        private System.Threading.Tasks.Task<string> CaptureCurrentFrame()
        {
            return System.Threading.Tasks.Task.Run(() =>
            {
                try
                {
                    // Create render texture
                    RenderTexture renderTexture = new RenderTexture(640, 480, 24);
                    RenderTexture previousRT = arCamera.targetTexture;
                    
                    // Render camera to texture
                    arCamera.targetTexture = renderTexture;
                    arCamera.Render();
                    
                    // Read pixels
                    RenderTexture.active = renderTexture;
                    Texture2D texture = new Texture2D(640, 480, TextureFormat.RGB24, false);
                    texture.ReadPixels(new Rect(0, 0, 640, 480), 0, 0);
                    texture.Apply();
                    
                    // Restore camera state
                    arCamera.targetTexture = previousRT;
                    RenderTexture.active = null;
                    
                    // Convert to base64
                    byte[] imageBytes = texture.EncodeToJPG(75);
                    string base64 = Convert.ToBase64String(imageBytes);
                    
                    // Cleanup
                    DestroyImmediate(texture);
                    DestroyImmediate(renderTexture);
                    
                    return base64;
                }
                catch (Exception e)
                {
                    Debug.LogError($"Frame capture failed: {e.Message}");
                    return null;
                }
            });
        }
        
        private CameraIntrinsics GetCameraIntrinsics()
        {
            // In a real implementation, you would get these from AR Foundation
            // For now, return default values
            return CameraIntrinsics.Default;
        }
        
        private IEnumerator SendVIOPacket(VIODataPacket packet)
        {
            string url = $"{baseUrl}/vio/process";
            string jsonData = JsonConvert.SerializeObject(packet);
            
            byte[] bodyRaw = Encoding.UTF8.GetBytes(jsonData);
            
            using (UnityWebRequest request = new UnityWebRequest(url, "POST"))
            {
                request.uploadHandler = new UploadHandlerRaw(bodyRaw);
                request.downloadHandler = new DownloadHandlerBuffer();
                request.SetRequestHeader("Content-Type", "application/json");
                request.timeout = (int)timeoutSeconds;
                
                float startTime = Time.time;
                
                yield return request.SendWebRequest();
                
                float requestTime = (Time.time - startTime) * 1000f; // Convert to ms
                UpdateNetworkMetrics(request.result == UnityWebRequest.Result.Success, requestTime);
                
                if (request.result == UnityWebRequest.Result.Success)
                {
                    try
                    {
                        string responseText = request.downloadHandler.text;
                        VIOResponse response = JsonConvert.DeserializeObject<VIOResponse>(responseText);
                        response.processingTime = requestTime;
                        
                        OnVIOResponseReceived?.Invoke(response);
                    }
                    catch (Exception e)
                    {
                        OnTransmissionError?.Invoke($"Response parsing error: {e.Message}");
                    }
                }
                else
                {
                    string error = $"VIO request failed: {request.error} (Code: {request.responseCode})";
                    OnTransmissionError?.Invoke(error);
                    
                    // Implement retry logic here if needed
                }
            }
        }
        
        private void UpdateNetworkMetrics(bool success, float latency)
        {
            totalRequests++;
            if (success)
            {
                successfulRequests++;
                
                // Update average latency (exponential moving average)
                averageLatency = averageLatency * 0.9f + latency * 0.1f;
            }
            
            // Calculate network quality
            float successRate = (float)successfulRequests / totalRequests;
            float latencyScore = Mathf.Clamp01(1f - (averageLatency / maxLatency));
            networkQuality = (successRate + latencyScore) / 2f;
            
            OnNetworkQualityChanged?.Invoke(networkQuality);
            
            // Adaptive quality adjustment
            if (enableAdaptiveQuality)
            {
                AdjustTransmissionRates();
            }
        }
        
        private void AdjustTransmissionRates()
        {
            if (networkQuality < networkQualityThreshold)
            {
                // Reduce transmission rates to improve reliability
                imuTransmissionRate = Mathf.Max(imuTransmissionRate * 0.9f, 10f);
                visualTransmissionRate = Mathf.Max(visualTransmissionRate * 0.8f, 2f);
            }
            else if (networkQuality > 0.95f)
            {
                // Increase transmission rates for better performance
                imuTransmissionRate = Mathf.Min(imuTransmissionRate * 1.1f, 100f);
                visualTransmissionRate = Mathf.Min(visualTransmissionRate * 1.1f, 30f);
            }
        }
        
        public void SetBaseUrl(string url)
        {
            baseUrl = url;
        }
        
        public void SetTransmissionRates(float imuRate, float visualRate)
        {
            imuTransmissionRate = Mathf.Clamp(imuRate, 1f, 1000f);
            visualTransmissionRate = Mathf.Clamp(visualRate, 0.1f, 60f);
        }
        
        public NetworkStats GetNetworkStats()
        {
            return new NetworkStats
            {
                averageLatency = averageLatency,
                networkQuality = networkQuality,
                successRate = totalRequests > 0 ? (float)successfulRequests / totalRequests : 0f,
                totalRequests = totalRequests,
                currentIMURate = imuTransmissionRate,
                currentVisualRate = visualTransmissionRate
            };
        }
        
        private void OnDestroy()
        {
            if (imuCollector != null)
            {
                imuCollector.OnIMUDataReceived -= OnIMUDataReceived;
            }
        }
    }
    
    [Serializable]
    public struct NetworkStats
    {
        public float averageLatency;
        public float networkQuality;
        public float successRate;
        public int totalRequests;
        public float currentIMURate;
        public float currentVisualRate;
    }
}