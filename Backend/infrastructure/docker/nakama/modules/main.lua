--[[
Spatial Platform - Nakama Main Module Loader
Loads all Lua modules for the AR platform
]]

local nk = require("nakama")

-- Load authentication system
local auth_system = require("auth_system")

-- Load AR match handler
local spatial_match = require("spatial_ar_match")

-- Register match handler for AR sessions
nk.register_matchmaker_matched(function(context, matched_users)
    -- Create a new AR match when users are matched
    local match_id = nk.match_create("spatial_ar_match", {
        matched_users = matched_users
    })
    
    return match_id
end)

-- Register RPC to create AR match directly (bypass matchmaker)
nk.register_rpc(function(context, payload)
    -- Parse payload safely
    local decoded = {}
    if type(payload) == "string" and payload ~= "" then
        decoded = nk.json_decode(payload) or {}
    elseif type(payload) == "table" then
        decoded = payload
    end
    
    -- Create match with configuration
    local match_id = nk.match_create("spatial_ar_match", {
        max_players = decoded.max_players or 8,
        colocalization_method = decoded.colocalization_method or "qr_code"
    })
    
    return nk.json_encode({
        match_id = match_id,
        success = true
    })
end, "create_ar_match")

-- Register RPC to list active AR matches
nk.register_rpc(function(context, payload)
    local limit = 100
    local authoritative = true
    local label = ""
    local min_size = 0
    local max_size = 8
    local query = "*"
    
    local matches = nk.match_list(limit, authoritative, label, min_size, max_size, query)
    
    local result = {}
    for _, match in ipairs(matches) do
        local label_data = nk.json_decode(match.label)
        table.insert(result, {
            match_id = match.match_id,
            size = match.size,
            session_id = label_data.session_id,
            max_players = label_data.max_players,
            colocalization_method = label_data.colocalization_method
        })
    end
    
    return nk.json_encode(result)
end, "list_ar_matches")

-- Log module initialization
nk.logger_info("Spatial Platform Nakama modules loaded successfully")
nk.logger_info("Authentication system: ACTIVE")
nk.logger_info("AR Match handler: ACTIVE")
nk.logger_info("Anonymous sessions: ENABLED")

return {
    auth_system = auth_system,
    spatial_match = spatial_match
}