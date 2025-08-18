using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using UnityEngine;
using Nakama;
using Newtonsoft.Json;

namespace SpatialPlatform.Nakama.Enterprise
{
    /// <summary>
    /// Enterprise Session Manager for Nakama AR
    /// Handles session creation, joining, and lifecycle management
    /// </summary>
    public class SessionManager
    {
        private readonly ConnectionManager connectionManager;
        private readonly SessionConfig config;
        private IMatch currentMatch;
        private string sessionCode;
        private string sessionId;
        private bool isHost = false;
        
        public bool IsHost => isHost;
        public string SessionCode => sessionCode;
        public string SessionId => sessionId;
        public IMatch CurrentMatch => currentMatch;
        
        public event Action<string> OnSessionCreated;
        public event Action<string> OnSessionJoined;
        public event Action<string> OnSessionLeft;
        public event Action<string> OnError;
        
        public SessionManager(ConnectionManager connectionManager, SessionConfig config)
        {
            this.connectionManager = connectionManager;
            this.config = config;
        }
        
        /// <summary>
        /// Create a new AR session with enterprise features
        /// </summary>
        public async Task<string> CreateSession(string displayName = null, bool isPrivate = false)
        {
            try
            {
                if (!connectionManager.IsConnected)
                {
                    throw new InvalidOperationException("Not connected to server");
                }
                
                // Call RPC to create anonymous session
                var payload = new Dictionary<string, object>
                {
                    { "display_name", displayName ?? $"Player_{UnityEngine.Random.Range(1000, 9999)}" },
                    { "is_private", isPrivate },
                    { "max_players", config.maxPlayers },
                    { "colocalization_method", config.colocalizationMethod },
                    { "session_timeout", config.sessionTimeout }
                };
                
                var result = await connectionManager.Client.RpcAsync(
                    connectionManager.Session, "create_ar_session", JsonConvert.SerializeObject(payload)
                );
                
                var response = JsonConvert.DeserializeObject<Dictionary<string, object>>(result.Payload);
                sessionCode = response["session_code"].ToString();
                sessionId = response["match_id"].ToString();
                
                // Join the created match
                currentMatch = await connectionManager.Socket.JoinMatchAsync(sessionId);
                isHost = true;
                
                SetupMatchHandlers();
                
                OnSessionCreated?.Invoke(sessionCode);
                Debug.Log($"[SessionManager] Session created: {sessionCode} (Match: {sessionId})");
                
                return sessionCode;
            }
            catch (Exception e)
            {
                OnError?.Invoke($"Session creation failed: {e.Message}");
                throw;
            }
        }
        
        /// <summary>
        /// Join an existing session by code
        /// </summary>
        public async Task<bool> JoinSession(string code, string displayName = null)
        {
            try
            {
                if (!connectionManager.IsConnected)
                {
                    throw new InvalidOperationException("Not connected to server");
                }
                
                // Call RPC to join session
                var payload = new Dictionary<string, object>
                {
                    { "session_code", code },
                    { "display_name", displayName ?? $"Player_{UnityEngine.Random.Range(1000, 9999)}" }
                };
                
                var result = await connectionManager.Client.RpcAsync(
                    connectionManager.Session, "join_ar_session", JsonConvert.SerializeObject(payload)
                );
                
                var response = JsonConvert.DeserializeObject<Dictionary<string, object>>(result.Payload);
                
                if (!response.ContainsKey("match_id"))
                {
                    throw new Exception("Session not found or full");
                }
                
                sessionCode = code;
                sessionId = response["match_id"].ToString();
                
                // Join the match
                currentMatch = await connectionManager.Socket.JoinMatchAsync(sessionId);
                isHost = false;
                
                SetupMatchHandlers();
                
                OnSessionJoined?.Invoke(sessionCode);
                Debug.Log($"[SessionManager] Joined session: {sessionCode} (Match: {sessionId})");
                
                return true;
            }
            catch (Exception e)
            {
                OnError?.Invoke($"Failed to join session: {e.Message}");
                return false;
            }
        }
        
        /// <summary>
        /// Leave current session cleanly
        /// </summary>
        public async Task LeaveSession()
        {
            try
            {
                if (currentMatch != null)
                {
                    await connectionManager.Socket.LeaveMatchAsync(currentMatch.Id);
                }
                
                ClearSessionState();
                OnSessionLeft?.Invoke(sessionCode);
                Debug.Log($"[SessionManager] Left session: {sessionCode}");
            }
            catch (Exception e)
            {
                OnError?.Invoke($"Error leaving session: {e.Message}");
            }
        }
        
        /// <summary>
        /// Send match state data to all players
        /// </summary>
        public async Task SendMatchState(OpCode opCode, Dictionary<string, object> data, bool reliable = false)
        {
            if (currentMatch == null || !connectionManager.IsConnected)
            {
                throw new InvalidOperationException("Not in a match");
            }
            
            try
            {
                var payload = JsonConvert.SerializeObject(data);
                var dataBytes = System.Text.Encoding.UTF8.GetBytes(payload);
                
                await connectionManager.Socket.SendMatchStateAsync(
                    currentMatch.Id, 
                    (long)opCode, 
                    dataBytes,
                    reliable ? new[] { connectionManager.Session.UserId } : null
                );
            }
            catch (Exception e)
            {
                OnError?.Invoke($"Failed to send match state: {e.Message}");
                throw;
            }
        }
        
        private void SetupMatchHandlers()
        {
            connectionManager.Socket.ReceivedMatchState += OnMatchStateReceived;
            connectionManager.Socket.ReceivedMatchPresence += OnMatchPresenceReceived;
        }
        
        private void OnMatchStateReceived(IMatchState matchState)
        {
            // This will be handled by the main client
            // Events are forwarded through the enterprise client
        }
        
        private void OnMatchPresenceReceived(IMatchPresenceEvent matchPresence)
        {
            // This will be handled by the main client
            // Events are forwarded through the enterprise client
        }
        
        private void ClearSessionState()
        {
            currentMatch = null;
            sessionCode = null;
            sessionId = null;
            isHost = false;
        }
        
        /// <summary>
        /// Save session state for recovery
        /// </summary>
        public void SaveSessionState()
        {
            if (!string.IsNullOrEmpty(sessionCode))
            {
                PlayerPrefs.SetString("LastSessionCode", sessionCode);
                PlayerPrefs.SetString("LastSessionId", sessionId);
                PlayerPrefs.SetInt("WasHost", isHost ? 1 : 0);
                PlayerPrefs.Save();
                
                Debug.Log("[SessionManager] Session state saved");
            }
        }
        
        /// <summary>
        /// Resume session after app pause/focus
        /// </summary>
        public async Task<bool> ResumeSession()
        {
            try
            {
                var lastCode = PlayerPrefs.GetString("LastSessionCode", "");
                var lastId = PlayerPrefs.GetString("LastSessionId", "");
                var wasHost = PlayerPrefs.GetInt("WasHost", 0) == 1;
                
                if (string.IsNullOrEmpty(lastCode) || string.IsNullOrEmpty(lastId))
                {
                    return false;
                }
                
                // Try to rejoin the match
                currentMatch = await connectionManager.Socket.JoinMatchAsync(lastId);
                sessionCode = lastCode;
                sessionId = lastId;
                isHost = wasHost;
                
                SetupMatchHandlers();
                
                Debug.Log($"[SessionManager] Session resumed: {sessionCode}");
                return true;
            }
            catch (Exception e)
            {
                Debug.LogWarning($"[SessionManager] Failed to resume session: {e.Message}");
                ClearSessionState();
                return false;
            }
        }
        
        public void Dispose()
        {
            _ = LeaveSession();
        }
    }
}