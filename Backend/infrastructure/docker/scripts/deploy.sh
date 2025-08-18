#!/bin/bash
# VOXAR Platform Deployment Script
# Enterprise-grade deployment automation

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DOCKER_DIR="$(dirname "$SCRIPT_DIR")"
BASE_DIR="$(dirname "$(dirname "$DOCKER_DIR")")"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Environment configuration
ENVIRONMENTS=("development" "staging" "production")
DEFAULT_ENV="development"
ENVIRONMENT="${1:-$DEFAULT_ENV}"

# Logging
log() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
    exit 1
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

# Validation functions
validate_environment() {
    if [[ ! " ${ENVIRONMENTS[@]} " =~ " ${ENVIRONMENT} " ]]; then
        error "Invalid environment: ${ENVIRONMENT}. Valid options: ${ENVIRONMENTS[*]}"
    fi
}

check_dependencies() {
    log "Checking dependencies..."
    
    command -v docker >/dev/null 2>&1 || error "Docker is not installed"
    command -v docker-compose >/dev/null 2>&1 || error "Docker Compose is not installed"
    
    if ! docker info >/dev/null 2>&1; then
        error "Docker daemon is not running"
    fi
    
    success "Dependencies check passed"
}

validate_compose_files() {
    log "Validating Docker Compose files..."
    
    local base_file="${DOCKER_DIR}/docker-compose.base.yml"
    local env_file="${DOCKER_DIR}/environments/docker-compose.${ENVIRONMENT}.yml"
    
    if [[ ! -f "$base_file" ]]; then
        error "Base compose file not found: $base_file"
    fi
    
    if [[ ! -f "$env_file" ]]; then
        error "Environment compose file not found: $env_file"
    fi
    
    # Validate syntax
    if ! docker-compose -f "$base_file" -f "$env_file" config >/dev/null 2>&1; then
        error "Docker Compose configuration is invalid"
    fi
    
    success "Compose files validation passed"
}

# Environment setup
setup_environment() {
    log "Setting up ${ENVIRONMENT} environment..."
    
    cd "$DOCKER_DIR"
    
    # Create environment file if it doesn't exist
    local env_file=".env.${ENVIRONMENT}"
    if [[ ! -f "$env_file" ]]; then
        log "Creating environment file: $env_file"
        cat > "$env_file" << EOF
# VOXAR Platform - ${ENVIRONMENT} Environment
ENVIRONMENT=${ENVIRONMENT}
COMPOSE_PROJECT_NAME=voxar-${ENVIRONMENT}

# Service Ports (${ENVIRONMENT})
POSTGRES_PORT=5432
REDIS_PORT=6379
MINIO_PORT=9000
MINIO_CONSOLE_PORT=9001
NAKAMA_GRPC_PORT=7348
NAKAMA_WS_PORT=7349
NAKAMA_HTTP_PORT=7350
NAKAMA_CONSOLE_PORT=7351
NAKAMA_METRICS_PORT=9100
GATEWAY_PORT=8000
LOCALIZATION_PORT=8081
PROMETHEUS_PORT=9090
GRAFANA_PORT=3000

# Logging
LOG_LEVEL=${ENVIRONMENT == "production" && echo "INFO" || echo "DEBUG"}

# Domain Configuration
DOMAIN_NAME=${ENVIRONMENT == "production" && echo "api.voxar.io" || echo "localhost"}
ENABLE_CERTBOT=${ENVIRONMENT == "production" && echo "true" || echo "false"}
EOF
    fi
    
    success "Environment setup completed"
}

# Production secrets setup
setup_production_secrets() {
    if [[ "$ENVIRONMENT" != "production" ]]; then
        return 0
    fi
    
    log "Setting up production secrets..."
    
    local secrets=(
        "postgres_password"
        "redis_password"
        "nakama_key"
        "nginx_admin_password"
        "minio_access_key"
        "minio_secret_key"
    )
    
    for secret in "${secrets[@]}"; do
        if ! docker secret ls --format "{{.Name}}" | grep -q "^${secret}$"; then
            warn "Production secret '${secret}' not found"
            echo "Please create it with: echo 'your_secret_value' | docker secret create ${secret} -"
        fi
    done
    
    success "Production secrets check completed"
}

# Deployment functions
pre_deployment_checks() {
    log "Running pre-deployment checks..."
    
    validate_environment
    check_dependencies
    validate_compose_files
    setup_environment
    setup_production_secrets
    
    success "Pre-deployment checks passed"
}

deploy_infrastructure() {
    log "Deploying infrastructure services..."
    
    cd "$DOCKER_DIR"
    
    local compose_files="-f docker-compose.base.yml -f environments/docker-compose.${ENVIRONMENT}.yml"
    local env_file=".env.${ENVIRONMENT}"
    
    # Load environment variables
    export $(cat "$env_file" | grep -v '^#' | xargs)
    
    # Deploy core infrastructure first
    log "Starting core infrastructure (postgres, redis, minio)..."
    docker-compose $compose_files up -d postgres redis minio
    
    # Wait for health checks
    log "Waiting for infrastructure health checks..."
    local max_attempts=30
    local attempt=0
    
    while [[ $attempt -lt $max_attempts ]]; do
        if docker-compose $compose_files ps | grep -q "healthy"; then
            break
        fi
        sleep 10
        ((attempt++))
    done
    
    if [[ $attempt -eq $max_attempts ]]; then
        error "Infrastructure health checks failed"
    fi
    
    success "Infrastructure deployment completed"
}

deploy_services() {
    log "Deploying application services..."
    
    cd "$DOCKER_DIR"
    
    local compose_files="-f docker-compose.base.yml -f environments/docker-compose.${ENVIRONMENT}.yml"
    
    # Deploy application services
    log "Starting application services..."
    docker-compose $compose_files up -d nakama gateway localization
    
    # Deploy monitoring
    log "Starting monitoring services..."
    docker-compose $compose_files up -d prometheus grafana
    
    # Deploy nginx last (production only)
    if [[ "$ENVIRONMENT" == "production" ]]; then
        log "Starting nginx load balancer..."
        docker-compose $compose_files up -d nginx
    fi
    
    success "Services deployment completed"
}

deploy_optional_services() {
    log "Deploying optional services..."
    
    cd "$DOCKER_DIR"
    
    local compose_files="-f docker-compose.base.yml -f environments/docker-compose.${ENVIRONMENT}.yml"
    
    # Deploy optional services based on profiles
    if [[ "$ENVIRONMENT" == "development" ]]; then
        log "Starting development tools..."
        docker-compose $compose_files --profile tools up -d
    fi
    
    # Ask about VPS and Cloud Anchor services
    if [[ "${2:-}" == "--full" ]] || [[ "${DEPLOY_FULL:-}" == "true" ]]; then
        log "Starting VPS and Cloud Anchor services..."
        docker-compose $compose_files --profile full up -d
    fi
    
    success "Optional services deployment completed"
}

# Health checks
run_health_checks() {
    log "Running health checks..."
    
    cd "$DOCKER_DIR"
    
    local compose_files="-f docker-compose.base.yml -f environments/docker-compose.${ENVIRONMENT}.yml"
    local failed_services=()
    
    # Check service health
    local services=(postgres redis minio nakama gateway localization prometheus grafana)
    
    for service in "${services[@]}"; do
        log "Checking $service health..."
        
        local max_attempts=30
        local attempt=0
        
        while [[ $attempt -lt $max_attempts ]]; do
            if docker-compose $compose_files ps "$service" | grep -q "healthy\|Up"; then
                success "$service is healthy"
                break
            fi
            sleep 5
            ((attempt++))
        done
        
        if [[ $attempt -eq $max_attempts ]]; then
            warn "$service health check failed"
            failed_services+=("$service")
        fi
    done
    
    if [[ ${#failed_services[@]} -gt 0 ]]; then
        error "Health checks failed for: ${failed_services[*]}"
    fi
    
    success "All health checks passed"
}

# Rollback functionality
rollback() {
    log "Rolling back deployment..."
    
    cd "$DOCKER_DIR"
    
    local compose_files="-f docker-compose.base.yml -f environments/docker-compose.${ENVIRONMENT}.yml"
    
    # Stop services in reverse order
    docker-compose $compose_files down
    
    success "Rollback completed"
}

# Cleanup
cleanup() {
    log "Cleaning up unused resources..."
    
    docker system prune -f
    docker volume prune -f
    
    success "Cleanup completed"
}

# Status check
status() {
    log "Checking deployment status..."
    
    cd "$DOCKER_DIR"
    
    local compose_files="-f docker-compose.base.yml -f environments/docker-compose.${ENVIRONMENT}.yml"
    
    echo ""
    echo "=== Service Status ==="
    docker-compose $compose_files ps
    
    echo ""
    echo "=== Resource Usage ==="
    docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}\t{{.BlockIO}}"
    
    echo ""
    echo "=== Logs (last 10 lines) ==="
    docker-compose $compose_files logs --tail=10
}

# Usage information
usage() {
    cat << EOF
VOXAR Platform Deployment Script

Usage: $0 [ENVIRONMENT] [OPTIONS]

Environments:
  development  - Development environment (default)
  staging      - Staging environment
  production   - Production environment

Options:
  --full       - Deploy all services including VPS and Cloud Anchors
  --rollback   - Rollback current deployment
  --status     - Show deployment status
  --cleanup    - Clean up unused Docker resources
  --help       - Show this help message

Examples:
  $0                          # Deploy development environment
  $0 staging                  # Deploy staging environment
  $0 production --full        # Deploy production with all services
  $0 development --rollback   # Rollback development deployment
  $0 staging --status         # Check staging deployment status

EOF
}

# Main execution
main() {
    case "${2:-}" in
        --help)
            usage
            exit 0
            ;;
        --rollback)
            rollback
            exit 0
            ;;
        --status)
            status
            exit 0
            ;;
        --cleanup)
            cleanup
            exit 0
            ;;
    esac
    
    log "Starting VOXAR Platform deployment for ${ENVIRONMENT} environment"
    
    # Run deployment steps
    pre_deployment_checks
    deploy_infrastructure
    deploy_services
    deploy_optional_services "$@"
    run_health_checks
    
    success "Deployment completed successfully!"
    
    # Show next steps
    cat << EOF

=== Deployment Summary ===
Environment: ${ENVIRONMENT}
Services: All core services deployed

Next steps:
1. Check service status: $0 ${ENVIRONMENT} --status
2. View logs: docker-compose -f docker-compose.base.yml -f environments/docker-compose.${ENVIRONMENT}.yml logs -f
3. Access services:
   - API Gateway: http://localhost:8000
   - Nakama Console: http://localhost:7351
   - Grafana: http://localhost:3000
   - Prometheus: http://localhost:9090

EOF
}

# Execute main function with all arguments
main "$@"