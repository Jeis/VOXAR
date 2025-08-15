-- Spatial Platform - Nakama AR Module
-- Handles multiplayer AR sessions, colocalization, and real-time synchronization

local nk = require("nakama")

-- Constants
local MATCH_LABEL = "spatial_ar_session"
local MAX_PLAYERS_PER_SESSION = 8
local POSE_UPDATE_INTERVAL = 16 -- ~60 FPS (16ms)
local ANCHOR_UPDATE_INTERVAL = 100 -- 10 FPS for anchors

-- Match state structure
local match_state = {
    players = {},
    anchors = {},
    session_id = "",
    creation_time = 0,
    last_update = 0,
    colocalization_method = "qr_code", -- "qr_code", "visual", "gps"
    coordinate_system = {
        origin = {x = 0, y = 0, z = 0},
        rotation = {x = 0, y = 0, z = 0, w = 1}
    }
}

-- Message types
local MESSAGE_TYPES = {
    POSE_UPDATE = 1,
    ANCHOR_CREATE = 2,
    ANCHOR_UPDATE = 3,
    ANCHOR_DELETE = 4,
    COLOCALIZATION_DATA = 5,
    COORDINATE_SYSTEM = 6,
    USER_JOINED = 7,
    USER_LEFT = 8,
    VOICE_DATA = 9,
    CHAT_MESSAGE = 10
}

-- Match lifecycle functions
function match_init(context, initial_state)
    local state = {
        players = {},
        anchors = {},
        session_id = nk.uuid_v4(),
        creation_time = nk.time(),
        last_update = nk.time(),
        colocalization_method = "qr_code",
        coordinate_system = {
            origin = {x = 0, y = 0, z = 0},
            rotation = {x = 0, y = 0, z = 0, w = 1}
        },
        host_user_id = nil,
        is_colocalized = false
    }
    
    nk.logger_info("AR Session initialized: " .. state.session_id)
    return state
end

function match_join_attempt(context, dispatcher, tick, state, presence, metadata)
    -- Check if session is full
    local player_count = 0
    for _ in pairs(state.players) do
        player_count = player_count + 1
    end
    
    if player_count >= MAX_PLAYERS_PER_SESSION then
        return state, false, "Session is full"
    end
    
    -- Accept the player
    nk.logger_info("Player joining AR session: " .. presence.user_id)
    return state, true
end

function match_join(context, dispatcher, tick, state, presences)
    for _, presence in ipairs(presences) do
        local user_id = presence.user_id
        
        -- Add player to state
        state.players[user_id] = {
            presence = presence,
            pose = {
                position = {x = 0, y = 0, z = 0},
                rotation = {x = 0, y = 0, z = 0, w = 1},
                timestamp = tick,
                confidence = 0.0,
                tracking_state = "initializing"
            },
            join_time = tick,
            is_host = (state.host_user_id == nil),
            colocalized = false
        }
        
        -- Set first player as host
        if state.host_user_id == nil then
            state.host_user_id = user_id
            nk.logger_info("Player " .. user_id .. " is now the host")
        end
        
        -- Notify all players about new user
        local join_message = {
            type = MESSAGE_TYPES.USER_JOINED,
            user_id = user_id,
            is_host = state.players[user_id].is_host,
            timestamp = tick
        }
        
        dispatcher.broadcast_message(2, nk.json_encode(join_message))
        
        -- Send current session state to new player
        local session_state = {
            type = MESSAGE_TYPES.COORDINATE_SYSTEM,
            session_id = state.session_id,
            coordinate_system = state.coordinate_system,
            colocalization_method = state.colocalization_method,
            is_colocalized = state.is_colocalized,
            anchors = state.anchors,
            players = get_player_list(state)
        }
        
        dispatcher.send_message(2, nk.json_encode(session_state), {presence})
    end
    
    return state
end

function match_leave(context, dispatcher, tick, state, presences)
    for _, presence in ipairs(presences) do
        local user_id = presence.user_id
        
        if state.players[user_id] then
            state.players[user_id] = nil
            
            -- Notify remaining players
            local leave_message = {
                type = MESSAGE_TYPES.USER_LEFT,
                user_id = user_id,
                timestamp = tick
            }
            
            dispatcher.broadcast_message(2, nk.json_encode(leave_message))
            
            -- Handle host transfer if needed
            if state.host_user_id == user_id then
                local new_host = get_next_host(state)
                if new_host then
                    state.host_user_id = new_host
                    state.players[new_host].is_host = true
                    
                    local host_transfer = {
                        type = MESSAGE_TYPES.USER_JOINED, -- Reuse for host update
                        user_id = new_host,
                        is_host = true,
                        timestamp = tick
                    }
                    
                    dispatcher.broadcast_message(2, nk.json_encode(host_transfer))
                    nk.logger_info("Host transferred to: " .. new_host)
                end
            end
        end
    end
    
    return state
end

function match_loop(context, dispatcher, tick, state, messages)
    -- Process incoming messages
    for _, message in ipairs(messages) do
        local decoded = nk.json_decode(message.data)
        local user_id = message.sender.user_id
        
        if decoded.type == MESSAGE_TYPES.POSE_UPDATE then
            handle_pose_update(state, user_id, decoded, tick)
            
        elseif decoded.type == MESSAGE_TYPES.ANCHOR_CREATE then
            handle_anchor_create(state, dispatcher, user_id, decoded, tick)
            
        elseif decoded.type == MESSAGE_TYPES.ANCHOR_UPDATE then
            handle_anchor_update(state, dispatcher, user_id, decoded, tick)
            
        elseif decoded.type == MESSAGE_TYPES.ANCHOR_DELETE then
            handle_anchor_delete(state, dispatcher, user_id, decoded, tick)
            
        elseif decoded.type == MESSAGE_TYPES.COLOCALIZATION_DATA then
            handle_colocalization_data(state, dispatcher, user_id, decoded, tick)
            
        elseif decoded.type == MESSAGE_TYPES.CHAT_MESSAGE then
            handle_chat_message(state, dispatcher, user_id, decoded, tick)
        end
    end
    
    -- Periodic updates
    if tick - state.last_update > POSE_UPDATE_INTERVAL then
        broadcast_pose_updates(state, dispatcher, tick)
        state.last_update = tick
    end
    
    return state
end

function match_terminate(context, dispatcher, tick, state, grace_seconds)
    nk.logger_info("AR Session terminating: " .. state.session_id)
    return state
end

-- Helper functions
function get_player_list(state)
    local players = {}
    for user_id, player in pairs(state.players) do
        players[user_id] = {
            user_id = user_id,
            is_host = player.is_host,
            colocalized = player.colocalized,
            join_time = player.join_time
        }
    end
    return players
end

function get_next_host(state)
    local earliest_join = nil
    local next_host = nil
    
    for user_id, player in pairs(state.players) do
        if earliest_join == nil or player.join_time < earliest_join then
            earliest_join = player.join_time
            next_host = user_id
        end
    end
    
    return next_host
end

function handle_pose_update(state, user_id, data, tick)
    if state.players[user_id] then
        state.players[user_id].pose = {
            position = data.position,
            rotation = data.rotation,
            timestamp = tick,
            confidence = data.confidence or 1.0,
            tracking_state = data.tracking_state or "tracking"
        }
    end
end

function handle_anchor_create(state, dispatcher, user_id, data, tick)
    local anchor_id = data.anchor_id or nk.uuid_v4()
    
    state.anchors[anchor_id] = {
        id = anchor_id,
        creator_id = user_id,
        position = data.position,
        rotation = data.rotation,
        metadata = data.metadata or {},
        creation_time = tick,
        last_update = tick
    }
    
    -- Broadcast to all players
    local anchor_message = {
        type = MESSAGE_TYPES.ANCHOR_CREATE,
        anchor = state.anchors[anchor_id]
    }
    
    dispatcher.broadcast_message(2, nk.json_encode(anchor_message))
    nk.logger_info("Anchor created: " .. anchor_id .. " by " .. user_id)
end

function handle_anchor_update(state, dispatcher, user_id, data, tick)
    local anchor_id = data.anchor_id
    
    if state.anchors[anchor_id] then
        -- Update anchor
        state.anchors[anchor_id].position = data.position or state.anchors[anchor_id].position
        state.anchors[anchor_id].rotation = data.rotation or state.anchors[anchor_id].rotation
        state.anchors[anchor_id].metadata = data.metadata or state.anchors[anchor_id].metadata
        state.anchors[anchor_id].last_update = tick
        
        -- Broadcast update
        local update_message = {
            type = MESSAGE_TYPES.ANCHOR_UPDATE,
            anchor_id = anchor_id,
            position = state.anchors[anchor_id].position,
            rotation = state.anchors[anchor_id].rotation,
            metadata = state.anchors[anchor_id].metadata
        }
        
        dispatcher.broadcast_message(2, nk.json_encode(update_message))
    end
end

function handle_anchor_delete(state, dispatcher, user_id, data, tick)
    local anchor_id = data.anchor_id
    
    if state.anchors[anchor_id] then
        -- Check permissions (creator or host can delete)
        if state.anchors[anchor_id].creator_id == user_id or state.host_user_id == user_id then
            state.anchors[anchor_id] = nil
            
            local delete_message = {
                type = MESSAGE_TYPES.ANCHOR_DELETE,
                anchor_id = anchor_id
            }
            
            dispatcher.broadcast_message(2, nk.json_encode(delete_message))
            nk.logger_info("Anchor deleted: " .. anchor_id .. " by " .. user_id)
        end
    end
end

function handle_colocalization_data(state, dispatcher, user_id, data, tick)
    -- Handle colocalization setup data (QR codes, visual features, etc.)
    if data.coordinate_system and state.host_user_id == user_id then
        state.coordinate_system = data.coordinate_system
        state.colocalization_method = data.method or "qr_code"
        state.is_colocalized = true
        
        -- Broadcast coordinate system to all players
        local coord_message = {
            type = MESSAGE_TYPES.COORDINATE_SYSTEM,
            coordinate_system = state.coordinate_system,
            colocalization_method = state.colocalization_method,
            is_colocalized = state.is_colocalized
        }
        
        dispatcher.broadcast_message(2, nk.json_encode(coord_message))
        nk.logger_info("Coordinate system established by host: " .. user_id)
    end
    
    -- Mark user as colocalized
    if state.players[user_id] then
        state.players[user_id].colocalized = data.colocalized or false
    end
end

function handle_chat_message(state, dispatcher, user_id, data, tick)
    local chat_message = {
        type = MESSAGE_TYPES.CHAT_MESSAGE,
        user_id = user_id,
        message = data.message,
        timestamp = tick
    }
    
    dispatcher.broadcast_message(2, nk.json_encode(chat_message))
end

function broadcast_pose_updates(state, dispatcher, tick)
    local pose_updates = {}
    
    for user_id, player in pairs(state.players) do
        if player.pose and player.colocalized then
            pose_updates[user_id] = player.pose
        end
    end
    
    if next(pose_updates) then
        local message = {
            type = MESSAGE_TYPES.POSE_UPDATE,
            poses = pose_updates,
            timestamp = tick
        }
        
        dispatcher.broadcast_message(1, nk.json_encode(message)) -- Lower priority for poses
    end
end

-- HTTP handlers for REST API integration
local function create_ar_session(context, payload)
    local request = nk.json_decode(payload)
    
    -- Create match
    local match_id = nk.match_create("spatial_ar", {
        max_players = request.max_players or MAX_PLAYERS_PER_SESSION,
        colocalization_method = request.colocalization_method or "qr_code",
        public = request.public or false
    })
    
    local response = {
        success = true,
        match_id = match_id,
        join_url = "nakama://match/" .. match_id
    }
    
    return nk.json_encode(response)
end

local function join_ar_session(context, payload)
    local request = nk.json_decode(payload)
    local match_id = request.match_id
    local user_id = context.user_id
    
    if not match_id then
        return nk.json_encode({success = false, error = "match_id required"})
    end
    
    -- Try to join the match
    local success, error = pcall(function()
        -- Match join will be handled by match_join_attempt
        return true
    end)
    
    local response = {
        success = success,
        match_id = match_id,
        error = error
    }
    
    return nk.json_encode(response)
end

-- Register RPC functions
nk.register_rpc(create_ar_session, "create_ar_session")
nk.register_rpc(join_ar_session, "join_ar_session")

-- Register match handler
nk.register_matchmaker_matched(function(context, matched_users)
    -- Create AR session when users are matched
    local match_id = nk.match_create("spatial_ar", {})
    return match_id
end)

nk.logger_info("Spatial AR module loaded successfully")