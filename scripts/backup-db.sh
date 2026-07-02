#!/bin/bash

# Exit on any error
set -e

# Resolve the absolute path of the script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Load environment variables from .env if present
if [ -f "$PROJECT_ROOT/.env" ]; then
    echo "🔑 Loading environment variables from .env..."
    # Export variables from .env, ignoring comments and empty lines
    export $(grep -v '^#' "$PROJECT_ROOT/.env" | xargs)
else
    echo "⚠️ .env file not found. Falling back to default environment variables."
fi

# Fallback values if not set in .env
DB_USER=${DB_USER:-"fil"}
DB_HOST=${DB_HOST:-"localhost"}
DB_PORT=${DB_PORT:-"5432"}
DB_NAME=${DB_NAME:-"leafcloud3"}

# Define backup folder and filename
BACKUP_DIR="$PROJECT_ROOT/exports"
mkdir -p "$BACKUP_DIR"

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="$BACKUP_DIR/${DB_NAME}_backup_${TIMESTAMP}.dump"

echo "💾 Starting database backup..."
echo "🔹 Database: $DB_NAME"
echo "🔹 Host:     $DB_HOST"
echo "🔹 Port:     $DB_PORT"
echo "🔹 User:     $DB_USER"
echo "🔹 Output:   $BACKUP_FILE"

# Execute pg_dump using Custom compressed format
pg_dump -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -F c -b -v -f "$BACKUP_FILE" "$DB_NAME"

echo "✅ Backup successfully completed: $BACKUP_FILE"
echo "📊 Backup file size: $(du -sh "$BACKUP_FILE" | cut -f1)"
