--[[
Spatial Platform - Nakama Authentication System
Replaces custom Python WebSocket auth with Nakama hooks
Supports both JWT tokens and anonymous 6-character session codes
]]

local nk = require("nakama")

-- Session code management (6-character ABC123 format)
local function generate_session_code()
    local letters = ""
    local numbers = ""
    
    -- Generate 3 random uppercase letters
    for i = 1, 3 do
        letters = letters .. string.char(math.random(65, 90))
    end
    
    -- Generate 3 random digits
    for i = 1, 3 do
        numbers = numbers .. tostring(math.random(0, 9))
    end
    
    return letters .. numbers
end

-- Validate session code format (ABC123)
local function validate_code_format(code)
    if not code or string.len(code) ~= 6 then
        return false
    end
    
    local letters = string.sub(code, 1, 3)
    local numbers = string.sub(code, 4, 6)
    
    return string.match(letters, "^[A-Z]+$") and string.match(numbers, "^[0-9]+$")
end

-- Before Authentication Hook - handles JWT validation
local function before_authenticate_custom(context, logger, nk, payload)
    -- nk.logger_info("Processing custom authentication request")
    
    -- Validate JWT token structure
    local token = payload.account.vars.token
    if not token or string.len(token) < 10 then
        error("Invalid JWT token format")
    end
    
    -- Extract user info from JWT (simplified - real implementation would verify signature)
    local user_id = payload.account.id or ("user_" .. nk.uuid_v4())
    local username = payload.account.vars.username or "authenticated_user"
    
    -- nk.logger_info("JWT authentication successful for user: " .. user_id)
    
    return payload
end

-- Before Session Refresh Hook - extends session on activity
local function before_session_refresh(context, logger, nk, payload)
    local user_id = context.user_id
    -- nk.logger_info("Refreshing session for user: " .. user_id)
    
    -- Update last activity timestamp
    local metadata = {
        last_activity = os.time(),
        session_extended = true
    }
    
    nk.account_update_id(user_id, nil, nil, nil, nil, nil, metadata)
    
    return payload
end

-- Anonymous Session Creation (replaces anonymous_sessions.py)
local function create_anonymous_session(context, payload)
    -- Creating anonymous session
    
    -- Parse payload if it's a JSON string
    local request_data = {}
    if type(payload) == "string" and payload ~= "" then
        request_data = nk.json_decode(payload) or {}
    elseif type(payload) == "table" then
        request_data = payload
    end
    
    -- Generate unique session code
    local session_code = generate_session_code()
    local max_attempts = 10
    local attempts = 0
    
    -- Ensure code uniqueness
    while attempts < max_attempts do
        local existing = nk.storage_read({
            {collection = "session_codes", key = session_code}
        })
        
        if #existing == 0 then
            break
        end
        
        session_code = generate_session_code()
        attempts = attempts + 1
    end
    
    if attempts >= max_attempts then
        error("Failed to generate unique session code")
    end
    
    -- Create anonymous user account
    local user_id = "anon_" .. string.sub(nk.uuid_v4(), 1, 12)
    local display_name = request_data.display_name or ("Player_" .. math.random(1000, 9999))
    
    -- Store session code mapping
    local session_data = {
        session_id = nk.uuid_v4(),
        creator_id = user_id,
        display_name = display_name,
        created_at = os.time(),
        expires_at = os.time() + 3600, -- 1 hour
        max_players = 10,
        is_anonymous = true
    }
    
    nk.storage_write({
        {
            collection = "session_codes",
            key = session_code,
            value = session_data,
            permission_read = 1, -- Public read
            permission_write = 0  -- No public write
        }
    })
    
    -- Store user session mapping
    nk.storage_write({
        {
            collection = "user_sessions",
            key = user_id,
            value = {
                session_id = session_data.session_id,
                session_code = session_code,
                created_at = os.time()
            },
            permission_read = 1,
            permission_write = 0
        }
    })
    
    -- nk.logger_info("Anonymous session created: " .. session_code .. " for user: " .. user_id)
    
    return nk.json_encode({
        session_id = session_data.session_id,
        share_code = session_code,
        creator = {
            id = user_id,
            display_name = display_name,
            is_anonymous = true
        },
        expires_in = 3600,
        max_players = 10,
        created_at = os.date("!%Y-%m-%dT%H:%M:%SZ", os.time())
    })
end

-- Join Session with Code (replaces join_with_code functionality)
local function join_with_session_code(context, payload)
    -- Parse payload if it's a JSON string
    local request_data = {}
    if type(payload) == "string" and payload ~= "" then
        request_data = nk.json_decode(payload) or {}
    elseif type(payload) == "table" then
        request_data = payload
    end
    
    local code = string.upper(request_data.code or "")
    local display_name = request_data.display_name or ("Player_" .. math.random(1000, 9999))
    
    -- nk.logger_info("Attempting to join with code: " .. code)
    
    -- Validate code format
    if not validate_code_format(code) then
        error("Invalid session code format")
    end
    
    -- Look up session by code
    local session_records = nk.storage_read({
        {collection = "session_codes", key = code}
    })
    
    if #session_records == 0 then
        error("Session code not found")
    end
    
    local session_data = session_records[1].value
    
    -- Check if session expired
    if os.time() > session_data.expires_at then
        -- Clean up expired session
        nk.storage_delete({
            {collection = "session_codes", key = code}
        })
        error("Session has expired")
    end
    
    -- Create anonymous user for joining
    local user_id = "anon_" .. string.sub(nk.uuid_v4(), 1, 12)
    
    -- Extend session expiry on activity
    session_data.expires_at = os.time() + 3600
    nk.storage_write({
        {
            collection = "session_codes",
            key = code,
            value = session_data,
            permission_read = 1,
            permission_write = 0
        }
    })
    
    -- Store user session mapping
    nk.storage_write({
        {
            collection = "user_sessions",
            key = user_id,
            value = {
                session_id = session_data.session_id,
                session_code = code,
                joined_at = os.time()
            },
            permission_read = 1,
            permission_write = 0
        }
    })
    
    -- nk.logger_info("User joined session with code: " .. code .. " user: " .. user_id)
    
    return nk.json_encode({
        session_id = session_data.session_id,
        user = {
            id = user_id,
            display_name = display_name,
            is_anonymous = true
        },
        share_code = code,
        session_info = {
            max_players = session_data.max_players,
            expires_in = math.max(0, session_data.expires_at - os.time())
        }
    })
end

-- Session Cleanup (replaces cleanup_expired_sessions)
local function cleanup_expired_sessions(context, payload)
    -- nk.logger_info("Running session cleanup")
    
    local current_time = os.time()
    local cleaned_count = 0
    
    -- Read all session codes
    local sessions = nk.storage_list(context.user_id, "session_codes", 100)
    
    for _, session_record in ipairs(sessions) do
        local session_data = session_record.value
        
        if current_time > session_data.expires_at then
            -- Delete expired session
            nk.storage_delete({
                {collection = "session_codes", key = session_record.key}
            })
            
            cleaned_count = cleaned_count + 1
            -- nk.logger_info("Cleaned expired session: " .. session_record.key)
        end
    end
    
    -- nk.logger_info("Session cleanup completed, cleaned: " .. cleaned_count)
    return nk.json_encode({cleaned_sessions = cleaned_count})
end

-- Get Session Stats (replaces get_stats functionality)
local function get_session_stats(context, payload)
    local active_sessions = 0
    local anonymous_users = 0
    
    -- Count active sessions
    local sessions = nk.storage_list(context.user_id, "session_codes", 100)
    local current_time = os.time()
    
    for _, session_record in ipairs(sessions) do
        local session_data = session_record.value
        if current_time <= session_data.expires_at then
            active_sessions = active_sessions + 1
            if session_data.is_anonymous then
                anonymous_users = anonymous_users + 1
            end
        end
    end
    
    return nk.json_encode({
        active_sessions = active_sessions,
        anonymous_users = anonymous_users,
        session_timeout = 3600,
        max_users_per_session = 10
    })
end

-- Register authentication hooks (disabled for testing)
-- nk.register_req_before(before_authenticate_custom, "AuthenticateCustom")
-- nk.register_req_before(before_session_refresh, "SessionRefresh")

-- Register RPC endpoints for anonymous sessions
nk.register_rpc(create_anonymous_session, "create_anonymous_session")
nk.register_rpc(join_with_session_code, "join_with_session_code")
nk.register_rpc(cleanup_expired_sessions, "cleanup_expired_sessions")
nk.register_rpc(get_session_stats, "get_session_stats")

-- Initialize random seed
math.randomseed(os.time())

return {
    before_authenticate_custom = before_authenticate_custom,
    before_session_refresh = before_session_refresh,
    create_anonymous_session = create_anonymous_session,
    join_with_session_code = join_with_session_code,
    cleanup_expired_sessions = cleanup_expired_sessions,
    get_session_stats = get_session_stats
}