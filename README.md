# VOXAR

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Unity Version](https://img.shields.io/badge/Unity-2022.3%2B-blue.svg)](https://unity3d.com/get-unity/download)

Enterprise-grade AR development framework with real-time multiplayer, spatial mapping, and cross-platform support.

## Features

- **Real-time multiplayer AR** with spatial anchor synchronization
- **Visual-inertial tracking** with sub-100ms localization
- **3D mapping pipeline** using COLMAP for persistent environments
- **Cross-platform support** (iOS, Android, Unity)
- **Anonymous sessions** with 6-character join codes
- **Enterprise authentication** with JWT and role-based access
- **Production-ready infrastructure** with Docker and monitoring

## Architecture

```
Unity/Mobile Clients
        ↓
   API Gateway (FastAPI)
        ↓
┌─────────────┬─────────────┬─────────────┐
│ Multiplayer │Localization │   Mapping   │
│  (WebSocket)│(SLAM/VIO)   │  (COLMAP)   │
└─────────────┴─────────────┴─────────────┘
        ↓
Infrastructure (PostgreSQL, Redis, MinIO)
```

## Quick Start

### Prerequisites

- Docker and Docker Compose
- Unity 2022.3+ (for client development)
- 4GB+ RAM

### 1. Clone and Start

```bash
git clone <repository-url>
cd Spatial/Backend/infrastructure/local
./start-dev.sh
```

### 2. Verify Services

- API Gateway: http://localhost:8000
- Grafana: http://localhost:3000 (admin/admin)
- MinIO Console: http://localhost:9001

### 3. Unity Setup

1. Import `Unity/SpatialPlatform` package
2. Configure API endpoint: `http://localhost:8000`
3. Run sample scenes

## Basic Usage

### Create Session (REST API)

```bash
# Anonymous session
curl -X POST http://localhost:8000/api/v1/session/anonymous/create \
  -H "Content-Type: application/json" \
  -d '{"display_name": "Demo User"}'

# Returns: {"session_id": "...", "share_code": "ABC123"}
```

### Connect to Session (WebSocket)

```javascript
const ws = new WebSocket('ws://localhost:8080/ws/{session_id}');
ws.send(JSON.stringify({
  type: 'pose_update',
  position: {x: 0, y: 0, z: 0},
  rotation: {x: 0, y: 0, z: 0, w: 1}
}));
```

### Unity Integration

```csharp
// Initialize AR session
var arManager = FindObjectOfType<ARSessionManager>();
arManager.StartARSession();

// Connect to multiplayer
var multiplayer = FindObjectOfType<MultiplayerManager>();
await multiplayer.ConnectToSession(sessionId);

// Create spatial anchor
var anchor = new SpatialAnchor(position, rotation, metadata);
await multiplayer.CreateAnchor(anchor);
```

## Development

### Service Management

```bash
# View logs
docker-compose logs -f multiplayer-service

# Restart service
docker-compose restart api-gateway

# Stop all
docker-compose down
```

### Database Access

```bash
docker-compose exec postgres psql -U spatial_admin -d spatial_platform
```

## Tech Stack

**Backend**: FastAPI, WebSockets, PostgreSQL+PostGIS, Redis, MinIO, COLMAP  
**Unity**: AR Foundation, ARKit/ARCore, WebSocket client  
**Infrastructure**: Docker, Prometheus, Grafana, nginx

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make changes with tests
4. Submit a pull request

## License

MIT License - see [LICENSE](LICENSE) file for details.