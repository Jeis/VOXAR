#!/bin/bash
# Enterprise-grade PostgreSQL readiness checker for VOXAR Platform
# Implements exponential backoff, comprehensive logging, and proper error handling

set -euo pipefail

# Configuration
readonly POSTGRES_HOST="${POSTGRES_HOST:-postgres}"
readonly POSTGRES_PORT="${POSTGRES_PORT:-5432}"
readonly POSTGRES_USER="${POSTGRES_USER:-admin}"
readonly POSTGRES_DB="${POSTGRES_DB:-spatial_platform}"
readonly MAX_ATTEMPTS="${MAX_ATTEMPTS:-30}"
readonly INITIAL_WAIT="${INITIAL_WAIT:-1}"
readonly MAX_WAIT="${MAX_WAIT:-10}"
readonly TIMEOUT="${POSTGRES_TIMEOUT:-5}"

# Logging functions with structured output
log_info() {
    echo "[$(date -Iseconds)] [INFO] [wait-for-postgres] $*" >&2
}

log_error() {
    echo "[$(date -Iseconds)] [ERROR] [wait-for-postgres] $*" >&2
}

log_debug() {
    if [[ "${DEBUG:-false}" == "true" ]]; then
        echo "[$(date -Iseconds)] [DEBUG] [wait-for-postgres] $*" >&2
    fi
}

log_warn() {
    echo "[$(date -Iseconds)] [WARN] [wait-for-postgres] $*" >&2
}

# Auto-detect PostgreSQL tools and set paths
detect_postgres_tools() {
    local pg_isready_path=""
    local psql_path=""
    
    # Check common locations for PostgreSQL tools
    for path in "/usr/bin/pg_isready" "/usr/local/bin/pg_isready" "/opt/postgresql/bin/pg_isready"; do
        if [[ -x "$path" ]]; then
            pg_isready_path="$path"
            break
        fi
    done
    
    for path in "/usr/bin/psql" "/usr/local/bin/psql" "/opt/postgresql/bin/psql"; do
        if [[ -x "$path" ]]; then
            psql_path="$path"
            break
        fi
    done
    
    # If not found in standard locations, try PATH
    if [[ -z "$pg_isready_path" ]] && command -v pg_isready >/dev/null 2>&1; then
        pg_isready_path="$(command -v pg_isready)"
    fi
    
    if [[ -z "$psql_path" ]] && command -v psql >/dev/null 2>&1; then
        psql_path="$(command -v psql)"
    fi
    
    export PG_ISREADY_PATH="$pg_isready_path"
    export PSQL_PATH="$psql_path"
    
    log_debug "PostgreSQL tool detection: pg_isready=$pg_isready_path, psql=$psql_path"
}

# Check PostgreSQL connectivity using best available method
check_postgres() {
    log_debug "Checking PostgreSQL connectivity: ${POSTGRES_HOST}:${POSTGRES_PORT}"
    
    # Method 1: Use pg_isready if available (preferred)
    if [[ -n "${PG_ISREADY_PATH}" ]]; then
        log_debug "Using pg_isready for connectivity check"
        timeout "${TIMEOUT}" "${PG_ISREADY_PATH}" \
            -h "${POSTGRES_HOST}" \
            -p "${POSTGRES_PORT}" \
            -U "${POSTGRES_USER}" \
            -d "${POSTGRES_DB}" \
            -q
        return $?
    fi
    
    # Method 2: Use psql if available
    if [[ -n "${PSQL_PATH}" ]]; then
        log_debug "Using psql for connectivity check"
        PGPASSWORD="${POSTGRES_PASSWORD:-admin}" timeout "${TIMEOUT}" "${PSQL_PATH}" \
            -h "${POSTGRES_HOST}" \
            -p "${POSTGRES_PORT}" \
            -U "${POSTGRES_USER}" \
            -d "${POSTGRES_DB}" \
            -c "SELECT 1;" >/dev/null 2>&1
        return $?
    fi
    
    # Method 3: Fallback to netcat for TCP connectivity
    log_warn "PostgreSQL tools not available, falling back to TCP connectivity check"
    if command -v nc >/dev/null 2>&1; then
        timeout "${TIMEOUT}" nc -z "${POSTGRES_HOST}" "${POSTGRES_PORT}"
        return $?
    fi
    
    # Method 4: Last resort - bash TCP test
    log_warn "No network tools available, using bash TCP test"
    timeout "${TIMEOUT}" bash -c "</dev/tcp/${POSTGRES_HOST}/${POSTGRES_PORT}"
    return $?
}

# Main waiting logic with exponential backoff
wait_for_postgres() {
    local attempt=1
    local wait_time="${INITIAL_WAIT}"
    
    log_info "Waiting for PostgreSQL at ${POSTGRES_HOST}:${POSTGRES_PORT} (database: ${POSTGRES_DB})"
    log_info "Max attempts: ${MAX_ATTEMPTS}, Initial wait: ${INITIAL_WAIT}s, Max wait: ${MAX_WAIT}s"
    
    while [[ ${attempt} -le ${MAX_ATTEMPTS} ]]; do
        log_debug "Attempt ${attempt}/${MAX_ATTEMPTS}"
        
        if check_postgres; then
            log_info "PostgreSQL is ready! (attempt ${attempt}/${MAX_ATTEMPTS})"
            return 0
        fi
        
        if [[ ${attempt} -eq ${MAX_ATTEMPTS} ]]; then
            log_error "PostgreSQL not ready after ${MAX_ATTEMPTS} attempts"
            log_error "Final check failed for ${POSTGRES_HOST}:${POSTGRES_PORT}"
            return 1
        fi
        
        log_info "PostgreSQL not ready, waiting ${wait_time}s before attempt $((attempt + 1))"
        sleep "${wait_time}"
        
        # Exponential backoff with jitter
        wait_time=$(( wait_time * 2 ))
        if [[ ${wait_time} -gt ${MAX_WAIT} ]]; then
            wait_time=${MAX_WAIT}
        fi
        
        # Add jitter (±20%)
        local jitter=$((wait_time * 20 / 100))
        local random_jitter=$((RANDOM % (jitter * 2 + 1) - jitter))
        wait_time=$((wait_time + random_jitter))
        if [[ ${wait_time} -lt 1 ]]; then
            wait_time=1
        fi
        
        ((attempt++))
    done
    
    return 1
}

# Signal handlers for graceful shutdown
cleanup() {
    log_info "Received signal, shutting down gracefully"
    exit 130
}

trap cleanup SIGTERM SIGINT

# Main execution
main() {
    log_info "Enterprise PostgreSQL dependency checker starting"
    log_info "Target: ${POSTGRES_HOST}:${POSTGRES_PORT}/${POSTGRES_DB} (user: ${POSTGRES_USER})"
    
    # Detect available PostgreSQL tools
    detect_postgres_tools
    
    # Perform dependency check
    if wait_for_postgres; then
        log_info "PostgreSQL dependency check completed successfully"
        exit 0
    else
        log_error "PostgreSQL dependency check failed"
        exit 1
    fi
}

# Execute main function
main "$@"