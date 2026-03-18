#!/bin/bash
# Script to connect to remote PostgreSQL database using appsettings.json
# Usage: ./connect-postgres.sh [sql_file]
#   ./connect-postgres.sh                    # Interactive psql session
#   ./connect-postgres.sh migration.sql      # Execute SQL file

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APPSETTINGS_FILE="$SCRIPT_DIR/appsettings.json"

# Check if appsettings.json exists
if [ ! -f "$APPSETTINGS_FILE" ]; then
    echo "❌ Error: appsettings.json not found at $APPSETTINGS_FILE"
    echo "Run ./generate-appsettings.sh first to create it"
    exit 1
fi

# Extract PostgreSQL connection details from appsettings.json
echo "📖 Reading connection details from appsettings.json..."

# Read from AzureServices.PostgreSQL structure
PG_HOST=$(jq -r '.AzureServices.PostgreSQL.Host // empty' "$APPSETTINGS_FILE")
PG_PORT=$(jq -r '.AzureServices.PostgreSQL.Port // 5432' "$APPSETTINGS_FILE")
PG_DATABASE=$(jq -r '.AzureServices.PostgreSQL.Database // empty' "$APPSETTINGS_FILE")
PG_USER="pgbootstrap"  # Override with bootstrap user for migrations

# Check if we got valid values
if [ -z "$PG_HOST" ]; then
    echo "❌ Error: Could not extract PostgreSQL host from appsettings.json"
    echo "Expected structure: .AzureServices.PostgreSQL.Host"
    exit 1
fi

if [ -z "$PG_DATABASE" ]; then
    echo "❌ Error: Could not extract PostgreSQL database from appsettings.json"
    echo "Expected structure: .AzureServices.PostgreSQL.Database"
    exit 1
fi

echo "🔗 Connecting to PostgreSQL..."
echo "   Host: $PG_HOST"
echo "   Port: $PG_PORT"
echo "   Database: $PG_DATABASE"
echo "   User: $PG_USER"
echo ""

# Prompt for password
read -sp "🔑 Enter PostgreSQL password: " PG_PASSWORD
echo ""

# Build connection string
export PGHOST="$PG_HOST"
export PGPORT="$PG_PORT"
export PGDATABASE="$PG_DATABASE"
export PGUSER="$PG_USER"
export PGPASSWORD="$PG_PASSWORD"

# If a SQL file is provided as argument, run it
if [ $# -eq 1 ]; then
    SQL_FILE="$1"
    if [ ! -f "$SQL_FILE" ]; then
        echo "❌ Error: SQL file not found: $SQL_FILE"
        exit 1
    fi
    echo "📝 Executing SQL file: $SQL_FILE"
    echo ""

    # Use Docker PostgreSQL client
    docker run --rm -i \
        -e PGHOST="$PG_HOST" \
        -e PGPORT="$PG_PORT" \
        -e PGDATABASE="$PG_DATABASE" \
        -e PGUSER="$PG_USER" \
        -e PGPASSWORD="$PG_PASSWORD" \
        -e PGSSLMODE="require" \
        -v "$(cd "$(dirname "$SQL_FILE")" && pwd)":/sql:ro \
        postgres:15-alpine \
        psql -f "/sql/$(basename "$SQL_FILE")"

    EXIT_CODE=$?

    # Clear password from environment
    unset PGPASSWORD

    if [ $EXIT_CODE -eq 0 ]; then
        echo ""
        echo "✅ SQL file executed successfully"
    else
        echo ""
        echo "❌ SQL file execution failed with exit code $EXIT_CODE"
        exit $EXIT_CODE
    fi
else
    # Interactive psql session
    echo "💡 Starting interactive psql session..."
    echo "💡 Type \\q to exit"
    echo ""

    # Use Docker PostgreSQL client
    docker run --rm -it \
        -e PGHOST="$PG_HOST" \
        -e PGPORT="$PG_PORT" \
        -e PGDATABASE="$PG_DATABASE" \
        -e PGUSER="$PG_USER" \
        -e PGPASSWORD="$PG_PASSWORD" \
        -e PGSSLMODE="require" \
        postgres:15-alpine \
        psql

    # Clear password from environment
    unset PGPASSWORD
fi
