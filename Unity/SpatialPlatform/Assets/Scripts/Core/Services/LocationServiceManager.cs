using System;
using System.Collections;
using UnityEngine;

namespace SpatialPlatform.Core.Services
{
    /// <summary>
    /// Enterprise-grade location services with fallback mechanisms
    /// Handles GPS, network-based location, and location permission management
    /// </summary>
    public class LocationServiceManager : MonoBehaviour
    {
        [Header("Location Configuration")]
        [SerializeField] private float desiredAccuracyInMeters = 3f;
        [SerializeField] private float updateDistanceInMeters = 1f;
        [SerializeField] private float timeoutSeconds = 30f;
        [SerializeField] private bool enableNetworkFallback = true;
        
        // Location data
        public struct LocationData
        {
            public double latitude;
            public double longitude;
            public float altitude;
            public float horizontalAccuracy;
            public float verticalAccuracy;
            public DateTime timestamp;
            public LocationSource source;
        }
        
        public enum LocationSource
        {
            Unknown,
            GPS,
            Network,
            Cached,
            Manual
        }
        
        public enum LocationServiceState
        {
            Stopped,
            Initializing,
            Running,
            Failed,
            PermissionDenied,
            ServiceDisabled
        }
        
        private LocationServiceState currentState = LocationServiceState.Stopped;
        private LocationData lastKnownLocation;
        private LocationData? cachedLocation;
        private float lastUpdateTime;
        
        // Events
        public static event Action<LocationData> OnLocationUpdated;
        public static event Action<LocationServiceState> OnLocationServiceStateChanged;
        public static event Action<string> OnLocationError;
        
        // Properties
        public LocationServiceState CurrentState => currentState;
        public LocationData LastKnownLocation => lastKnownLocation;
        public bool HasValidLocation => currentState == LocationServiceState.Running && 
                                       Time.time - lastUpdateTime < 60f; // Valid for 1 minute
        
        // Network-based location API configuration
        private const string IP_LOCATION_API = "http://ip-api.com/json/";
        private WWW networkLocationRequest;
        
        public void StartLocationServices(Action<bool, string> callback = null)
        {
            StartCoroutine(InitializeLocationServices(callback));
        }
        
        private IEnumerator InitializeLocationServices(Action<bool, string> callback)
        {
            Debug.Log("Starting location services...");
            ChangeState(LocationServiceState.Initializing);
            
            // First check if location services are available
            if (!SystemInfo.supportsLocationService)
            {
                var error = "Location services not supported on this device";
                Debug.LogError(error);
                ChangeState(LocationServiceState.ServiceDisabled);
                callback?.Invoke(false, error);
                yield break;
            }
            
            // Check permissions
            yield return StartCoroutine(RequestLocationPermission());
            
            if (currentState == LocationServiceState.PermissionDenied)
            {
                var error = "Location permission denied by user";
                Debug.LogWarning(error);
                
                // Try network-based location as fallback
                if (enableNetworkFallback)
                {
                    yield return StartCoroutine(TryNetworkLocation());
                }
                
                callback?.Invoke(currentState == LocationServiceState.Running, error);
                yield break;
            }
            
            // Start GPS location services
            Input.location.Start(desiredAccuracyInMeters, updateDistanceInMeters);
            
            // Wait for location service to initialize
            float startTime = Time.time;
            while (Input.location.status == LocationServiceStatus.Initializing && 
                   Time.time - startTime < timeoutSeconds)
            {
                yield return new WaitForSeconds(0.5f);
            }
            
            // Check final status
            if (Input.location.status == LocationServiceStatus.Failed)
            {
                var error = "Failed to start GPS location services";
                Debug.LogError(error);
                ChangeState(LocationServiceState.Failed);
                
                // Try network location fallback
                if (enableNetworkFallback)
                {
                    Debug.Log("Attempting network-based location fallback...");
                    yield return StartCoroutine(TryNetworkLocation());
                }
                
                callback?.Invoke(currentState == LocationServiceState.Running, error);
                yield break;
            }
            
            if (Input.location.status == LocationServiceStatus.Running)
            {
                Debug.Log("GPS location services started successfully");
                ChangeState(LocationServiceState.Running);
                
                // Get initial location
                UpdateLocationFromGPS();
                
                callback?.Invoke(true, null);
            }
            else
            {
                var error = $"Location service in unexpected state: {Input.location.status}";
                Debug.LogError(error);
                ChangeState(LocationServiceState.Failed);
                callback?.Invoke(false, error);
            }
        }
        
        private IEnumerator RequestLocationPermission()
        {
            // Request permission if not already granted
            if (!Input.location.isEnabledByUser)
            {
                Debug.LogWarning("Location not enabled by user");
                ChangeState(LocationServiceState.PermissionDenied);
                yield break;
            }
            
            // On some platforms, we need to explicitly request permission
#if UNITY_ANDROID && !UNITY_EDITOR
            if (!Permission.HasUserAuthorizedPermission(Permission.FineLocation))
            {
                Permission.RequestUserPermission(Permission.FineLocation);
                
                // Wait for user response
                float startTime = Time.time;
                while (!Permission.HasUserAuthorizedPermission(Permission.FineLocation) && 
                       Time.time - startTime < 10f)
                {
                    yield return new WaitForSeconds(0.1f);
                }
                
                if (!Permission.HasUserAuthorizedPermission(Permission.FineLocation))
                {
                    ChangeState(LocationServiceState.PermissionDenied);
                    yield break;
                }
            }
#endif
            
            Debug.Log("Location permission granted");
        }
        
        private IEnumerator TryNetworkLocation()
        {
            Debug.Log("Attempting to get location via IP geolocation...");
            
            // Use IP-based geolocation as fallback
            networkLocationRequest = new WWW(IP_LOCATION_API);
            yield return networkLocationRequest;
            
            if (string.IsNullOrEmpty(networkLocationRequest.error))
            {
                try
                {
                    var response = JsonUtility.FromJson<IPLocationResponse>(networkLocationRequest.text);
                    
                    if (response.status == "success")
                    {
                        var networkLocation = new LocationData
                        {
                            latitude = response.lat,
                            longitude = response.lon,
                            altitude = 0f,
                            horizontalAccuracy = 1000f, // Network location is less accurate
                            verticalAccuracy = -1f,
                            timestamp = DateTime.Now,
                            source = LocationSource.Network
                        };
                        
                        lastKnownLocation = networkLocation;
                        cachedLocation = networkLocation;
                        lastUpdateTime = Time.time;
                        ChangeState(LocationServiceState.Running);
                        
                        OnLocationUpdated?.Invoke(networkLocation);
                        Debug.Log($"Network location acquired: {response.lat:F6}, {response.lon:F6} ({response.city}, {response.country})");
                    }
                    else
                    {
                        Debug.LogWarning($"Network location failed: {response.message}");
                    }
                }
                catch (Exception e)
                {
                    Debug.LogError($"Failed to parse network location response: {e.Message}");
                }
            }
            else
            {
                Debug.LogError($"Network location request failed: {networkLocationRequest.error}");
            }
            
            networkLocationRequest.Dispose();
            networkLocationRequest = null;
        }
        
        void Update()
        {
            if (currentState == LocationServiceState.Running)
            {
                // Update location from GPS if available and enough time has passed
                if (Input.location.status == LocationServiceStatus.Running)
                {
                    if (Time.time - lastUpdateTime > 1f) // Update at most once per second
                    {
                        UpdateLocationFromGPS();
                    }
                }
                else if (Input.location.status == LocationServiceStatus.Failed)
                {
                    Debug.LogWarning("GPS location service failed during operation");
                    ChangeState(LocationServiceState.Failed);
                    OnLocationError?.Invoke("GPS service failed during operation");
                }
            }
        }
        
        private void UpdateLocationFromGPS()
        {
            if (Input.location.status != LocationServiceStatus.Running)
                return;
                
            var info = Input.location.lastData;
            
            // Validate location data quality
            if (info.horizontalAccuracy < 0)
            {
                Debug.LogWarning("Invalid GPS location data received");
                return;
            }
            
            // Ignore low-accuracy readings if we have better data
            if (HasValidLocation && info.horizontalAccuracy > lastKnownLocation.horizontalAccuracy * 2f)
            {
                Debug.LogWarning($"Ignoring low-accuracy GPS reading: {info.horizontalAccuracy}m");
                return;
            }
            
            var gpsLocation = new LocationData
            {
                latitude = info.latitude,
                longitude = info.longitude,
                altitude = info.altitude,
                horizontalAccuracy = info.horizontalAccuracy,
                verticalAccuracy = info.verticalAccuracy,
                timestamp = DateTime.Now,
                source = LocationSource.GPS
            };
            
            // Check if location has changed significantly
            if (HasValidLocation)
            {
                float distance = CalculateDistance(lastKnownLocation, gpsLocation);
                if (distance < updateDistanceInMeters && 
                    (DateTime.Now - lastKnownLocation.timestamp).TotalSeconds < 30)
                {
                    // Location hasn't changed enough, skip update
                    return;
                }
            }
            
            lastKnownLocation = gpsLocation;
            cachedLocation = gpsLocation;
            lastUpdateTime = Time.time;
            
            OnLocationUpdated?.Invoke(gpsLocation);
            
            Debug.Log($"GPS location updated: {info.latitude:F6}, {info.longitude:F6} " +
                     $"(accuracy: {info.horizontalAccuracy:F1}m)");
        }
        
        public void StopLocationServices()
        {
            if (currentState == LocationServiceState.Running)
            {
                Input.location.Stop();
                ChangeState(LocationServiceState.Stopped);
                Debug.Log("Location services stopped");
            }
        }
        
        public LocationData? GetCachedLocation()
        {
            return cachedLocation;
        }
        
        public void SetManualLocation(double latitude, double longitude, string source = "Manual")
        {
            var manualLocation = new LocationData
            {
                latitude = latitude,
                longitude = longitude,
                altitude = 0f,
                horizontalAccuracy = 5f, // Assume good accuracy for manual input
                verticalAccuracy = -1f,
                timestamp = DateTime.Now,
                source = LocationSource.Manual
            };
            
            lastKnownLocation = manualLocation;
            cachedLocation = manualLocation;
            lastUpdateTime = Time.time;
            
            if (currentState != LocationServiceState.Running)
            {
                ChangeState(LocationServiceState.Running);
            }
            
            OnLocationUpdated?.Invoke(manualLocation);
            Debug.Log($"Manual location set: {latitude:F6}, {longitude:F6}");
        }
        
        public static float CalculateDistance(LocationData location1, LocationData location2)
        {
            return CalculateDistance(location1.latitude, location1.longitude,
                                   location2.latitude, location2.longitude);
        }
        
        public static float CalculateDistance(double lat1, double lon1, double lat2, double lon2)
        {
            // Haversine formula for calculating distance between two points on Earth
            const double R = 6371000; // Earth's radius in meters
            
            double lat1Rad = lat1 * Mathf.Deg2Rad;
            double lat2Rad = lat2 * Mathf.Deg2Rad;
            double deltaLatRad = (lat2 - lat1) * Mathf.Deg2Rad;
            double deltaLonRad = (lon2 - lon1) * Mathf.Deg2Rad;
            
            double a = Math.Sin(deltaLatRad / 2) * Math.Sin(deltaLatRad / 2) +
                      Math.Cos(lat1Rad) * Math.Cos(lat2Rad) *
                      Math.Sin(deltaLonRad / 2) * Math.Sin(deltaLonRad / 2);
            
            double c = 2 * Math.Atan2(Math.Sqrt(a), Math.Sqrt(1 - a));
            
            return (float)(R * c);
        }
        
        public Vector2 LocationToVector2()
        {
            return new Vector2((float)lastKnownLocation.latitude, (float)lastKnownLocation.longitude);
        }
        
        public bool IsLocationValid(float maxAgeSeconds = 60f)
        {
            return HasValidLocation && 
                   (DateTime.Now - lastKnownLocation.timestamp).TotalSeconds < maxAgeSeconds;
        }
        
        private void ChangeState(LocationServiceState newState)
        {
            if (currentState != newState)
            {
                var previousState = currentState;
                currentState = newState;
                
                Debug.Log($"Location service state changed: {previousState} -> {newState}");
                OnLocationServiceStateChanged?.Invoke(newState);
            }
        }
        
        void OnApplicationPause(bool pauseStatus)
        {
            if (pauseStatus && currentState == LocationServiceState.Running)
            {
                // Pause location updates to save battery
                Debug.Log("Pausing location services due to app pause");
            }
            else if (!pauseStatus && currentState == LocationServiceState.Running)
            {
                // Resume location updates
                Debug.Log("Resuming location services");
            }
        }
        
        void OnDestroy()
        {
            StopLocationServices();
            
            if (networkLocationRequest != null)
            {
                networkLocationRequest.Dispose();
            }
        }
        
        // Data structure for IP-based location API response
        [Serializable]
        private class IPLocationResponse
        {
            public string status;
            public string message;
            public string country;
            public string countryCode;
            public string region;
            public string regionName;
            public string city;
            public string zip;
            public double lat;
            public double lon;
            public string timezone;
            public string isp;
            public string org;
            public string as_name;
        }
        
        // Debug methods for development
        [System.Diagnostics.Conditional("DEVELOPMENT_BUILD")]
        public void DebugLogLocationInfo()
        {
            if (HasValidLocation)
            {
                Debug.Log($"Current Location: {lastKnownLocation.latitude:F6}, {lastKnownLocation.longitude:F6}\n" +
                         $"Accuracy: {lastKnownLocation.horizontalAccuracy:F1}m\n" +
                         $"Source: {lastKnownLocation.source}\n" +
                         $"Age: {(DateTime.Now - lastKnownLocation.timestamp).TotalSeconds:F1}s");
            }
            else
            {
                Debug.Log($"No valid location available. State: {currentState}");
            }
        }
    }
}