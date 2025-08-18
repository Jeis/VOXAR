using System;
using System.Threading.Tasks;
using UnityEngine;
using Nakama;

namespace SpatialPlatform.Nakama.Enterprise
{
    /// <summary>
    /// Enterprise Connection Manager for Nakama
    /// Handles authentication, socket management, and reconnection logic
    /// </summary>
    public class ConnectionManager
    {
        private readonly ConnectionConfig config;
        private IClient client;
        private ISocket socket;
        private ISession session;
        private int reconnectAttempts = 0;
        
        public bool IsConnected => socket?.IsConnected ?? false;
        public IClient Client => client;
        public ISocket Socket => socket;
        public ISession Session => session;
        
        public event Action<bool> OnConnectionChanged;
        public event Action<string> OnError;
        
        public ConnectionManager(ConnectionConfig config)
        {
            this.config = config;
            InitializeClient();
        }
        
        private void InitializeClient()
        {
            client = new Client(config.scheme, config.host, config.port, config.serverKey, UnityWebRequestAdapter.Instance)
            {
                Timeout = 10,
                RetryConfiguration = new RetryConfiguration(
                    baseDelayMs: 500,
                    maxRetries: config.maxReconnectAttempts,
                    jitter: RetryJitter.FullJitter
                )
            };
            
            Debug.Log("[ConnectionManager] Nakama client initialized");
        }
        
        public async Task<bool> AuthenticateAndConnect(string displayName = null)
        {
            try
            {
                // Authenticate user
                await AuthenticateUser(displayName);
                
                // Create socket connection
                socket = client.NewSocket();
                await socket.ConnectAsync(session, true);
                
                // Setup socket event handlers
                SetupSocketHandlers();
                
                reconnectAttempts = 0;
                OnConnectionChanged?.Invoke(true);
                
                Debug.Log($"[ConnectionManager] Connected successfully as {session.Username}");
                return true;
            }
            catch (Exception e)
            {
                OnError?.Invoke($"Authentication/Connection failed: {e.Message}");
                return false;
            }
        }
        
        private async Task AuthenticateUser(string displayName)
        {
            if (config.requireAuthentication && !string.IsNullOrEmpty(config.apiKey))
            {
                // Authenticate with API key for enterprise
                session = await client.AuthenticateCustomAsync(config.apiKey, displayName);
            }
            else
            {
                // Anonymous authentication for development
                var deviceId = SystemInfo.deviceUniqueIdentifier;
                session = await client.AuthenticateDeviceAsync(deviceId, 
                    displayName ?? $"Player_{UnityEngine.Random.Range(1000, 9999)}");
            }
        }
        
        private void SetupSocketHandlers()
        {
            socket.Closed += OnSocketClosed;
            socket.Connected += OnSocketConnected;
            socket.ReceivedError += OnSocketError;
        }
        
        private void OnSocketConnected()
        {
            Debug.Log("[ConnectionManager] Socket connected");
            OnConnectionChanged?.Invoke(true);
        }
        
        private void OnSocketClosed()
        {
            Debug.Log("[ConnectionManager] Socket disconnected");
            OnConnectionChanged?.Invoke(false);
            
            if (config.autoReconnect && reconnectAttempts < config.maxReconnectAttempts)
            {
                _ = AttemptReconnection();
            }
        }
        
        private void OnSocketError(Exception e)
        {
            Debug.LogError($"[ConnectionManager] Socket error: {e.Message}");
            OnError?.Invoke($"Socket error: {e.Message}");
        }
        
        public async Task<bool> AttemptReconnection()
        {
            if (reconnectAttempts >= config.maxReconnectAttempts)
            {
                OnError?.Invoke("Max reconnection attempts reached");
                return false;
            }
            
            reconnectAttempts++;
            Debug.Log($"[ConnectionManager] Reconnection attempt {reconnectAttempts}/{config.maxReconnectAttempts}");
            
            try
            {
                await Task.Delay((int)(config.reconnectDelay * 1000));
                
                if (socket?.IsConnected == false)
                {
                    await socket.ConnectAsync(session, true);
                    reconnectAttempts = 0;
                    return true;
                }
                
                return socket?.IsConnected ?? false;
            }
            catch (Exception e)
            {
                OnError?.Invoke($"Reconnection failed: {e.Message}");
                return false;
            }
        }
        
        public async Task Disconnect()
        {
            try
            {
                if (socket?.IsConnected == true)
                {
                    await socket.CloseAsync();
                }
                
                socket = null;
                session = null;
                reconnectAttempts = 0;
                
                OnConnectionChanged?.Invoke(false);
                Debug.Log("[ConnectionManager] Disconnected successfully");
            }
            catch (Exception e)
            {
                OnError?.Invoke($"Disconnect error: {e.Message}");
            }
        }
        
        public void UpdateConfiguration(ConnectionConfig newConfig)
        {
            // Note: Some config changes require reconnection
            var reconnectRequired = 
                config.host != newConfig.host ||
                config.port != newConfig.port ||
                config.scheme != newConfig.scheme;
            
            if (reconnectRequired && IsConnected)
            {
                Debug.LogWarning("[ConnectionManager] Configuration change requires reconnection");
            }
        }
        
        public void Dispose()
        {
            _ = Disconnect();
        }
    }
}