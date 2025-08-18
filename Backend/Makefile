# VOXAR Enterprise Platform - Docker Management
# Version: 2.0.0

.PHONY: help build up down logs clean secrets dev prod test backup restore lint

# Default target
help: ## Show this help message
	@echo "🚀 VOXAR Enterprise Platform - Docker Management"
	@echo "================================================"
	@echo ""
	@echo "Available commands:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "Environment variables:"
	@echo "  ENVIRONMENT=dev|staging|prod  (default: dev)"
	@echo "  DOMAIN_NAME=your-domain.com   (default: api.voxar.io)"
	@echo "  LOG_LEVEL=DEBUG|INFO|WARNING  (default: INFO)"

# =================== SECRETS MANAGEMENT ===================

secrets: ## Create all Docker secrets for production
	@echo "🔐 Setting up Docker secrets..."
	@if [ "$(shell docker secret ls -q -f name=postgres_password)" = "" ]; then \
		echo "Creating postgres_password secret..."; \
		openssl rand -base64 32 | docker secret create postgres_password -; \
	fi
	@if [ "$(shell docker secret ls -q -f name=redis_password)" = "" ]; then \
		echo "Creating redis_password secret..."; \
		openssl rand -base64 32 | docker secret create redis_password -; \
	fi
	@if [ "$(shell docker secret ls -q -f name=nakama_key)" = "" ]; then \
		echo "Creating nakama_key secret..."; \
		openssl rand -base64 32 | docker secret create nakama_key -; \
	fi
	@if [ "$(shell docker secret ls -q -f name=nginx_admin_password)" = "" ]; then \
		echo "Creating nginx_admin_password secret..."; \
		echo "voxar2024!" | docker secret create nginx_admin_password -; \
	fi
	@if [ "$(shell docker secret ls -q -f name=minio_access_key)" = "" ]; then \
		echo "Creating minio_access_key secret..."; \
		echo "spatial_admin" | docker secret create minio_access_key -; \
	fi
	@if [ "$(shell docker secret ls -q -f name=minio_secret_key)" = "" ]; then \
		echo "Creating minio_secret_key secret..."; \
		openssl rand -base64 32 | docker secret create minio_secret_key -; \
	fi
	@echo "✅ All secrets created successfully"
	@echo ""
	@echo "🔑 Secret summary:"
	@docker secret ls

secrets-remove: ## Remove all Docker secrets
	@echo "🗑️  Removing all Docker secrets..."
	@docker secret ls -q | xargs -r docker secret rm
	@echo "✅ All secrets removed"

secrets-rotate: secrets-remove secrets ## Rotate all secrets (remove and recreate)

# =================== BUILD & DEPLOYMENT ===================

build: ## Build all Docker images
	@echo "🔨 Building all Docker images..."
	@export DOCKER_BUILDKIT=1 && docker-compose build --parallel
	@echo "✅ Build complete"

build-no-cache: ## Build all images without cache
	@echo "🔨 Building all Docker images (no cache)..."
	@export DOCKER_BUILDKIT=1 && docker-compose build --no-cache --parallel
	@echo "✅ Build complete"

pull: ## Pull latest base images
	@echo "📥 Pulling latest base images..."
	@docker-compose pull
	@echo "✅ Pull complete"

# =================== ENVIRONMENT MANAGEMENT ===================

DOCKER_DIR := infrastructure/docker
SCRIPT_DIR := $(DOCKER_DIR)/scripts

dev: ## Start development environment
	@echo "🚀 Starting development environment..."
	@$(SCRIPT_DIR)/deploy.sh development
	@echo ""
	@echo "=== Development Environment Ready ==="
	@echo "API Gateway: http://localhost:8000"
	@echo "Nakama Console: http://localhost:7351 (spatial_admin/spatial_console_dev)"
	@echo "Grafana: http://localhost:3000 (admin/spatial_admin_dev)"
	@echo "Prometheus: http://localhost:9090"
	@echo "pgAdmin: http://localhost:5050 (admin@voxar.io/pgadmin_dev)"
	@echo "Redis Commander: http://localhost:8082"

dev-full: ## Start development with all services
	@echo "🚀 Starting development environment with all services..."
	@DEPLOY_FULL=true $(SCRIPT_DIR)/deploy.sh development --full

staging: ## Start staging environment
	@echo "🚀 Starting staging environment..."
	@$(SCRIPT_DIR)/deploy.sh staging
	@echo "✅ Staging environment started"

prod: secrets ## Start production environment
	@echo "🚀 Starting production environment..."
	@$(SCRIPT_DIR)/deploy.sh production
	@echo "✅ Production environment started"

prod-full: secrets ## Start production with all services
	@echo "🚀 Starting production environment with all services..."
	@$(SCRIPT_DIR)/deploy.sh production --full

up: ## Start all services
	@echo "🚀 Starting VOXAR platform..."
	@docker-compose up -d
	@echo "✅ Platform started"
	@$(MAKE) status

down: ## Stop development environment
	@echo "🛑 Stopping development environment..."
	@$(SCRIPT_DIR)/deploy.sh development --rollback

down-staging: ## Stop staging environment
	@echo "🛑 Stopping staging environment..."
	@$(SCRIPT_DIR)/deploy.sh staging --rollback

down-prod: ## Stop production environment
	@echo "🛑 Stopping production environment..."
	@$(SCRIPT_DIR)/deploy.sh production --rollback

stop: ## Stop all environments
	@echo "🛑 Stopping all environments..."
	@cd $(DOCKER_DIR) && docker-compose -f docker-compose.base.yml -f environments/docker-compose.development.yml down || true
	@cd $(DOCKER_DIR) && docker-compose -f docker-compose.base.yml -f environments/docker-compose.staging.yml down || true
	@cd $(DOCKER_DIR) && docker-compose -f docker-compose.base.yml -f environments/docker-compose.production.yml down || true

restart: down up ## Restart all services

# =================== SERVICE MANAGEMENT ===================

scale: ## Scale services (usage: make scale SERVICE=nakama REPLICAS=3)
	@if [ -z "$(SERVICE)" ] || [ -z "$(REPLICAS)" ]; then \
		echo "❌ Usage: make scale SERVICE=service_name REPLICAS=number"; \
		exit 1; \
	fi
	@echo "📈 Scaling $(SERVICE) to $(REPLICAS) replicas..."
	@docker-compose up -d --scale $(SERVICE)=$(REPLICAS)
	@echo "✅ Scaling complete"

status: ## Show service status
	@$(SCRIPT_DIR)/deploy.sh development --status

status-staging: ## Show staging status
	@$(SCRIPT_DIR)/deploy.sh staging --status

status-prod: ## Show production status
	@$(SCRIPT_DIR)/deploy.sh production --status

health: ## Check health of all services
	@echo "🏥 Health Check Report"
	@echo "===================="
	@for service in $$(docker-compose ps --services); do \
		echo ""; \
		echo "Service: $$service"; \
		echo "Status: $$(docker-compose ps $$service | grep -v Name | awk '{print $$3}')"; \
		if docker-compose exec -T $$service curl -f http://localhost:8080/health >/dev/null 2>&1 || \
		   docker-compose exec -T $$service curl -f http://localhost:8000/health >/dev/null 2>&1 || \
		   docker-compose exec -T $$service curl -f http://localhost:7350/ >/dev/null 2>&1; then \
			echo "Health: ✅ Healthy"; \
		else \
			echo "Health: ❌ Unhealthy or no health endpoint"; \
		fi; \
	done

# =================== LOGS & DEBUGGING ===================

logs: ## Show logs for development environment
	@cd $(DOCKER_DIR) && docker-compose -f docker-compose.base.yml -f environments/docker-compose.development.yml logs -f --tail=100

logs-staging: ## Show logs for staging environment
	@cd $(DOCKER_DIR) && docker-compose -f docker-compose.base.yml -f environments/docker-compose.staging.yml logs -f --tail=100

logs-prod: ## Show logs for production environment
	@cd $(DOCKER_DIR) && docker-compose -f docker-compose.base.yml -f environments/docker-compose.production.yml logs -f --tail=100

logs-service: ## Show logs for specific service (usage: make logs-service SERVICE=nakama)
	@if [ -z "$(SERVICE)" ]; then \
		echo "❌ Usage: make logs-service SERVICE=service_name"; \
		exit 1; \
	fi
	@docker-compose logs -f --tail=100 $(SERVICE)

logs-errors: ## Show only error logs
	@docker-compose logs --tail=100 | grep -i error

shell: ## Open shell in service (usage: make shell SERVICE=gateway)
	@if [ -z "$(SERVICE)" ]; then \
		echo "❌ Usage: make shell SERVICE=service_name"; \
		exit 1; \
	fi
	@docker-compose exec $(SERVICE) sh

# =================== MAINTENANCE ===================

clean: ## Clean up containers, networks, and volumes
	@echo "🧹 Cleaning up Docker resources..."
	@docker-compose down -v --remove-orphans
	@docker system prune -f
	@docker volume prune -f
	@echo "✅ Cleanup complete"

clean-all: ## Deep clean (includes images)
	@echo "🧹 Deep cleaning Docker resources..."
	@docker-compose down -v --remove-orphans --rmi all
	@docker system prune -af
	@docker volume prune -f
	@echo "✅ Deep cleanup complete"

update: ## Update all services to latest
	@echo "🔄 Updating VOXAR platform..."
	@git pull
	@$(MAKE) pull
	@$(MAKE) build
	@$(MAKE) restart
	@echo "✅ Update complete"

# =================== BACKUP & RESTORE ===================

backup: ## Backup all data volumes
	@echo "💾 Creating backup..."
	@mkdir -p backups
	@docker run --rm \
		-v spatial_postgres_data:/data \
		-v $(PWD)/backups:/backup \
		alpine tar czf /backup/postgres-$(shell date +%Y%m%d-%H%M%S).tar.gz -C /data .
	@docker run --rm \
		-v spatial_redis_data:/data \
		-v $(PWD)/backups:/backup \
		alpine tar czf /backup/redis-$(shell date +%Y%m%d-%H%M%S).tar.gz -C /data .
	@docker run --rm \
		-v spatial_nakama_data:/data \
		-v $(PWD)/backups:/backup \
		alpine tar czf /backup/nakama-$(shell date +%Y%m%d-%H%M%S).tar.gz -C /data .
	@echo "✅ Backup complete - files saved to ./backups/"

restore: ## Restore from backup (usage: make restore BACKUP=backup-file.tar.gz)
	@if [ -z "$(BACKUP)" ]; then \
		echo "❌ Usage: make restore BACKUP=backup-file.tar.gz"; \
		echo "Available backups:"; \
		ls -la backups/; \
		exit 1; \
	fi
	@echo "🔄 Restoring from $(BACKUP)..."
	@docker-compose down
	@docker run --rm \
		-v spatial_postgres_data:/data \
		-v $(PWD)/backups:/backup \
		alpine tar xzf /backup/$(BACKUP) -C /data
	@echo "✅ Restore complete"
	@$(MAKE) up

# =================== DEVELOPMENT HELPERS ===================

dev-db: ## Connect to development database
	@cd $(DOCKER_DIR) && docker-compose -f docker-compose.base.yml -f environments/docker-compose.development.yml exec postgres psql -U spatial_admin -d spatial_platform

dev-shell: ## Access gateway shell
	@cd $(DOCKER_DIR) && docker-compose -f docker-compose.base.yml -f environments/docker-compose.development.yml exec gateway bash

dev-shell-localization: ## Access localization service shell
	@cd $(DOCKER_DIR) && docker-compose -f docker-compose.base.yml -f environments/docker-compose.development.yml exec localization bash

dev-redis: ## Connect to development Redis
	@cd $(DOCKER_DIR) && docker-compose -f docker-compose.base.yml -f environments/docker-compose.development.yml exec redis redis-cli

# =================== DEVELOPMENT ===================

dev-setup: ## Setup development environment
	@echo "🛠️  Setting up development environment..."
	@cp .env.example .env.development || echo ".env.example not found, skipping"
	@$(MAKE) build
	@echo "✅ Development setup complete"
	@echo ""
	@echo "Next steps:"
	@echo "1. Edit .env.development with your settings"
	@echo "2. Run 'make dev' to start development environment"

test: ## Run tests
	@echo "🧪 Running tests..."
	@docker-compose -f docker-compose.yml -f docker-compose.test.yml run --rm test-runner
	@echo "✅ Tests complete"

lint: ## Run linting on all services
	@echo "🔍 Running linter..."
	@docker run --rm -v $(PWD):/workspace -w /workspace \
		python:3.12-slim sh -c "pip install black flake8 && black --check . && flake8 ."
	@echo "✅ Linting complete"

# =================== MONITORING ===================

metrics: ## Show Prometheus metrics
	@echo "📊 Prometheus Metrics:"
	@curl -s http://localhost:9090/api/v1/query?query=up | jq '.data.result[] | {job: .metric.job, instance: .metric.instance, status: .value[1]}'

dashboard: ## Open Grafana dashboard
	@echo "📈 Opening Grafana dashboard..."
	@echo "URL: http://localhost:3000"
	@echo "Username: admin"
	@echo "Password: Check your nginx_admin_password secret"

# =================== SECURITY ===================

security-scan: ## Run security scan on images
	@echo "🛡️  Running security scan..."
	@docker run --rm -v /var/run/docker.sock:/var/run/docker.sock \
		-v $(PWD):/workspace \
		aquasec/trivy image spatial-nginx spatial-gateway spatial-localization spatial-mapping-processor
	@echo "✅ Security scan complete"

ssl-check: ## Check SSL certificate status
	@echo "🔒 Checking SSL certificates..."
	@openssl x509 -in /etc/nginx/ssl/fullchain.pem -text -noout | grep -E "(Subject|Not After)" || echo "Certificate not found"

# =================== DATABASE CLUSTERING ===================

CLUSTER_SCRIPT := $(SCRIPT_DIR)/cluster.sh

cluster-deploy: ## Deploy PostgreSQL HA cluster
	@echo "🗄️  Deploying PostgreSQL HA cluster..."
	@$(CLUSTER_SCRIPT) deploy

cluster-status: ## Show PostgreSQL cluster status
	@$(CLUSTER_SCRIPT) status

cluster-stop: ## Stop PostgreSQL cluster
	@$(CLUSTER_SCRIPT) stop

cluster-backup: ## Backup PostgreSQL cluster
	@$(CLUSTER_SCRIPT) backup

cluster-test: ## Test PostgreSQL cluster functionality
	@$(CLUSTER_SCRIPT) test

cluster-failover: ## Manual failover to replica
	@$(CLUSTER_SCRIPT) failover

cluster-cleanup: ## Remove cluster and data
	@$(CLUSTER_SCRIPT) cleanup

# =================== QUICK ACTIONS ===================

reset: clean secrets build up ## Complete reset (clean, secrets, build, up)

deploy: secrets pull build up ## Deploy to production

deploy-ha: secrets cluster-deploy ## Deploy with HA PostgreSQL cluster

quick-start: dev-setup dev ## Quick start for new developers