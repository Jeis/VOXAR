--[[
Spatial Platform - Nakama AR Match Handler
Replaces websocket_server.py (852 lines) with Nakama match engine
Handles real-time pose updates, spatial anchors, and colocalization
]]

local nk = require("nakama")

-- Message type constants (matching original Python MESSAGE_TYPES)
local MESSAGE_TYPES = {
    POSE_UPDATE = "pose_update",
    ANCHOR_CREATE = "anchor_create",
    ANCHOR_UPDATE = "anchor_update", 
    ANCHOR_DELETE = "anchor_delete",
    COLOCALIZATION_DATA = "colocalization_data",
    COORDINATE_SYSTEM = "coordinate_system",
    USER_JOINED = "user_joined",
    USER_LEFT = "user_left",
    CHAT_MESSAGE = "chat_message",
    SESSION_STATE = "session_state",
    PING = "ping",
    PONG = "pong"
}

-- Operation codes for Nakama
local OP_CODES = {
    POSE_UPDATE = 1,
    ANCHOR_CREATE = 2,
    ANCHOR_UPDATE = 3,
    ANCHOR_DELETE = 4,
    COLOCALIZATION_DATA = 5,
    COORDINATE_SYSTEM = 6,
    CHAT_MESSAGE = 7,
    PING = 8,
    PONG = 9,
    SESSION_STATE = 10
}

-- Match state structure (replaces ARSession class)
local function create_match_state()
    return {
        session_id = nk.uuid_v4(),
        creation_time = os.time(),
        players = {},  -- user_id -> player data
        anchors = {},  -- anchor_id -> anchor data
        host_user_id = nil,
        colocalization_method = "qr_code",
        coordinate_system = {
            origin = {x = 0, y = 0, z = 0},
            rotation = {x = 0, y = 0, z = 0, w = 1}
        },
        is_colocalized = false,
        max_players = 8,
        last_update_tick = 0,
        pose_update_interval = 1  -- Update every tick for 60 FPS
    }
end

-- Player structure (replaces Player dataclass)
local function create_player(user_id, username, is_host)
    return {
        user_id = user_id,
        username = username,
        pose = nil,  -- Will be set on first update
        join_time = os.time(),
        is_host = is_host,
        colocalized = false,
        last_ping = os.time(),
        is_anonymous = string.sub(user_id, 1, 5) == "anon_"
    }
end

-- Spatial anchor structure (replaces SpatialAnchor dataclass)
local function create_anchor(id, position, rotation, metadata, creator_id)
    return {
        id = id,
        position = position,
        rotation = rotation,
        metadata = metadata or {},
        creator_id = creator_id,
        creation_time = os.time(),
        last_update = os.time()
    }
end

-- Match initialization (called when match is created)
local function match_init(context, setupstate)
    local state = create_match_state()
    state.session_id = context.match_id
    
    -- Set match label for discovery
    local tickrate = 60  -- 60 FPS for AR
    local label = nk.json_encode({
        session_id = state.session_id,
        max_players = state.max_players,
        colocalization_method = state.colocalization_method
    })
    
    return state, tickrate, label
end

-- Handle player join (replaces handle_websocket_connection)
local function match_join_attempt(context, dispatcher, tick, state, presence, metadata)
    -- Check if session is full
    local player_count = 0
    for _ in pairs(state.players) do
        player_count = player_count + 1
    end
    
    if player_count >= state.max_players then
        return nil, false, "Session is full"
    end
    
    -- Accept the join
    return state, true
end

-- Handle player joined (add to session)
local function match_join(context, dispatcher, tick, state, presences)
    for _, presence in ipairs(presences) do
        local user_id = presence.user_id
        local username = presence.username
        
        -- First player becomes host
        local is_host = false
        if not state.host_user_id then
            state.host_user_id = user_id
            is_host = true
        end
        
        -- Create player
        local player = create_player(user_id, username, is_host)
        state.players[user_id] = player
        
        -- Notify all players about new user
        local join_msg = {
            type = MESSAGE_TYPES.USER_JOINED,
            user_id = user_id,
            display_name = username,
            is_host = is_host,
            is_anonymous = player.is_anonymous,
            timestamp = os.time()
        }
        
        dispatcher.broadcast_message(OP_CODES.SESSION_STATE, nk.json_encode(join_msg), nil, presence)
        
        -- Send current session state to new player
        local session_state = {
            type = MESSAGE_TYPES.SESSION_STATE,
            session_id = state.session_id,
            coordinate_system = state.coordinate_system,
            colocalization_method = state.colocalization_method,
            is_colocalized = state.is_colocalized,
            anchors = state.anchors,
            players = {},
            timestamp = os.time()
        }
        
        -- Add player info
        for uid, p in pairs(state.players) do
            session_state.players[uid] = {
                user_id = uid,
                is_host = p.is_host,
                colocalized = p.colocalized,
                join_time = p.join_time
            }
        end
        
        dispatcher.broadcast_message(OP_CODES.SESSION_STATE, nk.json_encode(session_state), {presence})
    end
    
    return state
end

-- Handle player leave (replaces handle_user_disconnect)
local function match_leave(context, dispatcher, tick, state, presences)
    for _, presence in ipairs(presences) do
        local user_id = presence.user_id
        
        if state.players[user_id] then
            -- Remove player
            state.players[user_id] = nil
            
            -- Notify remaining players
            local leave_msg = {
                type = MESSAGE_TYPES.USER_LEFT,
                user_id = user_id,
                timestamp = os.time()
            }
            dispatcher.broadcast_message(OP_CODES.SESSION_STATE, nk.json_encode(leave_msg))
            
            -- Handle host transfer if host left
            if state.host_user_id == user_id then
                local new_host = nil
                local earliest_join = nil
                
                -- Find player who joined earliest
                for uid, player in pairs(state.players) do
                    if not earliest_join or player.join_time < earliest_join then
                        earliest_join = player.join_time
                        new_host = uid
                    end
                end
                
                if new_host then
                    state.host_user_id = new_host
                    state.players[new_host].is_host = true
                    
                    local host_transfer = {
                        type = MESSAGE_TYPES.USER_JOINED,
                        user_id = new_host,
                        is_host = true,
                        timestamp = os.time()
                    }
                    dispatcher.broadcast_message(OP_CODES.SESSION_STATE, nk.json_encode(host_transfer))
                end
            end
        end
    end
    
    return state
end

-- Main message loop (replaces handle_message)
local function match_loop(context, dispatcher, tick, state, messages)
    -- Process incoming messages
    for _, message in ipairs(messages) do
        local decoded = nk.json_decode(message.data)
        local user_id = message.sender.user_id
        local player = state.players[user_id]
        
        if not player then
            goto continue
        end
        
        -- Update last ping time
        player.last_ping = os.time()
        
        -- Handle message based on opcode
        if message.op_code == OP_CODES.POSE_UPDATE then
            handle_pose_update(state, dispatcher, user_id, decoded)
            
        elseif message.op_code == OP_CODES.ANCHOR_CREATE then
            handle_anchor_create(state, dispatcher, user_id, decoded)
            
        elseif message.op_code == OP_CODES.ANCHOR_UPDATE then
            handle_anchor_update(state, dispatcher, user_id, decoded)
            
        elseif message.op_code == OP_CODES.ANCHOR_DELETE then
            handle_anchor_delete(state, dispatcher, user_id, decoded)
            
        elseif message.op_code == OP_CODES.COLOCALIZATION_DATA then
            handle_colocalization_data(state, dispatcher, user_id, decoded)
            
        elseif message.op_code == OP_CODES.CHAT_MESSAGE then
            handle_chat_message(state, dispatcher, user_id, decoded)
            
        elseif message.op_code == OP_CODES.PING then
            handle_ping(state, dispatcher, user_id, decoded, message.sender)
        end
        
        ::continue::
    end
    
    -- High-frequency pose update broadcasting (60 FPS)
    if tick % state.pose_update_interval == 0 then
        broadcast_pose_updates(state, dispatcher)
    end
    
    -- Cleanup inactive players every 30 seconds (1800 ticks at 60 FPS)
    if tick % 1800 == 0 then
        cleanup_inactive_players(state, dispatcher)
    end
    
    return state
end

-- Handle pose update (replaces handle_pose_update)
function handle_pose_update(state, dispatcher, user_id, data)
    local player = state.players[user_id]
    if not player then
        return
    end
    
    -- Update player pose
    player.pose = {
        position = data.position or {x = 0, y = 0, z = 0},
        rotation = data.rotation or {x = 0, y = 0, z = 0, w = 1},
        timestamp = os.time(),
        confidence = data.confidence or 1.0,
        tracking_state = data.tracking_state or "tracking"
    }
    
    -- Mark as needing broadcast in next tick
    player.pose_updated = true
end

-- Broadcast pose updates to colocalized players
function broadcast_pose_updates(state, dispatcher)
    -- Collect all updated poses
    local pose_updates = {}
    
    for user_id, player in pairs(state.players) do
        if player.pose_updated and player.colocalized then
            pose_updates[user_id] = player.pose
            player.pose_updated = false
        end
    end
    
    -- Only broadcast if there are updates
    if next(pose_updates) then
        local msg = {
            type = MESSAGE_TYPES.POSE_UPDATE,
            poses = pose_updates,
            timestamp = os.time()
        }
        
        -- Send only to colocalized players
        local colocalized_presences = {}
        for user_id, player in pairs(state.players) do
            if player.colocalized then
                -- Note: In production, you'd map user_id to presence objects
                -- This is simplified for the example
            end
        end
        
        dispatcher.broadcast_message(OP_CODES.POSE_UPDATE, nk.json_encode(msg))
    end
end

-- Handle anchor creation (replaces handle_anchor_create)
function handle_anchor_create(state, dispatcher, user_id, data)
    local anchor_id = data.anchor_id or nk.uuid_v4()
    
    local anchor = create_anchor(
        anchor_id,
        data.position or {x = 0, y = 0, z = 0},
        data.rotation or {x = 0, y = 0, z = 0, w = 1},
        data.metadata or {},
        user_id
    )
    
    state.anchors[anchor_id] = anchor
    
    -- Broadcast to all players
    local msg = {
        type = MESSAGE_TYPES.ANCHOR_CREATE,
        anchor = anchor
    }
    
    dispatcher.broadcast_message(OP_CODES.ANCHOR_CREATE, nk.json_encode(msg))
end

-- Handle anchor update (replaces handle_anchor_update)
function handle_anchor_update(state, dispatcher, user_id, data)
    local anchor_id = data.anchor_id
    if not anchor_id or not state.anchors[anchor_id] then
        return
    end
    
    local anchor = state.anchors[anchor_id]
    
    -- Update anchor properties
    if data.position then
        anchor.position = data.position
    end
    if data.rotation then
        anchor.rotation = data.rotation
    end
    if data.metadata then
        anchor.metadata = data.metadata
    end
    
    anchor.last_update = os.time()
    
    -- Broadcast update
    local msg = {
        type = MESSAGE_TYPES.ANCHOR_UPDATE,
        anchor_id = anchor_id,
        position = anchor.position,
        rotation = anchor.rotation,
        metadata = anchor.metadata,
        timestamp = anchor.last_update
    }
    
    dispatcher.broadcast_message(OP_CODES.ANCHOR_UPDATE, nk.json_encode(msg))
end

-- Handle anchor deletion (replaces handle_anchor_delete)
function handle_anchor_delete(state, dispatcher, user_id, data)
    local anchor_id = data.anchor_id
    if not anchor_id or not state.anchors[anchor_id] then
        return
    end
    
    local anchor = state.anchors[anchor_id]
    
    -- Check permissions (creator or host can delete)
    if anchor.creator_id == user_id or state.host_user_id == user_id then
        state.anchors[anchor_id] = nil
        
        local msg = {
            type = MESSAGE_TYPES.ANCHOR_DELETE,
            anchor_id = anchor_id,
            timestamp = os.time()
        }
        
        dispatcher.broadcast_message(OP_CODES.ANCHOR_DELETE, nk.json_encode(msg))
    end
end

-- Handle colocalization data (replaces handle_colocalization_data)
function handle_colocalization_data(state, dispatcher, user_id, data)
    local player = state.players[user_id]
    if not player then
        return
    end
    
    -- Host setting coordinate system
    if user_id == state.host_user_id and data.coordinate_system then
        state.coordinate_system = data.coordinate_system
        state.colocalization_method = data.method or "qr_code"
        state.is_colocalized = true
        
        -- Broadcast coordinate system to all players
        local msg = {
            type = MESSAGE_TYPES.COORDINATE_SYSTEM,
            coordinate_system = state.coordinate_system,
            colocalization_method = state.colocalization_method,
            is_colocalized = state.is_colocalized,
            timestamp = os.time()
        }
        
        dispatcher.broadcast_message(OP_CODES.COORDINATE_SYSTEM, nk.json_encode(msg))
    end
    
    -- Mark user as colocalized
    if data.colocalized ~= nil then
        player.colocalized = data.colocalized
        
        -- Notify other players about colocalization status
        local msg = {
            type = MESSAGE_TYPES.USER_JOINED,
            user_id = user_id,
            is_host = player.is_host,
            colocalized = player.colocalized,
            timestamp = os.time()
        }
        
        dispatcher.broadcast_message(OP_CODES.SESSION_STATE, nk.json_encode(msg), nil, {user_id})
    end
end

-- Handle chat messages (replaces handle_chat_message)
function handle_chat_message(state, dispatcher, user_id, data)
    local msg = {
        type = MESSAGE_TYPES.CHAT_MESSAGE,
        user_id = user_id,
        message = data.message or "",
        timestamp = os.time()
    }
    
    dispatcher.broadcast_message(OP_CODES.CHAT_MESSAGE, nk.json_encode(msg))
end

-- Handle ping (replaces handle_ping)
function handle_ping(state, dispatcher, user_id, data, sender)
    local player = state.players[user_id]
    if player then
        local pong_msg = {
            type = MESSAGE_TYPES.PONG,
            timestamp = os.time(),
            client_timestamp = data.timestamp or 0
        }
        
        dispatcher.broadcast_message(OP_CODES.PONG, nk.json_encode(pong_msg), {sender})
    end
end

-- Cleanup inactive players
function cleanup_inactive_players(state, dispatcher)
    local current_time = os.time()
    local players_to_remove = {}
    
    -- Check for inactive players (no ping for 60 seconds)
    for user_id, player in pairs(state.players) do
        if current_time - player.last_ping > 60 then
            table.insert(players_to_remove, user_id)
        end
    end
    
    -- Remove inactive players
    for _, user_id in ipairs(players_to_remove) do
        if state.players[user_id] then
            state.players[user_id] = nil
            
            -- Notify other players
            local msg = {
                type = MESSAGE_TYPES.USER_LEFT,
                user_id = user_id,
                timestamp = current_time
            }
            dispatcher.broadcast_message(OP_CODES.SESSION_STATE, nk.json_encode(msg))
        end
    end
end

-- Handle match termination
local function match_terminate(context, dispatcher, tick, state, grace_seconds)
    -- Save any persistent data if needed
    return state
end

-- Handle match signal (for admin commands)
local function match_signal(context, dispatcher, tick, state, data)
    return state, data
end

-- Register the match handler
return {
    match_init = match_init,
    match_join_attempt = match_join_attempt,
    match_join = match_join,
    match_leave = match_leave,
    match_loop = match_loop,
    match_terminate = match_terminate,
    match_signal = match_signal
}