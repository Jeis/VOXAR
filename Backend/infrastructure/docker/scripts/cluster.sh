#!/bin/bash
# VOXAR PostgreSQL Cluster Management Script
# Manages HA PostgreSQL cluster deployment and operations

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

# Cluster operations
ACTION="${1:-help}"

# Check dependencies
check_dependencies() {
    log "Checking dependencies..."
    
    command -v docker >/dev/null 2>&1 || error "Docker is not installed"
    command -v docker-compose >/dev/null 2>&1 || error "Docker Compose is not installed"
    
    if ! docker info >/dev/null 2>&1; then
        error "Docker daemon is not running"
    fi
    
    success "Dependencies check passed"
}

# Setup cluster secrets
setup_cluster_secrets() {
    log "Setting up PostgreSQL cluster secrets..."
    
    local secrets=(
        "postgres_password"
        "postgres_replica_password" 
        "postgres_reader_password"
    )
    
    for secret in "${secrets[@]}"; do
        if ! docker secret ls --format "{{.Name}}" | grep -q "^${secret}$"; then
            log "Creating secret: ${secret}"
            case "$secret" in
                "postgres_password")
                    openssl rand -base64 32 | docker secret create "$secret" -
                    ;;
                "postgres_replica_password")
                    openssl rand -base64 32 | docker secret create "$secret" -
                    ;;
                "postgres_reader_password")
                    openssl rand -base64 32 | docker secret create "$secret" -
                    ;;
            esac
        else
            log "Secret ${secret} already exists"
        fi
    done
    
    success "Cluster secrets setup completed"
}

# Deploy cluster
deploy_cluster() {
    log "Deploying PostgreSQL HA cluster..."
    
    cd "$DOCKER_DIR"
    
    check_dependencies
    setup_cluster_secrets
    
    # Build cluster images
    log "Building PostgreSQL cluster images..."
    docker-compose -f environments/docker-compose.cluster.yml build
    
    # Deploy cluster services
    log "Starting PostgreSQL master..."
    docker-compose -f environments/docker-compose.cluster.yml up -d postgres-master
    
    # Wait for master to be ready
    log "Waiting for master to be healthy..."
    local max_attempts=30
    local attempt=0
    
    while [[ $attempt -lt $max_attempts ]]; do
        if docker-compose -f environments/docker-compose.cluster.yml ps postgres-master | grep -q "healthy"; then
            success "PostgreSQL master is healthy"
            break
        fi
        sleep 10
        ((attempt++))
    done
    
    if [[ $attempt -eq $max_attempts ]]; then
        error "PostgreSQL master failed to become healthy"
    fi
    
    # Create replication slot
    log "Creating replication slot..."
    docker-compose -f environments/docker-compose.cluster.yml exec postgres-master \
        psql -U postgres -d spatial_platform -c \
        "SELECT pg_create_physical_replication_slot('replica_slot');" || warn "Replication slot may already exist"
    
    # Deploy replica
    log "Starting PostgreSQL replica..."
    docker-compose -f environments/docker-compose.cluster.yml up -d postgres-replica
    
    # Deploy supporting services
    log "Starting supporting services..."
    docker-compose -f environments/docker-compose.cluster.yml up -d pgbouncer postgres-exporter postgres-backup
    
    success "PostgreSQL HA cluster deployed successfully"
    
    # Show cluster status
    cluster_status
}

# Show cluster status
cluster_status() {
    log "PostgreSQL HA Cluster Status"
    echo "============================="
    
    cd "$DOCKER_DIR"
    
    # Service status
    echo ""
    echo "=== Service Status ==="
    docker-compose -f environments/docker-compose.cluster.yml ps
    
    # Replication status
    echo ""
    echo "=== Replication Status ==="
    docker-compose -f environments/docker-compose.cluster.yml exec postgres-master \
        psql -U postgres -d spatial_platform -c \
        "SELECT application_name, state, sync_state, sync_priority FROM pg_stat_replication;" 2>/dev/null || \
        warn "Could not retrieve replication status"
    
    # Connection pool status
    echo ""
    echo "=== Connection Pool Status ==="
    docker-compose -f environments/docker-compose.cluster.yml exec pgbouncer \
        psql -h localhost -U spatial_admin -d pgbouncer -c "SHOW STATS;" 2>/dev/null || \
        warn "Could not retrieve connection pool status"
    
    # Database sizes
    echo ""
    echo "=== Database Information ==="
    docker-compose -f environments/docker-compose.cluster.yml exec postgres-master \
        psql -U postgres -d spatial_platform -c \
        "SELECT pg_size_pretty(pg_database_size('spatial_platform')) AS size;" 2>/dev/null || \
        warn "Could not retrieve database size"
}

# Stop cluster
stop_cluster() {
    log "Stopping PostgreSQL HA cluster..."
    
    cd "$DOCKER_DIR"
    
    docker-compose -f environments/docker-compose.cluster.yml down
    
    success "PostgreSQL HA cluster stopped"
}

# Backup cluster
backup_cluster() {
    log "Running PostgreSQL cluster backup..."
    
    cd "$DOCKER_DIR"
    
    # Trigger manual backup
    docker-compose -f environments/docker-compose.cluster.yml exec postgres-backup /backup.sh
    
    success "Cluster backup completed"
}

# Failover to replica
failover() {
    log "Performing manual failover to replica..."
    
    cd "$DOCKER_DIR"
    
    warn "This will promote the replica to master. Continue? (y/N)"
    read -r response
    if [[ ! "$response" =~ ^[Yy]$ ]]; then
        log "Failover cancelled"
        return 0
    fi
    
    # Stop master
    log "Stopping master node..."
    docker-compose -f environments/docker-compose.cluster.yml stop postgres-master
    
    # Promote replica
    log "Promoting replica to master..."
    docker-compose -f environments/docker-compose.cluster.yml exec postgres-replica \
        pg_ctl promote -D /var/lib/postgresql/data
    
    # Update connection configuration (would need application restart)
    warn "Application services need to be reconfigured to use the new master"
    warn "New master is running on port 5433"
    
    success "Failover completed"
}

# Test cluster
test_cluster() {
    log "Testing PostgreSQL HA cluster..."
    
    cd "$DOCKER_DIR"
    
    # Test master connection
    log "Testing master connection..."
    docker-compose -f environments/docker-compose.cluster.yml exec postgres-master \
        psql -U postgres -d spatial_platform -c "SELECT 'Master connection OK' AS status;"
    
    # Test replica connection
    log "Testing replica connection..."
    docker-compose -f environments/docker-compose.cluster.yml exec postgres-replica \
        psql -U postgres -d spatial_platform -c "SELECT 'Replica connection OK' AS status;"
    
    # Test replication lag
    log "Testing replication lag..."
    docker-compose -f environments/docker-compose.cluster.yml exec postgres-master \
        psql -U postgres -d spatial_platform -c \
        "SELECT EXTRACT(EPOCH FROM (now() - pg_last_xact_replay_timestamp())) AS lag_seconds;"
    
    # Test connection pool
    log "Testing connection pool..."
    docker-compose -f environments/docker-compose.cluster.yml exec pgbouncer \
        psql -h localhost -U spatial_admin -d pgbouncer -c "SHOW POOLS;"
    
    success "Cluster tests completed"
}

# Cleanup cluster resources
cleanup_cluster() {
    log "Cleaning up PostgreSQL cluster resources..."
    
    cd "$DOCKER_DIR"
    
    warn "This will remove all cluster data. Continue? (y/N)"
    read -r response
    if [[ ! "$response" =~ ^[Yy]$ ]]; then
        log "Cleanup cancelled"
        return 0
    fi
    
    # Stop and remove services
    docker-compose -f environments/docker-compose.cluster.yml down -v
    
    # Remove secrets
    docker secret rm postgres_password postgres_replica_password postgres_reader_password 2>/dev/null || true
    
    success "Cluster cleanup completed"
}

# Usage information
usage() {
    cat << EOF
VOXAR PostgreSQL Cluster Management

Usage: $0 [COMMAND]

Commands:
  deploy      Deploy PostgreSQL HA cluster
  status      Show cluster status
  stop        Stop cluster services
  backup      Run cluster backup
  failover    Manual failover to replica
  test        Test cluster functionality
  cleanup     Remove cluster and data
  help        Show this help message

Examples:
  $0 deploy           # Deploy HA cluster
  $0 status           # Check cluster health
  $0 backup           # Run backup
  $0 failover         # Promote replica to master

EOF
}

# Main execution
case "$ACTION" in
    deploy)
        deploy_cluster
        ;;
    status)
        cluster_status
        ;;
    stop)
        stop_cluster
        ;;
    backup)
        backup_cluster
        ;;
    failover)
        failover
        ;;
    test)
        test_cluster
        ;;
    cleanup)
        cleanup_cluster
        ;;
    help|*)
        usage
        ;;
esac