#!/bin/bash
# Spatial Platform - Universal Service Health Check
# Compatible with all platforms and architectures

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
NC='\033[0m'

print_header() { echo -e "${PURPLE}$1${NC}"; }
print_status() { echo -e "${BLUE}[INFO]${NC} $1"; }
print_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
print_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
print_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Detect platform
detect_platform() {
    OS=$(uname -s)
    ARCH=$(uname -m)
    
    case "$OS" in
        "Darwin") echo "macOS ($ARCH)" ;;
        "Linux")
            if grep -q Microsoft /proc/version 2>/dev/null; then
                echo "WSL2 ($ARCH)"
            else
                echo "Linux ($ARCH)"
            fi
            ;;
        *) echo "$(uname -s) ($ARCH)" ;;
    esac
}

# Cross-platform network tools
check_port() {
    local host=$1
    local port=$2
    local timeout=${3:-3}
    
    # Try different methods based on available tools
    if command -v nc >/dev/null 2>&1; then
        timeout "$timeout" nc -z "$host" "$port" 2>/dev/null
    elif command -v telnet >/dev/null 2>&1; then
        timeout "$timeout" bash -c "echo '' | telnet $host $port" 2>/dev/null | grep -q "Connected"
    elif command -v curl >/dev/null 2>&1; then
        curl -s --connect-timeout "$timeout" "$host:$port" >/dev/null 2>&1
    else
        return 1
    fi
}

check_http() {
    local name=$1
    local url=$2
    local timeout=${3:-5}
    
    if command -v curl >/dev/null 2>&1; then
        if curl -sf --max-time "$timeout" "$url" >/dev/null 2>&1; then
            echo -e "✅ $name"
            return 0
        else
            echo -e "❌ $name"
            return 1
        fi
    elif command -v wget >/dev/null 2>&1; then
        if wget -q --timeout="$timeout" --tries=1 -O /dev/null "$url" 2>/dev/null; then
            echo -e "✅ $name"
            return 0
        else
            echo -e "❌ $name"
            return 1
        fi
    else
        echo -e "⚠️  $name (no HTTP client)"
        return 1
    fi
}

check_container() {
    local name=$1
    local status=$(docker-compose ps -q "$name" 2>/dev/null | xargs docker inspect --format='{{.State.Status}}' 2>/dev/null || echo "not_found")
    
    case "$status" in
        "running") echo -e "✅ $name"; return 0 ;;
        "exited"|"dead") echo -e "❌ $name (stopped)"; return 1 ;;
        "restarting") echo -e "🔄 $name (restarting)"; return 1 ;;
        "not_found") echo -e "❌ $name (not found)"; return 1 ;;
        *) echo -e "⚠️  $name ($status)"; return 1 ;;
    esac
}

# Main health check
main() {
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
    cd "$SCRIPT_DIR"
    
    print_header "🔍 Spatial Platform - Service Health Check"
    print_header "==========================================="
    echo "Platform: $(detect_platform)"
    echo "Time: $(date)"
    echo ""
    
    # Check if Docker Compose is running
    if ! docker-compose ps >/dev/null 2>&1; then
        print_error "Docker Compose services not running"
        print_status "Start with: ./start-dev.sh"
        exit 1
    fi
    
    # Container status
    print_header "🐳 Container Status"
    containers=("postgres" "redis" "minio" "prometheus" "grafana" "api-gateway" "mapping-processor" "localization-service" "celery-worker" "flower" "dev-tools")
    container_failures=0
    
    for container in "${containers[@]}"; do
        if ! check_container "$container"; then
            ((container_failures++))
        fi
    done
    
    echo ""
    
    # HTTP Services
    print_header "🌐 HTTP Services"
    http_failures=0
    
    services=(
        "API Gateway:http://localhost:8000/health"
        "MinIO API:http://localhost:9000/minio/health/live"
        "MinIO Console:http://localhost:9001"
        "Prometheus:http://localhost:9090/-/healthy"
        "Grafana:http://localhost:3000/api/health"
        "Flower:http://localhost:5555"
    )
    
    for service_info in "${services[@]}"; do
        IFS=':' read -r name url <<< "$service_info"
        if ! check_http "$name" "$url"; then
            ((http_failures++))
        fi
    done
    
    echo ""
    
    # Network connectivity
    print_header "🔌 Network Connectivity"
    tcp_failures=0
    
    ports=(
        "PostgreSQL:5432"
        "Redis:6379"
        "MinIO:9000"
        "API Gateway:8000"
        "Grafana:3000"
    )
    
    for port_info in "${ports[@]}"; do
        IFS=':' read -r name port <<< "$port_info"
        if check_port "localhost" "$port"; then
            echo -e "✅ $name (localhost:$port)"
        else
            echo -e "❌ $name (localhost:$port)"
            ((tcp_failures++))
        fi
    done
    
    echo ""
    
    # Resource usage
    print_header "📊 Resource Usage"
    
    # Docker stats
    if docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}" $(docker-compose ps -q 2>/dev/null) 2>/dev/null; then
        echo ""
    else
        print_warning "Unable to get resource statistics"
    fi
    
    # Storage usage
    print_header "💾 Storage Usage"
    docker system df 2>/dev/null || print_warning "Unable to show storage usage"
    
    echo ""
    
    # Summary
    print_header "📋 Health Summary"
    total_failures=$((container_failures + http_failures + tcp_failures))
    
    if [ $total_failures -eq 0 ]; then
        print_success "All services healthy! 🎉"
        echo ""
        print_header "🔗 Quick Access"
        echo "🌐 API Gateway:       http://localhost:8000"
        echo "📊 Grafana Dashboard: http://localhost:3000 (admin/admin)"
        echo "🗄️  MinIO Console:     http://localhost:9001"
        echo "🌸 Flower Monitor:    http://localhost:5555"
        echo ""
        print_success "Ready for development! 🚀"
    else
        print_warning "$total_failures issues detected:"
        [ $container_failures -gt 0 ] && echo "  - $container_failures container(s) not running"
        [ $http_failures -gt 0 ] && echo "  - $http_failures HTTP service(s) not responding"
        [ $tcp_failures -gt 0 ] && echo "  - $tcp_failures network service(s) not accessible"
        
        echo ""
        print_header "🛠️  Troubleshooting"
        echo "Check logs:    docker-compose logs -f [service]"
        echo "Restart all:   docker-compose restart"
        echo "Full restart:  docker-compose down && ./start-dev.sh"
        echo "Clean restart: docker-compose down && docker system prune -f && ./start-dev.sh"
    fi
    
    echo ""
    print_header "🛠️  Common Commands"
    echo "View logs:        docker-compose logs -f [service]"
    echo "Shell access:     docker-compose exec [service] bash"
    echo "Database shell:   docker-compose exec postgres psql -U spatial_admin -d spatial_platform"
    echo "Redis shell:      docker-compose exec redis redis-cli"
    echo "Stop services:    docker-compose down"
    echo "Restart service:  docker-compose restart [service]"
    echo "Rebuild service:  docker-compose up -d --build [service]"
    
    # Platform-specific tips
    case "$(uname -s)" in
        "Darwin")
            echo ""
            print_header "🍎 macOS Tips"
            echo "- Increase Docker memory: Docker Desktop > Settings > Resources"
            echo "- Enable VirtioFS: Docker Desktop > Settings > General > Use VirtioFS"
            ;;
        "Linux")
            if grep -q Microsoft /proc/version 2>/dev/null; then
                echo ""
                print_header "🐧 WSL2 Tips"
                echo "- Ensure Docker Desktop is running on Windows"
                echo "- Check WSL integration: Docker Desktop > Settings > Resources > WSL"
            fi
            ;;
    esac
    
    exit $total_failures
}

main "$@"