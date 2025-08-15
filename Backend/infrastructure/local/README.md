# Spatial Platform - Universal Development Environment

**One command setup for any platform** - Works on macOS (Intel/Apple Silicon), Linux (x86_64/ARM64), and Windows WSL2.

## 🚀 Quick Start

```bash
# Clone and navigate
git clone https://github.com/your-org/spatial-platform.git
cd spatial-platform/Backend/infrastructure/local

# Start everything (auto-detects your platform)
./start-dev.sh

# Check health
./check-services.sh
```

That's it! The environment auto-configures for your system.

## 🌍 Platform Support

| Platform | Status | Optimizations |
|----------|--------|---------------|
| **macOS Apple Silicon** | ✅ Fully Supported | ARM64 optimized, thermal aware |
| **macOS Intel** | ✅ Fully Supported | x86_64 optimized, performance focused |
| **Linux x86_64** | ✅ Fully Supported | High performance, server optimized |
| **Linux ARM64** | ✅ Fully Supported | Efficiency optimized |
| **Windows WSL2** | ✅ Fully Supported | Cross-platform compatible |

## 🎯 What's Included

### Core Services
- **PostgreSQL + PostGIS** - Spatial database for 3D map data
- **Redis** - Caching and job queues
- **MinIO** - S3-compatible object storage
- **Prometheus + Grafana** - Monitoring and dashboards

### AR/3D Services
- **Mapping Processor** - COLMAP-based 3D reconstruction
- **Localization Service** - AR tracking and positioning
- **API Gateway** - RESTful API with FastAPI
- **Background Workers** - Celery task processing

### Development Tools
- **Dev Container** - Interactive development environment
- **Health Monitoring** - Automatic service health checks
- **Log Aggregation** - Centralized logging
- **Hot Reloading** - Code changes reflected instantly

## 📊 Auto-Configuration

The system automatically detects your platform and optimizes:

### Apple Silicon (M1/M2/M3)
```bash
Workers: 2-3        # Efficiency cores
Memory: 4-6GB       # Thermal management
GPU: Disabled       # Metal not supported in containers
```

### Intel/AMD (x86_64)
```bash
Workers: 4-6        # Performance cores
Memory: 6-8GB       # Maximum throughput
GPU: Optional       # CUDA support available
```

### Resource Detection
- **CPU Cores**: Auto-detected via `nproc`
- **Memory**: Auto-detected and allocated efficiently
- **Architecture**: ARM64 vs x86_64 optimization
- **Platform**: macOS/Linux/WSL2 specific tools

## 🔗 Service URLs

| Service | URL | Credentials |
|---------|-----|-------------|
| **API Gateway** | http://localhost:8000 | - |
| **Grafana Dashboard** | http://localhost:3000 | admin/admin |
| **Prometheus Metrics** | http://localhost:9090 | - |
| **MinIO Console** | http://localhost:9001 | spatial_admin/spatial_minio_123 |
| **Celery Monitor** | http://localhost:5555 | - |
| **PostgreSQL** | localhost:5432 | spatial_admin/spatial_dev_123 |
| **Redis** | localhost:6379 | password: spatial_redis_123 |

## 🛠️ Development Workflow

### Daily Development
```bash
# Start everything
./start-dev.sh

# Check status
./check-services.sh

# View logs
docker-compose logs -f api-gateway
docker-compose logs -f mapping-processor

# Access services
docker-compose exec dev-tools bash
docker-compose exec postgres psql -U spatial_admin -d spatial_platform
```

### Testing 3D Reconstruction
```bash
# Shell into mapping processor
docker-compose exec mapping-processor bash

# Test COLMAP
colmap --help
python3 -c "import spatial_mapping; print('✓ Module loaded')"

# Check processing capabilities
curl http://localhost:8081/health
```

### Database Operations
```bash
# Connect to database
docker-compose exec postgres psql -U spatial_admin -d spatial_platform

# View tables
\dt

# Check sample data
SELECT * FROM reconstruction_jobs;
SELECT map_id, name, ST_AsText(center_point) FROM spatial_maps;
```

### Object Storage
```bash
# Web interface
open http://localhost:9001

# CLI access
docker-compose exec dev-tools bash
pip install minio
python3 -c "
from minio import Minio
client = Minio('localhost:9000', access_key='spatial_admin', secret_key='spatial_minio_123', secure=False)
print('Buckets:', [b.name for b in client.list_buckets()])
"
```

## 🧪 Testing & Validation

### Service Health
```bash
# Quick health check
./check-services.sh

# Detailed service status
docker-compose ps
docker stats
```

### API Testing
```bash
# API documentation
open http://localhost:8000/docs

# Test endpoints
curl http://localhost:8000/health
curl http://localhost:8000/api/v1/maps/

# Test reconstruction job
curl -X POST http://localhost:8000/api/v1/jobs/ \
  -H "Content-Type: application/json" \
  -d '{"location_id": "test-001", "images": []}'
```

### Performance Testing
```bash
# Monitor resources
docker stats --no-stream

# Load testing (if you have Apache Bench)
ab -n 100 -c 10 http://localhost:8000/health

# Database performance
docker-compose exec postgres psql -U spatial_admin -d spatial_platform -c "
SELECT 
  schemaname,
  tablename,
  attname,
  n_distinct,
  correlation
FROM pg_stats 
WHERE tablename IN ('reconstruction_jobs', 'spatial_maps');
"
```

## 🚨 Troubleshooting

### Common Issues

#### Services Won't Start
```bash
# Check Docker
docker info
docker-compose --version

# Clean restart
docker-compose down
docker system prune -f
./start-dev.sh
```

#### Port Conflicts
```bash
# Check what's using ports
lsof -i :5432  # PostgreSQL
lsof -i :8000  # API Gateway
lsof -i :9000  # MinIO

# Kill conflicting processes
sudo lsof -ti:5432 | xargs kill -9
```

#### Performance Issues
```bash
# Check resource usage
docker stats
htop  # or Activity Monitor on macOS

# Adjust resources in Docker Desktop settings:
# - Memory: 8-16GB recommended
# - CPUs: 4-8 cores recommended
# - Enable VirtioFS (macOS) for better file performance
```

#### Database Connection Issues
```bash
# Reset database
docker-compose down postgres
docker volume rm spatial-platform_postgres_data
./start-dev.sh
```

### Platform-Specific Tips

#### macOS
```bash
# Optimize Docker Desktop
# Settings > Resources > Advanced:
# - Memory: 12-16GB
# - CPUs: 6-8 cores
# - Enable "Use VirtioFS for file sharing"
```

#### Linux
```bash
# Increase file watchers (for hot reloading)
echo fs.inotify.max_user_watches=524288 | sudo tee -a /etc/sysctl.conf
sudo sysctl -p

# Docker post-installation
sudo usermod -aG docker $USER
# Log out and back in
```

#### Windows WSL2
```bash
# Ensure Docker Desktop integration
# Docker Desktop > Settings > Resources > WSL Integration
# Enable integration for your WSL distro

# Increase WSL memory
# Create/edit ~/.wslconfig:
[wsl2]
memory=12GB
processors=6
```

## 🔧 Customization

### Environment Variables
Edit `.env` file to customize:
```bash
# Change default ports
API_GATEWAY_PORT=8080
GRAFANA_PORT=3001

# Adjust resources
MAX_WORKERS=8
MEMORY_LIMIT_GB=16

# Enable GPU (if available)
ENABLE_GPU=true
```

### Adding Services
Add to `docker-compose.yml`:
```yaml
your-service:
  build: ./your-service
  depends_on:
    - postgres
    - redis
  networks:
    - spatial-network
```

### Custom Configuration
```bash
# Override compose file
cp docker-compose.yml docker-compose.override.yml
# Edit docker-compose.override.yml with your changes
```

## 🌟 Features

### Cross-Platform Compatibility
- **Zero Configuration** - Works out of the box on any platform
- **Auto-Detection** - Automatically optimizes for your hardware
- **Universal Containers** - Same Docker images work everywhere
- **Platform Tools** - Uses available system tools intelligently

### Development Experience
- **Hot Reloading** - Code changes reflected immediately
- **Comprehensive Logging** - Structured logs with log levels
- **Health Monitoring** - Built-in service health checks
- **Performance Metrics** - Real-time performance monitoring

### Production Readiness
- **Enterprise Architecture** - Microservices with proper separation
- **Scalable Design** - Horizontal scaling ready
- **Security Best Practices** - Non-root containers, secret management
- **Monitoring Stack** - Prometheus + Grafana included

## 📚 Next Steps

1. **Explore the API** - Visit http://localhost:8000/docs
2. **Upload Test Images** - Use the MinIO console or API
3. **Create 3D Maps** - Submit reconstruction jobs
4. **Monitor Performance** - Check Grafana dashboards
5. **Develop Features** - Use the dev-tools container

## 🤝 Contributing

This universal development environment makes it easy for anyone to contribute:

1. **Fork the repository**
2. **Run `./start-dev.sh`** (works on any platform)
3. **Make your changes**
4. **Test with `./check-services.sh`**
5. **Submit a pull request**

No platform-specific setup required! 🎉

---

**Happy coding on any platform!** 🚀