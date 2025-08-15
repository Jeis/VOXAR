#!/bin/bash
# Spatial Platform - Production Deployment
# One-command deployment for end users

set -e

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
YELLOW='\033[1;33m'
NC='\033[0m'

print_header() { echo -e "${PURPLE}$1${NC}"; }
print_status() { echo -e "${BLUE}[INFO]${NC} $1"; }
print_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
print_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }

print_header "🚀 Spatial Platform - Production Deployment"
print_header "============================================"

# Check if Docker is running
if ! docker info >/dev/null 2>&1; then
    echo "❌ Docker is not running. Please start Docker and try again."
    exit 1
fi

print_status "Downloading latest production images..."

# Pull production images (these would be built and published to Docker Hub)
docker pull postgis/postgis:15-3.3-alpine
docker pull redis:7-alpine  
docker pull minio/minio:latest

# Note: These would be your published images
print_warning "Production images spatialplatform/* not yet published to Docker Hub"
print_status "Using development setup for now..."

# Create environment file if it doesn't exist
if [ ! -f .env.prod ]; then
    print_status "Creating production environment configuration..."
    cat > .env.prod << 'EOF'
# Spatial Platform - Production Configuration
# IMPORTANT: Change these default passwords!

POSTGRES_PASSWORD=your_secure_postgres_password_here
REDIS_PASSWORD=your_secure_redis_password_here
MINIO_USER=spatial_admin
MINIO_PASSWORD=your_secure_minio_password_here

# Optional: Customize ports
# POSTGRES_PORT=5432
# REDIS_PORT=6379
# API_PORT=8000
EOF
    print_warning "🔐 IMPORTANT: Edit .env.prod and change the default passwords!"
    print_status "Created .env.prod with default values"
fi

print_status "Starting Spatial Platform in production mode..."

# Start services
docker-compose --env-file .env.prod -f docker-compose.prod.yml up -d

print_success "🎉 Spatial Platform is starting up!"
print_header "📋 Access Information"
echo ""
echo "🌐 API Gateway:       http://localhost:8000"
echo "🗄️  MinIO Console:     http://localhost:9001"
echo "📊 Database:          localhost:5432"
echo ""
print_header "🔐 Security"
echo "⚠️  Remember to change default passwords in .env.prod"
echo "⚠️  This is for development/testing only"
echo "⚠️  For production deployment, use proper secrets management"
echo ""
print_success "Platform deployed successfully! 🚀"