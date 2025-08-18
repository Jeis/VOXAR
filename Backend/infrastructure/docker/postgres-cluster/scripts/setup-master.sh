#!/bin/bash
# PostgreSQL Master Setup Script
# Configures streaming replication and creates required users

set -e

# Create replication user
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    -- Create replication user
    CREATE USER replicator WITH REPLICATION ENCRYPTED PASSWORD '${POSTGRES_REPLICA_PASSWORD:-replica_password}';
    
    -- Create read-only user for applications
    CREATE USER spatial_reader WITH ENCRYPTED PASSWORD '${POSTGRES_READER_PASSWORD:-reader_password}';
    
    -- Grant read access to spatial_reader
    GRANT CONNECT ON DATABASE spatial_platform TO spatial_reader;
    GRANT USAGE ON SCHEMA public TO spatial_reader;
    GRANT SELECT ON ALL TABLES IN SCHEMA public TO spatial_reader;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO spatial_reader;
    
    -- Create additional schemas for spatial data
    CREATE SCHEMA IF NOT EXISTS spatial;
    CREATE SCHEMA IF NOT EXISTS analytics;
    
    -- Grant permissions on new schemas
    GRANT USAGE ON SCHEMA spatial TO spatial_reader;
    GRANT USAGE ON SCHEMA analytics TO spatial_reader;
    GRANT SELECT ON ALL TABLES IN SCHEMA spatial TO spatial_reader;
    GRANT SELECT ON ALL TABLES IN SCHEMA analytics TO spatial_reader;
    ALTER DEFAULT PRIVILEGES IN SCHEMA spatial GRANT SELECT ON TABLES TO spatial_reader;
    ALTER DEFAULT PRIVILEGES IN SCHEMA analytics GRANT SELECT ON TABLES TO spatial_reader;
    
    -- Install required extensions
    CREATE EXTENSION IF NOT EXISTS postgis;
    CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
    CREATE EXTENSION IF NOT EXISTS pgcrypto;
    CREATE EXTENSION IF NOT EXISTS uuid-ossp;
EOSQL

# Copy master configuration
cp /tmp/postgresql_master.conf "$PGDATA/postgresql.conf"
cp /tmp/pg_hba_master.conf "$PGDATA/pg_hba.conf"

# Create WAL archive directory
mkdir -p "$PGDATA/archive"
chown postgres:postgres "$PGDATA/archive"

echo "Master PostgreSQL setup completed"