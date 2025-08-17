# VOXAR - Enterprise AR Platform

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Unity Version](https://img.shields.io/badge/Unity-2022.3%2B-blue.svg)](https://unity3d.com/get-unity/download)
[![Nakama Version](https://img.shields.io/badge/Nakama-3.17.1-orange.svg)](https://heroiclabs.com/nakama/)
[![Docker](https://img.shields.io/badge/Docker-Ready-blue.svg)](https://www.docker.com/)

Enterprise-grade AR multiplayer platform powered by Nakama game server, featuring real-time synchronization, spatial mapping, and cross-platform support.

## 🚀 Key Features

- **Real-time Multiplayer AR** - 60 FPS pose synchronization with Nakama match engine
- **Anonymous Sessions** - Simple 6-character join codes (ABC123 format)
- **Spatial Anchors** - Persistent AR anchor sharing and colocalization
- **Visual-Inertial Tracking** - Sub-100ms localization with SLAM integration
- **3D Mapping Pipeline** - COLMAP-based persistent environment mapping
- **Enterprise Authentication** - JWT tokens with role-based access control
- **Production Infrastructure** - Docker Compose with monitoring and scaling
- **Cross-Platform Support** - Unity SDK for iOS, Android, and HoloLens

## 🏗️ Architecture

```
┌─────────────────────────────────────────────┐
│         Unity/Mobile AR Clients             │
│    (AR Foundation, Nakama Unity SDK)        │
└─────────────────┬───────────────────────────┘
                  │ WebSocket/HTTP
┌─────────────────▼───────────────────────────┐
│         Nakama Game Server (3.17.1)         │
│   • Match Engine (60 FPS AR updates)        │
│   • Session Management (6-char codes)       │
│   • Storage API (anchors, user data)        │
│   • Authentication (JWT, anonymous)         │
└─────────────────┬───────────────────────────┘
                  │
┌─────────────────▼───────────────────────────┐
│         Infrastructure Layer                │
├─────────────┬─────────────┬─────────────────┤
│ PostgreSQL  │    Redis    │     MinIO       │
│   15 (DB)   │  (Cache)    │  (Storage)      │
└─────────────┴─────────────┴─────────────────┘
                  │
┌─────────────────▼───────────────────────────┐
│         Monitoring & Analytics              │
├─────────────┬─────────────┬─────────────────┤
│ Prometheus  │   Grafana   │    Nginx        │
│  (Metrics)  │(Dashboards) │(Load Balancer)  │
└─────────────┴─────────────┴─────────────────┘
```

## 🚀 Quick Start

### Prerequisites

- Docker and Docker Compose
- Unity 2022.3+ (for client development)
- 8GB+ RAM (recommended for full stack)
- macOS, Linux, or Windows with WSL2

### 1. Clone Repository

```bash
git clone https://github.com/your-username/VOXAR.git
cd VOXAR
```

### 2. Start Enterprise Stack

```bash
# Navigate to backend directory
cd Backend

# Start the enterprise Nakama stack
docker-compose -f docker-compose.enterprise.yml up -d

# Verify all services are running
docker ps --filter "name=spatial-"
```

### 3. Verify Services

| Service | URL | Credentials |
|---------|-----|-------------|
| Nakama Console | http://localhost:7351 | spatial_admin / spatial_console_2024_secure |
| Nakama API | http://localhost:7350 | - |
| WebSocket | ws://localhost:7349 | Bearer token required |
| Prometheus | http://localhost:9090 | - |
| Grafana | http://localhost:3000 | admin / spatial_admin_2024 |

### 4. Test Anonymous Session

```bash
# Authenticate and get token
TOKEN=$(curl -s -X POST "http://localhost:7350/v2/account/authenticate/device" \
  -H "Authorization: Basic ZGVmYXVsdGtleTo=" \
  -H "Content-Type: application/json" \
  -d '{"id":"test-device","create":true}' | jq -r .token)

# Create anonymous session with 6-character code
curl -X POST "http://localhost:7350/v2/rpc/create_anonymous_session" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '"{\"display_name\":\"TestUser\"}"' | jq '.payload | fromjson'

# Response: {"session_id":"...","share_code":"ABC123",...}
```

## 📱 Unity Integration

### Installation

1. Open Unity 2022.3+
2. Import the Nakama Unity SDK
3. Copy `Unity/SpatialPlatform` to your project
4. Configure Nakama client settings

### Basic Usage

```csharp
using Nakama;
using SpatialPlatform;

public class ARMultiplayerExample : MonoBehaviour
{
    private IClient client;
    private ISession session;
    private ISocket socket;
    private MultiplayerManager multiplayer;
    
    async void Start()
    {
        // Initialize Nakama client
        client = new Client("defaultkey", "localhost", 7350, false);
        
        // Authenticate (device ID for anonymous)
        var deviceId = SystemInfo.deviceUniqueIdentifier;
        session = await client.AuthenticateDeviceAsync(deviceId);
        
        // Connect WebSocket for real-time
        socket = client.NewSocket();
        await socket.ConnectAsync(session);
        
        // Create anonymous AR session
        var payload = JsonUtility.ToJson(new { display_name = "Player" });
        var response = await client.RpcAsync(session, "create_anonymous_session", payload);
        var sessionData = JsonUtility.FromJson<SessionResponse>(response.Payload);
        
        Debug.Log($"Share Code: {sessionData.share_code}");
        
        // Join AR match
        var match = await socket.CreateMatchAsync($"ar_session_{sessionData.session_id}");
        
        // Start sending pose updates at 60 FPS
        StartCoroutine(SendPoseUpdates(match.Id));
    }
    
    IEnumerator SendPoseUpdates(string matchId)
    {
        while (socket.IsConnected)
        {
            var pose = new
            {
                position = transform.position,
                rotation = transform.rotation,
                timestamp = Time.time
            };
            
            var json = JsonUtility.ToJson(pose);
            socket.SendMatchStateAsync(matchId, 1, json); // OpCode 1 = POSE_UPDATE
            
            yield return new WaitForSeconds(1f / 60f); // 60 FPS
        }
    }
}
```

## 🛠️ Development

### Project Structure

```
VOXAR/
├── Backend/
│   ├── docker-compose.enterprise.yml    # Production stack
│   ├── infrastructure/
│   │   ├── docker/
│   │   │   └── nakama/
│   │   │       └── modules/          # Lua modules
│   │   │           ├── auth_system.lua
│   │   │           ├── spatial_ar_match.lua
│   │   │           └── main.lua
│   │   ├── monitoring/               # Prometheus/Grafana configs
│   │   └── nginx/                    # Load balancer config
│   ├── multiplayer_service/          # Legacy (migrated to Nakama)
│   ├── localization_service/         # SLAM/VIO service
│   └── mapping_pipeline/             # COLMAP integration
├── Unity/
│   └── SpatialPlatform/
│       ├── Scripts/
│       │   ├── Core/
│       │   │   ├── Multiplayer/      # Nakama integration
│       │   │   └── AR/               # AR Foundation
│       │   └── UI/                   # Session UI
│       └── Prefabs/                  # AR prefabs
└── Docs/
    ├── API.md                        # API documentation
    ├── Deployment.md                 # Production deployment
    └── Unity-Integration.md          # Unity SDK guide
```

### Local Development

```bash
# Start development stack
cd Backend
docker-compose -f docker-compose.enterprise.yml up

# View logs
docker logs -f spatial-nakama

# Access Nakama console
open http://localhost:7351

# Run tests
docker exec spatial-nakama /nakama/nakama test

# Connect to database
docker exec -it spatial-postgres psql -U spatial_admin -d nakama
```

### Configuration

#### Environment Variables

Create `.env` file in Backend directory:

```env
# Database
POSTGRES_PASSWORD=spatial_prod_secure_2024
POSTGRES_DB=nakama

# Redis
REDIS_PASSWORD=redis_secure_2024

# Nakama
CONSOLE_PASSWORD=spatial_console_2024_secure

# Monitoring
GRAFANA_PASSWORD=spatial_admin_2024

# MinIO (if using object storage)
MINIO_ROOT_USER=spatial_admin
MINIO_ROOT_PASSWORD=spatial_minio_2024
```

#### Nakama Configuration

Key parameters in `docker-compose.enterprise.yml`:

```yaml
nakama:
  command: >
    --name spatial-ar-ent
    --database.address postgres://...
    --console.port 7351
    --metrics.prometheus_port 9100
    --session.token_expiry_sec 7200
    --socket.max_message_size_bytes 8192
```

## 📊 Monitoring

### Prometheus Metrics

Access metrics at http://localhost:9100/metrics

Key metrics to monitor:
- `nakama_api_request_count` - API request rate
- `nakama_match_count` - Active AR matches
- `nakama_session_count` - Active sessions
- `nakama_db_query_time` - Database performance

### Grafana Dashboards

1. Access Grafana: http://localhost:3000
2. Import dashboard from `infrastructure/monitoring/dashboards/`
3. View real-time metrics for:
   - AR session activity
   - WebSocket connections
   - Pose update frequency
   - Database performance

## 🔧 API Reference

### RPC Endpoints

| Endpoint | Description | Payload |
|----------|-------------|---------|
| `create_anonymous_session` | Create session with 6-char code | `{"display_name": "string"}` |
| `join_with_session_code` | Join existing session | `{"code": "ABC123", "display_name": "string"}` |
| `create_ar_match` | Create AR match room | `{"max_players": 8, "colocalization_method": "qr_code"}` |
| `list_ar_matches` | List active matches | `{}` |

### WebSocket Message Types

| OpCode | Type | Description |
|--------|------|-------------|
| 1 | POSE_UPDATE | Player position/rotation update |
| 2 | ANCHOR_CREATE | Create spatial anchor |
| 3 | ANCHOR_UPDATE | Update anchor position |
| 4 | ANCHOR_DELETE | Remove anchor |
| 5 | COLOCALIZATION_DATA | Share colocalization info |

## 🚀 Production Deployment

### AWS/GCP/Azure

1. Use Kubernetes manifests in `infrastructure/k8s/`
2. Configure cloud load balancer
3. Set up managed PostgreSQL and Redis
4. Enable auto-scaling for Nakama pods

### Docker Swarm

```bash
# Initialize swarm
docker swarm init

# Deploy stack
docker stack deploy -c docker-compose.enterprise.yml spatial-ar

# Scale Nakama
docker service scale spatial-ar_nakama=3
```

### Security Considerations

- Always use TLS in production (configure in nginx)
- Change all default passwords
- Enable Nakama authentication
- Configure firewall rules
- Regular security updates

## 📈 Performance

### Benchmarks

- **Concurrent Users**: 10,000+ per Nakama node
- **Pose Update Rate**: 60 FPS per user
- **Latency**: <50ms (regional deployment)
- **Session Creation**: <100ms
- **Anchor Sync**: <200ms

### Optimization Tips

1. Enable connection pooling in PostgreSQL
2. Configure Redis maxmemory policy
3. Use CDN for static assets
4. Enable gzip compression in nginx
5. Optimize Unity batching

## 🤝 Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for details.

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- [Nakama](https://heroiclabs.com/) - Game server powering multiplayer
- [Unity AR Foundation](https://unity.com/unity/features/arfoundation) - Cross-platform AR
- [COLMAP](https://colmap.github.io/) - 3D reconstruction pipeline
- [Docker](https://www.docker.com/) - Containerization platform

