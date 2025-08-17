/*
 * Spatial Platform - Authentication UI
 * Simple UI for user registration and login
 */

using UnityEngine;
using UnityEngine.UI;
using TMPro;
using SpatialPlatform.Auth;

namespace SpatialPlatform.UI
{
    public class AuthenticationUI : MonoBehaviour
    {
        [Header("UI References")]
        [SerializeField] private GameObject loginPanel;
        [SerializeField] private GameObject registerPanel;
        [SerializeField] private GameObject authenticatedPanel;
        
        [Header("Login UI")]
        [SerializeField] private TMP_InputField loginUsernameField;
        [SerializeField] private TMP_InputField loginPasswordField;
        [SerializeField] private Button loginButton;
        [SerializeField] private Button showRegisterButton;
        
        [Header("Register UI")]
        [SerializeField] private TMP_InputField registerUsernameField;
        [SerializeField] private TMP_InputField registerEmailField;
        [SerializeField] private TMP_InputField registerPasswordField;
        [SerializeField] private TMP_InputField registerConfirmPasswordField;
        [SerializeField] private Button registerButton;
        [SerializeField] private Button showLoginButton;
        
        [Header("Authenticated UI")]
        [SerializeField] private TextMeshProUGUI welcomeText;
        [SerializeField] private TextMeshProUGUI userInfoText;
        [SerializeField] private Button logoutButton;
        [SerializeField] private Button createSessionButton;
        
        [Header("Anonymous Session UI")]
        [SerializeField] private GameObject anonymousPanel;
        [SerializeField] private TMP_InputField displayNameField;
        [SerializeField] private Button createAnonymousSessionButton;
        [SerializeField] private TMP_InputField joinCodeField;
        [SerializeField] private Button joinAnonymousSessionButton;
        [SerializeField] private Button skipAuthButton;
        
        [Header("Session Display")]
        [SerializeField] private GameObject sessionInfoPanel;
        [SerializeField] private TextMeshProUGUI shareCodeText;
        [SerializeField] private Button copyCodeButton;
        [SerializeField] private TextMeshProUGUI sessionStatusText;
        
        [Header("Status")]
        [SerializeField] private TextMeshProUGUI statusText;
        [SerializeField] private Color errorColor = Color.red;
        [SerializeField] private Color successColor = Color.green;
        [SerializeField] private Color infoColor = Color.white;
        
        private AuthenticationManager authManager;
        private SpatialPlatform.Multiplayer.MultiplayerManager multiplayerManager;
        
        private void Start()
        {
            // Find authentication manager
            authManager = FindObjectOfType<AuthenticationManager>();
            if (authManager == null)
            {
                ShowStatus("AuthenticationManager not found!", errorColor);
                return;
            }
            
            // Find multiplayer manager
            multiplayerManager = FindObjectOfType<SpatialPlatform.Multiplayer.MultiplayerManager>();
            if (multiplayerManager == null)
            {
                ShowStatus("MultiplayerManager not found!", errorColor);
                return;
            }
            
            // Setup event listeners
            authManager.OnAuthenticationStateChanged += OnAuthenticationStateChanged;
            authManager.OnUserProfileLoaded += OnUserProfileLoaded;
            authManager.OnAuthenticationError += OnAuthenticationError;
            
            // Setup multiplayer event listeners
            multiplayerManager.OnAnonymousSessionCreated += OnAnonymousSessionCreated;
            multiplayerManager.OnAnonymousSessionJoined += OnAnonymousSessionJoined;
            multiplayerManager.OnConnectionStateChanged += OnConnectionStateChanged;
            multiplayerManager.OnError += OnMultiplayerError;
            
            // Setup button listeners
            loginButton.onClick.AddListener(OnLoginClicked);
            registerButton.onClick.AddListener(OnRegisterClicked);
            logoutButton.onClick.AddListener(OnLogoutClicked);
            showRegisterButton.onClick.AddListener(() => ShowPanel(registerPanel));
            showLoginButton.onClick.AddListener(() => ShowPanel(loginPanel));
            
            // Setup anonymous session button listeners
            createAnonymousSessionButton.onClick.AddListener(OnCreateAnonymousSessionClicked);
            joinAnonymousSessionButton.onClick.AddListener(OnJoinAnonymousSessionClicked);
            skipAuthButton.onClick.AddListener(() => ShowPanel(anonymousPanel));
            copyCodeButton.onClick.AddListener(OnCopyCodeClicked);
            
            // Setup input field listeners for Enter key
            loginPasswordField.onSubmit.AddListener((_) => OnLoginClicked());
            registerConfirmPasswordField.onSubmit.AddListener((_) => OnRegisterClicked());
            
            // Initialize UI state
            OnAuthenticationStateChanged(authManager.IsAuthenticated);
            
            if (authManager.IsAuthenticated)
            {
                ShowStatus($"Welcome back, {authManager.Username}!", successColor);
            }
            else
            {
                ShowStatus("Please log in or register to continue", infoColor);
            }
        }
        
        private void OnDestroy()
        {
            // Clean up event listeners
            if (authManager != null)
            {
                authManager.OnAuthenticationStateChanged -= OnAuthenticationStateChanged;
                authManager.OnUserProfileLoaded -= OnUserProfileLoaded;
                authManager.OnAuthenticationError -= OnAuthenticationError;
            }
        }
        
        private void OnLoginClicked()
        {
            string username = loginUsernameField.text.Trim();
            string password = loginPasswordField.text;
            
            // Validation
            if (string.IsNullOrEmpty(username))
            {
                ShowStatus("Username is required", errorColor);
                return;
            }
            
            if (string.IsNullOrEmpty(password))
            {
                ShowStatus("Password is required", errorColor);
                return;
            }
            
            // Disable UI during login
            SetUIEnabled(false);
            ShowStatus("Logging in...", infoColor);
            
            // Attempt login
            authManager.LoginUser(username, password);
        }
        
        private void OnRegisterClicked()
        {
            string username = registerUsernameField.text.Trim();
            string email = registerEmailField.text.Trim();
            string password = registerPasswordField.text;
            string confirmPassword = registerConfirmPasswordField.text;
            
            // Validation
            if (string.IsNullOrEmpty(username))
            {
                ShowStatus("Username is required", errorColor);
                return;
            }
            
            if (username.Length < 3)
            {
                ShowStatus("Username must be at least 3 characters", errorColor);
                return;
            }
            
            if (string.IsNullOrEmpty(email) || !email.Contains("@"))
            {
                ShowStatus("Valid email is required", errorColor);
                return;
            }
            
            if (string.IsNullOrEmpty(password))
            {
                ShowStatus("Password is required", errorColor);
                return;
            }
            
            if (password.Length < 6)
            {
                ShowStatus("Password must be at least 6 characters", errorColor);
                return;
            }
            
            if (password != confirmPassword)
            {
                ShowStatus("Passwords do not match", errorColor);
                return;
            }
            
            // Disable UI during registration
            SetUIEnabled(false);
            ShowStatus("Creating account...", infoColor);
            
            // Attempt registration
            authManager.RegisterUser(username, email, password);
        }
        
        private void OnLogoutClicked()
        {
            SetUIEnabled(false);
            ShowStatus("Logging out...", infoColor);
            authManager.LogoutUser();
        }
        
        private void OnAuthenticationStateChanged(bool isAuthenticated)
        {
            if (isAuthenticated)
            {
                ShowPanel(authenticatedPanel);
                welcomeText.text = $"Welcome, {authManager.Username}!";
                SetUIEnabled(true);
            }
            else
            {
                ShowPanel(loginPanel);
                ClearInputFields();
                SetUIEnabled(true);
            }
        }
        
        private void OnUserProfileLoaded(UserProfile profile)
        {
            userInfoText.text = $"User ID: {profile.id}\\n" +
                               $"Email: {profile.email}\\n" +
                               $"Roles: {string.Join(\", \", profile.roles)}\\n" +
                               $"Member since: {profile.created_at}";
            
            ShowStatus($"Profile loaded for {profile.username}", successColor);
        }
        
        private void OnAuthenticationError(string errorMessage)
        {
            ShowStatus($"Error: {errorMessage}", errorColor);
            SetUIEnabled(true);
        }
        
        private void ShowPanel(GameObject panelToShow)
        {
            loginPanel.SetActive(panelToShow == loginPanel);
            registerPanel.SetActive(panelToShow == registerPanel);
            authenticatedPanel.SetActive(panelToShow == authenticatedPanel);
            if (anonymousPanel != null)
                anonymousPanel.SetActive(panelToShow == anonymousPanel);
        }
        
        private void ShowStatus(string message, Color color)
        {
            if (statusText != null)
            {
                statusText.text = message;
                statusText.color = color;
            }
            
            Debug.Log($"Auth UI: {message}");
        }
        
        private void SetUIEnabled(bool enabled)
        {
            // Login UI
            loginButton.interactable = enabled;
            showRegisterButton.interactable = enabled;
            loginUsernameField.interactable = enabled;
            loginPasswordField.interactable = enabled;
            
            // Register UI
            registerButton.interactable = enabled;
            showLoginButton.interactable = enabled;
            registerUsernameField.interactable = enabled;
            registerEmailField.interactable = enabled;
            registerPasswordField.interactable = enabled;
            registerConfirmPasswordField.interactable = enabled;
            
            // Authenticated UI
            logoutButton.interactable = enabled;
            if (createSessionButton != null)
                createSessionButton.interactable = enabled;
        }
        
        private void ClearInputFields()
        {
            loginUsernameField.text = "";
            loginPasswordField.text = "";
            registerUsernameField.text = "";
            registerEmailField.text = "";
            registerPasswordField.text = "";
            registerConfirmPasswordField.text = "";
        }
        
        public void OnCreateSessionClicked()
        {
            var multiplayerManager = FindObjectOfType<SpatialPlatform.Multiplayer.MultiplayerManager>();
            if (multiplayerManager != null)
            {
                ShowStatus("Creating session...", infoColor);
                multiplayerManager.CreateSession();
            }
            else
            {
                ShowStatus("MultiplayerManager not found!", errorColor);
            }
        }
        
        // Anonymous session methods
        private void OnCreateAnonymousSessionClicked()
        {
            if (multiplayerManager != null)
            {
                multiplayerManager.anonymousDisplayName = displayNameField.text;
                ShowStatus("Creating anonymous session...", infoColor);
                multiplayerManager.CreateAnonymousSession();
            }
        }
        
        private void OnJoinAnonymousSessionClicked()
        {
            string code = joinCodeField.text.Trim().ToUpper();
            if (string.IsNullOrEmpty(code))
            {
                ShowStatus("Please enter a session code", errorColor);
                return;
            }
            
            if (code.Length != 6)
            {
                ShowStatus("Session code must be 6 characters", errorColor);
                return;
            }
            
            if (multiplayerManager != null)
            {
                multiplayerManager.anonymousDisplayName = displayNameField.text;
                ShowStatus($"Joining session {code}...", infoColor);
                multiplayerManager.JoinAnonymousSession(code);
            }
        }
        
        private void OnCopyCodeClicked()
        {
            if (!string.IsNullOrEmpty(multiplayerManager.AnonymousShareCode))
            {
                GUIUtility.systemCopyBuffer = multiplayerManager.AnonymousShareCode;
                ShowStatus("Share code copied to clipboard!", successColor);
            }
        }
        
        // Anonymous session event handlers
        private void OnAnonymousSessionCreated(SpatialPlatform.Multiplayer.AnonymousSessionResponse response)
        {
            ShowStatus($"Anonymous session created!", successColor);
            ShowSessionInfo(response.share_code);
        }
        
        private void OnAnonymousSessionJoined(SpatialPlatform.Multiplayer.AnonymousJoinResponse response)
        {
            ShowStatus($"Joined anonymous session!", successColor);
            ShowSessionInfo(response.share_code);
        }
        
        private void OnConnectionStateChanged(bool isConnected)
        {
            if (isConnected)
            {
                ShowStatus("Connected to session!", successColor);
                if (sessionStatusText != null)
                    sessionStatusText.text = "Status: Connected";
            }
            else
            {
                ShowStatus("Disconnected from session", infoColor);
                if (sessionStatusText != null)
                    sessionStatusText.text = "Status: Disconnected";
            }
        }
        
        private void OnMultiplayerError(string error)
        {
            ShowStatus($"Error: {error}", errorColor);
        }
        
        private void ShowSessionInfo(string shareCode)
        {
            if (sessionInfoPanel != null)
                sessionInfoPanel.SetActive(true);
                
            if (shareCodeText != null)
                shareCodeText.text = $"Share Code: {shareCode}";
                
            if (sessionStatusText != null)
                sessionStatusText.text = "Status: Connecting...";
        }
        
        private void UpdatePanelVisibility()
        {
            bool showAnonymous = anonymousPanel != null;
            bool showSessionInfo = sessionInfoPanel != null && multiplayerManager.IsAnonymousSession;
            
            if (anonymousPanel != null)
                anonymousPanel.SetActive(showAnonymous && !authManager.IsAuthenticated);
                
            if (sessionInfoPanel != null)
                sessionInfoPanel.SetActive(showSessionInfo);
        }
    }
}