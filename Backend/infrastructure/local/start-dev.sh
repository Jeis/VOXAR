#!/bin/bash
# Spatial Platform - Universal Development Environment
# Compatible with macOS, Linux, Windows WSL2 - All architectures

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
NC='\033[0m' # No Color

print_header() {
    echo -e "${PURPLE}$1${NC}"
}

print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Detect platform and architecture
detect_platform() {
    OS=$(uname -s)
    ARCH=$(uname -m)
    
    case "$OS" in
        "Darwin")
            if [[ "$ARCH" == "arm64" ]]; then
                echo "macOS Apple Silicon (M1/M2/M3)"
            else
                echo "macOS Intel"
            fi
            ;;
        "Linux")
            if grep -q Microsoft /proc/version 2>/dev/null; then
                echo "Windows WSL2 ($ARCH)"
            elif [[ -f /etc/os-release ]]; then
                . /etc/os-release
                echo "$NAME ($ARCH)"
            else
                echo "Linux ($ARCH)"
            fi
            ;;
        "MINGW"*|"CYGWIN"*|"MSYS"*)
            echo "Windows ($ARCH)"
            ;;
        *)
            echo "Unknown OS ($ARCH)"
            ;;
    esac
}

# Auto-configure resources based on platform
configure_resources() {
    ARCH=$(uname -m)
    CPU_CORES=$(nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo "2")
    
    # Get available memory in GB
    if command -v free >/dev/null 2>&1; then
        TOTAL_MEMORY=$(free -m | awk 'NR==2{printf "%.0f", $2/1024}')
    elif command -v vm_stat >/dev/null 2>&1; then
        # macOS
        TOTAL_MEMORY=$(( $(vm_stat | grep "Pages free" | awk '{print $3}' | sed 's/\.//' ) * 4096 / 1024 / 1024 / 1024 ))
    else
        TOTAL_MEMORY=8  # Default fallback
    fi
    
    print_status "Detected: $CPU_CORES cores, ${TOTAL_MEMORY}GB memory"
    
    # Architecture-specific optimization
    case "$ARCH" in
        "arm64"|"aarch64")
            # ARM64 (Apple Silicon, ARM servers)
            export MAX_WORKERS=$(( CPU_CORES > 4 ? 3 : 2 ))
            export MEMORY_LIMIT_GB=$(( TOTAL_MEMORY > 16 ? 6 : 4 ))
            export CELERY_CONCURRENCY=1
            print_status "ARM64 optimization: Efficiency-focused configuration"
            ;;
        "x86_64"|"amd64")
            # Intel/AMD processors
            export MAX_WORKERS=$(( CPU_CORES > 8 ? 6 : 4 ))
            export MEMORY_LIMIT_GB=$(( TOTAL_MEMORY > 16 ? 8 : 6 ))
            export CELERY_CONCURRENCY=2
            print_status "x86_64 optimization: Performance-focused configuration"
            ;;
        *)
            # Conservative defaults for unknown architectures
            export MAX_WORKERS=2
            export MEMORY_LIMIT_GB=4
            export CELERY_CONCURRENCY=1
            print_warning "Unknown architecture, using conservative settings"
            ;;
    esac
    
    print_success "Resource configuration: ${MAX_WORKERS} workers, ${MEMORY_LIMIT_GB}GB memory, ${CELERY_CONCURRENCY} celery workers"
}

# Check prerequisites
check_prerequisites() {
    print_status "Checking prerequisites..."
    
    local errors=0
    
    # Check Docker
    if ! command -v docker >/dev/null 2>&1; then
        print_error "Docker not found. Please install Docker:"
        echo "  macOS: https://docs.docker.com/desktop/mac/install/"
        echo "  Linux: https://docs.docker.com/engine/install/"
        echo "  Windows: https://docs.docker.com/desktop/windows/install/"
        ((errors++))
    else
        print_success "Docker: $(docker --version | cut -d' ' -f3 | cut -d',' -f1)"
    fi
    
    # Check Docker Compose
    if ! command -v docker-compose >/dev/null 2>&1; then
        print_error "Docker Compose not found. Please install Docker Compose"
        ((errors++))
    else
        print_success "Docker Compose: $(docker-compose --version | cut -d' ' -f3 | cut -d',' -f1)"
    fi
    
    # Check Docker daemon
    if ! docker info >/dev/null 2>&1; then
        print_error "Docker daemon not running. Please start Docker"
        ((errors++))
    else
        print_success "Docker daemon is running"
    fi
    
    if [ $errors -gt 0 ]; then
        print_error "Prerequisites check failed. Please fix the above issues."
        exit 1
    fi
    
    print_success "All prerequisites satisfied!"
}

# Create environment configuration
create_environment() {
    print_status "Creating environment configuration..."
    
    cat > .env << 'EOF'
# Spatial Platform - Development Environment
# Auto-generated configuration

# Project
COMPOSE_PROJECT_NAME=spatial-platform
ENVIRONMENT=development
DEBUG=true

# Database (PostgreSQL + PostGIS)
POSTGRES_DB=spatial_platform
POSTGRES_USER=spatial_admin
POSTGRES_PASSWORD=spatial_dev_123
POSTGRES_PORT=5432

# Cache (Redis)
REDIS_PASSWORD=spatial_redis_123
REDIS_PORT=6379

# Object Storage (MinIO)
MINIO_USER=spatial_admin
MINIO_PASSWORD=spatial_minio_123
MINIO_API_PORT=9000
MINIO_CONSOLE_PORT=9001

# Security
JWT_SECRET=spatial_jwt_dev_secret_key_123

# Services
API_GATEWAY_PORT=8000
MAPPING_METRICS_PORT=8080
MAPPING_HEALTH_PORT=8081
LOCALIZATION_API_PORT=8090
LOCALIZATION_HEALTH_PORT=8091
FLOWER_PORT=5555
PROMETHEUS_PORT=9090
GRAFANA_PORT=3000
GRAFANA_PASSWORD=admin

# Development
LOG_LEVEL=DEBUG
ENABLE_GPU=false
EOF
    
    # Load the environment
    source .env
    
    print_success "Environment configuration created"
}

# Initialize directories and configs
initialize_environment() {
    print_status "Initializing development environment..."
    
    # Create necessary directories
    mkdir -p data/{temp,cache,models} logs sql/init monitoring/{grafana/{dashboards,datasources},prometheus}
    
    # Database initialization script
    cat > sql/init/01-init-spatial-platform.sql << 'EOF'
-- Spatial Platform Database Initialization
-- Runs automatically when PostgreSQL container starts

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "postgis";
CREATE EXTENSION IF NOT EXISTS "postgis_topology";

-- Create core tables
CREATE TABLE IF NOT EXISTS reconstruction_jobs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    job_id VARCHAR(255) UNIQUE NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'pending',
    location_id VARCHAR(255),
    center_lat FLOAT,
    center_lng FLOAT,
    progress_percentage FLOAT DEFAULT 0.0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE,
    metadata JSONB DEFAULT '{}',
    error_message TEXT,
    warnings TEXT[]
);

CREATE TABLE IF NOT EXISTS spatial_maps (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    map_id VARCHAR(255) UNIQUE NOT NULL,
    location_id VARCHAR(255),
    name VARCHAR(255),
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    center_point GEOMETRY(POINT, 4326),
    bounding_box GEOMETRY(POLYGON, 4326),
    quality_score FLOAT,
    num_cameras INTEGER DEFAULT 0,
    num_points INTEGER DEFAULT 0,
    file_size_bytes BIGINT DEFAULT 0,
    metadata JSONB DEFAULT '{}',
    is_public BOOLEAN DEFAULT false
);

CREATE TABLE IF NOT EXISTS ar_sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id VARCHAR(255) UNIQUE NOT NULL,
    map_id VARCHAR(255) REFERENCES spatial_maps(map_id),
    user_id VARCHAR(255),
    started_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    ended_at TIMESTAMP WITH TIME ZONE,
    device_info JSONB DEFAULT '{}',
    tracking_quality FLOAT,
    localization_success BOOLEAN DEFAULT false,
    pose_estimates JSONB DEFAULT '[]'
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_reconstruction_jobs_status ON reconstruction_jobs(status);
CREATE INDEX IF NOT EXISTS idx_reconstruction_jobs_location ON reconstruction_jobs(location_id);
CREATE INDEX IF NOT EXISTS idx_reconstruction_jobs_created ON reconstruction_jobs(created_at);

CREATE INDEX IF NOT EXISTS idx_spatial_maps_location ON spatial_maps(location_id);
CREATE INDEX IF NOT EXISTS idx_spatial_maps_created ON spatial_maps(created_at);
CREATE INDEX IF NOT EXISTS idx_spatial_maps_public ON spatial_maps(is_public);

CREATE INDEX IF NOT EXISTS idx_ar_sessions_map ON ar_sessions(map_id);
CREATE INDEX IF NOT EXISTS idx_ar_sessions_user ON ar_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_ar_sessions_started ON ar_sessions(started_at);

-- Spatial indexes
CREATE INDEX IF NOT EXISTS idx_spatial_maps_center_point ON spatial_maps USING GIST(center_point);
CREATE INDEX IF NOT EXISTS idx_spatial_maps_bounding_box ON spatial_maps USING GIST(bounding_box);

-- Insert sample data for development
INSERT INTO reconstruction_jobs (job_id, status, location_id, metadata) VALUES 
    ('sample-job-001', 'pending', 'dev-location-001', '{"description": "Sample reconstruction job", "image_count": 25}'),
    ('sample-job-002', 'completed', 'dev-location-002', '{"description": "Completed test job", "image_count": 18}')
ON CONFLICT (job_id) DO NOTHING;

INSERT INTO spatial_maps (map_id, location_id, name, center_point, quality_score, num_cameras, num_points) VALUES 
    ('sample-map-001', 'dev-location-001', 'Development Test Map', ST_SetSRID(ST_MakePoint(-122.4194, 37.7749), 4326), 0.85, 15, 2500),
    ('sample-map-002', 'dev-location-002', 'Office Building Map', ST_SetSRID(ST_MakePoint(-73.9857, 40.7484), 4326), 0.92, 22, 4800)
ON CONFLICT (map_id) DO NOTHING;

-- Grant permissions
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO spatial_admin;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO spatial_admin;

-- Log completion
\echo 'Spatial Platform database initialized successfully!'
EOF

    # Prometheus configuration
    cat > monitoring/prometheus.yml << 'EOF'
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'spatial-platform'
    static_configs:
      - targets: 
        - 'mapping-processor:8080'
        - 'localization-service:8080'
        - 'api-gateway:8000'
    scrape_interval: 30s
    metrics_path: '/metrics'
    
  - job_name: 'infrastructure'
    static_configs:
      - targets:
        - 'postgres:5432'
        - 'redis:6379'
        - 'minio:9000'
    scrape_interval: 60s
EOF

    # Grafana datasource
    mkdir -p monitoring/grafana/datasources
    cat > monitoring/grafana/datasources/prometheus.yml << 'EOF'
apiVersion: 1
datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://prometheus:9090
    isDefault: true
EOF

    # Set permissions
    chmod -R 755 data/ logs/ monitoring/
    
    print_success "Environment initialized"
}

# Main execution
main() {
    # Navigate to correct directory
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
    cd "$SCRIPT_DIR"
    
    # Header
    print_header "🚀 Spatial Platform - Universal Development Environment"
    print_header "======================================================"
    
    PLATFORM_INFO=$(detect_platform)
    print_status "Platform: $PLATFORM_INFO"
    print_status "Starting development environment setup..."
    echo ""
    
    # Setup process
    check_prerequisites
    configure_resources
    create_environment
    initialize_environment
    
    print_status "Starting services with Docker Compose..."
    
    # Stop any existing containers
    docker-compose down 2>/dev/null || true
    
    # Start infrastructure services first
    print_status "Starting infrastructure (PostgreSQL, Redis, MinIO)..."
    docker-compose up -d postgres redis minio
    
    # Wait for infrastructure
    print_status "Waiting for infrastructure services..."
    
    # Wait for PostgreSQL
    timeout 60 bash -c 'until docker-compose exec -T postgres pg_isready -U spatial_admin; do sleep 2; done' && \
    print_success "PostgreSQL ready" || (print_error "PostgreSQL timeout" && exit 1)
    
    # Setup MinIO buckets
    docker-compose up -d minio-setup
    
    # Start monitoring
    print_status "Starting monitoring (Prometheus, Grafana)..."
    docker-compose up -d prometheus grafana
    
    # Start application services
    print_status "Starting application services..."
    print_warning "Building containers for first time... This may take 5-10 minutes."
    
    docker-compose up -d \
        dev-tools \
        mapping-processor \
        localization-service \
        celery-worker \
        flower \
        api-gateway
    
    # Wait for API Gateway
    print_status "Waiting for services to be ready..."
    timeout 120 bash -c 'until curl -sf http://localhost:8000/health >/dev/null 2>&1; do sleep 3; done' && \
    print_success "API Gateway ready" || print_warning "API Gateway may still be starting"
    
    # Final status
    echo ""
    print_header "🎉 Spatial Platform Development Environment Started!"
    print_header "=================================================="
    
    echo ""
    echo "📋 Platform: $PLATFORM_INFO"
    echo "⚙️  Resources: $MAX_WORKERS workers, ${MEMORY_LIMIT_GB}GB memory"
    echo ""
    
    print_header "🔗 Service Access URLs:"
    echo "📡 API Gateway:       http://localhost:8000"
    echo "📊 Grafana Dashboard: http://localhost:3000 (admin/admin)"
    echo "📈 Prometheus:        http://localhost:9090"
    echo "🗄️  MinIO Console:     http://localhost:9001 (spatial_admin/spatial_minio_123)"
    echo "🌸 Flower (Celery):   http://localhost:5555"
    echo ""
    
    print_header "🛠️  Development Commands:"
    echo "View logs:     docker-compose logs -f [service]"
    echo "Stop all:      docker-compose down"
    echo "Restart:       docker-compose restart [service]"
    echo "Shell access:  docker-compose exec [service] bash"
    echo "Health check:  ./check-services.sh"
    echo ""
    
    print_header "📚 Quick Start:"
    echo "1. Open http://localhost:8000 for API documentation"
    echo "2. Check service health: ./check-services.sh"
    echo "3. View logs: docker-compose logs -f api-gateway"
    echo "4. Access database: docker-compose exec postgres psql -U spatial_admin -d spatial_platform"
    echo ""
    
    print_success "Happy coding! 🚀"
}

# Run main function
main "$@"