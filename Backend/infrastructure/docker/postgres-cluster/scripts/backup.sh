#!/bin/bash
# PostgreSQL Backup Script for Enterprise Cluster
# Performs full backups with rotation and compression

set -e

# Configuration
BACKUP_DIR="/backups"
POSTGRES_HOST="${POSTGRES_HOST:-postgres-master}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_DB="${POSTGRES_DB:-spatial_platform}"
POSTGRES_USER="${POSTGRES_USER:-postgres}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"

# Create backup directory
mkdir -p "$BACKUP_DIR"

# Timestamp for backup files
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")

# Database backup
echo "Starting database backup..."
PGPASSWORD="$(cat /run/secrets/postgres_password)" \
pg_dump -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" \
    --verbose --format=custom --compress=9 \
    --file="$BACKUP_DIR/spatial_platform_${TIMESTAMP}.dump" \
    "$POSTGRES_DB"

# WAL archive backup
echo "Backing up WAL archives..."
if [ -d "/var/lib/postgresql/archive" ]; then
    tar -czf "$BACKUP_DIR/wal_archive_${TIMESTAMP}.tar.gz" \
        -C /var/lib/postgresql/archive .
fi

# Schema-only backup for quick recovery planning
echo "Creating schema backup..."
PGPASSWORD="$(cat /run/secrets/postgres_password)" \
pg_dump -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" \
    --schema-only --verbose \
    --file="$BACKUP_DIR/schema_${TIMESTAMP}.sql" \
    "$POSTGRES_DB"

# Globals backup (users, roles, tablespaces)
echo "Backing up global objects..."
PGPASSWORD="$(cat /run/secrets/postgres_password)" \
pg_dumpall -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" \
    --globals-only --verbose \
    --file="$BACKUP_DIR/globals_${TIMESTAMP}.sql"

# Create backup manifest
cat > "$BACKUP_DIR/backup_${TIMESTAMP}.manifest" <<EOF
Backup Manifest
==============
Date: $(date)
Host: $POSTGRES_HOST
Database: $POSTGRES_DB
Files:
- spatial_platform_${TIMESTAMP}.dump (Full database)
- wal_archive_${TIMESTAMP}.tar.gz (WAL archives)
- schema_${TIMESTAMP}.sql (Schema only)
- globals_${TIMESTAMP}.sql (Global objects)

Sizes:
$(ls -lh "$BACKUP_DIR"/*_${TIMESTAMP}.* | awk '{print $9, $5}')
EOF

# Compress schema and globals files
gzip "$BACKUP_DIR/schema_${TIMESTAMP}.sql"
gzip "$BACKUP_DIR/globals_${TIMESTAMP}.sql"

# Cleanup old backups
echo "Cleaning up old backups (older than $RETENTION_DAYS days)..."
find "$BACKUP_DIR" -name "*.dump" -mtime +$RETENTION_DAYS -delete
find "$BACKUP_DIR" -name "*.tar.gz" -mtime +$RETENTION_DAYS -delete
find "$BACKUP_DIR" -name "*.sql.gz" -mtime +$RETENTION_DAYS -delete
find "$BACKUP_DIR" -name "*.manifest" -mtime +$RETENTION_DAYS -delete

# Calculate total backup size
TOTAL_SIZE=$(du -sh "$BACKUP_DIR" | awk '{print $1}')

echo "Backup completed successfully!"
echo "Backup location: $BACKUP_DIR"
echo "Total backup size: $TOTAL_SIZE"
echo "Files created:"
ls -lh "$BACKUP_DIR"/*_${TIMESTAMP}.*