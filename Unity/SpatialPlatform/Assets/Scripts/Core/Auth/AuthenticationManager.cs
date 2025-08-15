/*
 * Spatial Platform - Authentication Manager
 * Handles user authentication, token management, and secure API communication
 */

using System;
using System.Collections;
using System.Text;
using UnityEngine;
using UnityEngine.Networking;
using Newtonsoft.Json;

namespace SpatialPlatform.Auth
{
    [Serializable]
    public class UserCredentials
    {
        public string username;
        public string email;
        public string password;
    }

    [Serializable]
    public class AuthResponse
    {
        public string access_token;
        public string refresh_token;
        public string token_type;
        public int expires_in;
        public string user_id;
        public string username;
        public string[] roles;
    }

    [Serializable]
    public class UserProfile
    {
        public string id;
        public string username;
        public string email;
        public string[] roles;
        public string created_at;
        public string last_active;
        public bool is_active;
    }

    [Serializable]
    public class TokenRefreshRequest
    {
        public string refresh_token;
    }

    [Serializable]
    public class AuthErrorResponse
    {
        public bool error;
        public string message;
        public string code;
    }

    public class AuthenticationManager : MonoBehaviour
    {
        [Header("Server Settings")]
        [SerializeField] private string serverHost = "localhost";
        [SerializeField] private int serverPort = 8080;
        [SerializeField] private bool useSSL = false;
        
        [Header("Token Management")]
        [SerializeField] private bool autoRefreshTokens = true;
        [SerializeField] private float tokenRefreshThreshold = 300f; // 5 minutes before expiry
        
        // Authentication state
        private string accessToken;
        private string refreshToken;
        private string userId;
        private string username;
        private string[] userRoles;
        private DateTime tokenExpiry;
        private bool isAuthenticated = false;
        
        // Events
        public event Action<bool> OnAuthenticationStateChanged;
        public event Action<UserProfile> OnUserProfileLoaded;
        public event Action<string> OnAuthenticationError;
        
        // Properties
        public bool IsAuthenticated => isAuthenticated && !string.IsNullOrEmpty(accessToken);
        public string AccessToken => accessToken;
        public string UserId => userId;
        public string Username => username;
        public string[] UserRoles => userRoles;
        
        private void Start()
        {
            // Try to load saved credentials
            LoadSavedCredentials();
            
            // Start token refresh routine
            if (autoRefreshTokens)
            {
                StartCoroutine(TokenRefreshRoutine());
            }
        }
        
        public async void RegisterUser(string username, string email, string password)
        {
            var credentials = new UserCredentials
            {
                username = username,
                email = email,
                password = password
            };
            
            string url = $"http{(useSSL ? "s" : "")}://{serverHost}:{serverPort}/api/v1/auth/register";
            yield return StartCoroutine(SendAuthRequest(url, credentials, OnRegistrationComplete));
        }
        
        public async void LoginUser(string username, string password)
        {
            var credentials = new UserCredentials
            {
                username = username,
                password = password
            };
            
            string url = $"http{(useSSL ? "s" : "")}://{serverHost}:{serverPort}/api/v1/auth/login";
            yield return StartCoroutine(SendAuthRequest(url, credentials, OnLoginComplete));
        }
        
        public async void LogoutUser()
        {
            if (!IsAuthenticated)
            {
                Debug.LogWarning("User is not authenticated");
                return;
            }
            
            try
            {
                string url = $"http{(useSSL ? "s" : "")}://{serverHost}:{serverPort}/api/v1/auth/logout";
                var logoutRequest = new TokenRefreshRequest { refresh_token = refreshToken };
                
                yield return StartCoroutine(SendAuthenticatedRequest(url, logoutRequest, null));
                
                // Clear local credentials
                ClearCredentials();
                Debug.Log("User logged out successfully");
                
                OnAuthenticationStateChanged?.Invoke(false);
            }
            catch (Exception e)
            {
                Debug.LogError($"Logout error: {e.Message}");
                OnAuthenticationError?.Invoke($"Logout failed: {e.Message}");
            }
        }
        
        public async void RefreshAccessToken()
        {
            if (string.IsNullOrEmpty(refreshToken))
            {
                Debug.LogError("No refresh token available");
                OnAuthenticationError?.Invoke("No refresh token available");
                return;
            }
            
            try
            {
                string url = $"http{(useSSL ? "s" : "")}://{serverHost}:{serverPort}/api/v1/auth/refresh";
                var refreshRequest = new TokenRefreshRequest { refresh_token = refreshToken };
                
                yield return StartCoroutine(SendAuthRequest(url, refreshRequest, OnTokenRefreshComplete));
            }
            catch (Exception e)
            {
                Debug.LogError($"Token refresh error: {e.Message}");
                OnAuthenticationError?.Invoke($"Token refresh failed: {e.Message}");
            }
        }
        
        public async void LoadUserProfile()
        {
            if (!IsAuthenticated)
            {
                Debug.LogWarning("User is not authenticated");
                return;
            }
            
            try
            {
                string url = $"http{(useSSL ? "s" : "")}://{serverHost}:{serverPort}/api/v1/auth/profile";
                yield return StartCoroutine(SendAuthenticatedRequest(url, null, OnProfileLoadComplete));
            }
            catch (Exception e)
            {
                Debug.LogError($"Profile load error: {e.Message}");
                OnAuthenticationError?.Invoke($"Failed to load profile: {e.Message}");
            }
        }
        
        public UnityWebRequest CreateAuthenticatedRequest(string url, string method = "GET", object data = null)
        {
            UnityWebRequest request = new UnityWebRequest(url, method);
            
            // Add authentication header
            if (IsAuthenticated)
            {
                request.SetRequestHeader("Authorization", $"Bearer {accessToken}");
            }
            
            // Add content if provided
            if (data != null)
            {
                string jsonData = JsonConvert.SerializeObject(data);
                byte[] bodyRaw = Encoding.UTF8.GetBytes(jsonData);
                request.uploadHandler = new UploadHandlerRaw(bodyRaw);
                request.SetRequestHeader("Content-Type", "application/json");
            }
            
            request.downloadHandler = new DownloadHandlerBuffer();
            return request;
        }
        
        private IEnumerator SendAuthRequest(string url, object data, Action<UnityWebRequest> callback)
        {
            string jsonData = JsonConvert.SerializeObject(data);
            
            using (UnityWebRequest request = new UnityWebRequest(url, "POST"))
            {
                byte[] bodyRaw = Encoding.UTF8.GetBytes(jsonData);
                request.uploadHandler = new UploadHandlerRaw(bodyRaw);
                request.downloadHandler = new DownloadHandlerBuffer();
                request.SetRequestHeader("Content-Type", "application/json");
                
                yield return request.SendWebRequest();
                
                callback?.Invoke(request);
            }
        }
        
        private IEnumerator SendAuthenticatedRequest(string url, object data, Action<UnityWebRequest> callback)
        {
            using (UnityWebRequest request = CreateAuthenticatedRequest(url, data != null ? "POST" : "GET", data))
            {
                yield return request.SendWebRequest();
                callback?.Invoke(request);
            }
        }
        
        private void OnRegistrationComplete(UnityWebRequest request)
        {
            HandleAuthResponse(request, "Registration");
        }
        
        private void OnLoginComplete(UnityWebRequest request)
        {
            HandleAuthResponse(request, "Login");
        }
        
        private void OnTokenRefreshComplete(UnityWebRequest request)
        {
            if (request.result == UnityWebRequest.Result.Success)
            {
                try
                {
                    var response = JsonConvert.DeserializeObject<AuthResponse>(request.downloadHandler.text);
                    accessToken = response.access_token;
                    tokenExpiry = DateTime.UtcNow.AddSeconds(response.expires_in);
                    
                    SaveCredentials();
                    Debug.Log("Access token refreshed successfully");
                }
                catch (Exception e)
                {
                    Debug.LogError($"Token refresh parsing error: {e.Message}");
                    OnAuthenticationError?.Invoke("Failed to parse token refresh response");
                }
            }
            else
            {
                Debug.LogError($"Token refresh failed: {request.error}");
                OnAuthenticationError?.Invoke($"Token refresh failed: {request.error}");
                
                // Clear credentials on refresh failure
                ClearCredentials();
                OnAuthenticationStateChanged?.Invoke(false);
            }
        }
        
        private void OnProfileLoadComplete(UnityWebRequest request)
        {
            if (request.result == UnityWebRequest.Result.Success)
            {
                try
                {
                    var profile = JsonConvert.DeserializeObject<UserProfile>(request.downloadHandler.text);
                    OnUserProfileLoaded?.Invoke(profile);
                    Debug.Log($"Profile loaded for user: {profile.username}");
                }
                catch (Exception e)
                {
                    Debug.LogError($"Profile parsing error: {e.Message}");
                    OnAuthenticationError?.Invoke("Failed to parse profile response");
                }
            }
            else
            {
                Debug.LogError($"Profile load failed: {request.error}");
                OnAuthenticationError?.Invoke($"Profile load failed: {request.error}");
            }
        }
        
        private void HandleAuthResponse(UnityWebRequest request, string operation)
        {
            if (request.result == UnityWebRequest.Result.Success)
            {
                try
                {
                    var response = JsonConvert.DeserializeObject<AuthResponse>(request.downloadHandler.text);
                    
                    // Store authentication data
                    accessToken = response.access_token;
                    refreshToken = response.refresh_token;
                    userId = response.user_id;
                    username = response.username;
                    userRoles = response.roles;
                    tokenExpiry = DateTime.UtcNow.AddSeconds(response.expires_in);
                    isAuthenticated = true;
                    
                    // Save credentials for persistence
                    SaveCredentials();
                    
                    Debug.Log($"{operation} successful for user: {username}");
                    OnAuthenticationStateChanged?.Invoke(true);
                    
                    // Load user profile
                    LoadUserProfile();
                }
                catch (Exception e)
                {
                    Debug.LogError($"{operation} response parsing error: {e.Message}");
                    OnAuthenticationError?.Invoke($"Failed to parse {operation.ToLower()} response");
                }
            }
            else
            {
                try
                {
                    var errorResponse = JsonConvert.DeserializeObject<AuthErrorResponse>(request.downloadHandler.text);
                    Debug.LogError($"{operation} failed: {errorResponse.message}");
                    OnAuthenticationError?.Invoke($"{operation} failed: {errorResponse.message}");
                }
                catch
                {
                    Debug.LogError($"{operation} failed: {request.error}");
                    OnAuthenticationError?.Invoke($"{operation} failed: {request.error}");
                }
            }
        }
        
        private void SaveCredentials()
        {
            try
            {
                PlayerPrefs.SetString("access_token", accessToken ?? "");
                PlayerPrefs.SetString("refresh_token", refreshToken ?? "");
                PlayerPrefs.SetString("user_id", userId ?? "");
                PlayerPrefs.SetString("username", username ?? "");
                PlayerPrefs.SetString("token_expiry", tokenExpiry.ToBinary().ToString());
                
                if (userRoles != null)
                {
                    PlayerPrefs.SetString("user_roles", string.Join(",", userRoles));
                }
                
                PlayerPrefs.Save();
            }
            catch (Exception e)
            {
                Debug.LogError($"Failed to save credentials: {e.Message}");
            }
        }
        
        private void LoadSavedCredentials()
        {
            try
            {
                accessToken = PlayerPrefs.GetString("access_token", "");
                refreshToken = PlayerPrefs.GetString("refresh_token", "");
                userId = PlayerPrefs.GetString("user_id", "");
                username = PlayerPrefs.GetString("username", "");
                
                string expiryString = PlayerPrefs.GetString("token_expiry", "");
                if (!string.IsNullOrEmpty(expiryString) && long.TryParse(expiryString, out long expiryBinary))
                {
                    tokenExpiry = DateTime.FromBinary(expiryBinary);
                }
                
                string rolesString = PlayerPrefs.GetString("user_roles", "");
                if (!string.IsNullOrEmpty(rolesString))
                {
                    userRoles = rolesString.Split(',');
                }
                
                // Check if token is still valid
                if (!string.IsNullOrEmpty(accessToken) && tokenExpiry > DateTime.UtcNow)
                {
                    isAuthenticated = true;
                    Debug.Log($"Loaded saved credentials for user: {username}");
                    OnAuthenticationStateChanged?.Invoke(true);
                }
                else if (!string.IsNullOrEmpty(refreshToken))
                {
                    // Try to refresh token
                    RefreshAccessToken();
                }
                else
                {
                    ClearCredentials();
                }
            }
            catch (Exception e)
            {
                Debug.LogError($"Failed to load saved credentials: {e.Message}");
                ClearCredentials();
            }
        }
        
        private void ClearCredentials()
        {
            accessToken = "";
            refreshToken = "";
            userId = "";
            username = "";
            userRoles = null;
            tokenExpiry = DateTime.MinValue;
            isAuthenticated = false;
            
            // Clear saved credentials
            PlayerPrefs.DeleteKey("access_token");
            PlayerPrefs.DeleteKey("refresh_token");
            PlayerPrefs.DeleteKey("user_id");
            PlayerPrefs.DeleteKey("username");
            PlayerPrefs.DeleteKey("user_roles");
            PlayerPrefs.DeleteKey("token_expiry");
            PlayerPrefs.Save();
        }
        
        private IEnumerator TokenRefreshRoutine()
        {
            while (true)
            {
                yield return new WaitForSeconds(60f); // Check every minute
                
                if (IsAuthenticated && autoRefreshTokens)
                {
                    // Check if token needs refresh
                    TimeSpan timeUntilExpiry = tokenExpiry - DateTime.UtcNow;
                    if (timeUntilExpiry.TotalSeconds <= tokenRefreshThreshold)
                    {
                        Debug.Log("Token approaching expiry, refreshing...");
                        RefreshAccessToken();
                    }
                }
            }
        }
        
        private void OnApplicationPause(bool pauseStatus)
        {
            if (!pauseStatus && IsAuthenticated)
            {
                // App resumed - check if token is still valid
                if (tokenExpiry <= DateTime.UtcNow)
                {
                    RefreshAccessToken();
                }
            }
        }
        
        private void OnDestroy()
        {
            StopAllCoroutines();
        }
    }
}