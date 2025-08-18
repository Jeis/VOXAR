#!/bin/bash
# PostgreSQL Replica Setup Script
# Configures read replica with streaming replication

set -e

# Wait for master to be ready
echo "Waiting for master PostgreSQL..."
until pg_isready -h postgres-master -p 5432 -U postgres; do
    echo "Master not ready, waiting..."
    sleep 5
done

# Stop PostgreSQL if running
if pg_ctl status -D "$PGDATA" >/dev/null 2>&1; then
    pg_ctl stop -D "$PGDATA" -m fast
fi

# Remove existing data directory
rm -rf "$PGDATA"/*

# Create base backup from master
echo "Creating base backup from master..."
PGPASSWORD="${POSTGRES_REPLICA_PASSWORD:-replica_password}" \
pg_basebackup -h postgres-master -D "$PGDATA" -U replicator -v -P -W -R

# Copy replica configuration
cp /tmp/postgresql_replica.conf "$PGDATA/postgresql.conf"
cp /tmp/pg_hba_replica.conf "$PGDATA/pg_hba.conf"

# Create recovery configuration
cat > "$PGDATA/postgresql.auto.conf" <<EOF
# Replica configuration
primary_conninfo = 'host=postgres-master port=5432 user=replicator password=${POSTGRES_REPLICA_PASSWORD:-replica_password} sslmode=prefer'
primary_slot_name = 'replica_slot'
hot_standby = on
EOF

# Set proper ownership
chown -R postgres:postgres "$PGDATA"
chmod 700 "$PGDATA"

echo "Replica PostgreSQL setup completed"