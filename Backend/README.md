# VOXAR Enterprise Platform - Deployment Guide

Enterprise-grade spatial AR platform with consolidated Docker orchestration.

## Quick Start

```bash
# Development environment
make dev

# Development with all services (VPS + Cloud Anchors)
make dev-full

# Staging environment  
make staging

# Production environment
make prod
```

## Environment Structure

Our platform uses a **base + override** architecture for clean environment management:

```
infrastructure/docker/
├── docker-compose.base.yml              # Common services
├── environments/
│   ├── docker-compose.development.yml   # Dev overrides
│   ├── docker-compose.staging.yml      # Staging overrides
│   └── docker-compose.production.yml   # Production config
└── scripts/
    └── deploy.sh                        # Deployment automation
```

## Available Commands

### Environment Management
- `make dev` - Start development environment
- `make dev-full` - Start development with all services
- `make staging` - Start staging environment
- `make prod` - Start production environment
- `make stop` - Stop all environments

### Monitoring & Status
- `make status` - Check development status
- `make status-staging` - Check staging status  
- `make status-prod` - Check production status
- `make logs` - View development logs
- `make health` - Run health checks

### Service Management
- `make build` - Build all images
- `make clean` - Clean up resources
- `make backup` - Backup data volumes
- `make secrets` - Setup production secrets

## Service URLs (Development)

| Service | URL | Credentials |
|---------|-----|-------------|
| API Gateway | http://localhost:8000 | - |
| Nakama Console | http://localhost:7351 | spatial_admin/spatial_console_dev |
| Grafana | http://localhost:3000 | admin/spatial_admin_dev |
| Prometheus | http://localhost:9090 | - |
| pgAdmin | http://localhost:5050 | admin@voxar.io/pgadmin_dev |
| Redis Commander | http://localhost:8082 | - |

## Environment Profiles

### Development
- Hot reload enabled
- Debug logging
- Development tools (pgAdmin, Redis Commander)
- All ports exposed for debugging
- Relaxed security settings

### Staging
- Production-like settings
- INFO level logging
- Resource constraints
- SSL termination
- Performance monitoring

### Production
- Docker secrets management
- nginx load balancer with TLS
- Resource limits and monitoring
- Security hardening
- Backup automation

## Manual Deployment Script

For advanced deployment options:

```bash
# Direct script usage
./infrastructure/docker/scripts/deploy.sh [environment] [options]

# Examples
./infrastructure/docker/scripts/deploy.sh development
./infrastructure/docker/scripts/deploy.sh staging --full
./infrastructure/docker/scripts/deploy.sh production
```

## Production Setup

1. **Create Docker Secrets**:
```bash
make secrets
```

2. **Configure nginx SSL**:
```bash
# Place SSL certificates in:
infrastructure/docker/nginx/ssl/
├── fullchain.pem
├── privkey.pem
└── chain.pem
```

3. **Deploy Production**:
```bash
make prod
```

## Architecture Overview

### Core Services
- **PostgreSQL** - Primary database with spatial extensions
- **Redis** - Caching and session storage
- **MinIO** - Object storage for 3D maps and assets
- **Nakama** - Real-time multiplayer game server
- **nginx** - Load balancer and SSL termination

### Spatial Services
- **API Gateway** - Unified API endpoint
- **Localization Service** - AR tracking and positioning
- **VPS Engine** - Visual positioning system
- **Cloud Anchor Service** - Persistent spatial anchors
- **Mapping Processor** - 3D reconstruction pipeline

### Monitoring Stack
- **Prometheus** - Metrics collection
- **Grafana** - Visualization and alerting
- **OpenTelemetry** - Distributed tracing (coming soon)

## Development Workflow

1. **Start Development Environment**:
```bash
make dev
```

2. **Monitor Services**:
```bash
make status
make logs
```

3. **Access Development Tools**:
- Database: `make dev-db`
- Service Shell: `make shell SERVICE=gateway`
- Health Check: `make health`

4. **Test Changes**:
```bash
make test
```

5. **Deploy to Staging**:
```bash
make staging
```

## Troubleshooting

### Common Issues

**Services not starting**:
```bash
make status
make logs
```

**Port conflicts**:
```bash
make stop
make clean
make dev
```

**Database connection issues**:
```bash
make dev-db
# Check PostgreSQL logs
make logs-service SERVICE=postgres
```

**Build failures**:
```bash
make build-no-cache
```

### Health Checks

All services include health checks. Monitor with:
```bash
make health
```

### Resource Usage

Monitor resource consumption:
```bash
docker stats
```

## Database Clustering

For high availability PostgreSQL setup:

```bash
# Deploy HA cluster
make cluster-deploy

# Check cluster status
make cluster-status

# Manual backup
make cluster-backup

# Connection strings:
# Write: postgresql://spatial_admin:<password>@localhost:6432/spatial_platform
# Read:  postgresql://spatial_reader:<password>@localhost:5433/spatial_platform
```

## Contributing

1. Use the development environment for all changes
2. Test with `make test` before committing
3. Validate staging deployment before production
4. Follow the established environment patterns

## Support

For deployment issues:
1. Check `make status` and `make health`
2. Review service logs with `make logs`
3. Validate configuration with the deployment script
4. Check resource usage and conflicts