/**
 * Spatial Platform - Unity SLAM Client
 * Communicates with backend localization service for real-time tracking
 */

using System;
using System.Collections;
using System.Collections.Generic;
using System.Text;
using UnityEngine;
using UnityEngine.Networking;
using UnityEngine.XR.ARFoundation;
using UnityEngine.XR.ARSubsystems;

namespace SpatialPlatform.Core.Services
{
    [Serializable]
    public class CameraIntrinsics
    {
        public float fx;
        public float fy;
        public float cx;
        public float cy;
        public int width;
        public int height;
        public float fps = 30.0f;
        public float k1 = 0.0f;
        public float k2 = 0.0f;
        public float p1 = 0.0f;
        public float p2 = 0.0f;
        public float k3 = 0.0f;
    }

    [Serializable]
    public class SLAMInitRequest
    {
        public CameraIntrinsics camera_intrinsics;
        public bool enable_loop_closure = true;
        public bool enable_relocalization = true;
        public string map_id = null;
    }

    [Serializable]
    public class TrackingFrame
    {
        public float timestamp;
        public string image_data; // Base64 encoded image
        public int camera_id = 0;
    }

    [Serializable]
    public class PoseResponse
    {
        public float timestamp;
        public float[] position = new float[3]; // [x, y, z]
        public float[] rotation = new float[4]; // [qw, qx, qy, qz]
        public float confidence;
        public string tracking_state;
    }

    [Serializable]
    public class SLAMStatus
    {
        public bool is_initialized;
        public bool is_tracking;
        public int frame_count;
        public float fps;
        public float last_pose_time;
        public PoseResponse current_pose;
    }

    [Serializable]
    public class ApiResponse<T>
    {
        public string status;
        public string message;
        public T data;
    }

    public class SpatialSLAMClient : MonoBehaviour
    {
        [Header("SLAM Configuration")]
        [SerializeField] private string backendUrl = "http://localhost:8080";
        [SerializeField] private bool enableVerboseLogging = true;
        [SerializeField] private float trackingIntervalMs = 33.0f; // ~30 FPS
        [SerializeField] private int maxQueueSize = 5;

        [Header("Camera Configuration")]
        [SerializeField] private ARCamera arCamera;
        [SerializeField] private Camera unityCamera;

        // Events
        public event Action<PoseResponse> OnPoseReceived;
        public event Action<string> OnTrackingStateChanged;
        public event Action<SLAMStatus> OnStatusUpdate;
        public event Action<string> OnError;

        // Internal state
        private bool isInitialized = false;
        private bool isTracking = false;
        private bool isConnected = false;
        private Queue<TrackingFrame> frameQueue = new Queue<TrackingFrame>();
        private CameraIntrinsics currentIntrinsics;
        private string currentMapId;
        
        // Performance monitoring
        private float lastFrameTime;
        private int framesSent = 0;
        private int framesProcessed = 0;
        private float startTime;

        private void Start()
        {
            ValidateConfiguration();
            startTime = Time.time;
        }

        private void ValidateConfiguration()
        {
            if (arCamera == null)
            {
                arCamera = FindObjectOfType<ARCamera>();
                if (arCamera == null)
                {
                    LogError("ARCamera not found. Please assign an ARCamera component.");
                    return;
                }
            }

            if (unityCamera == null)
            {
                unityCamera = arCamera.GetComponent<Camera>();
            }

            Log("SLAM Client initialized successfully");
        }

        #region Public API

        /// <summary>
        /// Initialize SLAM system with camera parameters
        /// </summary>
        public void InitializeSLAM(string mapId = null)
        {
            if (isInitialized)
            {
                LogWarning("SLAM already initialized");
                return;
            }

            currentMapId = mapId;
            StartCoroutine(InitializeSLAMCoroutine());
        }

        /// <summary>
        /// Start SLAM tracking
        /// </summary>
        public void StartTracking()
        {
            if (!isInitialized)
            {
                LogError("SLAM not initialized. Call InitializeSLAM() first.");
                return;
            }

            if (isTracking)
            {
                LogWarning("SLAM tracking already started");
                return;
            }

            StartCoroutine(StartTrackingCoroutine());
        }

        /// <summary>
        /// Stop SLAM tracking
        /// </summary>
        public void StopTracking()
        {
            if (!isTracking)
            {
                LogWarning("SLAM tracking not active");
                return;
            }

            StartCoroutine(StopTrackingCoroutine());
        }

        /// <summary>
        /// Save current map with given ID
        /// </summary>
        public void SaveMap(string mapId)
        {
            if (!isInitialized)
            {
                LogError("SLAM not initialized");
                return;
            }

            StartCoroutine(SaveMapCoroutine(mapId));
        }

        /// <summary>
        /// Load existing map
        /// </summary>
        public void LoadMap(string mapId)
        {
            if (!isInitialized)
            {
                LogError("SLAM not initialized");
                return;
            }

            StartCoroutine(LoadMapCoroutine(mapId));
        }

        /// <summary>
        /// Get current SLAM status
        /// </summary>
        public void GetStatus()
        {
            StartCoroutine(GetStatusCoroutine());
        }

        #endregion

        #region Frame Processing

        private void Update()
        {
            if (!isTracking) return;

            // Throttle frame processing to configured interval
            if (Time.time - lastFrameTime < trackingIntervalMs / 1000.0f) return;

            ProcessCameraFrame();
            lastFrameTime = Time.time;
        }

        private void ProcessCameraFrame()
        {
            try
            {
                // Get camera frame from AR Foundation
                var texture = GetCameraTexture();
                if (texture == null) return;

                // Convert to byte array
                var imageData = TextureToBase64(texture);
                if (string.IsNullOrEmpty(imageData)) return;

                // Create tracking frame
                var frame = new TrackingFrame
                {
                    timestamp = Time.time,
                    image_data = imageData,
                    camera_id = 0
                };

                // Add to queue (thread-safe)
                lock (frameQueue)
                {
                    if (frameQueue.Count >= maxQueueSize)
                    {
                        frameQueue.Dequeue(); // Remove oldest frame
                    }
                    frameQueue.Enqueue(frame);
                }

                framesSent++;

                // Process frame asynchronously
                StartCoroutine(SendTrackingFrame(frame));
            }
            catch (Exception e)
            {
                LogError($"Error processing camera frame: {e.Message}");
            }
        }

        private Texture2D GetCameraTexture()
        {
            // Get camera image from AR Foundation
            if (arCamera == null || !arCamera.enabled) return null;

            // For AR Foundation, we need to access the camera image
            // This is a simplified approach - in production, you'd use ARCameraBackground
            var renderTexture = RenderTexture.GetTemporary(
                Screen.width, Screen.height, 24, RenderTextureFormat.RGB565
            );

            var previousTarget = RenderTexture.active;
            RenderTexture.active = renderTexture;

            unityCamera.targetTexture = renderTexture;
            unityCamera.Render();

            var texture = new Texture2D(renderTexture.width, renderTexture.height, TextureFormat.RGB565, false);
            texture.ReadPixels(new Rect(0, 0, renderTexture.width, renderTexture.height), 0, 0);
            texture.Apply();

            unityCamera.targetTexture = null;
            RenderTexture.active = previousTarget;
            RenderTexture.ReleaseTemporary(renderTexture);

            return texture;
        }

        private string TextureToBase64(Texture2D texture)
        {
            try
            {
                var bytes = texture.EncodeToJPG(75); // 75% quality for balance of size/quality
                return Convert.ToBase64String(bytes);
            }
            catch (Exception e)
            {
                LogError($"Error encoding texture: {e.Message}");
                return null;
            }
            finally
            {
                if (texture != null)
                {
                    DestroyImmediate(texture);
                }
            }
        }

        #endregion

        #region API Coroutines

        private IEnumerator InitializeSLAMCoroutine()
        {
            Log("Initializing SLAM system...");

            // Get camera intrinsics
            currentIntrinsics = GetCameraIntrinsics();

            var request = new SLAMInitRequest
            {
                camera_intrinsics = currentIntrinsics,
                enable_loop_closure = true,
                enable_relocalization = true,
                map_id = currentMapId
            };

            var json = JsonUtility.ToJson(request);
            var www = CreatePostRequest("/slam/initialize", json);

            yield return www.SendWebRequest();

            if (www.result == UnityWebRequest.Result.Success)
            {
                var response = JsonUtility.FromJson<ApiResponse<object>>(www.downloadHandler.text);
                if (response.status == "success")
                {
                    isInitialized = true;
                    isConnected = true;
                    Log("SLAM system initialized successfully");
                }
                else
                {
                    LogError($"SLAM initialization failed: {response.message}");
                }
            }
            else
            {
                LogError($"Failed to initialize SLAM: {www.error}");
                OnError?.Invoke(www.error);
            }
        }

        private IEnumerator StartTrackingCoroutine()
        {
            Log("Starting SLAM tracking...");

            var www = CreatePostRequest("/slam/start", "{}");
            yield return www.SendWebRequest();

            if (www.result == UnityWebRequest.Result.Success)
            {
                var response = JsonUtility.FromJson<ApiResponse<object>>(www.downloadHandler.text);
                if (response.status == "success")
                {
                    isTracking = true;
                    Log("SLAM tracking started successfully");
                    OnTrackingStateChanged?.Invoke("tracking");
                }
                else
                {
                    LogError($"Failed to start tracking: {response.message}");
                }
            }
            else
            {
                LogError($"Failed to start tracking: {www.error}");
                OnError?.Invoke(www.error);
            }
        }

        private IEnumerator StopTrackingCoroutine()
        {
            Log("Stopping SLAM tracking...");

            var www = CreatePostRequest("/slam/stop", "{}");
            yield return www.SendWebRequest();

            if (www.result == UnityWebRequest.Result.Success)
            {
                isTracking = false;
                Log("SLAM tracking stopped");
                OnTrackingStateChanged?.Invoke("stopped");
            }
            else
            {
                LogError($"Failed to stop tracking: {www.error}");
            }
        }

        private IEnumerator SendTrackingFrame(TrackingFrame frame)
        {
            var json = JsonUtility.ToJson(frame);
            var www = CreatePostRequest("/slam/track", json);

            yield return www.SendWebRequest();

            if (www.result == UnityWebRequest.Result.Success)
            {
                try
                {
                    var poseResponse = JsonUtility.FromJson<PoseResponse>(www.downloadHandler.text);
                    framesProcessed++;
                    
                    // Convert pose to Unity coordinate system
                    var unityPose = ConvertToUnityPose(poseResponse);
                    OnPoseReceived?.Invoke(unityPose);

                    if (enableVerboseLogging && framesProcessed % 30 == 0)
                    {
                        LogFrameStats();
                    }
                }
                catch (Exception e)
                {
                    LogError($"Error parsing pose response: {e.Message}");
                }
            }
            else if (www.responseCode != 0) // Ignore network timeouts
            {
                LogError($"Tracking request failed: {www.error}");
            }
        }

        private IEnumerator SaveMapCoroutine(string mapId)
        {
            Log($"Saving map: {mapId}");

            var www = CreatePostRequest($"/slam/save_map?map_id={mapId}", "{}");
            yield return www.SendWebRequest();

            if (www.result == UnityWebRequest.Result.Success)
            {
                Log($"Map saved successfully: {mapId}");
            }
            else
            {
                LogError($"Failed to save map: {www.error}");
            }
        }

        private IEnumerator LoadMapCoroutine(string mapId)
        {
            Log($"Loading map: {mapId}");

            var www = CreatePostRequest($"/slam/load_map?map_id={mapId}", "{}");
            yield return www.SendWebRequest();

            if (www.result == UnityWebRequest.Result.Success)
            {
                currentMapId = mapId;
                Log($"Map loaded successfully: {mapId}");
            }
            else
            {
                LogError($"Failed to load map: {www.error}");
            }
        }

        private IEnumerator GetStatusCoroutine()
        {
            var www = UnityWebRequest.Get($"{backendUrl}/slam/status");
            yield return www.SendWebRequest();

            if (www.result == UnityWebRequest.Result.Success)
            {
                try
                {
                    var status = JsonUtility.FromJson<SLAMStatus>(www.downloadHandler.text);
                    OnStatusUpdate?.Invoke(status);
                }
                catch (Exception e)
                {
                    LogError($"Error parsing status response: {e.Message}");
                }
            }
            else
            {
                LogError($"Failed to get status: {www.error}");
            }
        }

        #endregion

        #region Utility Methods

        private UnityWebRequest CreatePostRequest(string endpoint, string jsonData)
        {
            var www = new UnityWebRequest($"{backendUrl}{endpoint}", "POST");
            byte[] bodyRaw = Encoding.UTF8.GetBytes(jsonData);
            www.uploadHandler = new UploadHandlerRaw(bodyRaw);
            www.downloadHandler = new DownloadHandlerBuffer();
            www.SetRequestHeader("Content-Type", "application/json");
            www.timeout = 10; // 10 second timeout
            return www;
        }

        private CameraIntrinsics GetCameraIntrinsics()
        {
            // Get camera intrinsics from Unity Camera
            var camera = unityCamera;
            var intrinsics = new CameraIntrinsics();

            // Calculate focal lengths in pixels
            float fovRad = camera.fieldOfView * Mathf.Deg2Rad;
            float aspectRatio = camera.aspect;
            
            intrinsics.width = Screen.width;
            intrinsics.height = Screen.height;
            intrinsics.fps = 30.0f;

            // Calculate focal lengths
            intrinsics.fy = (intrinsics.height / 2.0f) / Mathf.Tan(fovRad / 2.0f);
            intrinsics.fx = intrinsics.fy * aspectRatio;

            // Principal point (assume center)
            intrinsics.cx = intrinsics.width / 2.0f;
            intrinsics.cy = intrinsics.height / 2.0f;

            // Distortion parameters (assume no distortion for Unity camera)
            intrinsics.k1 = 0.0f;
            intrinsics.k2 = 0.0f;
            intrinsics.p1 = 0.0f;
            intrinsics.p2 = 0.0f;
            intrinsics.k3 = 0.0f;

            return intrinsics;
        }

        private PoseResponse ConvertToUnityPose(PoseResponse slamPose)
        {
            // Convert from SLAM coordinate system to Unity coordinate system
            // SLAM: Right-handed, Y-up, Z-forward
            // Unity: Left-handed, Y-up, Z-forward
            
            var unityPose = new PoseResponse
            {
                timestamp = slamPose.timestamp,
                confidence = slamPose.confidence,
                tracking_state = slamPose.tracking_state,
                position = new float[3],
                rotation = new float[4]
            };

            // Convert position (negate X for right-to-left hand conversion)
            unityPose.position[0] = -slamPose.position[0]; // X
            unityPose.position[1] = slamPose.position[1];   // Y
            unityPose.position[2] = slamPose.position[2];   // Z

            // Convert quaternion (negate Y and Z for coordinate system conversion)
            unityPose.rotation[0] = slamPose.rotation[0];   // qw
            unityPose.rotation[1] = -slamPose.rotation[1];  // qx
            unityPose.rotation[2] = slamPose.rotation[2];   // qy
            unityPose.rotation[3] = -slamPose.rotation[3];  // qz

            return unityPose;
        }

        private void LogFrameStats()
        {
            float elapsed = Time.time - startTime;
            float sendFPS = framesSent / elapsed;
            float processFPS = framesProcessed / elapsed;
            
            Log($"SLAM Stats - Sent: {sendFPS:F1} FPS, Processed: {processFPS:F1} FPS, Queue: {frameQueue.Count}");
        }

        private void Log(string message)
        {
            if (enableVerboseLogging)
            {
                Debug.Log($"[SpatialSLAM] {message}");
            }
        }

        private void LogWarning(string message)
        {
            Debug.LogWarning($"[SpatialSLAM] {message}");
        }

        private void LogError(string message)
        {
            Debug.LogError($"[SpatialSLAM] {message}");
            OnError?.Invoke(message);
        }

        #endregion

        #region Unity Lifecycle

        private void OnDestroy()
        {
            if (isTracking)
            {
                StopTracking();
            }
        }

        private void OnApplicationPause(bool pauseStatus)
        {
            if (pauseStatus && isTracking)
            {
                StopTracking();
            }
            else if (!pauseStatus && isInitialized && !isTracking)
            {
                StartTracking();
            }
        }

        #endregion
    }
}